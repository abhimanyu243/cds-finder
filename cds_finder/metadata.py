"""Read the metadata CSV files and build an in-memory catalog with lookup indexes.

Everything is read once, in a single streaming pass per file. Searches then
work on the indexes built here (table -> views, view name -> view), so a
search never scans the raw rows.

Inputs
  CDS_FIELD_ORIGIN : DDLNAME, LEVEL, ENTITY_NAME, ELEMENT_NAME, BASE_OBJECT,
                     BASE_FIELD, IS_CALCULATED (one row per CDS field and base field)
  IXTRCTNENBLDVW   : DATAEXTRACTIONVIEWNAME, DATAEXTRACTIONVIEWDESCRIPTION,
                     ISSAPRELEASEDVIEW, DELTACHGDATACAPTUREISSUPPORTED
                     (one row per extraction-enabled CDS view)
  DD03N            : STRUCOBJN, FIELDNAME, KEYFLAG (fields of CDS views; KEYFLAG = X
                     marks the view's key). Joined on DDLNAME = STRUCOBJN and
                     ELEMENT_NAME = FIELDNAME.

Column names are matched loosely (case, spaces and underscores are ignored),
and comma, semicolon, tab and SE16 pipe layouts are all accepted.
"""

from __future__ import annotations

import csv
import gc
import re
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from collections.abc import Callable, Iterator

csv.field_size_limit(min(sys.maxsize, 2**31 - 1))

FIELD_ORIGIN_FILE = "CDS_FIELD_ORIGIN"
EXTRACTION_FILE = "IXTRCTNENBLDVW"
KEY_FIELDS_FILE = "DD03N"
TEXTS_FILE = "DDDDLSRCT"          # optional: description of each DDL source
TEXT_LANGUAGE = "E"               # language used for descriptions when the file has several
DATA_SUFFIXES = (".csv", ".txt", ".tsv")
CLIENT_FIELDS = frozenset({"MANDT", "CLIENT", "RCLNT", "MANDANT"})   # never treated as business keys
TRUE_FLAGS = frozenset({"X", "TRUE", "1", "YES", "Y", "ABAP_TRUE"})
DELIMITERS = (",", ";", "\t", "|")
ENCODINGS = ("utf-8-sig", "cp1252")
HEADER_SCAN_LINES = 60


class LoadError(Exception):
    """A file is unreadable or has no recognisable header."""


def find_data_file(folder: Path, name: str) -> Path | None:
    """First file in folder whose name contains `name` (any case)."""
    if not folder.is_dir():
        return None
    hits = sorted(p for p in folder.iterdir() if p.is_file() and name.lower() in p.name.lower()
                  and p.suffix.lower() in DATA_SUFFIXES and "error" not in p.name.lower())
    return hits[0] if hits else None


def canon(name: str) -> str:
    """Upper case, letters and digits only. 'Base object ( Table )' -> 'BASEOBJECTTABLE'."""
    return re.sub(r"[^A-Z0-9]", "", name.upper())


def is_true(value: str) -> bool:
    return value.strip().upper() in TRUE_FLAGS


# --------------------------------------------------------------------------
# Column specs
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Column:
    key: str
    aliases: tuple[str, ...]          # exact matches on canon(header)
    contains: tuple[str, ...] = ()    # fallback: header contains one of these
    required: bool = True


FIELD_ORIGIN_COLUMNS = (
    Column("DDLNAME", ("DDLNAME", "DDLSOURCE", "DDLSOURCENAME"), required=False),
    Column("LEVEL", ("LEVEL", "LVL"), required=False),
    Column("ENTITY_NAME", ("ENTITYNAME", "CDSENTITY", "CDSVIEWNAME", "CDSVIEW"), required=False),
    Column("ELEMENT_NAME", ("ELEMENTNAME", "ELEMENT", "CDSFIELD"), ("ELEMENT",)),
    Column("BASE_OBJECT", ("BASEOBJECT", "BASEOBJECTTABLE", "BASETABLE"), ("BASEOBJECT", "BASETAB")),
    Column("BASE_FIELD", ("BASEFIELD", "BASEFIELDNAME", "BASECOLUMN"), ("BASEFIELD",)),
    Column("IS_CALCULATED", ("ISCALCULATED", "CALCULATED"), ("CALCULATED",), required=False),
)

