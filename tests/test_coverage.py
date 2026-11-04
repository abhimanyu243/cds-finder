"""Field comparison: which views provide a list of fields (example metadata, MSEG and MKPF map to MATDOC)."""

from __future__ import annotations

import pytest

from cds_finder.coverage import MAX_FIELDS, Wanted, parse_fields

MSEG = [{"ecc": "MSEG"}]


def compare(client, fields, tables=MSEG, **extra):
    return client.post("/api/coverage", json={"tables": tables, "fields": fields, **extra})


def test_parse_fields_accepts_the_usual_spellings():
    assert parse_fields(["vbap-netwr", " VBAP.NETWR ", "VBAP NETWR", "netwr", "", "/BIC/T-/BIC/F"]) == [
        Wanted("VBAP", "NETWR"), Wanted("", "NETWR"), Wanted("/BIC/T", "/BIC/F")]


@pytest.mark.parametrize("fields, message", [
    (["VBAP-NET WR-X"], "is not a field"),
    (["VBAP-NETWR;"], "is not a field"),
    ([" "], "Enter at least one field."),
    ([], "Enter at least one field."),
    ([f"F{i}" for i in range(MAX_FIELDS + 1)], f"at most {MAX_FIELDS} fields"),
])
def test_invalid_fields(client, fields, message):
    r = compare(client, fields)
    assert r.status_code == 400 and message in r.json()["detail"]


def test_best_view_counts_and_order(client):
    r = compare(client, ["mblnr", "MSEG-MATNR", "WERKS", "MENGE", "BWART", "ZZNOTHERE"]).json()
    assert [(i["ecc"], i["s4"]) for i in r["inputs"]] == [("MSEG", ["MATDOC"])]          # the mapping is used
    fields = {f["label"]: f for f in r["fields"]}
    assert fields["MSEG-MATNR"]["s4Tables"] == ["MATDOC"] and fields["MSEG-MATNR"]["status"] == "found"
    assert fields["ZZNOTHERE"] == {**fields["ZZNOTHERE"], "status": "missing", "views": 0}
    summary = r["summary"]
    assert (summary["requested"], summary["coverable"]) == (6, 5)
    assert summary["best"]["name"] == "I_MaterialDocumentItem_2" and summary["best"]["covered"] == 5
    assert summary["combination"] is None                         # the best view already has every coverable field
    covered = [(v["name"], v["covered"]) for v in r["views"]]
    assert covered[0] == ("I_MaterialDocumentItem_2", 5)
    order = [(v["priority"], -v["covered"]) for v in r["views"]]
    assert order == sorted(order)                                 # P1 first, then the most fields
    ranks_at_five = [v["rank"] for v in r["views"] if v["covered"] == 5]
    assert ranks_at_five == sorted(ranks_at_five)                 # equal coverage keeps the recommended order
    assert r["viewsFound"] == 5


def test_smallest_combination_when_no_view_has_everything(client):
    r = compare(client, ["MATNR", "MENGE", "MKPF-USNAM", "MKPF-BKTXT"]).json()
    assert r["summary"]["best"]["name"] == "I_MaterialDocumentItem_2"
    combination = r["summary"]["combination"]
    assert (combination["views"], combination["covered"]) == (["I_MaterialDocumentItem_2",
                                                               "I_MaterialDocumentHeader_2"], 4)
    comparison = r["comparison"]
    assert [v["name"] for v in comparison["views"]] == ["I_MaterialDocumentItem_2", "I_MaterialDocumentHeader_2"]
    cells = {row["label"]: [c["status"] for c in row["cells"]] for row in comparison["rows"]}
    assert cells == {"MATNR": ["yes", "no"], "MENGE": ["yes", "no"], "MKPF-USNAM": ["no", "yes"],
                     "MKPF-BKTXT": ["no", "yes"]}
    assert comparison["rows"][2]["cells"][1]["element"]          # the view field that carries it


def test_field_used_only_in_a_calculation_is_not_counted(client):
    r = compare(client, ["STOCK_QTY", "MATNR"]).json()
    stock = r["fields"][0]
    assert (stock["status"], stock["views"], stock["calculatedOnly"]) == ("calculated", 0, 1)
    view = next(v for v in r["views"] if v["name"] == "I_MaterialStock_2")
    assert (view["covered"], view["calculated"]) == (1, 1)
    chosen = compare(client, ["STOCK_QTY"], compare=["I_MaterialStock_2"]).json()["comparison"]
    assert chosen["rows"][0]["cells"][0]["status"] == "calculated"


