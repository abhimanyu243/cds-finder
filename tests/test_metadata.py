from __future__ import annotations

from pathlib import Path

import pytest

from cds_finder.metadata import (
    EXTRACTION_COLUMNS, LoadError, build_catalog, canon, find_data_file, has_metadata, read_rows,
)


def write(path: Path, text: str, encoding: str = "utf-8") -> Path:
    path.write_text(text, encoding=encoding)
    return path


def test_canon_ignores_case_spaces_and_punctuation():
    assert canon("Base object ( Table )") == "BASEOBJECTTABLE"
    assert canon("data_extraction_view_name") == "DATAEXTRACTIONVIEWNAME"


@pytest.mark.parametrize("delim", [",", ";", "\t", "|"])
def test_reader_accepts_common_delimiters(tmp_path, delim):
    header = delim.join(["DATAEXTRACTIONVIEWNAME", "DATAEXTRACTIONVIEWDESCRIPTION", "ISSAPRELEASEDVIEW",
                         "DELTACHGDATACAPTUREISSUPPORTED"])
    path = write(tmp_path / "IXTRCTNENBLDVW.csv", f"{header}\n{delim.join(['I_A', 'View A', 'X', 'X'])}\n")
    assert read_rows(path, EXTRACTION_COLUMNS) == [
        {"VIEW_NAME": "I_A", "DESCRIPTION": "View A", "RELEASED": "X", "CDC": "X"}]


def test_reader_skips_preamble_separators_and_repeated_headers(tmp_path):
    text = ("Table: IXTRCTNENBLDVW\nDisplayed fields: 4\n\n"
            "| DataExtractionViewName | Description | Released | DeltaChangedCaptureIsSupported |\n"
            "|------------------------|-------------|----------|--------------------------------|\n"
            "| I_A | View A | X | |\n"
            "| DataExtractionViewName | Description | Released | DeltaChangedCaptureIsSupported |\n"
            "| I_B | View B | | X |\n")
    rows = read_rows(write(tmp_path / "x.txt", text), EXTRACTION_COLUMNS)
    assert [r["VIEW_NAME"] for r in rows] == ["I_A", "I_B"]
    assert rows[1]["CDC"] == "X"


def test_reader_falls_back_to_windows_1252(tmp_path):
    text = "DATAEXTRACTIONVIEWNAME,DATAEXTRACTIONVIEWDESCRIPTION\nI_A,Prix unitaire étendu\n"
    rows = read_rows(write(tmp_path / "x.csv", text, encoding="cp1252"), EXTRACTION_COLUMNS)
    assert rows[0]["DESCRIPTION"] == "Prix unitaire étendu"


def test_reader_rejects_a_file_without_the_needed_columns(tmp_path):
    with pytest.raises(LoadError, match="no header row"):
        read_rows(write(tmp_path / "x.csv", "A,B\n1,2\n"), EXTRACTION_COLUMNS)


def test_find_data_file_matches_part_of_the_name_and_skips_error_files(tmp_path):
    write(tmp_path / "CDS_FIELD_ORIGIN_errors.csv", "x")
    write(tmp_path / "export_cds_field_origin_2026.csv", "x")
    write(tmp_path / "CDS_FIELD_ORIGIN.xlsx", "x")
    assert find_data_file(tmp_path, "CDS_FIELD_ORIGIN").name == "export_cds_field_origin_2026.csv"
    assert find_data_file(tmp_path / "missing", "CDS_FIELD_ORIGIN") is None


def test_has_metadata_needs_both_required_files(tmp_path):
    write(tmp_path / "CDS_FIELD_ORIGIN.csv", "x")
    assert not has_metadata(tmp_path)
    write(tmp_path / "IXTRCTNENBLDVW.csv", "x")
    assert has_metadata(tmp_path)


def test_build_catalog_without_files_raises(tmp_path):
    with pytest.raises(LoadError):
        build_catalog(tmp_path)


def test_catalog_indexes_views_by_table(catalog):
    assert catalog.loaded
    assert "I_MATERIALDOCUMENTITEM_2" in catalog.table_index["MATDOC"]
    assert catalog.views_reading(["MATDOC"]) == len(set(catalog.table_index["MATDOC"]))
    assert catalog.views_reading(["NO_SUCH_TABLE"]) == 0


def test_stacked_views_are_followed_down_to_tables(catalog):
    cube = catalog.find_view("i_goodsmovementcube")
    assert cube.tables["MATDOC"].min_depth == 2
    source = next(s for e in cube.elements for s in e.sources if s.table == "MATDOC")
    assert source.via == ("I_MaterialDocumentItem_2",)


def test_key_fields_are_joined_on_view_and_field_name(catalog):
    item = catalog.find_view("I_MaterialDocumentItem_2")
    assert [e.name for e in item.keys] == ["MaterialDocumentYear", "MaterialDocument", "MaterialDocumentItem"]
    assert catalog.keys_loaded


def test_client_field_is_never_a_key(catalog):
    for view in catalog.views.values():
        assert all(e.name.upper() not in ("MANDT", "CLIENT") for e in view.keys)


def test_extraction_flags_are_linked_to_views(catalog):
    item = catalog.find_view("I_MaterialDocumentItem_2")
    assert item.extraction.delta and item.extraction.released
    stock = catalog.find_view("I_MaterialStock_2")
    assert stock.extraction and not stock.extraction.delta
    assert catalog.find_view("I_GoodsMovementCube").extraction is None


