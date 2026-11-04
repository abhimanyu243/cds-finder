"""Table mapping routes. Changes need the version you opened, so nobody overwrites a change unseen."""

from __future__ import annotations

from typing import Annotated, Literal

from fastapi import APIRouter, Query, status
from fastapi.responses import Response

from ..schemas import (
    ErrorResponse, HistoryPage, ImportRequest, ImportResult, Mapping, MappingCreate, MappingPage, MappingQuery,
    MappingUpdate, StatusChange,
)
from .common import FinderDep, RepositoryDep, csv_download

router = APIRouter(prefix="/api/mappings", tags=["Table mapping"],
                   responses={404: {"model": ErrorResponse}, 409: {"model": ErrorResponse}})


def _with_usage(finder: FinderDep, item: Mapping) -> Mapping:
    item.views = finder.catalog.views_reading(item.s4)
    return item


@router.get("")
def list_mappings(query: Annotated[MappingQuery, Query()], repo: RepositoryDep, finder: FinderDep) -> MappingPage:
    page = repo.list(query)
    for item in page.items:
        _with_usage(finder, item)
    return page


@router.post("", status_code=status.HTTP_201_CREATED)
def create_mapping(body: MappingCreate, repo: RepositoryDep, finder: FinderDep) -> Mapping:
    return _with_usage(finder, repo.create(body, body.changed_by))


@router.get("/export", response_class=Response,
            responses={200: {"content": {"text/csv": {}}, "description": "The mapping as CSV"}})
def export_mappings(repo: RepositoryDep, status: Literal["active", "retired", "all"] = "active") -> Response:
    rows = [["ECC_TABLE", "S4_TABLES", "NOTE"]] + [[m.ecc, ";".join(m.s4), m.note] for m in repo.export(status)]
    return csv_download(rows, "table_mapping.csv")


@router.post("/import")
def import_mappings(body: ImportRequest, repo: RepositoryDep) -> ImportResult:
    """Check rows first (apply=false), then save them all at once (apply=true)."""
    return repo.import_rows(body.rows, body.apply, body.changed_by)


@router.get("/{ecc:path}/history")
def mapping_history(ecc: str, repo: RepositoryDep, page: Annotated[int, Query(ge=1)] = 1,
                    page_size: Annotated[int, Query(alias="pageSize", ge=1, le=100)] = 20) -> HistoryPage:
    return repo.history(ecc, page, page_size)


@router.post("/{ecc:path}/retire")
def retire_mapping(ecc: str, body: StatusChange, repo: RepositoryDep, finder: FinderDep) -> Mapping:
    return _with_usage(finder, repo.set_status(ecc, "retired", body.version, body.changed_by))


@router.post("/{ecc:path}/restore")
def restore_mapping(ecc: str, body: StatusChange, repo: RepositoryDep, finder: FinderDep) -> Mapping:
    return _with_usage(finder, repo.set_status(ecc, "active", body.version, body.changed_by))


@router.get("/{ecc:path}")
def get_mapping(ecc: str, repo: RepositoryDep, finder: FinderDep) -> Mapping:
    return _with_usage(finder, repo.get(ecc))


@router.put("/{ecc:path}")
def update_mapping(ecc: str, body: MappingUpdate, repo: RepositoryDep, finder: FinderDep) -> Mapping:
    return _with_usage(finder, repo.update(ecc, body.s4, body.note, body.version, body.changed_by))
