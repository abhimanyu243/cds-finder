"""Search routes: ranked views, one view in full, CSV export, and reference data for the UI."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Path, Query
from fastapi.responses import Response

from ..schemas import (
    NAME_RE, DataProduct, ErrorResponse, Health, Meta, ProductPage, ProductQuery,
    SearchRequest, SearchResponse, TableUsage, ViewDetail, ViewRequest, split_tables,
)
from .common import FinderDep, csv_download

router = APIRouter(prefix="/api")


@router.get("/health", tags=["System"])
def health(finder: FinderDep) -> Health:
    return Health(ready=finder.catalog.loaded)


@router.get("/meta", tags=["System"])
def meta(finder: FinderDep) -> Meta:
    """Loaded files, active mapping, table name suggestions and priority labels."""
    return finder.meta()


@router.post("/search", tags=["Search"])
def search(req: SearchRequest, finder: FinderDep) -> SearchResponse:
    """One page of ranked views. Results carry no field list; ask /api/view for that."""
    return finder.search(req)


@router.post("/view", tags=["Search"])
def view(req: ViewRequest, finder: FinderDep) -> ViewDetail:
    """One view in full, with every field, seen from the tables you searched for."""
    return finder.view(req)


@router.post("/search/export", tags=["Search"], response_class=Response,
             responses={200: {"content": {"text/csv": {}}, "description": "Every matching view as CSV"}})
def export(req: SearchRequest, finder: FinderDep) -> Response:
    name = "_".join(dict.fromkeys(t.ecc for t in req.tables)).replace("/", "")
    return csv_download(finder.export_rows(req), f"views_for_{name}.csv")


@router.get("/data-products", tags=["Data products"])
def data_products(query: Annotated[ProductQuery, Query()], finder: FinderDep) -> ProductPage:
    """One page of data products from the catalogue, in catalogue order."""
    return finder.products_page(query)


@router.get("/data-products/{name}", tags=["Data products"], responses={404: {"model": ErrorResponse}})
def data_product(name: Annotated[str, Path(max_length=200)], finder: FinderDep) -> DataProduct:
    """A data product from the catalogue, with all of its entities, keys and extraction details."""
    return finder.product(name)


@router.get("/tables/usage", tags=["Search"])
def table_usage(finder: FinderDep, names: Annotated[str, Query(max_length=400)] = "") -> TableUsage:
    """How many views read each table (shown while editing a mapping)."""
    tables = [t for t in split_tables(names) if NAME_RE.fullmatch(t)][:10]
    return finder.table_usage(tables)