def test_standard_and_custom_names(catalog):
    assert catalog.find_view("I_MaterialStock_2").standard
    assert catalog.find_view("C_SalesDocumentItemDEX_1").standard
    custom = catalog.find_view("ZI_MATDOC_SCRAP_EXT")
    assert custom.custom and not custom.standard


def test_descriptions_from_ddl_source_texts(tmp_path):
    """DDDDLSRCT fills descriptions the extraction file lacks: active version, English first."""
    from .conftest import EXAMPLES
    data = tmp_path / "data"
    data.mkdir()
    for src in EXAMPLES.glob("*.csv"):
        (data / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    before = build_catalog(data)
    blank = next(v for v in before.views.values() if not v.description)
    with_ext = next(v for v in before.views.values() if v.description)
    (data / "DDDDLSRCT.csv").write_text(
        "DDLNAME,DDLANGUAGE,AS4LOCAL,DDTEXT\n"
        f"{blank.ddlname},D,A,Deutscher Text\n"
        f"{blank.ddlname},E,A,English text\n"
        f"{blank.ddlname},E,N,Inactive draft\n"
        f"{with_ext.ddlname},E,A,Should not replace the extraction text\n", encoding="utf-8")
    after = build_catalog(data)
    assert after.views[blank.key].description == "English text"
    assert after.views[with_ext.key].description == with_ext.description
    assert after.report["textsFile"] == "DDDDLSRCT.csv"
    assert after.report["viewsWithDescription"] == before.report["viewsWithDescription"] + 1


DD08B_HEADER = ("STRUCOBJN,NODENAME,ASSOCIATIONNAME,AS4LOCAL,STRUCOBJN_T,NODENAME_T,TYPEKIND_T,ASSOCIATIONKIND,"
                "CHECKINDICATOR,CARDINALITY,CARD_MIN,CARD_MAX,ASSORIGIN,DOPATH_T,ON_SOURCE,ASSOCNAME_RAW,"
                "ASSOCNAME_ORIG,STRUCOBJN_S,EXTENDNAME,IS_REDIRECTED,HAS_EXPLICIT_FILTER,DDTEXT\n")


def write_associations(folder: Path, rows: str) -> None:
    """Copy the example metadata into folder and add a DD08B file in the SE16 column layout."""
    from .conftest import EXAMPLES
    folder.mkdir(parents=True, exist_ok=True)
    for src in EXAMPLES.glob("*.csv"):
        (folder / src.name).write_text(src.read_text(encoding="utf-8"), encoding="utf-8")
    (folder / "DD08B.csv").write_text(DD08B_HEADER + rows, encoding="utf-8")


def test_associations_from_dd08b(tmp_path):
    """Each view gets the associations it defines: active rows only, original spelling, sorted, no repeats."""
    write_associations(tmp_path / "data", (
        "I_MATERIALDOCUMENTITEM_2,.NODE1,_MATERIALDOCUMENTHEADER,A,I_MATERIALDOCUMENTHEADER_2,.NODE1,B,0,,,1,1,,,"
        ",_MaterialDocumentHeader,_MATERIALDOCUMENTHEADER,I_MATERIALDOCUMENTITEM_2,,,,\n"
        "I_MATERIALDOCUMENTITEM_2,.NODE1,_CURRENCY,A,I_CURRENCY,.NODE1,B,0,,,0,2147483647,,,"
        '"_Currency.Currency =\n  $projection.CompanyCodeCurrency",_Currency,_CURRENCY,I_MATERIALDOCUMENTITEM_2,,,,\n'
        "I_MATERIALDOCUMENTITEM_2,.NODE1,_OLDNAME,N,I_PLANT,.NODE1,B,0,,,0,1,,,,_OldName,_OLDNAME,,,,,\n"
        "I_MATERIALDOCUMENTITEM_2,.NODE1,_CURRENCY,A,I_CURRENCY,.NODE1,B,0,,,0,1,,,,_Currency,_CURRENCY,,,,,\n"
        "I_NOTINTHEFIELDORIGIN,.NODE1,_PLANT,A,I_PLANT,.NODE1,B,0,,,0,1,,,,_Plant,_PLANT,,,,,\n"))
    catalog = build_catalog(tmp_path / "data")
    view = catalog.find_view("I_MaterialDocumentItem_2")
    assert catalog.associations_loaded
    assert [(a.name, a.target, a.cardinality, a.condition) for a in view.associations] == [
        ("_Currency", "I_CURRENCY", "0..*", "_Currency.Currency = $projection.CompanyCodeCurrency"),
        ("_MaterialDocumentHeader", "I_MATERIALDOCUMENTHEADER_2", "1..1", ""),
    ]
    assert catalog.find_view("I_GoodsMovementCube").associations == ()
    r = catalog.report
    assert (r["associationsFile"], r["associations"], r["viewsWithAssociations"],
            r["associationViewsNotInFieldOrigin"]) == ("DD08B.csv", 2, 1, 1)


def test_catalog_without_associations_file(catalog):
    assert not catalog.associations_loaded and catalog.report["associationsFile"] is None
    assert all(v.associations == () for v in catalog.views.values())


@pytest.mark.parametrize(("low", "high", "text"), [
    ("1", "1", "1..1"), ("0", "1", "0..1"), ("0", "5", "0..5"), ("0", "0", "0..*"), ("1", "1-", "1..*"),
    ("0", "2147483647", "0..*"), ("0", "2,147,483,647", "0..*"), ("0", "2.147.483.647", "0..*"),
    ("", "1", "0..1"), ("1", "", ""), ("", "", ""),
])
def test_cardinality_reads_card_min_and_card_max(low, high, text):
    from cds_finder.metadata import cardinality
    assert cardinality(low, high) == text
