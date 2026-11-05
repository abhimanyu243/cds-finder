"""Request and response models. JSON uses camelCase; Python code uses snake_case."""

from __future__ import annotations

import re
from typing import Annotated, Literal

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, Field
from pydantic.alias_generators import to_camel

MAX_INPUT_TABLES = 10
MAX_S4_TABLES = 10
MAX_PAGE_SIZE = 100
NAME_RE = re.compile(r"[A-Z0-9_/]{1,30}")


class Schema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


# --------------------------------------------------------------------------
# Field types
# --------------------------------------------------------------------------

def _table_name(value: str) -> str:
    name = value.strip().upper()
    if not NAME_RE.fullmatch(name):
        raise ValueError(f"'{value.strip()}' is not a valid table name. "
                         "Use letters, digits, _ and /, up to 30 characters")
    return name


def split_tables(value: object) -> object:
    """'VBAK; LIKP, vbrk' -> ['VBAK', 'LIKP', 'VBRK'] (upper case, no repeats)."""
    if isinstance(value, str):
        value = re.split(r"[\s,;+]+", value)
    if isinstance(value, (list, tuple)):
        return list(dict.fromkeys(str(v).strip().upper() for v in value if v and str(v).strip()))
    return value


def _one_line(value: object) -> object:
    return " ".join(value.split()) if isinstance(value, str) else value


TableName = Annotated[str, AfterValidator(_table_name)]
TableList = Annotated[list[TableName], BeforeValidator(split_tables), Field(max_length=MAX_S4_TABLES)]
RequiredTableList = Annotated[list[TableName], BeforeValidator(split_tables),
                              Field(min_length=1, max_length=MAX_S4_TABLES)]
NoteText = Annotated[str, BeforeValidator(_one_line), Field(max_length=200)]
PersonName = Annotated[str, BeforeValidator(_one_line), Field(max_length=60)]
PriorityLevel = Literal[1, 2, 3]