def test_tables_come_from_the_fields_when_nothing_was_searched(client):
    r = compare(client, ["MSEG-MATNR", "MKPF-BUDAT"], tables=[]).json()
    assert [i["ecc"] for i in r["inputs"]] == ["MSEG", "MKPF"]
    assert all(f["status"] == "found" for f in r["fields"])
    bare = compare(client, ["MATNR"], tables=[])
    assert bare.status_code == 400 and "Add the table to each field" in bare.json()["detail"]
    many = compare(client, [f"T{i}-F" for i in range(11)], tables=[])
    assert many.status_code == 400 and "more than 10 tables" in many.json()["detail"]


def test_choose_the_views_to_compare(client):
    r = compare(client, ["MATNR", "USNAM"], compare=["I_GoodsMovementCube", "i_materialdocumentheader_2"]).json()
    assert [v["name"] for v in r["comparison"]["views"]] == ["I_GoodsMovementCube", "I_MaterialDocumentHeader_2"]
    unknown = compare(client, ["MATNR"], compare=["I_Nope"])
    assert unknown.status_code == 400
    assert unknown.json()["detail"] == "I_Nope does not read the tables you are comparing."
    assert compare(client, ["MATNR"], compare=["A", "B", "C", "D", "E"]).status_code == 422


def test_export_csv(client):
    r = client.post("/api/coverage/export", json={"tables": MSEG, "fields": ["MATNR", "USNAM", "ZZNOTHERE"]})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    lines = r.text.lstrip("﻿").strip().splitlines()
    assert lines[0].startswith("Rank,View,Description,Priority,Fields provided")
    assert lines[1].startswith("1,I_MaterialDocumentItem_2,")
    assert lines[-1] == "Fields no view provides,ZZNOTHERE"


def test_nothing_is_stored(client):
    before = client.get("/api/meta").json()["mappingVersion"]
    compare(client, ["MATNR"])
    client.post("/api/coverage/export", json={"tables": MSEG, "fields": ["MATNR"]})
    assert client.get("/api/meta").json()["mappingVersion"] == before


def test_without_metadata_comparison_is_unavailable(tmp_path):
    from fastapi.testclient import TestClient

    from cds_finder.api import create_app
    from cds_finder.settings import Settings
    settings = Settings(data_dir=tmp_path / "none", db_path=tmp_path / "m.db", log_level="WARNING")
    with TestClient(create_app(settings)) as c:
        assert compare(c, ["MATNR"]).status_code == 503


def test_page_has_one_script_one_stylesheet_and_the_compare_drawer(client):
    page = client.get("/").text
    assert page.count("<script ") == 1 and page.count('rel="stylesheet"') == 1
    assert 'id="fieldsDrawer"' in page and 'id="compareFields"' in page and 'id="fieldsFile"' in page
    assert client.get("/assets/coverage.js").status_code == 404


def test_views_say_whether_the_search_can_show_them(client):
    r = compare(client, ["VBAP-NETWR", "MATNR"]).json()          # VBAP is named in the fields, MSEG was searched
    assert any(v["searched"] for v in r["views"])
    assert all(v["searched"] for v in r["views"] if v["name"].startswith(("I_Material", "I_Goods")))
    nothing_searched = compare(client, ["MSEG-MATNR"], tables=[]).json()
    assert not any(v["searched"] for v in nothing_searched["views"])


def test_a_field_without_a_table_stays_in_the_searched_tables(client):
    r = compare(client, ["MATNR", "VBAP-NETWR"]).json()                 # MSEG searched, VBAP named
    plain = next(f for f in r["fields"] if f["label"] == "MATNR")
    assert plain["s4Tables"] == ["MATDOC"]


# -- choosing between views --------------------------------------------------------------------

def test_side_by_side_lists_the_facts_the_ranking_uses(client):
    view = compare(client, ["MBLNR"], compare=["I_MaterialDocumentItem_2"]).json()["comparison"]["views"][0]
    assert {k: view[k] for k in ("extraction", "delta", "released", "detail", "detailText", "reads", "direct",
                                 "otherTables", "fieldsInView", "dataProducts")} == {
        "extraction": True, "delta": True, "released": True, "detail": "same",
        "detailText": "Same level of detail as your table", "reads": ["MSEG"], "direct": True, "otherTables": 0,
        "fieldsInView": 30, "dataProducts": []}


