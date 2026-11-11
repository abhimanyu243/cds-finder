"""Field comparison: which views give you the fields you need.

The user names fields, either with their table (VBAP-NETWR) or, after a search, on their own
(NETWR). Each field is looked for in the S/4HANA tables its ECC table resolves to, using the
same table mapping as the search. A view provides a field when one of its elements is a copy
of that table field, read directly or through other views. A field used only inside a
calculation is reported separately and does not count as provided.

Views are taken by priority: P1 views first, then P2, then P3. The best view is the P1 view with
the most fields (P2 only when no P1 view has any of them), and the views used together are
picked from P1 first, adding P2 and then P3 only for the fields the higher priority cannot give.
For each table the fields name, the top view of each priority is listed too: the best ranked view in a
search for that table alone that has at least one of its fields. The user switches between them without
paging through every view.

The side-by-side comparison also helps choose between views: it lists the facts the ranking
uses (extraction, delta, release, level of detail...), says in words which view to prefer and
why, and suggests how to join views that are used together.

Nothing is stored: every request is computed from the cached ranking and then forgotten.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from pydantic import Field

from . import ranking
from .errors import BadRequest
from .metadata import CLIENT_FIELDS, View
from .products import product_title
from .schemas import MAX_INPUT_TABLES, NAME_RE, PriorityLevel, ResolvedTable, Schema, TableInput
from .service import Finder

MAX_FIELDS = 500
MAX_COMPARE = 4                 # views shown side by side
MAX_COMBINATION = MAX_COMPARE   # views used together, so the suggestion can always be shown side by side
_SPLIT = re.compile(r"\s*[-.]\s*|\s+")


# --------------------------------------------------------------------------
# Request and response
# --------------------------------------------------------------------------

class CoverageRequest(Schema):
    tables: list[TableInput] = Field(default_factory=list, max_length=MAX_INPUT_TABLES,
                                     description="Tables already searched; tables named in the fields are added")
    fields: list[str] = Field(default_factory=list, description="VBAP-NETWR, VBAP.NETWR, or NETWR after a search")
    compare: list[str] = Field(default_factory=list, max_length=MAX_COMPARE,
                               description="Views to show side by side; empty means the suggested combination")
    driver: str = Field("", description="One of the compared views: the view of the driver table. The other "
                                        "views are joined to it first, and to each other only when they share "
                                        "no key field with it")


class WantedField(Schema):
    label: str = Field(description="As shown to the user: VBAP-NETWR, or NETWR when no table was given")
    table: str = Field(description="ECC table, empty when the field was given without one")
    field: str
    s4_tables: list[str] = Field(description="S/4HANA tables the field is looked for in")
    views: int = Field(description="Views that provide the field")
    calculated_only: int = Field(description="Views that use the field only inside a calculation")
    status: Literal["found", "calculated", "missing"]


class ViewCoverage(Schema):
    name: str
    rank: int
    priority: PriorityLevel
    priority_label: str
    description: str
    custom: bool
    covered: int = Field(description="Requested fields the view provides")
    calculated: int = Field(description="Requested fields the view uses only inside a calculation")
    searched: bool = Field(description="The view reads the searched tables, so the search can show its details")


class ComparedView(ViewCoverage):
    """A view in the side-by-side comparison, with the facts the ranking orders views by."""
    extraction: bool
    delta: bool
    released: bool | None = Field(description="Null when the view is not enabled for extraction (not stated)")
    detail: Literal["same", "check", "different", "unknown"]
    detail_text: str
    reads: list[str] = Field(description="Your tables (ECC names) that the view reads")
    direct: bool = Field(description="Reads your tables itself rather than through other views")
    other_tables: int = Field(description="Tables the view mixes in besides yours")
    fields_in_view: int
    data_products: list[str] = Field(description="Titles of the data products that use the view")


class JoinPair(Schema):
    left: str = Field(description="Field of the left view")
    right: str = Field(description="Key field of the right view")
    via: str = Field(description="Why they match, for example ACDOCA-MATNR = MARA-MATNR")


class JoinHint(Schema):
    """A suggestion, matched on SAP field names and the key fields file. The user confirms it."""
    left: str = Field(description="View whose rows are kept")
    right: str = Field(description="View looked up by its key fields")
    pairs: list[JoinPair]
    complete: bool = Field(description="Every key field of the right view is matched")
    note: str


class Combination(Schema):
    views: list[str] = Field(description="Fewest views, best ranked first, that provide every field any view has")
    covered: int
    joins: list[JoinHint] = Field(default_factory=list, description="How to join each added view")


class CoverageSummary(Schema):
    requested: int
    coverable: int = Field(description="Requested fields at least one view provides")
    best: ViewCoverage | None = Field(description="The highest priority view with the most fields; ties go to the "
                                                  "better rank")
    more_fields: ViewCoverage | None = Field(None, description="A lower priority view that provides more fields "
                                                               "than the best one")
    combination: Combination | None = Field(description="Only when the best view alone misses coverable fields")


class Cell(Schema):
    status: Literal["yes", "calculated", "no"]
    element: str = Field("", description="The view field that carries it")


class CompareRow(Schema):
    label: str
    cells: list[Cell]


class Comparison(Schema):
    views: list[ComparedView]
    rows: list[CompareRow]
    recommended: str | None = Field(description="The view to choose, when one view has every field the others have")
    verdict: list[str] = Field(description="Which view to choose and why, in plain words")
    joins: list[JoinHint] = Field(description="How to join views that add fields the main view lacks")


class TablePick(Schema):
    priority: PriorityLevel
    view: ViewCoverage = Field(description="Best ranked view of this priority; rank is the table's own rank")
    table_covered: int = Field(description="Fields of this table the view provides")


class TableViews(Schema):
    table: str = Field(description="ECC table; for fields given without a table, the searched tables")
    fields: list[str] = Field(description="The requested fields of this table")
    picks: list[TablePick] = Field(description="Top view of each priority that has one, P1 first")


class CoverageResponse(Schema):
    inputs: list[ResolvedTable]
    fields: list[WantedField]
    summary: CoverageSummary
    by_table: list[TableViews] = Field(description="Per table, the top P1, P2 and P3 view for its fields")
    views: list[ViewCoverage] = Field(description="Views that provide at least one field: P1 first, then the "
                                                  "most fields")
    views_found: int = Field(description="All views that read the tables")
    comparison: Comparison


# --------------------------------------------------------------------------
# Parsing
# --------------------------------------------------------------------------

@dataclass(frozen=True, slots=True)
class Wanted:
    table: str          # ECC table, '' when not given
    field: str

    @property
    def label(self) -> str:
        return f"{self.table}-{self.field}" if self.table else self.field


def parse_fields(items: list[str]) -> list[Wanted]:
    """'vbap-netwr', 'VBAP.NETWR', 'VBAP NETWR' or 'NETWR' -> Wanted, in order, without repeats."""
    wanted: dict[tuple[str, str], Wanted] = {}
    for raw in items:
        text = str(raw).strip().upper()
        if not text:
            continue
        parts = [p for p in _SPLIT.split(text) if p]
        if len(parts) > 2 or not all(NAME_RE.fullmatch(p) for p in parts):
            raise BadRequest(f"'{str(raw).strip()[:60]}' is not a field. Write it as TABLE-FIELD, "
                             "for example VBAP-NETWR, or as the field name alone after a search.")
        w = Wanted(*parts) if len(parts) == 2 else Wanted("", parts[0])
        wanted.setdefault((w.table, w.field), w)
    if not wanted:
        raise BadRequest("Enter at least one field.")
    if len(wanted) > MAX_FIELDS:
        raise BadRequest(f"Enter at most {MAX_FIELDS} fields at a time.")
    return list(wanted.values())


def _tables(req: CoverageRequest, wanted: list[Wanted]) -> list[TableInput]:
    """The searched tables plus any table named in the fields."""
    tables = {t.ecc: t for t in req.tables}
    for w in wanted:
        if w.table and w.table not in tables:
            tables[w.table] = TableInput(ecc=w.table)
    if not tables:
        raise BadRequest("Add the table to each field, for example VBAP-NETWR, or search the tables first.")
    if len(tables) > MAX_INPUT_TABLES:
        raise BadRequest(f"The fields name more than {MAX_INPUT_TABLES} tables. Compare fields from fewer tables.")
    return list(tables.values())


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------

Found = dict[int, tuple[str, str]]       # requested field index -> (status 'yes' | 'calculated', view field)


@dataclass
class _Run:
    """One comparison: the requested fields and what every view of the ranking provides."""
    wanted: list[Wanted]
    ranked: ranking.Ranking
    looked_in: list[tuple[str, ...]]                 # S/4HANA tables searched for each requested field
    scans: list[tuple[ranking.Match, Found]]         # in rank order
    searched_s4: frozenset[str]                      # S/4HANA tables of the tables the user searched


def _run(finder: Finder, req: CoverageRequest) -> _Run:
    wanted = parse_fields(req.fields)
    r = finder.ranking(_tables(req, wanted))          # cached: the same ranking the search used
    s4_of = {i.ecc: i.s4 for i in r.inputs}
    searched = {t.ecc for t in req.tables}
    # a field without a table is looked for in the searched tables (or in every named table without a search)
    plain = tuple(dict.fromkeys(t for i in r.inputs if i.ecc in searched or not searched for t in i.s4))
    targets: dict[tuple[str, str], list[int]] = {}   # (S/4HANA table, field) -> requested field indexes
    looked_in = []
    for i, w in enumerate(wanted):
        tables = s4_of[w.table] if w.table else plain
        looked_in.append(tables)
        for t in tables:
            targets.setdefault((t, w.field), []).append(i)
    searched_s4 = frozenset(t for i in r.inputs if i.ecc in searched for t in i.s4)
    return _Run(wanted, r, looked_in, [(m, _scan(m, targets)) for m in r.matches], searched_s4)


def _scan(match: ranking.Match, targets: dict[tuple[str, str], list[int]]) -> Found:
    """What one view provides, in one pass over its fields. A plain copy beats a calculation."""
    found: Found = {}
    for el in match.view.elements:
        for s in el.sources:
            for i in targets.get((s.table, s.field), ()):
                if found.get(i, ("",))[0] != "yes":
                    found[i] = ("calculated" if s.calculated else "yes", el.name)
    return found


def _provided(found: Found) -> set[int]:
    return {i for i, (status, _) in found.items() if status == "yes"}


def _view(run: _Run, m: ranking.Match, found: Found) -> ViewCoverage:
    yes = len(_provided(found))
    return ViewCoverage(name=m.view.name, rank=run.ranked.position[m.view.key], priority=m.priority,
                        priority_label=ranking.PRIORITY_LABEL[m.priority], description=m.view.description,
                        custom=m.view.custom, covered=yes, calculated=len(found) - yes,
                        searched=any(t in m.view.tables for t in run.searched_s4))


def compare(finder: Finder, req: CoverageRequest) -> CoverageResponse:
    run = _run(finder, req)
    n = len(run.wanted)
    provides, calc_only = [0] * n, [0] * n
    yes_sets = []                                    # per view, in rank order: the fields it provides
    for _, found in run.scans:
        yes = _provided(found)
        yes_sets.append(yes)
        for i, (status, _) in found.items():
            (provides if status == "yes" else calc_only)[i] += 1

    # priority first, then the most fields; the sort is stable, so equal views keep the rank order
    order = sorted((k for k, yes in enumerate(yes_sets) if yes),
                   key=lambda k: (run.scans[k][0].priority, -len(yes_sets[k])))
    views = [_view(run, *run.scans[k]) for k in order]
    coverable = {i for i in range(n) if provides[i]}
    best = views[0] if views else None
    most = max(views, key=lambda v: v.covered) if views else None   # the first view with the most fields
    combination = None
    if best and best.covered < len(coverable):
        combination = _combination([(m.view.name, m.priority, yes)
                                    for (m, _), yes in zip(run.scans, yes_sets, strict=True)], coverable)
        views_by_key = {m.view.key: m.view for m, _ in run.scans}
        combination.joins = _joins([views_by_key[n.upper()] for n in combination.views], finder.catalog.keys_loaded)

    fields = [WantedField(label=w.label, table=w.table, field=w.field, s4_tables=list(run.looked_in[i]),
                          views=provides[i], calculated_only=calc_only[i],
                          status="found" if provides[i] else "calculated" if calc_only[i] else "missing")
              for i, w in enumerate(run.wanted)]
    chosen = req.compare or (combination.views if combination else [best.name] if best else [])
    return CoverageResponse(
        inputs=ranking.resolved_tables(finder.catalog, run.ranked.inputs),
        fields=fields,
        summary=CoverageSummary(requested=n, coverable=len(coverable), best=best, combination=combination,
                                more_fields=most if most and most.covered > best.covered else None),
        views=views,
        views_found=len(run.ranked.matches),
        comparison=_comparison(finder, run, chosen, req.driver if req.compare else ""),
        by_table=_by_table(finder, req, run, yes_sets),
    )


def _by_table(finder: Finder, req: CoverageRequest, run: _Run, yes_sets: list[set[int]]) -> list[TableViews]:
    """Group the fields by table. Per priority, pick the best ranked view that provides at least one of
    the table's fields, ranked as a search for that table alone ranks it, so the rank shown here is the
    rank on the Find Views page. Fields without a table use the ranking of the searched tables."""
    groups: dict[str, set[int]] = {}
    for i, w in enumerate(run.wanted):
        groups.setdefault(w.table, set()).add(i)
    provided = {m.view.key: (k, yes) for k, ((m, _), yes) in enumerate(zip(run.scans, yes_sets, strict=True)) if yes}
    searched = {t.ecc: t for t in req.tables}
    result = []
    for table, idx in groups.items():
        own = finder.ranking([searched.get(table) or TableInput(ecc=table)]) if table else run.ranked   # cached
        picks: dict[int, TablePick] = {}
        for m in own.matches:                              # in rank order: the first hit per priority wins
            hit = provided.get(m.view.key)
            if m.priority in picks or hit is None or not hit[1] & idx:
                continue
            view = _view(run, *run.scans[hit[0]]).model_copy(update={"rank": own.position[m.view.key]})
            picks[m.priority] = TablePick(priority=m.priority, view=view, table_covered=len(hit[1] & idx))
            if len(picks) == len(ranking.PRIORITY_LABEL):
                break
        result.append(TableViews(table=table or ", ".join(searched), fields=[run.wanted[i].label for i in sorted(idx)],
                                 picks=[picks[level] for level in sorted(picks)]))
    return result


def _combination(candidates: list[tuple[str, int, set[int]]], coverable: set[int]) -> Combination:
    """P1 views first, then P2, then P3. Within a priority, add the view that provides the most fields
    still missing; candidates are in rank order, so on equal gains the better ranked view wins."""
    picked: list[str] = []
    have: set[int] = set()
    for level in (1, 2, 3):
        tier = [(name, yes) for name, priority, yes in candidates if priority == level]
        while len(picked) < MAX_COMBINATION and have != coverable:
            name, gain, adds = "", 0, set()
            for view, yes in tier:
                new = yes - have
                if len(new) > gain:
                    name, gain, adds = view, len(new), new
            if not gain:
                break
            picked.append(name)
            have |= adds
    return Combination(views=picked, covered=len(have))


def _comparison(finder: Finder, run: _Run, names: list[str], driver: str = "") -> Comparison:
    """Requested fields down the side, chosen views across, with the facts and advice to choose between them."""
    by_name = {m.view.key: (m, found) for m, found in run.scans}
    cols = []
    for name in dict.fromkeys(n.strip() for n in names if n.strip()):
        if name.upper() not in by_name:
            raise BadRequest(f"{name} does not read the tables you are comparing.")
        cols.append(by_name[name.upper()])
    recommended, verdict, added = _verdict(run, cols)
    by_driver = bool(driver.strip())
    if by_driver:
        main = by_name.get(driver.strip().upper())
        if main not in cols:
            raise BadRequest(f"{driver.strip()} is not one of the views you are comparing.")
        # the user named the driver: keep its rows and join every other chosen view, driver first
        added = [main[0].view, *(m.view for m, _ in cols if m is not main[0])] if len(cols) > 1 else []
        recommended = None
        verdict = [f"{main[0].view.name} is the view of your driver table. Each other view is joined to it "
                   "first, and to another view only when it shares no key field with it. The join fields are the same "
                   "whichever table is the driver."] if added else []
    return Comparison(
        views=[_compared(finder, run, m, found) for m, found in cols],
        rows=[CompareRow(label=w.label, cells=[Cell(status=found[i][0], element=found[i][1]) if i in found
                                                else Cell(status="no") for _, found in cols])
              for i, w in enumerate(run.wanted)],
        recommended=recommended, verdict=verdict, joins=_joins(added, finder.catalog.keys_loaded, by_driver))


def _compared(finder: Finder, run: _Run, m: ranking.Match, found: Found) -> ComparedView:
    return ComparedView(
        **_view(run, m, found).model_dump(), extraction=m.extraction, delta=m.delta,
        released=m.released if m.extraction else None, detail=m.detail, detail_text=ranking.DETAIL_TEXT[m.detail],
        reads=[u.inp.ecc for u in m.covered], direct=m.depth == 1, other_tables=len(m.other_tables),
        fields_in_view=len(m.view.elements),
        data_products=[product_title(n)[0] for n in finder.products.for_view(m.view.key, m.view.ddlname)])


def _verdict(run: _Run, cols: list[tuple[ranking.Match, Found]]) -> tuple[str | None, list[str], list[View]]:
    """Which compared view to choose. Returns the recommended view (None when views must be used
    together), the advice in plain words, and the views to join: the main view first, then each
    view that adds fields the main view lacks."""
    if len(cols) < 2:
        return None, [], []
    rank = {m.view.key: run.ranked.position[m.view.key] for m, _ in cols}
    best, best_found = min(cols, key=lambda c: (c[0].priority, -len(_provided(c[1])), rank[c[0].view.key]))
    have = _provided(best_found)
    lines, added = [], [best.view]
    for m, found in cols:
        if m is best:
            continue
        mine = _provided(found)
        extra = mine - have
        if extra:
            labels = ", ".join(run.wanted[i].label for i in sorted(extra))
            lines.append(f"{m.view.name} adds {labels}, which {best.view.name} lacks. Use the two together.")
            added.append(m.view)
            continue
        if not mine:
            line = f"{m.view.name} provides none of these fields."
        elif mine == have:
            line = (f"Same fields as {best.view.name}. {best.view.name} ranks higher because "
                    f"{ranking.why_higher(best, m)}.")
        elif rank[m.view.key] < rank[best.view.key]:
            line = (f"{m.view.name} has no field that {best.view.name} lacks, but ranks higher because "
                    f"{ranking.why_higher(m, best)}. Prefer it only if its fields are all you need.")
        else:
            line = f"{m.view.name} has no field that {best.view.name} lacks, so {best.view.name} is enough."
        if m.view.custom and not best.view.custom:
            line += f" {m.view.name} is a custom view built in your system."
        lines.append(line)
    if len(added) == 1:
        return best.view.name, [f"Choose {best.view.name}.", *lines], []
    return None, lines, added


# --------------------------------------------------------------------------
# Join suggestions
# --------------------------------------------------------------------------

def _business_keys(view: View) -> list:
    return [k for k in view.keys if not any(s.field in CLIENT_FIELDS for s in k.sources)]


def _key_pairs(left: View, right: View) -> list[JoinPair]:
    """The right view's key fields matched to fields of the left view: first by the table field they
    come from (MATNR = MATNR, whatever the table), then by the field name in the views."""
    by_source: dict[str, tuple[str, str]] = {}                  # table field -> (left field, TABLE-FIELD)
    by_name: dict[str, str] = {}
    for el in left.elements:
        if el.calculated:
            continue
        by_name.setdefault(el.name.upper(), el.name)
        for s in el.sources:
            if s.table and s.field not in CLIENT_FIELDS:
                by_source.setdefault(s.field, (el.name, f"{s.table}-{s.field}"))
    pairs = []
    for k in _business_keys(right):
        src = next((s for s in k.sources if s.table and s.field in by_source), None)
        if src:
            field, origin = by_source[src.field]
            pairs.append(JoinPair(left=field, right=k.name, via=f"{origin} = {src.table}-{src.field}"))
        elif k.name.upper() in by_name:
            pairs.append(JoinPair(left=by_name[k.name.upper()], right=k.name, via="same field name in both views"))
    return pairs


def _join(a: View, b: View, keys_loaded: bool) -> JoinHint:
    """How to join two views: look one up by its key fields, in whichever direction matches best."""
    options = []
    for left, right in ((a, b), (b, a)):
        pairs, keys = _key_pairs(left, right), len(_business_keys(right))
        if pairs:
            options.append((len(pairs) == keys, len(pairs), keys, left, right, pairs))
    if not options:
        if not keys_loaded:
            note = "Add the DD03N key fields file to see how to join these views."
        elif not (a.keys or b.keys):
            note = "The key fields file does not list the key fields of these views, so no join can be suggested."
        else:
            note = "No shared key field was found. Check how to join these views by hand."
        return JoinHint(left=a.name, right=b.name, pairs=[], complete=False, note=note)
    complete, n, keys, left, right, pairs = max(options, key=lambda o: o[:2])
    if complete:
        note = (f"This is the full key of {right.name}, so each {left.name} row finds at most one "
                f"{right.name} row. Matched on field names: confirm before you build on it.")
    else:
        note = (f"Only {n} of the {keys} key fields of {right.name} match, so one {left.name} row may find "
                f"several {right.name} rows. Check the join before using it.")
    return JoinHint(left=left.name, right=right.name, pairs=pairs, complete=complete, note=note)


def _joins(views: list[View], keys_loaded: bool, by_driver: bool = False) -> list[JoinHint]:
    """Join each view after the first to the first view it shares a key with: the main view if possible,
    else the views before it. With a driver (the first view), a view that only connects through another
    view waits until that view is joined, so the order of the views does not matter. The driver decides
    which view is tried first, never the join fields: two views always join on their best key match."""
    if not by_driver:
        hints = []
        for k in range(1, len(views)):
            tried = [_join(views[j], views[k], keys_loaded) for j in range(k)]
            hints.append(next((h for h in tried if h.pairs), tried[0]))
        return hints
    joined, waiting, hints = views[:1], views[1:], []
    while waiting:
        found = next(((v, h) for v in waiting for h in (_join(j, v, keys_loaded) for j in joined)
                      if h.pairs), None)
        if found is None:                                  # nothing left connects: say so for each
            return hints + [_join(views[0], v, keys_loaded) for v in waiting]
        view, hint = found
        hints.append(hint)
        joined.append(view)
        waiting.remove(view)
    return hints


def export_rows(finder: Finder, req: CoverageRequest) -> list[list]:
    """One row per view that provides at least one field (P1 first, then the most fields), then the fields
    no view provides."""
    run = _run(finder, req)
    labels = [w.label for w in run.wanted]
    useful = sorted(((m, f) for m, f in run.scans if _provided(f)),
                    key=lambda mf: (mf[0].priority, -len(_provided(mf[1]))))
    rows = [["Rank", "View", "Description", "Priority", "Fields provided", "Fields requested", "Missing fields",
             "Used only in a calculation"]]
    for m, found in useful:
        v = _view(run, m, found)
        rows.append([v.rank, v.name, v.description, f"{v.priority} - {v.priority_label}", v.covered, len(labels),
                     ", ".join(labels[i] for i in range(len(labels)) if found.get(i, ("",))[0] != "yes"),
                     ", ".join(labels[i] for i, (st, _) in found.items() if st == "calculated")])
    anywhere = set().union(*(_provided(f) for _, f in run.scans)) if run.scans else set()
    gaps = [labels[i] for i in range(len(labels)) if i not in anywhere]
    if gaps:
        rows += [[], ["Fields no view provides", ", ".join(gaps)]]
    return rows