EXTRACTION_COLUMNS = (
    Column("VIEW_NAME", ("DATAEXTRACTIONVIEWNAME",), ("VIEWNAME",)),
    Column("DESCRIPTION", ("DATAEXTRACTIONVIEWDESCRIPTION",), ("DESCR",), required=False),
    Column("RELEASED", ("ISSAPRELEASEDVIEW",), ("RELEASED",), required=False),
    Column("CDC", ("DELTACHGDATACAPTUREISSUPPORTED", "DELTACHANGEDCAPTUREISSUPPORTED",
                   "DELTACHANGEDATACAPTUREISSUPPORTED"), ("CAPTURE", "CDC"), required=False),
)


TEXT_COLUMNS = (
    Column("DDLNAME", ("DDLNAME", "DDLSOURCE", "DDLSOURCENAME"), ("DDLNAME",)),
    Column("LANGUAGE", ("DDLANGUAGE", "LANGUAGE", "SPRAS", "LANGU"), ("LANGU",), required=False),
    Column("VERSION", ("AS4LOCAL", "VERSION"), required=False),
    Column("TEXT", ("DDTEXT", "TEXT", "DESCRIPTION"), ("TEXT",)),
)


def match_columns(tokens: list[str], columns: tuple[Column, ...]) -> dict[str, int] | None:
    """Map column keys to positions in a header row, or None if a required one is missing."""
    names = [canon(t) for t in tokens]
    found: dict[str, int] = {}
    for col in columns:
        idx = next((i for i, n in enumerate(names) if n in col.aliases), None)
        if idx is None and col.contains:
            taken = set(found.values())
            idx = next((i for i, n in enumerate(names)
                        if i not in taken and any(p in n for p in col.contains)), None)
        if idx is not None:
            found[col.key] = idx
        elif col.required:
            return None
    return found


# --------------------------------------------------------------------------
# Streaming reader
# --------------------------------------------------------------------------

