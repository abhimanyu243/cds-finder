"""Dependencies and helpers shared by the routers."""

from __future__ import annotations

import csv
import io
from typing import Annotated

from fastapi import Depends, Request
from fastapi.responses import Response

from ..mappings import MappingRepository
from ..service import Finder


def get_finder(request: Request) -> Finder:
    return request.app.state.finder


def get_repository(finder: Annotated[Finder, Depends(get_finder)]) -> MappingRepository:
    return finder.repository


FinderDep = Annotated[Finder, Depends(get_finder)]
RepositoryDep = Annotated[MappingRepository, Depends(get_repository)]


def csv_download(rows: list[list], filename: str) -> Response:
    """CSV with a byte order mark, so Excel opens it with the right encoding."""
    buf = io.StringIO()
    csv.writer(buf, lineterminator="\r\n").writerows(rows)
    return Response("﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"'})
