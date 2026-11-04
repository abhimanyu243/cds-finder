"""Table mapping stored in SQLite: ECC table -> S/4HANA table(s).

Tables
  mapping            one row per ECC table: note, status, version, last change
  mapping_s4_table   one row per S/4HANA table of a mapping (VBUK -> VBAK, LIKP, VBRK)
  mapping_history    every change: who, when, old and new value
  app_meta           a 'mapping_version' counter, bumped on every change

Rules
  - Every write runs in one transaction (BEGIN IMMEDIATE), so writers queue up safely.
  - Updates need the row's version number. If someone else saved in between, the
    update is refused with a conflict, so nobody overwrites a change unseen.
  - Mappings are retired, not deleted, so the history stays complete.
  - Lists are paginated in SQL, and the S/4HANA tables of a page are read in one query.
"""

from __future__ import annotations

import json
import re
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from collections.abc import Iterator

from pydantic import TypeAdapter, ValidationError

from .errors import BadRequest, Conflict, NotFound, describe_validation_error
from .metadata import Column, read_rows
from .schemas import (
    HistoryEntry, HistoryPage, ImportResult, ImportRow, ImportRowResult, ImportSummary, Mapping, MappingIn,
    MappingPage, MappingQuery, MappingSnapshot, Paging, TableName, clamp_page,
)

SCHEMA = """
CREATE TABLE IF NOT EXISTS mapping (
    ecc_table   TEXT PRIMARY KEY,
    note        TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'retired')),
    version     INTEGER NOT NULL DEFAULT 1,
    changed_by  TEXT NOT NULL DEFAULT '',
    changed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS mapping_s4_table (
    ecc_table   TEXT NOT NULL REFERENCES mapping(ecc_table) ON DELETE CASCADE,
    position    INTEGER NOT NULL,
    s4_table    TEXT NOT NULL,
    PRIMARY KEY (ecc_table, s4_table)
);
CREATE TABLE IF NOT EXISTS mapping_history (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ecc_table   TEXT NOT NULL,
    action      TEXT NOT NULL,
    old_value   TEXT,
    new_value   TEXT,
    changed_by  TEXT NOT NULL DEFAULT '',
    changed_at  TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_meta (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS ix_mapping_status ON mapping(status);
CREATE INDEX IF NOT EXISTS ix_s4_table ON mapping_s4_table(s4_table);
CREATE INDEX IF NOT EXISTS ix_history_ecc ON mapping_history(ecc_table, id);
"""

MAPPING_COLUMNS = (
    Column("ECC", ("ECCTABLE", "ECC"), ("ECC",)),
    Column("S4", ("S4TABLES", "S4TABLE", "S4", "S4HANATABLES", "S4HANATABLE"), ("S4",), required=False),
    Column("NOTE", ("NOTE", "NOTES", "COMMENT", "DESCRIPTION"), required=False),
)
SORTS = {   # the latest history row is the exact order of changes, even within one second
    "ecc": "m.ecc_table",
    "changed": "(SELECT MAX(h.id) FROM mapping_history h WHERE h.ecc_table = m.ecc_table) DESC, m.ecc_table",
}
TABLE_NAME = TypeAdapter(TableName)


def read_mapping_csv(path: Path) -> list[ImportRow]:
    """Rows of a mapping CSV (ECC_TABLE, S4_TABLES separated by ;, NOTE)."""
    return [ImportRow(ecc=r["ECC"], s4=r.get("S4", ""), note=r.get("NOTE", "")[:400])
            for r in read_rows(path, MAPPING_COLUMNS)]


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