class Paging(Schema):
    page: int
    page_size: int
    pages: int
    total: int
    start: int = Field(description="Position of the first item on this page (0 when empty)")
    end: int = Field(description="Position of the last item on this page")

    @classmethod
    def of(cls, page: int, page_size: int, total: int, shown: int) -> Paging:
        first = (page - 1) * page_size
        return cls(page=page, page_size=page_size, pages=max(1, -(-total // page_size)), total=total,
                   start=first + 1 if shown else 0, end=first + shown)


def clamp_page(page: int, page_size: int, total: int) -> int:
    return min(max(1, page), max(1, -(-total // page_size)))


class ErrorResponse(Schema):
    detail: str
    current: Mapping | None = None


# --------------------------------------------------------------------------
# Search
# --------------------------------------------------------------------------

class TableInput(Schema):
    ecc: TableName
    s4: TableList = Field(default_factory=list, description="S/4HANA tables to use instead of the mapping")


class Tables(Schema):
    tables: list[TableInput] = Field(min_length=1, max_length=MAX_INPUT_TABLES)


class SearchRequest(Tables):
    priority: PriorityLevel | None = Field(None, description="Show only views with this priority")
    include_custom: bool = True
    with_data_product: bool = Field(False, description="Show only views that belong to a data product")
    q: str = Field("", max_length=60, description="Filter by view name or description")
    sort: Literal["recommended", "name"] = "recommended"
    page: int = Field(1, ge=1)
    page_size: int = Field(20, ge=1, le=MAX_PAGE_SIZE)


class ViewRequest(Tables):
    name: str = Field(min_length=1, max_length=60)


class ResolvedTable(Schema):
    ecc: str
    s4: list[str]
    source: Literal["mapping", "entered", "same"]
    note: str = ""
    views: int = Field(description="Views that read these S/4HANA tables")
    unknown_tables: list[str] = Field(description="S/4HANA tables no view reads")


class Capability(Schema):
    label: str
    value: str
    tone: Literal["positive", "caution", "neutral"]


class BusinessNote(Schema):
    summary: str = Field(description="Why the view has its priority")
    recommendation: str = Field(description="How it fits a migration")
    capabilities: list[Capability]
    considerations: list[str] = Field(description="Points to check before using it")


class DataProductRef(Schema):
    name: str = Field(description="Data product name as in the catalogue, e.g. sap-s4com-Address-v1")
    title: str = Field(description="Readable name, e.g. Address")
    entities: list[str] = Field(description="Entities of the data product that use this view")
    cds_views: list[str] = Field(description="The CDS view names as written in the catalogue rows that matched")


class ViewSummary(Schema):
    rank: int | None = Field(description="Position in the recommended order")
    name: str
    description: str
    priority: PriorityLevel
    priority_label: str
    extraction: bool
    delta: bool
    released: bool
    custom: bool
    covered: list[str] = Field(description="ECC tables this view reads")
    not_covered: list[str]
    field_count: int
    matched_field_count: int = Field(description="Fields that come from your tables")
    detail_level: Literal["same", "check", "different", "unknown"]
    data_products: list[DataProductRef] = Field(default_factory=list,
                                                description="Data products that use this view (empty when none)")
    note: BusinessNote


class TableUse(Schema):
    table: str
    fields: int
    calculated_fields: int
    direct: bool
    yours: bool


class FieldSource(Schema):
    table: str
    field: str
    calculated: bool
    via: list[str]


class ViewField(Schema):
    name: str
    key: bool
    calculated: bool
    from_your_tables: bool
    sources: list[FieldSource]


class ViewAssociation(Schema):
    name: str = Field(description="Association name as SAP spells it, e.g. _BusinessPartnerCompany")
    target: str = Field(description="The view or table it points to")
    target_description: str = Field(description="Description of the target view, empty when not known")
    cardinality: str = Field(description="For example 1..1 or 0..*; empty when not stated")
    condition: str = Field(description="ON condition when the associations file has it, else empty")


class ViewDetail(ViewSummary):
    data_definition: str
    detail_level_text: str
    builds_on: list[str]
    tables: list[TableUse]
    fields: list[ViewField]
    associations: list[ViewAssociation] | None = Field(
        None, description="Associations the view defines, from DD08B; null when no DD08B file is loaded")


class PriorityCount(Schema):
    level: PriorityLevel
    label: str
    count: int


class Guidance(Schema):
    title: str
    tips: list[str]


class SearchResponse(Schema):
    inputs: list[ResolvedTable]
    views_found: int = Field(description="All views that read the tables, before filters")
    data_product_views: int = Field(0, description="Views found that belong to a data product")
    priorities: list[PriorityCount]
    results: list[ViewSummary]
    paging: Paging
    guidance: Guidance | None = None


class DataProductEntity(Schema):
    entity: str
    cds_view: str
    entity_type: str
    extraction: bool | None = Field(description="Extraction enabled; null when the catalogue does not say")
    root: bool
    size: str
    fields: int | None = Field(description="Number of elements")
    keys: list[str]
    in_metadata: bool = Field(False, description="The CDS view is in the loaded view metadata")


class DataProduct(Schema):
    name: str
    title: str
    version: str | None
    entities: list[DataProductEntity]


class ProductQuery(Schema):
    q: str = Field("", max_length=60, description="Filter by product, entity or CDS view name")
    in_metadata: bool = Field(False, description="Only products with a CDS view in the loaded view metadata")
    page: int = Field(1, ge=1)
    page_size: int = Field(24, ge=1, le=MAX_PAGE_SIZE)


class ProductSummary(Schema):
    name: str
    title: str
    version: str | None
    entities: int
    extraction_entities: int = Field(description="Entities enabled for extraction")
    root_entities: int
    cds_views: int = Field(description="Different CDS views the product uses")
    views_in_metadata: int = Field(description="Of those, views found in the loaded view metadata")


class ProductPage(Schema):
    items: list[ProductSummary]
    paging: Paging


# --------------------------------------------------------------------------
# Meta
# --------------------------------------------------------------------------

class DataFile(Schema):
    name: str
    holds: str


class PriorityInfo(Schema):
    level: PriorityLevel
    label: str
    description: str


class Notice(Schema):
    level: Literal["warning", "info"]
    title: str
    text: str


class Meta(Schema):
    app_version: str
    ready: bool = Field(description="True when the metadata files are loaded")
    views: int
    loaded_at: str | None
    files: list[DataFile]
    data_products: int = Field(description="Data products in the catalogue (0 when no catalogue is loaded)")
    notices: list[Notice] = Field(default_factory=list, description="Files that are missing or need attention")
    brand_logo: bool = Field(False, description="True when a logo file is available at /brand-logo")
    mappings: dict[str, list[str]] = Field(description="Active mapping: ECC table -> S/4HANA tables")
    mapping_version: int
    suggestions: list[str]
    priorities: list[PriorityInfo]


class TableUsage(Schema):
    tables: dict[str, int]
    total: int


class Health(Schema):
    status: Literal["ok"] = "ok"
    ready: bool


# --------------------------------------------------------------------------
# Mappings
# --------------------------------------------------------------------------

MappingStatus = Literal["active", "retired"]


class MappingIn(Schema):
    ecc: TableName
    s4: RequiredTableList
    note: NoteText = ""


class MappingCreate(MappingIn):
    changed_by: PersonName = ""


class MappingUpdate(Schema):
    s4: RequiredTableList
    note: NoteText = ""
    version: int
    changed_by: PersonName = ""


class StatusChange(Schema):
    version: int
    changed_by: PersonName = ""


class Mapping(Schema):
    ecc: str
    s4: list[str]
    note: str
    status: MappingStatus
    version: int
    changed_by: str
    changed_at: str
    views: int = Field(0, description="Views that read the S/4HANA tables")


class MappingQuery(Schema):
    q: str = Field("", max_length=60)
    status: Literal["active", "retired", "all"] = "active"
    sort: Literal["ecc", "changed"] = "ecc"
    page: int = Field(1, ge=1)
    page_size: int = Field(25, ge=1, le=MAX_PAGE_SIZE)


class MappingPage(Schema):
    items: list[Mapping]
    paging: Paging


class MappingSnapshot(Schema):
    s4: list[str]
    note: str
    status: MappingStatus


class HistoryEntry(Schema):
    action: Literal["create", "update", "retire", "restore", "import"]
    old: MappingSnapshot | None
    new: MappingSnapshot | None
    changed_by: str
    changed_at: str


class HistoryPage(Schema):
    items: list[HistoryEntry]
    paging: Paging


class ImportRow(Schema):
    ecc: str = Field("", max_length=60)
    s4: str | list[str] = ""
    note: str = Field("", max_length=400)


class ImportRequest(Schema):
    rows: list[ImportRow] = Field(min_length=1, max_length=5000)
    apply: bool = False
    changed_by: PersonName = ""


class ImportRowResult(Schema):
    row: int
    ecc: str
    s4: list[str] = Field(default_factory=list)
    note: str = ""
    action: Literal["new", "change", "restore", "same", "error"]
    message: str = ""


class ImportSummary(Schema):
    new: int = 0
    change: int = 0
    restore: int = 0
    same: int = 0
    error: int = 0


class ImportResult(Schema):
    summary: ImportSummary
    rows: list[ImportRowResult] = Field(description="Up to the first 500 rows")
    applied: bool


ErrorResponse.model_rebuild()