@dataclass
class FileReport:
    name: str
    rows: int = 0
    skipped: int = 0
    encoding: str = ""
    delimiter: str = ""
    columns: dict[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        delim = {",": "comma", ";": "semicolon", "\t": "tab", "|": "pipe"}.get(self.delimiter, self.delimiter)
        return {"name": self.name, "rows": self.rows, "skipped": self.skipped,
                "encoding": self.encoding, "delimiter": delim, "columns": self.columns}


def _is_separator(rec: list[str]) -> bool:
    text = "".join(rec).strip()
    return not text or set(text) <= set("-+|= ")


def _iter_rows(path: Path, columns: tuple[Column, ...], encoding: str, report: FileReport) -> Iterator[dict[str, str]]:
    with path.open("r", encoding=encoding, newline="") as fh:
        header, delim, cols = None, "", None
        for _ in range(HEADER_SCAN_LINES):
            line = fh.readline()
            if not line:
                break
            if line.lstrip().startswith("#"):          # comment lines in config files
                continue
            for d in DELIMITERS:
                if d not in line:
                    continue
                tokens = next(csv.reader([line], delimiter=d))
                cols = match_columns(tokens, columns)
                if cols:
                    header, delim = tokens, d
                    break
            if header:
                break
        if not header or cols is None:
            needed = ", ".join(c.key for c in columns if c.required)
            raise LoadError(f"{path.name}: no header row with the columns {needed} "
                            f"in the first {HEADER_SCAN_LINES} lines")

        report.encoding, report.delimiter = encoding, delim
        report.columns = {k: header[i].strip() for k, i in cols.items()}
        width = max(cols.values()) + 1
        required_width = max(i for k, i in cols.items()
                             if next(c for c in columns if c.key == k).required) + 1
        first_key = next(c.key for c in columns if c.required)
        header_first = canon(header[cols[first_key]])

        for rec in csv.reader(fh, delimiter=delim):
            if len(rec) < width:
                if len(rec) < required_width:
                    if not _is_separator(rec):
                        report.skipped += 1
                    continue
                rec = rec + [""] * (width - len(rec))
            row = {k: rec[i].strip() for k, i in cols.items()}
            first = row[first_key]
            if first[:1] in ("-", "=") and _is_separator(rec):     # ----|---- lines in SE16 exports
                continue
            if canon(first) == header_first:                      # header repeated at SE16 page breaks
                continue
            report.rows += 1
            yield row


def stream_file(path: Path, columns: tuple[Column, ...],
                consume: Callable[[Iterator[dict[str, str]]], object]) -> FileReport:
    """Feed every row of path to consume(). Retries with cp1252 if the file is not UTF-8."""
    last: Exception | None = None
    for enc in ENCODINGS:
        report = FileReport(path.name)
        try:
            consume(_iter_rows(path, columns, enc, report))
            return report
        except UnicodeDecodeError as exc:
            last = exc
    raise LoadError(f"{path.name}: could not read the file as UTF-8 or Windows-1252 ({last})")


# --------------------------------------------------------------------------
# Catalog model
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Source:
    """Where one CDS field's data comes from, after following stacked views down to a table."""
    table: str              # '' for a constant
    field: str
    depth: int              # 1 = the view reads the table itself
    calculated: bool
    via: tuple[str, ...] = ()   # views passed through on the way down


@dataclass(slots=True)
class Element:
    name: str
    sources: tuple[Source, ...]
    key: bool = False           # part of the view's key, from DD03N

    @property
    def calculated(self) -> bool:
        return not self.sources or any(s.calculated for s in self.sources)


@dataclass(slots=True)
class TableUse:
    fields: set[str] = field(default_factory=set)        # plain copies of table fields
    calc_fields: set[str] = field(default_factory=set)   # fields only used inside calculations
    min_depth: int = 99


@dataclass(frozen=True, slots=True)
class ExtractionInfo:
    name: str
    description: str
    released: bool
    delta: bool              # change data capture supported


@dataclass(slots=True)
class View:
    key: str                 # upper-case entity name, used for lookups
    name: str                # name as SAP spells it
    ddlname: str
    level: int
    elements: list[Element]
    tables: dict[str, TableUse]
    extraction: ExtractionInfo | None = None
    key_rows: int = 0            # key fields found for this view in DD03N
    keys: list[Element] = field(default_factory=list)   # key elements in view order
    text: str = ""               # description from DDDDLSRCT

    @property
    def description(self) -> str:
        """The extraction file's description, else the DDL source text, else empty."""
        return (self.extraction.description if self.extraction else "") or self.text

    @property
    def custom(self) -> bool:
        return self.key[:1] in ("Z", "Y") or self.ddlname[:1].upper() in ("Z", "Y")

    @property
    def standard(self) -> bool:
        """SAP interface (I_) or consumption (C_) view."""
        return self.key.startswith(("I_", "C_"))


@dataclass
class Catalog:
    views: dict[str, View]
    table_index: dict[str, list[str]]           # table -> view keys that read it
    report: dict
    keys_loaded: bool = False                   # True when a key fields file was read

    @property
    def loaded(self) -> bool:
        return bool(self.views)

    @classmethod
    def empty(cls) -> Catalog:
        return cls({}, {}, {"files": [], "views": 0, "elements": 0, "tables": 0})

    def find_view(self, name: str) -> View | None:
        return self.views.get(name.strip().upper())

    def views_reading(self, tables: list[str] | tuple[str, ...]) -> int:
        readers: set[str] = set()
        for t in tables:
            readers.update(self.table_index.get(t, ()))
        return len(readers)


# --------------------------------------------------------------------------
# Building the catalog
# --------------------------------------------------------------------------

class _RawView:
    __slots__ = ("ddlname", "elements", "level", "name")

    def __init__(self, name: str, ddlname: str, level: int):
        self.name, self.ddlname, self.level = name, ddlname, level
        # upper element name -> (display name, [(base_object, base_field, calculated), ...])
        self.elements: dict[str, tuple[str, list[tuple[str, str, bool]]]] = {}


class _FieldOriginSink:
    def __init__(self) -> None:
        self.raw: dict[str, _RawView] = {}
        self.alias: dict[str, str] = {}
        self.duplicates = 0
        self.no_name = 0

    def __call__(self, rows: Iterator[dict[str, str]]) -> None:
        intern = sys.intern
        raw, alias = self.raw, self.alias
        for row in rows:
            ent = row.get("ENTITY_NAME", "")
            ddl = row.get("DDLNAME", "")
            elem = row.get("ELEMENT_NAME", "")
            if not (ent or ddl) or not elem:
                self.no_name += 1
                continue
            key = alias.get(ddl.upper()) or alias.get(ent.upper()) or intern((ent or ddl).upper())
            lvl_text = row.get("LEVEL", "")
            level = int(lvl_text) if lvl_text.isdigit() else 1
            rv = raw.get(key)
            if rv is None:
                rv = raw[key] = _RawView(ent or ddl, ddl.upper(), level)
                alias[key] = key
            elif level < rv.level:
                rv.level = level
            if ent and rv.name.isupper() and not ent.isupper():
                rv.name = ent                                   # prefer SAP's mixed-case spelling
            if ddl:
                alias.setdefault(ddl.upper(), key)
                if not rv.ddlname:
                    rv.ddlname = ddl.upper()
            if ent:
                alias.setdefault(ent.upper(), key)

            src = (intern(row.get("BASE_OBJECT", "").upper()),
                   intern(row.get("BASE_FIELD", "").upper()),
                   is_true(row.get("IS_CALCULATED", "")))
            up = intern(elem.upper())
            entry = rv.elements.get(up)
            if entry is None:
                rv.elements[up] = (intern(elem), [src])
            elif src in entry[1]:
                self.duplicates += 1
            else:
                entry[1].append(src)


def _resolve_all(raw: dict[str, _RawView], alias: dict[str, str]) -> dict[str, View]:
    """Follow fields that point at other CDS views down to real tables (memoised)."""
    memo: dict[tuple[str, str], tuple[Source, ...]] = {}
    pool: dict[tuple, Source] = {}

    def _source(table: str, fld: str, depth: int, calc: bool, via: tuple[str, ...]) -> Source:
        """Reuse one Source object per distinct value: many views read the same table fields."""
        k = (table, fld, depth, calc, via)
        src = pool.get(k)
        if src is None:
            src = pool[k] = Source(table, fld, depth, calc, via)
        return src

    def resolve(vkey: str, elem: str, path: frozenset[str]) -> tuple[Source, ...]:
        nested = bool(path)          # only results reused by stacked views are memoised
        if nested:
            hit = memo.get((vkey, elem))
            if hit is not None:
                return hit
        out: list[Source] = []
        for base_obj, base_field, calc in raw[vkey].elements[elem][1]:
            if not base_obj:
                out.append(_source("", "", 1, True, ()))
                continue
            target = alias.get(base_obj)
            if (target and target != vkey and target not in path
                    and base_field and base_field in raw[target].elements):
                tname = raw[target].name
                for s in resolve(target, base_field, path | {vkey}):
                    out.append(_source(s.table, s.field, s.depth + 1, s.calculated or calc, (tname, *s.via)))
            else:
                out.append(_source(base_obj, base_field, 1, calc, ()))
        result = tuple(dict.fromkeys(out))      # dedupe, keep order
        if nested:
            memo[(vkey, elem)] = result
        return result

    views: dict[str, View] = {}
    for vkey, rv in list(raw.items()):
        elements: list[Element] = []
        tables: dict[str, TableUse] = {}
        for up, (display, _) in rv.elements.items():
            sources = resolve(vkey, up, frozenset())
            elements.append(Element(display, sources))
            for s in sources:
                if not s.table:
                    continue
                use = tables.get(s.table)
                if use is None:
                    use = tables[s.table] = TableUse()
                if s.depth < use.min_depth:
                    use.min_depth = s.depth
                if s.field:
                    (use.calc_fields if s.calculated else use.fields).add(s.field)
        for use in tables.values():
            use.calc_fields -= use.fields
        views[vkey] = View(vkey, rv.name, rv.ddlname, rv.level, elements, tables)
    return views


def _read_extraction(path: Path) -> tuple[dict[str, ExtractionInfo], FileReport]:
    ext: dict[str, ExtractionInfo] = {}

    def consume(rows: Iterator[dict[str, str]]) -> None:
        ext.clear()
        for row in rows:
            name = row.get("VIEW_NAME", "")
            if name:
                ext[name.upper()] = ExtractionInfo(
                    name=name,
                    description=row.get("DESCRIPTION", ""),
                    released=is_true(row.get("RELEASED", "")),
                    delta=is_true(row.get("CDC", "")),
                )

    report = stream_file(path, EXTRACTION_COLUMNS, consume)
    return ext, report


def _read_texts(path: Path) -> tuple[dict[str, str], FileReport]:
    """DDLNAME (upper case) -> text. Active version only; TEXT_LANGUAGE wins, else the first language found."""
    texts: dict[str, str] = {}

    def consume(rows: Iterator[dict[str, str]]) -> None:
        texts.clear()
        preferred: set[str] = set()
        for row in rows:
            name, text = row["DDLNAME"].upper(), row["TEXT"].strip()
            if not name or not text or row.get("VERSION", "A").upper() not in ("A", ""):
                continue
            if row.get("LANGUAGE", "").upper() == TEXT_LANGUAGE:
                texts[name] = text
                preferred.add(name)
            elif name not in preferred:
                texts.setdefault(name, text)

    report = stream_file(path, TEXT_COLUMNS, consume)
    return texts, report


DD03N_COLUMNS = (
    Column("STRUCOBJN", ("STRUCOBJN", "STRUCOBJNM", "STRUCOBJNAME", "DDLNAME"), ("STRUCOBJ",)),
    Column("FIELDNAME", ("FIELDNAME", "ELEMENTNAME"), ("FIELDNAME",)),
    Column("KEYFLAG", ("KEYFLAG", "ISKEY"), ("KEYFLAG",), required=False),
)


def _apply_view_keys(path: Path, views: dict[str, View], alias: dict[str, str]) -> tuple[FileReport, dict]:
    """Mark key elements from DD03N: STRUCOBJN = DDLNAME and FIELDNAME = ELEMENT_NAME."""
    pairs: set[tuple[str, str]] = set()

    def consume(rows: Iterator[dict[str, str]]) -> None:
        pairs.clear()
        for row in rows:
            obj, fld = row["STRUCOBJN"].upper(), row["FIELDNAME"].upper()
            if not obj or not fld or fld in CLIENT_FIELDS or fld.startswith("."):
                continue
            if "KEYFLAG" in row and not is_true(row["KEYFLAG"]):
                continue
            pairs.add((obj, fld))

    report = stream_file(path, DD03N_COLUMNS, consume)
    lookup: dict[str, dict[str, Element]] = {}
    unknown_views: set[str] = set()
    unknown_fields: list[str] = []
    matched = 0
    for obj, fld in sorted(pairs):
        vkey = alias.get(obj)
        if vkey is None:
            unknown_views.add(obj)
            continue
        elems = lookup.get(vkey)
        if elems is None:
            elems = lookup[vkey] = {e.name.upper(): e for e in views[vkey].elements}
        el = elems.get(fld)
        if el is None:
            unknown_fields.append(f"{obj}.{fld}")
            continue
        if not el.key:
            el.key = True
            views[vkey].key_rows += 1
            matched += 1
    for vkey in lookup:
        views[vkey].keys = [e for e in views[vkey].elements if e.key]
    stats = {
        "keyRows": len(pairs),
        "keysMatched": matched,
        "viewsWithKeys": sum(1 for v in views.values() if v.key_rows),
        "keyViewsNotInFieldOrigin": len(unknown_views),
        "keyViewsNotInFieldOriginList": sorted(unknown_views)[:25],
        "keyFieldsNotInFieldOrigin": len(unknown_fields),
        "keyFieldsNotInFieldOriginList": unknown_fields[:25],
    }
    return report, stats


def has_metadata(data_dir: Path) -> bool:
    return bool(find_data_file(data_dir, FIELD_ORIGIN_FILE) and find_data_file(data_dir, EXTRACTION_FILE))


def build_catalog(data_dir: Path) -> Catalog:
    """Read the metadata files in data_dir. Raises LoadError if they cannot be used."""
    gc_was_enabled = gc.isenabled()
    gc.disable()            # millions of small objects: collection passes would only slow the load
    try:
        catalog = _build_catalog(data_dir)
    finally:
        if gc_was_enabled:
            gc.enable()
    gc.freeze()             # the catalog lives as long as the process: keep it out of later collection passes
    return catalog


def _build_catalog(data_dir: Path) -> Catalog:
    started = time.perf_counter()
    fo_path = find_data_file(data_dir, FIELD_ORIGIN_FILE)
    ex_path = find_data_file(data_dir, EXTRACTION_FILE)
    if not fo_path or not ex_path:
        raise LoadError(f"{data_dir} needs a {FIELD_ORIGIN_FILE} file and an {EXTRACTION_FILE} file")

    holder: list[_FieldOriginSink] = []

    def consume(rows: Iterator[dict[str, str]]) -> None:
        sink = _FieldOriginSink()          # fresh state if the file is re-read with another encoding
        holder[:] = [sink]
        sink(rows)

    fo_report = stream_file(fo_path, FIELD_ORIGIN_COLUMNS, consume)
    if "ENTITY_NAME" not in fo_report.columns and "DDLNAME" not in fo_report.columns:
        raise LoadError(f"{fo_path.name}: needs an ENTITY_NAME or a DDLNAME column")
    sink = holder[0]
    views = _resolve_all(sink.raw, sink.alias)

    files = [fo_report]
    key_stats: dict = {}
    dd03n_path = find_data_file(data_dir, KEY_FIELDS_FILE)
    if dd03n_path:
        dd03n_report, key_stats = _apply_view_keys(dd03n_path, views, sink.alias)

    extraction, ex_report = _read_extraction(ex_path)
    files.append(ex_report)
    if dd03n_path:
        files.append(dd03n_report)
    for v in views.values():
        v.extraction = extraction.get(v.key) or (extraction.get(v.ddlname) if v.ddlname else None)

    texts_path = find_data_file(data_dir, TEXTS_FILE)
    if texts_path:
        texts, texts_report = _read_texts(texts_path)
        files.append(texts_report)
        for v in views.values():
            v.text = texts.get(v.ddlname) or texts.get(v.key, "")

    table_index: dict[str, list[str]] = {}
    for v in views.values():
        for t in v.tables:
            table_index.setdefault(t, []).append(v.key)

    linked = {v.extraction.name.upper() for v in views.values() if v.extraction}
    missing = sorted(info.name for k, info in extraction.items() if k not in linked)
    report = {
        "dataDir": str(data_dir),
        "files": [f.as_dict() for f in files],
        "dd03nFile": dd03n_path.name if dd03n_path else None,
        "textsFile": texts_path.name if texts_path else None,
        "viewsWithDescription": sum(1 for v in views.values() if v.description),
        **key_stats,
        "views": len(views),
        "elements": sum(len(v.elements) for v in views.values()),
        "tables": len(table_index),
        "extractionViews": len(extraction),
        "extractionViewsWithLineage": len(linked),
        "extractionViewsWithoutLineage": len(missing),
        "extractionViewsWithoutLineageList": missing[:25],
        "duplicateRows": sink.duplicates,
        "rowsWithoutName": sink.no_name,
        "loadSeconds": round(time.perf_counter() - started, 2),
        "loadedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    return Catalog(views, table_index, report, keys_loaded=bool(dd03n_path))


def read_rows(path: Path, columns: tuple[Column, ...]) -> list[dict[str, str]]:
    """All rows of a small CSV file, with the same forgiving rules as the metadata files."""
    rows: list[dict[str, str]] = []

    def consume(it: Iterator[dict[str, str]]) -> None:
        rows.clear()                      # fresh start if the file is re-read with another encoding
        rows.extend(it)

    stream_file(path, columns, consume)
    return rows