def test_verdict_names_the_rule_that_decides_a_tie(client):
    tie = compare(client, ["MBLNR", "MJAHR"], compare=["I_GoodsMovementCube", "I_MaterialDocumentItem_2"]).json()
    c = tie["comparison"]
    assert c["recommended"] == "I_MaterialDocumentItem_2" and c["joins"] == []
    assert c["verdict"] == ["Choose I_MaterialDocumentItem_2.",
                            "Same fields as I_MaterialDocumentItem_2. I_MaterialDocumentItem_2 ranks higher because "
                            "it supports data extraction and delta loads."]
    custom = compare(client, ["MBLNR"], compare=["I_MaterialDocumentItem_2", "ZI_MATDOC_SCRAP_EXT"]).json()
    assert custom["comparison"]["verdict"][1].endswith("ZI_MATDOC_SCRAP_EXT is a custom view built in your system.")
    none = compare(client, ["MBLNR"], compare=["I_MaterialDocumentItem_2", "I_MaterialStock_2"]).json()
    assert none["comparison"]["verdict"][1] == "I_MaterialStock_2 provides none of these fields."
    one = compare(client, ["MBLNR"], compare=["I_MaterialDocumentItem_2"]).json()["comparison"]
    assert (one["recommended"], one["verdict"], one["joins"]) == (None, [], [])


def test_why_one_view_ranks_above_another(client):
    from dataclasses import replace

    from cds_finder import ranking
    from cds_finder.schemas import TableInput
    item = client.app.state.finder.ranking([TableInput(ecc="MSEG")]).matches[0]
    mixed = replace(item, other_tables=["T001"])
    assert ranking.why_higher(item, mixed) == "it mixes in fewer other tables (0 against 1)"
    assert ranking.why_higher(item, replace(item, detail="check")) == "it has the same level of detail as your table"
    assert ranking.why_higher(item, item) == "the two are equal on every ranking rule, so the name decides"


def test_views_used_together_come_with_a_join_suggestion(client):
    r = compare(client, ["MATNR", "MENGE", "MKPF-USNAM", "MKPF-BKTXT"]).json()
    join = r["summary"]["combination"]["joins"][0]
    assert (join["left"], join["right"], join["complete"]) == ("I_MaterialDocumentItem_2",
                                                                 "I_MaterialDocumentHeader_2", True)
    assert [(p["left"], p["right"], p["via"]) for p in join["pairs"]] == [
        ("MaterialDocumentYear", "MaterialDocumentYear", "MATDOC-MJAHR = MATDOC-MJAHR"),
        ("MaterialDocument", "MaterialDocument", "MATDOC-MBLNR = MATDOC-MBLNR")]
    assert join["note"].startswith("This is the full key of I_MaterialDocumentHeader_2")
    c = r["comparison"]
    assert c["recommended"] is None and c["joins"] == [join]
    assert c["verdict"] == ["I_MaterialDocumentHeader_2 adds MKPF-USNAM, MKPF-BKTXT, which I_MaterialDocumentItem_2 "
                            "lacks. Use the two together."]


