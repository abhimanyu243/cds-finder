from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from cds_finder.api import create_app
from cds_finder.metadata import Catalog, build_catalog
from cds_finder.settings import Settings

EXAMPLES = Path(__file__).resolve().parent.parent / "examples"


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return build_catalog(EXAMPLES)


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(data_dir=EXAMPLES, db_path=tmp_path / "mapping.db", log_level="WARNING")


@pytest.fixture
def client(settings: Settings):
    with TestClient(create_app(settings)) as c:
        yield c


# Data product catalogue rows copied from the catalogue layout (Product, Entity, CDS view, Entity type,
# Extraction, Root, Size, Elements, Keys). Used only by the tests, together with a few lineage rows for
# the views they name.
CATALOGUE = '''Product,Entity,CDS view,Entity type,Extraction,Root,Size,Elements,Keys
sap-s4com-Address-v1,AddressRemark,I_ADDRESSREMARK_2,sap.vdm.sont:AddressRemark,Yes,TRUE,XXL,4,"AddressID, AddressRepresentationCode"
sap-s4com-Address-v1,EmailAddress,I_ADDRESSEMAILADDRESS_2,sap.vdm.sont:EmailAddress,Yes,TRUE,XXL,8,"AddressID, AddressPersonID, CommMediumSequenceNumber"
sap-s4com-Address-v1,FaxNumber,I_ADDRESSFAXNUMBER_2,sap.vdm.sont:FaxNumber,No,TRUE,XXL,11,"AddressID, AddressPersonID, CommMediumSequenceNumber"
sap-s4com-HANACurrency-v1,TCURC,I_CURRENCY,,No,,,7,"MANDT, WAERS"
sap-s4com-HANACurrency-v1,TCURT,I_CURRENCYTEXT,,No,,,6,"MANDT, WAERS, SPRAS"
sap-s4com-HANACurrency-v1,TCURR,I_EXCHANGERATERAWDATA,,No,,L,11,"MANDT, KURST, FCURR, TCURR, GDATU"
sap-s4com-HANACurrency-v1,TCURV,I_EXCHANGERATETYPE,,Yes,,M,10,"MANDT, KURST"
sap-s4com-HANACurrency-v1,TCURX,I_CURRENCY,,No,,,4,"MANDT, CURRKEY"
sap-s4com-HANACurrency-v1,TCURX,I_CURRENCY,,No,,,4,"MANDT, CURRKEY"
,Orphan,I_CURRENCY,,No,,,1,X
sap-s4com-Country-v1,Country,I_COUNTRY,sap.vdm.sont:Country,No,TRUE,S,7,"Country, Language"
'''

LINEAGE = '''DDLNAME,LEVEL,ENTITY_NAME,ELEMENT_NAME,BASE_OBJECT,BASE_FIELD,IS_CALCULATED
I_CURRENCY,1,I_Currency,Currency,TCURC,WAERS,
I_CURRENCY,1,I_Currency,ISOCurrency,TCURC,ISOCD,
I_CURRENCY,1,I_Currency,Decimals,TCURX,CURRDEC,
I_EXCHANGERATERAWDATA,1,I_ExchangeRateRawData,ExchangeRateType,TCURR,KURST,
I_EXCHANGERATERAWDATA,1,I_ExchangeRateRawData,SourceCurrency,TCURR,FCURR,
ZI_CURRENCYREPORT,1,ZI_CurrencyReport,Currency,TCURC,WAERS,
I_ADDRESSREMARK_2,1,I_AddressRemark_2,AddressID,ADRCT,ADDRNUMBER,
I_ADDRESSREMARK_2,1,I_AddressRemark_2,AddressRemark,ADRCT,REMARK,
'''


def write_product_data(folder: Path) -> Path:
    """Copy the example metadata into folder, add the lineage rows above and the catalogue."""
    folder.mkdir(parents=True, exist_ok=True)
    for src in EXAMPLES.glob("*.csv"):
        text = src.read_text(encoding="utf-8")
        if src.name.startswith("CDS_FIELD_ORIGIN"):
            text = text.rstrip("\n") + "\n" + LINEAGE.split("\n", 1)[1]
        (folder / src.name).write_text(text, encoding="utf-8")
    (folder / "DataProductCatalogue.csv").write_text(CATALOGUE, encoding="utf-8")
    return folder


@pytest.fixture
def product_client(tmp_path: Path):
    data = write_product_data(tmp_path / "data")
    settings = Settings(data_dir=data, db_path=tmp_path / "mapping.db", log_level="WARNING")
    with TestClient(create_app(settings)) as c:
        yield c
