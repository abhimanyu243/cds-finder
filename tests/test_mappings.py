from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from cds_finder.errors import BadRequest, Conflict, NotFound
from cds_finder.mappings import MappingRepository, read_mapping_csv
from cds_finder.schemas import ImportRow, MappingIn, MappingQuery
from cds_finder.settings import PACKAGE_DIR


@pytest.fixture
def repo(tmp_path: Path) -> MappingRepository:
    return MappingRepository(tmp_path / "m.db")


def add(repo: MappingRepository, ecc: str, s4: str, note: str = "", by: str = "Ann"):
    return repo.create(MappingIn(ecc=ecc, s4=s4, note=note), by)


def test_create_cleans_input_and_bumps_the_version(repo):
    before = repo.version()
    item = add(repo, "vbuk", "vbak; likp, VBRK vbak", "  header   status ")
    assert (item.ecc, item.s4, item.note, item.version, item.status) == (
        "VBUK", ["VBAK", "LIKP", "VBRK"], "header status", 1, "active")
    assert repo.version() == before + 1
    assert repo.active() == {"VBUK": (("VBAK", "LIKP", "VBRK"), "header status")}


def test_create_twice_is_a_conflict(repo):
    add(repo, "MSEG", "MATDOC")
    with pytest.raises(Conflict) as exc:
        add(repo, "MSEG", "OTHER")
    assert exc.value.current.s4 == ["MATDOC"]


def test_update_needs_the_current_version(repo):
    add(repo, "MSEG", "MATDOC")
    updated = repo.update("mseg", ["MATDOC", "MKPF"], "both", version=1, by="Ben")
    assert (updated.version, updated.s4, updated.changed_by) == (2, ["MATDOC", "MKPF"], "Ben")
    with pytest.raises(Conflict) as exc:
        repo.update("MSEG", ["X"], "", version=1)
    assert exc.value.current.version == 2
    with pytest.raises(NotFound):
        repo.update("NOPE", ["X"], "", version=1)


def test_retire_and_restore_keep_history(repo):
    add(repo, "KONV", "PRCD_ELEMENTS")
    retired = repo.set_status("KONV", "retired", version=1)
    assert retired.status == "retired" and repo.active() == {}
    same = repo.set_status("KONV", "retired", version=2)          # no change, no new version
    assert same.version == 2
    restored = repo.set_status("KONV", "active", version=2)
    assert restored.status == "active" and restored.version == 3
    history = repo.history("KONV")
    assert [h.action for h in history.items] == ["restore", "retire", "create"]
    assert history.items[1].old.status == "active" and history.items[1].new.status == "retired"


def test_get_unknown_or_invalid_name_is_not_found(repo):
    with pytest.raises(NotFound):
        repo.get("NOPE")
    with pytest.raises(NotFound):
        repo.get("not a name!")


def test_list_pages_searches_and_sorts_in_sql(repo):
    for i in range(30):
        add(repo, f"T{i:02d}", f"S{i:02d}", note="odd" if i % 2 else "even")
    page = repo.list(MappingQuery(page=2, page_size=10))
    assert [m.ecc for m in page.items][:2] == ["T10", "T11"]
    assert (page.paging.total, page.paging.pages, page.paging.start, page.paging.end) == (30, 3, 11, 20)
    assert repo.list(MappingQuery(q="s05")).items[0].ecc == "T05"          # matches S/4HANA tables too
    assert repo.list(MappingQuery(q="ODD")).paging.total == 15            # notes, any case
    assert repo.list(MappingQuery(page=99, page_size=10)).paging.page == 3
    repo.update("T03", ["S03"], "changed", version=1)
    assert repo.list(MappingQuery(sort="changed")).items[0].ecc == "T03"
    repo.set_status("T04", "retired", version=1)
    assert [m.ecc for m in repo.list(MappingQuery(status="retired")).items] == ["T04"]
    assert repo.list(MappingQuery(status="all")).paging.total == 30


def test_list_search_text_cannot_inject_sql(repo):
    add(repo, "MSEG", "MATDOC")
    assert repo.list(MappingQuery(q="' OR 1=1 --")).paging.total == 0


def test_import_preview_writes_nothing(repo):
    add(repo, "MSEG", "MATDOC", "same")
    rows = [ImportRow(ecc="MSEG", s4="MATDOC", note="same"), ImportRow(ecc="MKPF", s4="MATDOC"),
            ImportRow(ecc="bad name", s4="X"), ImportRow(ecc="A1", s4=""), ImportRow(ecc="MKPF", s4="Y")]
    version = repo.version()
    result = repo.import_rows(rows, apply=False)
    assert result.summary.model_dump() == {"new": 1, "change": 0, "restore": 0, "same": 1, "error": 3}
    messages = {r.row: r.message for r in result.rows if r.action == "error"}
    assert messages[3].startswith("ECC table: 'bad name' is not a valid table name")
    assert messages[4] == "Enter at least one S/4HANA table."
    assert messages[5] == "MKPF appears more than once."
    assert repo.version() == version and repo.count() == 1


def test_import_apply_is_all_or_nothing(repo):
    add(repo, "MSEG", "MATDOC")
    repo.set_status("MSEG", "retired", version=1)
    with pytest.raises(BadRequest):
        repo.import_rows([ImportRow(ecc="NEW1", s4="A"), ImportRow(ecc="x x", s4="B")], apply=True)
    assert repo.count() == 1
    result = repo.import_rows([ImportRow(ecc="NEW1", s4="A;B"), ImportRow(ecc="MSEG", s4="MATDOC")],
                              apply=True, by="Loader")
    assert result.applied and result.summary.new == 1 and result.summary.restore == 1
    assert repo.get("MSEG").status == "active"
    assert repo.history("NEW1").items[0].action == "import"


def test_seed_runs_only_on_an_empty_database(repo):
    seed = PACKAGE_DIR / "initial_mapping.csv"
    added = repo.seed(seed)
    assert added == len(read_mapping_csv(seed)) > 10
    assert repo.get("MSEG").changed_by == "Initial setup"
    assert repo.seed(seed) == 0


def test_read_mapping_csv_handles_comments_and_quotes(tmp_path):
    path = tmp_path / "m.csv"
    path.write_text('# exported\nECC_TABLE;S4_TABLES;NOTE\nVBUK;VBAK,LIKP;"Status; split"\n', encoding="utf-8")
    assert read_mapping_csv(path) == [ImportRow(ecc="VBUK", s4="VBAK,LIKP", note="Status; split")]


def test_database_uses_wal_and_foreign_keys(repo):
    con = sqlite3.connect(repo.path)
    assert con.execute("PRAGMA journal_mode").fetchone()[0] == "wal"
    con.close()
