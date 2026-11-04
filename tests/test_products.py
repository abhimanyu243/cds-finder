from __future__ import annotations

from pathlib import Path

import pytest

from cds_finder.metadata import LoadError
from cds_finder.products import humanize, load_catalogue, product_title

from .conftest import CATALOGUE


def write(folder: Path, text: str, name: str = "DataProductCatalogue.csv") -> Path:
    (folder / name).write_text(text, encoding="utf-8")
    return folder


def test_no_catalogue_file_means_an_empty_catalogue(tmp_path):
    catalogue, report = load_catalogue(tmp_path)
    assert not catalogue.loaded and report is None and catalogue.for_view("I_CURRENCY") == {}


def test_catalogue_is_indexed_by_cds_view(tmp_path):
    catalogue, report = load_catalogue(write(tmp_path, CATALOGUE))
    assert report.name == "DataProductCatalogue.csv"
    assert list(catalogue.products) == ["sap-s4com-Address-v1", "sap-s4com-HANACurrency-v1", "sap-s4com-Country-v1"]
    linked = catalogue.for_view("i_currency")                      # names compare in upper case
    assert list(linked) == ["sap-s4com-HANACurrency-v1"]
    assert [e.entity for e in linked["sap-s4com-HANACurrency-v1"]] == ["TCURC", "TCURX"]


def test_view_is_found_by_entity_or_data_definition_name_without_duplicates(tmp_path):
    catalogue, _ = load_catalogue(write(tmp_path, CATALOGUE))
    linked = catalogue.for_view("I_Currency", "I_CURRENCY")
    assert [e.entity for e in linked["sap-s4com-HANACurrency-v1"]] == ["TCURC", "TCURX"]
    assert catalogue.for_view("I_CURRENCYX") == {}                 # exact names only, nothing guessed
    assert catalogue.for_view("", "") == {}


def test_duplicate_rows_and_rows_without_product_are_skipped(tmp_path):
    catalogue, _ = load_catalogue(write(tmp_path, CATALOGUE))
    assert catalogue.report["duplicateRows"] == 1
    assert catalogue.report["rowsWithoutProduct"] == 1
    entities = [e.entity for e in catalogue.products["sap-s4com-HANACurrency-v1"]]
    assert entities == ["TCURC", "TCURT", "TCURR", "TCURV", "TCURX"]


def test_entity_details_are_parsed(tmp_path):
    catalogue, _ = load_catalogue(write(tmp_path, CATALOGUE))
    remark = catalogue.products["sap-s4com-Address-v1"][0]
    assert (remark.entity, remark.cds_view, remark.entity_type) == (
        "AddressRemark", "I_ADDRESSREMARK_2", "sap.vdm.sont:AddressRemark")
    assert (remark.extraction, remark.root, remark.size, remark.elements) == (True, True, "XXL", 4)
    assert remark.keys == ("AddressID", "AddressRepresentationCode")
    currency = catalogue.products["sap-s4com-HANACurrency-v1"][0]
    assert (currency.extraction, currency.root, currency.size) == (False, False, "")
    assert currency.keys == ("MANDT", "WAERS")


def test_same_view_in_several_products(tmp_path):
    text = CATALOGUE + "sap-s4com-Treasury-v1,Currency,I_CURRENCY,,Yes,TRUE,S,3,Currency\n"
    catalogue, _ = load_catalogue(write(tmp_path, text))
    assert list(catalogue.for_view("I_CURRENCY")) == ["sap-s4com-HANACurrency-v1", "sap-s4com-Treasury-v1"]


def test_unknown_extraction_value_is_not_stated(tmp_path):
    text = "Product,Entity,CDS view,Extraction\nP-x-A-v1,A,I_A,\nP-x-A-v1,B,I_B,Maybe\nP-x-A-v1,C,I_C,No\n"
    catalogue, _ = load_catalogue(write(tmp_path, text))
    assert [e.extraction for e in catalogue.products["P-x-A-v1"]] == [None, None, False]


def test_semicolon_layout_and_catalog_spelling(tmp_path):
    text = 'Product;Entity;CDS view;Keys\nsap-s4com-Country-v1;Country;I_COUNTRY;"Country, Language"\n'
    catalogue, report = load_catalogue(write(tmp_path, text, name="dataproductcatalog_2026.csv"))
    assert catalogue.products["sap-s4com-Country-v1"][0].keys == ("Country", "Language")


def test_file_without_the_needed_columns_is_rejected(tmp_path):
    with pytest.raises(LoadError):
        load_catalogue(write(tmp_path, "Name,Value\nA,B\n"))


@pytest.mark.parametrize("name, title, version", [
    ("sap-s4com-Address-v1", "Address", "1"),
    ("sap-s4com-AddressConfigurationData-v1", "Address configuration data", "1"),
    ("sap-s4com-HANACurrency-v2", "HANA currency", "2"),
    ("CustomerSales", "CustomerSales", None),                  # other formats are shown as they are
])
def test_product_title(name, title, version):
    assert product_title(name) == (title, version)


def test_humanize_keeps_technical_names():
    for name in ("TCURC", "Z_SALES", "Sales order"):
        assert humanize(name) == name
