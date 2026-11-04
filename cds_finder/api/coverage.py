"""Field comparison routes: which views provide a list of fields. Nothing is stored."""

from __future__ import annotations

from fastapi import APIRouter
from fastapi.responses import Response

from .. import coverage
from ..schemas import ErrorResponse
from .common import FinderDep, csv_download

router = APIRouter(prefix="/api/coverage", tags=["Field comparison"],
                   responses={400: {"model": ErrorResponse}, 503: {"model": ErrorResponse}})


@router.post("")
def compare(req: coverage.CoverageRequest, finder: FinderDep) -> coverage.CoverageResponse:
    """Coverage of the requested fields by every view that reads their tables, with the best view,
    the smallest set of views that provides every field, and a side-by-side comparison."""
    return coverage.compare(finder, req)


@router.post("/export", response_class=Response,
             responses={200: {"content": {"text/csv": {}}, "description": "Coverage per view as CSV"}})
def export(req: coverage.CoverageRequest, finder: FinderDep) -> Response:
    return csv_download(coverage.export_rows(finder, req), "field_comparison.csv")
