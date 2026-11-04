from __future__ import annotations

import re

import pytest

from cds_finder import ranking
from cds_finder.metadata import Catalog, Element, ExtractionInfo, Source, TableUse, View
from cds_finder.ranking import Input, rank, resolve

MAPPING = {"MSEG": (("MATDOC",), "Header and item merged"), "MKPF": (("MATDOC",), ""),
           "KONV": (("PRCD_ELEMENTS",), ""), "VBUK": (("VBAK", "LIKP", "VBRK"), "")}


def names(r: ranking.Ranking) -> list[str]:
    return [m.view.name for m in r.matches]


def run(catalog: Catalog, *ecc: str) -> ranking.Ranking:
    return rank(catalog, [resolve(e, [], MAPPING) for e in ecc])


# -- resolving the S/4HANA tables ------------------------------------------------

def test_resolve_prefers_entered_tables_then_mapping_then_same_name():
    assert resolve("MSEG", ["X1"], MAPPING) == Input("MSEG", ("X1",), "entered", "Header and item merged")
    assert resolve("MSEG", [], MAPPING) == Input("MSEG", ("MATDOC",), "mapping", "Header and item merged")
    assert resolve("VBAP", [], MAPPING) == Input("VBAP", ("VBAP",), "same")


# -- priorities ----------------------------------------------------------------------

def view(name: str, extraction: bool = False, delta: bool = False) -> View:
    use = TableUse(fields={"F1"})
    info = ExtractionInfo(name, "", True, delta) if extraction else None
    return View(name.upper(), name, name.upper(), 1, [Element("F1", (Source("T1", "F1", 1, False),))],
                {"T1": use}, extraction=info)


@pytest.mark.parametrize("name, extraction, delta, expected", [
    ("I_A", True, True, 1),          # extraction and delta
    ("ZI_A", True, True, 1),         # custom, but extraction and delta win
    ("I_A", True, False, 2),         # standard prefix
    ("C_A", False, False, 2),
    ("P_A", True, False, 3),         # other prefixes
    ("ZI_A", False, False, 3),
    ("A_A", False, False, 3),
])
def test_priority_tiers(name, extraction, delta, expected):
    m = ranking.evaluate(view(name, extraction, delta), [Input("T", ("T1",), "same")], keys_loaded=False)
    assert m.priority == expected


def test_priority_comes_first_in_the_order(catalog):
    r = run(catalog, "MSEG")
    assert [m.priority for m in r.matches] == sorted(m.priority for m in r.matches)
    assert names(r) == ["I_MaterialDocumentItem_2", "I_MaterialDocumentHeader_2", "I_MaterialStock_2",
                        "I_GoodsMovementCube", "ZI_MATDOC_SCRAP_EXT"]


def test_within_a_priority_extraction_ranks_above_no_extraction(catalog):
    r = run(catalog, "MSEG")
    p2 = [m for m in r.matches if m.priority == 2]
    assert [m.extraction for m in p2] == [True, False]


def test_views_reading_all_tables_rank_first_within_a_priority(catalog):
    r = run(catalog, "VBAK", "VBAP")
    p1 = [m for m in r.matches if m.priority == 1]
    covered = [len(m.covered) for m in p1]
    assert covered == sorted(covered, reverse=True)
    assert p1[0].all_covered


def test_ranking_is_stable(catalog):
    first = names(run(catalog, "VBAP", "VBAK"))
    for _ in range(5):
        assert names(run(catalog, "VBAP", "VBAK")) == first


def test_positions_follow_the_order(catalog):
    r = run(catalog, "MKPF")
    assert [r.position[m.view.key] for m in r.matches] == list(range(1, len(r.matches) + 1))


def test_level_of_detail(catalog):
    by_name = {m.view.name: m for m in run(catalog, "KONV").matches}
    assert by_name["I_SalesDocItemPricingElement"].detail == "check"      # keys partly from the order item
    assert {m.view.name: m.detail for m in run(catalog, "MSEG").matches}["I_MaterialDocumentItem_2"] == "same"


def test_filters_keep_counts_for_every_priority(catalog):
    r = run(catalog, "MSEG")
    kept, counts = r.filtered(priority=2, include_custom=True, q="")
    assert {m.priority for m in kept} == {2}
    assert counts == {1: 2, 2: 2, 3: 1}
    kept, counts = r.filtered(priority=None, include_custom=False, q="")
    assert all(not m.view.custom for m in kept) and counts[3] == 0
    kept, _ = r.filtered(priority=None, include_custom=True, q="stock")
    assert [m.view.name for m in kept] == ["I_MaterialStock_2"]


# -- business notes ----------------------------------------------------------------------