def test_join_across_tables_through_the_same_field(tmp_path):
    """Line items on ACDOCA and products on MARA: the product key comes from MARA-MATNR and the line
    item has a field from ACDOCA-MATNR, so the suggestion is to look products up by that field."""
    from fastapi.testclient import TestClient

    from cds_finder.api import create_app
    from cds_finder.settings import Settings
    data = tmp_path / "data"
    data.mkdir()
    (data / "CDS_FIELD_ORIGIN.csv").write_text(
        "DDLNAME,LEVEL,ENTITY_NAME,ELEMENT_NAME,BASE_OBJECT,BASE_FIELD,IS_CALCULATED\n"
        "I_GLLINE,1,I_GLLine,AccountingDocument,ACDOCA,BELNR,\n"
        "I_GLLINE,1,I_GLLine,GLAccount,ACDOCA,RACCT,\n"
        "I_GLLINE,1,I_GLLine,Product,ACDOCA,MATNR,\n"
        "I_PRODUCTX,1,I_ProductX,Product,MARA,MATNR,\n"
        "I_PRODUCTX,1,I_ProductX,ProductType,MARA,MTART,\n", encoding="utf-8")
    (data / "IXTRCTNENBLDVW.csv").write_text(
        "DATAEXTRACTIONVIEWNAME,DATAEXTRACTIONVIEWDESCRIPTION,ISSAPRELEASEDVIEW,DELTACHGDATACAPTUREISSUPPORTED\n"
        "I_GLLINE,Line item,X,X\nI_PRODUCTX,Product,X,X\n", encoding="utf-8")
    (data / "DD03N.csv").write_text("STRUCOBJN,FIELDNAME,KEYFLAG\nI_GLLINE,ACCOUNTINGDOCUMENT,X\n"
                                    "I_PRODUCTX,PRODUCT,X\n", encoding="utf-8")
    with TestClient(create_app(Settings(data_dir=data, db_path=tmp_path / "m.db", log_level="WARNING"))) as c:
        r = compare(c, ["ACDOCA-RACCT", "MARA-MTART"], tables=[]).json()
        assert r["summary"]["combination"]["views"] == ["I_GLLine", "I_ProductX"]
        join = r["comparison"]["joins"][0]
        assert (join["left"], join["right"], join["complete"]) == ("I_GLLine", "I_ProductX", True)
        assert [(p["left"], p["right"], p["via"]) for p in join["pairs"]] == [
            ("Product", "Product", "ACDOCA-MATNR = MARA-MATNR")]
        (data / "DD03N.csv").unlink()
    with TestClient(create_app(Settings(data_dir=data, db_path=tmp_path / "m2.db", log_level="WARNING"))) as c:
        join = compare(c, ["ACDOCA-RACCT", "MARA-MTART"], tables=[]).json()["comparison"]["joins"][0]
        assert join["pairs"] == [] and join["note"] == "Add the DD03N key fields file to see how to join these views."


def test_p1_views_come_first_even_when_a_lower_priority_view_has_more_fields(tmp_path):
    """Two P1 views have one field each; a P2 view has three and a P3 view has the fourth. The best view
    is a P1 view, and the views used together are taken from P1, then P2, then P3."""
    from fastapi.testclient import TestClient

    from cds_finder.api import create_app
    from cds_finder.settings import Settings
    data = tmp_path / "data"
    data.mkdir()
    lineage = {"I_ITEMONE": ["F1"], "I_ITEMTWO": ["F2"], "I_ITEMWIDE": ["F1", "F2", "F3"], "Z_ITEMEXTRA": ["F4"]}
    (data / "CDS_FIELD_ORIGIN.csv").write_text(
        "DDLNAME,LEVEL,ENTITY_NAME,ELEMENT_NAME,BASE_OBJECT,BASE_FIELD,IS_CALCULATED\n"
        + "".join(f"{v},1,{v},{f.title()},TABX,{f},\n" for v, fields in lineage.items() for f in fields),
        encoding="utf-8")
    (data / "IXTRCTNENBLDVW.csv").write_text(
        "DATAEXTRACTIONVIEWNAME,DATAEXTRACTIONVIEWDESCRIPTION,ISSAPRELEASEDVIEW,DELTACHGDATACAPTUREISSUPPORTED\n"
        "I_ITEMONE,One,X,X\nI_ITEMTWO,Two,X,X\n", encoding="utf-8")
    with TestClient(create_app(Settings(data_dir=data, db_path=tmp_path / "m.db", log_level="WARNING"))) as c:
        r = compare(c, ["F1", "F2", "F3", "F4"], tables=[{"ecc": "TABX"}]).json()
        assert [(v["name"], v["priority"], v["covered"]) for v in r["views"]] == [
            ("I_ITEMONE", 1, 1), ("I_ITEMTWO", 1, 1), ("I_ITEMWIDE", 2, 3), ("Z_ITEMEXTRA", 3, 1)]
        s = r["summary"]
        assert s["best"]["name"] == "I_ITEMONE" and s["moreFields"]["name"] == "I_ITEMWIDE"
        assert s["combination"]["views"] == ["I_ITEMONE", "I_ITEMTWO", "I_ITEMWIDE", "Z_ITEMEXTRA"]
        assert s["combination"]["covered"] == 4
        picked = compare(c, ["F1", "F2"], tables=[{"ecc": "TABX"}], compare=["I_ITEMWIDE", "I_ITEMONE"]).json()
        assert picked["comparison"]["verdict"][0].startswith("I_ITEMWIDE adds F2, which I_ITEMONE lacks")
        alone = compare(c, ["F3"], tables=[{"ecc": "TABX"}]).json()["summary"]
        assert alone["best"]["name"] == "I_ITEMWIDE" and alone["moreFields"] is None   # no P1 view has it: P2
