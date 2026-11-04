from __future__ import annotations

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cds_finder.api import create_app
from cds_finder.schemas import Mapping, MappingPage, Meta, SearchResponse, ViewDetail
from cds_finder.settings import PACKAGE_DIR, Settings

WORDING = re.compile(r"\b(sample|samples|test|tests|testing|demo|dummy|lorem)\b", re.IGNORECASE)


def search(client: TestClient, *tables, **options):
    body = {"tables": [t if isinstance(t, dict) else {"ecc": t} for t in tables], **options}
    return client.post("/api/search", json=body)


# -- system --------------------------------------------------------------------------

def test_health_and_meta(client):
    assert client.get("/api/health").json() == {"status": "ok", "ready": True}
    meta = Meta.model_validate(client.get("/api/meta").json())
    assert meta.ready and meta.views == 17
    assert [f.name for f in meta.files] == ["CDS_FIELD_ORIGIN.csv", "IXTRCTNENBLDVW.csv", "DD03N.csv", "mapping.db"]
    assert meta.mappings["VBUK"] == ["VBAK", "LIKP", "VBRK"]
    assert [p.level for p in meta.priorities] == [1, 2, 3]
    assert "MSEG" in meta.suggestions


def test_meta_does_not_expose_folders(client):
    text = client.get("/api/meta").text
    assert str(Path.cwd()) not in text and "/tmp" not in text and "examples" not in text


def test_json_uses_camel_case(client):
    body = search(client, "MSEG").json()
    assert {"viewsFound", "priorities", "results", "paging"} <= body.keys()
    assert {"priorityLabel", "matchedFieldCount", "detailLevel", "notCovered"} <= body["results"][0].keys()


def test_home_page_and_assets(client):
    page = client.get("/")
    assert page.status_code == 200 and "text/html" in page.headers["content-type"]
    assert page.headers["cache-control"] == "no-cache"
    for asset in ("/assets/app.css", "/assets/app.js", "/assets/icon.svg"):
        r = client.get(asset)
        assert r.status_code == 200 and r.headers["cache-control"] == "no-cache"
        assert client.get(asset, headers={"If-None-Match": r.headers["etag"]}).status_code == 304


def test_page_points_at_the_current_files(client):
    """A browser must never pair a new page with a script it kept from an older version."""
    page = client.get("/").text
    for name in ("app.css", "app.js"):
        digest = hashlib.sha256((PACKAGE_DIR / "web" / name).read_bytes()).hexdigest()[:12]
        assert f'"/assets/{name}?v={digest}"' in page
        assert client.get(f"/assets/{name}?v={digest}").content == (PACKAGE_DIR / "web" / name).read_bytes()


def test_security_headers(client):
    r = client.get("/api/health")
    assert r.headers["x-content-type-options"] == "nosniff"
    assert r.headers["x-frame-options"] == "DENY"
    assert "default-src 'self'" in r.headers["content-security-policy"]
    assert r.headers["cache-control"] == "no-store"