TECHNICAL_TERMS = re.compile(r"\b(CDS|CDC|DDL|DD03N|IXTRCTNENBLDVW|annotation|element|entity|true|false|null|"
                             r"key fields?|ABAP|SQL)\b|[_@{}<>]", re.IGNORECASE)
UPPER_CASE_NAME = re.compile(r"\b[A-Z][A-Z0-9_/]{2,}\b")       # MATDOC, I_MATERIALSTOCK ...
ALLOWED_UPPER = {"SAP"}


def note_texts(note) -> list[str]:
    return [note.summary, note.recommendation, *note.considerations,
            *(f"{c.label} {c.value}" for c in note.capabilities)]


@pytest.mark.parametrize("tables", [("MSEG",), ("MKPF",), ("VBAK", "VBAP"), ("KONV",), ("BSEG",), ("VBUK",)])
def test_notes_use_plain_business_wording(catalog, tables):
    r = run(catalog, *tables)
    assert r.matches
    table_names = {t for m in r.matches for t in m.view.tables} | set(tables)
    for m in r.matches:
        for text in note_texts(ranking.business_note(m, catalog.keys_loaded)):
            assert text and text[0].isupper(), text
            words = set(re.findall(r"[A-Za-z0-9_/]+", text))
            assert not words & table_names, f"table name in note: {text}"
            assert m.view.name not in text
            assert not TECHNICAL_TERMS.search(text), text
            assert set(UPPER_CASE_NAME.findall(text)) <= ALLOWED_UPPER, text
            assert not re.search(r"\b(sample|test|demo)\b", text, re.IGNORECASE)


def test_note_explains_the_priority(catalog):
    by_name = {m.view.name: m for m in run(catalog, "MSEG").matches}
    p1 = ranking.business_note(by_name["I_MaterialDocumentItem_2"], True)
    assert p1.summary.startswith("Priority 1 because it supports both data extraction and delta loads")
    assert "Strong candidate" in p1.recommendation and not p1.considerations
    p2 = ranking.business_note(by_name["I_GoodsMovementCube"], True)
    assert p2.summary.startswith("Priority 2 because it is a standard SAP view")
    assert "not enabled for data extraction" in p2.summary
    assert "cannot be extracted as delivered" in p2.recommendation
    assert "Builds on other views rather than reading your table directly." in p2.considerations
    p3 = ranking.business_note(by_name["ZI_MATDOC_SCRAP_EXT"], True)
    assert p3.summary.startswith("Priority 3 because it is a custom view")
    assert any("Not released by SAP" in c for c in p3.considerations)
    assert [(c.label, c.value) for c in p3.capabilities] == [
        ("Data extraction", "Available"), ("Delta loads", "Not supported"), ("Released by SAP", "No")]


def test_note_mentions_missing_tables_and_detail_level(catalog):
    by_name = {m.view.name: m for m in run(catalog, "VBAK", "VBAP").matches}
    note = ranking.business_note(by_name["I_SalesDocItemPricingElement"], True)
    assert "Does not read 1 table of the 2 you entered." in note.considerations
    assert any("more detailed records" in c for c in note.considerations)
    assert note.recommendation.startswith("Good candidate once the points below are checked")


def test_guidance_when_nothing_reads_the_table(catalog):
    r = run(catalog, "ZZTAB")
    g = ranking.guidance(r, catalog)
    assert g.title == "No view reads ZZTAB"
    assert any("no table mapping" in t for t in g.tips)


def test_guidance_when_no_view_has_priority_1():
    plain = view("I_ONLY")
    cat = Catalog({plain.key: plain}, {"T1": [plain.key]}, {"views": 1})
    r = rank(cat, [Input("T1", ("T1",), "same")])
    g = ranking.guidance(r, cat)
    assert "supports both extraction and delta loads" in g.title
    assert g.tips[0] == "Start with I_ONLY, the highest ranked view."


def test_detail_lists_fields_and_tables(catalog):
    r = run(catalog, "MSEG")
    cube = next(m for m in r.matches if m.view.name == "I_GoodsMovementCube")
    d = ranking.detail(cube, r.position[cube.view.key], catalog.keys_loaded)
    assert d.builds_on == ["I_MaterialDocumentItem_2"]
    assert d.tables[0].table == "MATDOC" and d.tables[0].yours and not d.tables[0].direct
    assert len(d.fields) == len(cube.view.elements)
    assert d.detail_level_text == "Same level of detail as your table"


def test_extra_condition_filters_before_counting(catalog):
    r = run(catalog, "MSEG")
    kept, counts = r.filtered(None, True, "", keep=lambda m: m.view.name.startswith("I_MaterialDocument"))
    assert [m.view.name for m in kept] == ["I_MaterialDocumentItem_2", "I_MaterialDocumentHeader_2"]
    assert counts == {1: 2}