class MappingRepository:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connect() as con:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
            con.execute("INSERT OR IGNORE INTO app_meta(key, value) VALUES ('mapping_version', '0')")

    # -- plumbing ------------------------------------------------------------

    @contextmanager
    def _connect(self) -> Iterator[sqlite3.Connection]:
        con = sqlite3.connect(self.path, timeout=10, isolation_level=None)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA foreign_keys=ON")
        try:
            yield con
        finally:
            con.close()

    @contextmanager
    def _write(self) -> Iterator[sqlite3.Connection]:
        with self._connect() as con:
            con.execute("BEGIN IMMEDIATE")
            try:
                yield con
                con.execute("UPDATE app_meta SET value = CAST(value AS INTEGER) + 1 WHERE key = 'mapping_version'")
                con.execute("COMMIT")
            except BaseException:
                con.execute("ROLLBACK")
                raise

    @staticmethod
    def _rows(con: sqlite3.Connection, rows: list[sqlite3.Row]) -> list[Mapping]:
        """Turn mapping rows into models, reading all their S/4HANA tables in one query."""
        tables: dict[str, list[str]] = {r["ecc_table"]: [] for r in rows}
        if rows:
            marks = ",".join("?" * len(tables))
            for r in con.execute(f"SELECT ecc_table, s4_table FROM mapping_s4_table WHERE ecc_table IN ({marks}) "
                                 "ORDER BY ecc_table, position", list(tables)):
                tables[r["ecc_table"]].append(r["s4_table"])
        return [Mapping(ecc=r["ecc_table"], s4=tables[r["ecc_table"]], note=r["note"], status=r["status"],
                        version=r["version"], changed_by=r["changed_by"], changed_at=r["changed_at"]) for r in rows]

    def _get(self, con: sqlite3.Connection, ecc: str) -> Mapping | None:
        found = self._rows(con, con.execute("SELECT * FROM mapping WHERE ecc_table = ?", (ecc,)).fetchall())
        return found[0] if found else None

    @staticmethod
    def _snapshot(item: Mapping | None) -> str | None:
        if item is None:
            return None
        return MappingSnapshot(s4=item.s4, note=item.note, status=item.status).model_dump_json()

    @staticmethod
    def _log(con: sqlite3.Connection, ecc: str, action: str, old: str | None, new: str | None, by: str) -> None:
        con.execute("INSERT INTO mapping_history(ecc_table, action, old_value, new_value, changed_by, changed_at) "
                    "VALUES (?, ?, ?, ?, ?, ?)", (ecc, action, old, new, by, _now()))

    @staticmethod
    def _put_tables(con: sqlite3.Connection, ecc: str, s4: list[str]) -> None:
        con.execute("DELETE FROM mapping_s4_table WHERE ecc_table = ?", (ecc,))
        con.executemany("INSERT INTO mapping_s4_table(ecc_table, position, s4_table) VALUES (?, ?, ?)",
                        [(ecc, i, t) for i, t in enumerate(s4)])

    @staticmethod
    def _ecc(value: str) -> str:
        try:
            return TABLE_NAME.validate_python(value)
        except ValidationError:
            raise NotFound(f"There is no mapping for {value.upper()}.") from None

    # -- reads ---------------------------------------------------------------

    def version(self) -> int:
        with self._connect() as con:
            return int(con.execute("SELECT value FROM app_meta WHERE key = 'mapping_version'").fetchone()[0])

    def count(self) -> int:
        with self._connect() as con:
            return con.execute("SELECT COUNT(*) FROM mapping").fetchone()[0]

    def active(self) -> dict[str, tuple[tuple[str, ...], str]]:
        """Active mappings for the search: ECC table -> (S/4HANA tables, note). Two queries in total."""
        with self._connect() as con:
            notes = {r[0]: r[1] for r in con.execute("SELECT ecc_table, note FROM mapping WHERE status = 'active'")}
            tables: dict[str, list[str]] = {}
            for ecc, s4 in con.execute("SELECT s.ecc_table, s.s4_table FROM mapping_s4_table s "
                                       "JOIN mapping m ON m.ecc_table = s.ecc_table WHERE m.status = 'active' "
                                       "ORDER BY s.ecc_table, s.position"):
                tables.setdefault(ecc, []).append(s4)
        return {ecc: (tuple(tables[ecc]), note) for ecc, note in notes.items() if ecc in tables}

    def get(self, ecc: str) -> Mapping:
        key = self._ecc(ecc)
        with self._connect() as con:
            item = self._get(con, key)
        if item is None:
            raise NotFound(f"There is no mapping for {key}.")
        return item

    def list(self, query: MappingQuery) -> MappingPage:
        where, args = [], []
        if query.status != "all":
            where.append("m.status = ?")
            args.append(query.status)
        term = re.sub(r"[^A-Za-z0-9_/ ]", "", query.q).strip().upper()
        if term:
            like = f"%{term}%"
            where.append("(m.ecc_table LIKE ? OR m.note LIKE ? COLLATE NOCASE OR EXISTS "
                         "(SELECT 1 FROM mapping_s4_table s WHERE s.ecc_table = m.ecc_table AND s.s4_table LIKE ?))")
            args += [like, like, like]
        sql_where = ("WHERE " + " AND ".join(where)) if where else ""
        with self._connect() as con:
            total = con.execute(f"SELECT COUNT(*) FROM mapping m {sql_where}", args).fetchone()[0]
            page = clamp_page(query.page, query.page_size, total)
            rows = con.execute(f"SELECT m.* FROM mapping m {sql_where} ORDER BY {SORTS[query.sort]} LIMIT ? OFFSET ?",
                               [*args, query.page_size, (page - 1) * query.page_size]).fetchall()
            items = self._rows(con, rows)
        return MappingPage(items=items, paging=Paging.of(page, query.page_size, total, len(items)))

    def history(self, ecc: str, page: int = 1, page_size: int = 20) -> HistoryPage:
        key = self._ecc(ecc)
        with self._connect() as con:
            total = con.execute("SELECT COUNT(*) FROM mapping_history WHERE ecc_table = ?", (key,)).fetchone()[0]
            page = clamp_page(page, page_size, total)
            rows = con.execute("SELECT * FROM mapping_history WHERE ecc_table = ? ORDER BY id DESC LIMIT ? OFFSET ?",
                               (key, page_size, (page - 1) * page_size)).fetchall()
        items = [HistoryEntry(action=r["action"],
                              old=json.loads(r["old_value"]) if r["old_value"] else None,
                              new=json.loads(r["new_value"]) if r["new_value"] else None,
                              changed_by=r["changed_by"], changed_at=r["changed_at"]) for r in rows]
        return HistoryPage(items=items, paging=Paging.of(page, page_size, total, len(items)))

    def export(self, status: str = "active") -> list[Mapping]:
        with self._connect() as con:
            args = [] if status == "all" else [status]
            rows = con.execute("SELECT * FROM mapping " + ("WHERE status = ? " if args else "") +
                               "ORDER BY ecc_table", args).fetchall()
            return self._rows(con, rows)

    # -- writes --------------------------------------------------------------

    def create(self, item: MappingIn, by: str = "") -> Mapping:
        with self._write() as con:
            existing = self._get(con, item.ecc)
            if existing:
                hint = " It is retired: restore it instead." if existing.status == "retired" else ""
                raise Conflict(f"{item.ecc} already has a mapping.{hint}", existing)
            con.execute("INSERT INTO mapping(ecc_table, note, status, version, changed_by, changed_at) "
                        "VALUES (?, ?, 'active', 1, ?, ?)", (item.ecc, item.note, by, _now()))
            self._put_tables(con, item.ecc, item.s4)
            new = self._get(con, item.ecc)
            self._log(con, item.ecc, "create", None, self._snapshot(new), by)
        return new

    def update(self, ecc: str, s4: list[str], note: str, version: int, by: str = "") -> Mapping:
        key = self._ecc(ecc)
        with self._write() as con:
            old = self._current(con, key, version)
            con.execute("UPDATE mapping SET note = ?, version = version + 1, changed_by = ?, changed_at = ? "
                        "WHERE ecc_table = ?", (note, by, _now(), key))
            self._put_tables(con, key, s4)
            new = self._get(con, key)
            self._log(con, key, "update", self._snapshot(old), self._snapshot(new), by)
        return new

    def set_status(self, ecc: str, status: str, version: int, by: str = "") -> Mapping:
        key = self._ecc(ecc)
        with self._write() as con:
            old = self._current(con, key, version)
            if old.status == status:
                return old
            con.execute("UPDATE mapping SET status = ?, version = version + 1, changed_by = ?, changed_at = ? "
                        "WHERE ecc_table = ?", (status, by, _now(), key))
            new = self._get(con, key)
            self._log(con, key, "retire" if status == "retired" else "restore",
                      self._snapshot(old), self._snapshot(new), by)
        return new

    def _current(self, con: sqlite3.Connection, ecc: str, version: int) -> Mapping:
        old = self._get(con, ecc)
        if old is None:
            raise NotFound(f"There is no mapping for {ecc}.")
        if old.version != version:
            raise Conflict(f"Someone changed the mapping for {ecc} after you opened it. "
                           "Their version is shown now. Make your change again.", old)
        return old

    def import_rows(self, rows: list[ImportRow], apply: bool = False, by: str = "") -> ImportResult:
        """Add or update many mappings at once. Mappings not in the rows are left alone.

        With apply=False nothing is written: the result says what would happen.
        With apply=True every row is written in one transaction, or none if any row has an error.
        """
        checked: list[ImportRowResult] = []
        seen: set[str] = set()
        for i, row in enumerate(rows, start=1):
            try:
                item = MappingIn.model_validate(row.model_dump())
                if item.ecc in seen:
                    raise BadRequest(f"{item.ecc} appears more than once.")
                seen.add(item.ecc)
                checked.append(ImportRowResult(row=i, ecc=item.ecc, s4=item.s4, note=item.note, action="new"))
            except ValidationError as exc:
                checked.append(ImportRowResult(row=i, ecc=row.ecc.strip().upper(), action="error",
                                               message=describe_validation_error(exc.errors())))
            except BadRequest as exc:
                checked.append(ImportRowResult(row=i, ecc=row.ecc.strip().upper(), action="error", message=exc.message))

        with self._connect() as con:
            existing = {m.ecc: m for m in self._rows(con, con.execute("SELECT * FROM mapping").fetchall())}
        for e in checked:
            old = existing.get(e.ecc)
            if e.action == "error" or old is None:
                continue
            if old.status == "retired":
                e.action = "restore"
            elif old.s4 != e.s4 or old.note != e.note:
                e.action = "change"
            else:
                e.action = "same"

        summary = ImportSummary(**{k: sum(1 for e in checked if e.action == k) for k in ImportSummary.model_fields})
        if apply and summary.error:
            raise BadRequest(f"{summary.error} row(s) have errors. Fix them and import again.")
        if apply:
            with self._write() as con:
                now = _now()
                for e in checked:
                    if e.action == "same":
                        continue
                    old = existing.get(e.ecc)
                    if old is None:
                        con.execute("INSERT INTO mapping(ecc_table, note, status, version, changed_by, changed_at) "
                                    "VALUES (?, ?, 'active', 1, ?, ?)", (e.ecc, e.note, by, now))
                    else:
                        con.execute("UPDATE mapping SET note = ?, status = 'active', version = version + 1, "
                                    "changed_by = ?, changed_at = ? WHERE ecc_table = ?", (e.note, by, now, e.ecc))
                    self._put_tables(con, e.ecc, e.s4)
                    new = MappingSnapshot(s4=e.s4, note=e.note, status="active").model_dump_json()
                    self._log(con, e.ecc, "import", self._snapshot(old), new, by)
        return ImportResult(summary=summary, rows=checked[:500], applied=apply)

    def seed(self, csv_path: Path) -> int:
        """Fill an empty database from the initial mapping file. Does nothing once there are rows."""
        if self.count() or not csv_path.is_file():
            return 0
        rows = read_mapping_csv(csv_path)
        if not rows:
            return 0
        return self.import_rows(rows, apply=True, by="Initial setup").summary.new