def test_large_responses_are_compressed(client):
    r = client.post("/api/view", json={"tables": [{"ecc": "MSEG"}], "name": "I_MaterialDocumentItem_2"},
                    headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") == "gzip"


def test_api_docs_can_be_switched_off(settings):
    assert TestClient(create_app(settings)).get("/api/docs").status_code == 200
    off = settings.model_copy(update={"docs_enabled": False})
    with TestClient(create_app(off)) as c:
        assert c.get("/api/docs").status_code == 404
        assert c.get("/api/openapi.json").status_code == 404


# -- search ---------------------------------------------------------------------------

def test_search_ranks_by_priority(client):
    r = search(client, "MSEG")
    assert r.status_code == 200
    data = SearchResponse.model_validate(r.json())
    assert [v.name for v in data.results] == ["I_MaterialDocumentItem_2", "I_MaterialDocumentHeader_2",
                                             "I_MaterialStock_2", "I_GoodsMovementCube", "ZI_MATDOC_SCRAP_EXT"]
    assert [v.priority for v in data.results] == [1, 1, 2, 2, 3]
    assert [v.rank for v in data.results] == [1, 2, 3, 4, 5]
    assert [(p.level, p.count) for p in data.priorities] == [(1, 2), (2, 2), (3, 1)]
    assert data.inputs[0].source == "mapping" and data.inputs[0].s4 == ["MATDOC"]
    assert data.results[0].note.summary.startswith("Priority 1")


def test_search_filters_sort_and_paging(client):
    p2 = search(client, "MSEG", priority=2).json()
    assert [v["priority"] for v in p2["results"]] == [2, 2]
    assert [v["rank"] for v in p2["results"]] == [3, 4]                 # rank stays the overall position
    assert [p["count"] for p in p2["priorities"]] == [2, 2, 1]
    by_name = search(client, "MSEG", sort="name").json()["results"]
    assert [v["name"] for v in by_name] == sorted((v["name"] for v in by_name), key=str.lower)
    no_custom = search(client, "MSEG", includeCustom=False).json()
    assert all(not v["custom"] for v in no_custom["results"]) and no_custom["viewsFound"] == 5
    assert [v["name"] for v in search(client, "MSEG", q="stock").json()["results"]] == ["I_MaterialStock_2"]
    page = search(client, "MSEG", pageSize=2, page=2).json()
    assert [v["rank"] for v in page["results"]] == [3, 4]
    assert page["paging"] == {"page": 2, "pageSize": 2, "pages": 3, "total": 5, "start": 3, "end": 4}
    assert search(client, "MSEG", pageSize=2, page=40).json()["paging"]["page"] == 3


def test_entered_tables_override_the_mapping(client):
    data = search(client, {"ecc": "MSEG", "s4": "vbak"}).json()
    assert data["inputs"][0] == {"ecc": "MSEG", "s4": ["VBAK"], "source": "entered", "note": data["inputs"][0]["note"],
                                 "views": 3, "unknownTables": []}
    assert all("I_Material" not in v["name"] for v in data["results"])


def test_same_ecc_table_twice_counts_once(client):
    data = search(client, "VBAP", "vbap").json()
    assert len(data["inputs"]) == 1


def test_unknown_table_gives_guidance(client):
    data = search(client, "ZZTAB").json()
    assert data["viewsFound"] == 0 and data["results"] == []
    assert data["inputs"][0]["unknownTables"] == ["ZZTAB"]
    assert data["guidance"]["title"] == "No view reads ZZTAB"


def test_view_detail(client):
    r = client.post("/api/view", json={"tables": [{"ecc": "MSEG"}], "name": "i_goodsmovementcube"})
    detail = ViewDetail.model_validate(r.json())
    assert detail.rank == 4 and detail.builds_on == ["I_MaterialDocumentItem_2"]
    assert detail.fields[0].sources[0].via == ["I_MaterialDocumentItem_2"]
    missing = client.post("/api/view", json={"tables": [{"ecc": "MSEG"}], "name": "I_SalesDocument"})
    assert missing.status_code == 404 and "does not read the tables" in missing.json()["detail"]


def test_export_csv(client):
    r = client.post("/api/search/export", json={"tables": [{"ecc": "MSEG"}], "priority": 1})
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/csv")
    assert 'filename="views_for_MSEG.csv"' in r.headers["content-disposition"]
    lines = r.text.lstrip("﻿").splitlines()
    assert lines[0].startswith("Rank,View,Description,Priority")
    assert len(lines) == 3 and lines[1].startswith("1,I_MaterialDocumentItem_2")


def test_table_usage(client):
    assert client.get("/api/tables/usage?names=vbak; likp,bad!").json() == {
        "tables": {"VBAK": 3, "LIKP": 1}, "total": 4}


@pytest.mark.parametrize("body, message", [
    ({}, "Enter at least one ECC table."),
    ({"tables": []}, "Enter at least one ECC table."),
    ({"tables": [{"ecc": "MS EG!"}]}, "ECC table: 'MS EG!' is not a valid table name"),
    ({"tables": [{"ecc": "MSEG", "s4": ";".join(f"T{i}" for i in range(11))}]}, "S/4HANA tables:"),
    ({"tables": [{"ecc": "MSEG"}], "priority": 4}, "Priority: Input should be 1, 2 or 3."),
    ({"tables": [{"ecc": "MSEG"}], "pageSize": 1000}, "Page size:"),
    ({"tables": [{"ecc": f"T{i}"} for i in range(11)]}, "Tables:"),
])
def test_invalid_search_requests(client, body, message):
    r = client.post("/api/search", json=body)
    assert r.status_code == 422
    assert r.json()["detail"].startswith(message)


def test_malformed_json(client):
    r = client.post("/api/search", content="{bad", headers={"Content-Type": "application/json"})
    assert r.status_code == 422 and r.json()["detail"] == "The request body is not valid JSON."


def test_without_metadata_search_is_unavailable_but_mapping_works(tmp_path):
    settings = Settings(data_dir=tmp_path / "empty", db_path=tmp_path / "m.db", log_level="WARNING")
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health").json() == {"status": "ok", "ready": False}
        meta = c.get("/api/meta").json()
        assert not meta["ready"] and [f["name"] for f in meta["files"]] == ["m.db"]
        r = search(c, "MSEG")
        assert r.status_code == 503 and "not loaded" in r.json()["detail"]
        assert c.get("/api/mappings").json()["paging"]["total"] > 0


# -- mappings ----------------------------------------------------------------------------

def test_mapping_lifecycle(client):
    created = client.post("/api/mappings", json={"ecc": "vbfa", "s4": "vbfa", "note": "Flow", "changedBy": "Ann"})
    assert created.status_code == 201
    item = Mapping.model_validate(created.json())
    assert (item.ecc, item.s4, item.views) == ("VBFA", ["VBFA"], 0)

    dup = client.post("/api/mappings", json={"ecc": "VBFA", "s4": ["X"]})
    assert dup.status_code == 409 and dup.json()["current"]["ecc"] == "VBFA"

    put = client.put("/api/mappings/VBFA", json={"s4": ["VBAP"], "note": "", "version": 1})
    assert put.status_code == 200 and put.json()["version"] == 2 and put.json()["views"] == 4
    stale = client.put("/api/mappings/VBFA", json={"s4": ["X"], "version": 1})
    assert stale.status_code == 409 and stale.json()["current"]["version"] == 2

    assert client.post("/api/mappings/VBFA/retire", json={"version": 2}).json()["status"] == "retired"
    assert client.post("/api/mappings/VBFA/restore", json={"version": 3}).json()["status"] == "active"
    history = client.get("/api/mappings/VBFA/history?pageSize=2").json()
    assert [h["action"] for h in history["items"]] == ["restore", "retire"] and history["paging"]["pages"] == 2
    assert client.get("/api/mappings/NOPE").status_code == 404


def test_mapping_change_is_used_by_the_next_search(client):
    assert search(client, "ZZOLD").json()["viewsFound"] == 0
    client.post("/api/mappings", json={"ecc": "ZZOLD", "s4": ["MATDOC"]})
    data = search(client, "ZZOLD").json()
    assert data["inputs"][0]["source"] == "mapping" and data["viewsFound"] == 5


def test_namespaced_table_names(client):
    assert client.post("/api/mappings", json={"ecc": "/BIC/AZSALES", "s4": ["/BIC/AZSALES2"]}).status_code == 201
    assert client.get("/api/mappings/%2FBIC%2FAZSALES").json()["s4"] == ["/BIC/AZSALES2"]
    assert client.get("/api/mappings/%2FBIC%2FAZSALES/history").json()["paging"]["total"] == 1


def test_mapping_list_and_export(client):
    page = MappingPage.model_validate(client.get("/api/mappings?pageSize=5&sort=ecc").json())
    assert len(page.items) == 5 and page.paging.total == 21
    assert [m.ecc for m in page.items] == sorted(m.ecc for m in page.items)
    assert client.get("/api/mappings?status=bogus").status_code == 422
    csv_text = client.get("/api/mappings/export").text.lstrip("﻿")
    assert csv_text.splitlines()[0] == "ECC_TABLE,S4_TABLES,NOTE" and "VBUK,VBAK;LIKP;VBRK" in csv_text


def test_mapping_import_endpoint(client):
    rows = [{"ecc": "NEW1", "s4": "A;B"}, {"ecc": "bad!", "s4": "X"}]
    preview = client.post("/api/mappings/import", json={"rows": rows}).json()
    assert preview["summary"]["new"] == 1 and preview["summary"]["error"] == 1 and not preview["applied"]
    refused = client.post("/api/mappings/import", json={"rows": rows, "apply": True})
    assert refused.status_code == 400
    ok = client.post("/api/mappings/import", json={"rows": rows[:1], "apply": True})
    assert ok.json()["applied"] and client.get("/api/mappings/NEW1").json()["s4"] == ["A", "B"]


@pytest.mark.parametrize("body, message", [
    ({"ecc": "", "s4": ["A"]}, "ECC table:"),
    ({"ecc": "A", "s4": []}, "Enter at least one S/4HANA table."),
    ({"ecc": "A", "s4": ["A"], "note": "x" * 201}, "Note:"),
    ({"ecc": "A", "s4": ["A"], "changedBy": "x" * 61}, "Your name:"),
])
def test_invalid_mappings(client, body, message):
    r = client.post("/api/mappings", json=body)
    assert r.status_code == 422 and r.json()["detail"].startswith(message)


# -- wording ----------------------------------------------------------------------------------

def visible_text(path: Path) -> str:
    text = path.read_text(encoding="utf-8")
    return re.sub(r"\.test\(", "(", text)            # the RegExp method name is code, not wording


@pytest.mark.parametrize("name", ["index.html", "app.js", "app.css"])
def test_web_assets_have_no_placeholder_wording(name):
    assert not WORDING.search(visible_text(PACKAGE_DIR / "web" / name))


def test_initial_mapping_has_no_placeholder_wording():
    assert not WORDING.search((PACKAGE_DIR / "initial_mapping.csv").read_text(encoding="utf-8"))


def test_api_output_has_no_placeholder_wording(client):
    texts = [client.get("/api/meta").text, client.get("/api/openapi.json").text]
    for tables in ("MSEG", "VBUK", "KONV", "ZZTAB"):
        texts.append(search(client, tables).text)
    for text in texts:
        assert not WORDING.search(text), WORDING.search(text)


# -- data products -------------------------------------------------------------------------

def test_views_carry_their_data_products(product_client):
    meta = product_client.get("/api/meta").json()
    assert meta["dataProducts"] == 3
    assert {"name": "DataProductCatalogue.csv",
            "holds": "Data products with their entities, keys and extraction details"} in meta["files"]
    data = search(product_client, "TCURC").json()
    by_name = {v["name"]: v["dataProducts"] for v in data["results"]}
    assert by_name["I_Currency"] == [{"name": "sap-s4com-HANACurrency-v1", "title": "HANA currency",
                                      "entities": ["TCURC", "TCURX"], "cdsViews": ["I_CURRENCY"]}]
    assert by_name["ZI_CurrencyReport"] == []                                   # no mapping, said plainly


def test_view_detail_and_export_include_data_products(product_client):
    detail = product_client.post("/api/view", json={"tables": [{"ecc": "ADRCT"}], "name": "I_AddressRemark_2"}).json()
    assert [p["title"] for p in detail["dataProducts"]] == ["Address"]
    csv_text = product_client.post("/api/search/export", json={"tables": [{"ecc": "TCURC"}]}).text
    header, first = csv_text.lstrip("\ufeff").splitlines()[:2]
    assert "Data products" in header and "sap-s4com-HANACurrency-v1" in first


def test_data_product_details(product_client):
    p = product_client.get("/api/data-products/sap-s4com-Address-v1").json()
    assert (p["title"], p["version"]) == ("Address", "1")
    first = p["entities"][0]
    assert first == {"entity": "AddressRemark", "cdsView": "I_ADDRESSREMARK_2",
                     "entityType": "sap.vdm.sont:AddressRemark", "extraction": True, "root": True, "size": "XXL",
                     "fields": 4, "keys": ["AddressID", "AddressRepresentationCode"], "inMetadata": True}
    assert [e["inMetadata"] for e in p["entities"]] == [True, False, False]   # only the first view has lineage rows
    missing = product_client.get("/api/data-products/sap-s4com-Unknown-v1")
    assert missing.status_code == 404 and "not in the catalogue" in missing.json()["detail"]


def test_without_catalogue_nothing_changes(client):
    assert client.get("/api/meta").json()["dataProducts"] == 0
    assert all(v["dataProducts"] == [] for v in search(client, "MSEG").json()["results"])
    assert client.get("/api/data-products/sap-s4com-Address-v1").status_code == 404


def test_unreadable_catalogue_is_skipped(tmp_path):
    from .conftest import write_product_data
    data = write_product_data(tmp_path / "data")
    (data / "DataProductCatalogue.csv").write_text("Name,Value\nA,B\n", encoding="utf-8")
    settings = Settings(data_dir=data, db_path=tmp_path / "m.db", log_level="WARNING")
    with TestClient(create_app(settings)) as c:
        assert c.get("/api/health").json()["ready"] and c.get("/api/meta").json()["dataProducts"] == 0


def test_catalogue_output_has_no_placeholder_wording(product_client):
    texts = (product_client.get("/api/data-products/sap-s4com-Address-v1").text, search(product_client, "TCURC").text)
    for text in texts:
        assert not WORDING.search(text)


def test_filter_views_with_a_data_product(product_client):
    everything = search(product_client, "TCURC").json()
    assert everything["viewsFound"] == 2 and everything["dataProductViews"] == 1
    only = search(product_client, "TCURC", withDataProduct=True).json()
    assert [v["name"] for v in only["results"]] == ["I_Currency"]
    assert [p["count"] for p in only["priorities"]] == [0, 1, 0]              # counts follow the filter
    assert only["results"][0]["rank"] == 1 and only["viewsFound"] == 2
    csv_lines = product_client.post("/api/search/export", json={"tables": [{"ecc": "TCURC"}],
                                                                "withDataProduct": True}).text.strip().splitlines()
    assert len(csv_lines) == 2 and "I_Currency" in csv_lines[1]


def test_data_product_filter_combines_with_other_filters(product_client):
    assert search(product_client, "TCURC", withDataProduct=True, priority=3).json()["results"] == []
    assert search(product_client, "TCURC", withDataProduct=True, includeCustom=False).json()["paging"]["total"] == 1
    none = search(product_client, "MSEG", withDataProduct=True).json()
    assert none["results"] == [] and none["viewsFound"] == 5 and none["dataProductViews"] == 0


def test_data_product_count_is_zero_without_catalogue(client):
    assert search(client, "MSEG").json()["dataProductViews"] == 0


def test_bundled_logo_is_the_default_and_a_configured_logo_replaces_it(client, tmp_path):
    assert client.get("/api/meta").json()["brandLogo"] is True
    bundled = client.get("/brand-logo")
    assert bundled.status_code == 200 and bundled.headers["content-type"].startswith("image/svg")
    assert "#86bc24" in bundled.text and "#0f0b0b" not in bundled.text          # green dot kept, white lettering
    logo = tmp_path / "logo.svg"
    logo.write_text('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"></svg>', encoding="utf-8")
    settings = Settings(data_dir=tmp_path / "none", db_path=tmp_path / "m.db", brand_logo=logo, log_level="WARNING")
    with TestClient(create_app(settings)) as c:
        assert c.get("/brand-logo").text == logo.read_text(encoding="utf-8")
    missing = Settings(data_dir=tmp_path / "none", db_path=tmp_path / "m2.db", brand_logo=tmp_path / "gone.svg",
                       log_level="WARNING")
    with TestClient(create_app(missing)) as c:                                  # a wrong path falls back
        assert c.get("/brand-logo").text == bundled.text


def test_data_products_page(product_client):
    page = product_client.get("/api/data-products").json()
    assert [p["name"] for p in page["items"]] == ["sap-s4com-Address-v1", "sap-s4com-HANACurrency-v1",
                                                  "sap-s4com-Country-v1"]
    currency = page["items"][1]
    assert currency == {"name": "sap-s4com-HANACurrency-v1", "title": "HANA currency", "version": "1",
                        "entities": 5, "extractionEntities": 1, "rootEntities": 0, "cdsViews": 4,
                        "viewsInMetadata": 2}
    assert page["paging"]["total"] == 3
    by_entity = product_client.get("/api/data-products", params={"q": "tcurv"}).json()["items"]
    assert [p["name"] for p in by_entity] == ["sap-s4com-HANACurrency-v1"]          # entity names are searched
    known = product_client.get("/api/data-products", params={"inMetadata": "true"}).json()["items"]
    assert [p["name"] for p in known] == ["sap-s4com-Address-v1", "sap-s4com-HANACurrency-v1"]
    second = product_client.get("/api/data-products", params={"pageSize": 2, "page": 2}).json()
    assert [p["name"] for p in second["items"]] == ["sap-s4com-Country-v1"] and second["paging"]["start"] == 3


def test_data_products_page_is_empty_without_a_catalogue(client):
    assert client.get("/api/data-products").json()["items"] == []
    assert client.get("/api/catalogue").status_code == 404                        # the Catalogue page was removed
    meta = client.get("/api/meta").json()
    assert "catalogue" not in meta
    assert [n["title"] for n in meta["notices"]] == ["No data product catalogue"]


def test_notices_describe_what_needs_attention(product_client, tmp_path):
    meta = product_client.get("/api/meta").json()
    assert [n["title"] for n in meta["notices"]] == ["Repeated catalogue rows", "Catalogue rows without a product"]
    from .conftest import write_product_data
    data = write_product_data(tmp_path / "bad")
    (data / "DataProductCatalogue.csv").write_text("Name,Value\nA,B\n", encoding="utf-8")
    with TestClient(create_app(Settings(data_dir=data, db_path=tmp_path / "m.db", log_level="WARNING"))) as c:
        notice = c.get("/api/meta").json()["notices"][0]
        assert notice["level"] == "warning" and notice["title"] == "The data product catalogue could not be read"
    with TestClient(create_app(Settings(data_dir=tmp_path / "empty", db_path=tmp_path / "e.db",
                                        log_level="WARNING"))) as c:
        notices = c.get("/api/meta").json()["notices"]
        assert notices[0]["level"] == "warning" and notices[0]["title"] == "View metadata is not loaded"


def test_new_pages_have_no_placeholder_wording(product_client):
    for url in ("/api/data-products", "/api/meta"):
        assert not WORDING.search(product_client.get(url).text)
