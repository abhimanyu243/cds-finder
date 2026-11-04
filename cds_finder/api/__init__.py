"""FastAPI application: the web UI, the search API and the table mapping API.

Run it with `cds-finder serve`, or with uvicorn directly (settings come from CDS_FINDER_* variables):
    uvicorn cds_finder.api:create_app --factory --host 0.0.0.0 --port 8000

Use one worker process: each worker would hold its own copy of the metadata in memory.
Route handlers are plain functions on purpose: the work is CPU and SQLite bound, so
FastAPI runs them in its thread pool and the event loop stays free.
"""

from __future__ import annotations

import hashlib
import logging
import time
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .. import __version__
from ..errors import AppError, NotFound, describe_validation_error
from ..logs import configure_logging
from ..schemas import ErrorResponse
from ..service import Finder
from ..settings import Settings
from . import coverage, mappings, search

log = logging.getLogger("cds_finder")

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
}
# The UI loads nothing from other sites. The API docs page does (Swagger UI), so it is left out.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; "
       "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
ASSETS = ("app.css", "app.js")


def _page(web_dir: Path) -> str:
    """index.html with a hash of each file in its address (app.js?v=...), so after an update the
    browser fetches the new file instead of running a copy it kept from an older version."""
    page = (web_dir / "index.html").read_text(encoding="utf-8")
    for name in ASSETS:
        digest = hashlib.sha256((web_dir / name).read_bytes()).hexdigest()[:12]
        page = page.replace(f'"/assets/{name}"', f'"/assets/{name}?v={digest}"')
    return page


def _error(status_code: int, detail: str, current: object = None) -> JSONResponse:
    body = ErrorResponse(detail=detail, current=current)
    return JSONResponse(body.model_dump(by_alias=True, exclude_none=True, mode="json"), status_code=status_code)


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or Settings.from_env()
    configure_logging(settings.log_level, settings.log_json)

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        app.state.finder = Finder(settings)        # reads the metadata once
        log.info("Ready on version %s", __version__)
        yield

    docs = settings.docs_enabled
    app = FastAPI(
        title="CDS View Finder",
        version=__version__,
        summary="Find and rank the S/4HANA views that replace an ECC table.",
        lifespan=lifespan,
        docs_url="/api/docs" if docs else None,
        redoc_url=None,
        openapi_url="/api/openapi.json" if docs else None,
        responses={400: {"model": ErrorResponse}, 422: {"model": ErrorResponse}, 503: {"model": ErrorResponse}},
    )
    app.add_middleware(GZipMiddleware, minimum_size=1024)

    @app.middleware("http")
    async def observe(request: Request, call_next):
        started = time.perf_counter()
        path = request.url.path
        try:
            response = await call_next(request)
        except Exception:
            log.exception("Unhandled error on %s %s", request.method, path)
            response = _error(500, "Something went wrong on the server. Please try again.")
        response.headers.update(SECURITY_HEADERS)
        if not path.startswith("/api/docs"):
            response.headers["Content-Security-Policy"] = CSP
        if path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        elif path.startswith("/assets/"):
            response.headers["Cache-Control"] = "no-cache"        # the browser checks first; unchanged files answer 304
        ms = round((time.perf_counter() - started) * 1000, 1)
        log.info("%s %s %s %.0fms", request.method, path, response.status_code, ms,
                 extra={"fields": {"method": request.method, "path": path,
                                   "status": response.status_code, "duration_ms": ms}})
        return response

    @app.exception_handler(AppError)
    async def app_error(_: Request, exc: AppError) -> JSONResponse:
        return _error(exc.status_code, exc.message, exc.current)

    @app.exception_handler(RequestValidationError)
    async def invalid_request(_: Request, exc: RequestValidationError) -> JSONResponse:
        return _error(422, describe_validation_error(list(exc.errors())))

    app.include_router(search.router)
    app.include_router(mappings.router)
    app.include_router(coverage.router)
    app.mount("/assets", StaticFiles(directory=settings.web_dir), name="assets")
    page = _page(settings.web_dir)

    @app.get("/", include_in_schema=False)
    def home() -> HTMLResponse:
        return HTMLResponse(page, headers={"Cache-Control": "no-cache"})

    @app.get("/brand-logo", include_in_schema=False)
    def brand_logo(request: Request) -> FileResponse:
        """The company logo file, when one is configured (see CDS_FINDER_BRAND_LOGO)."""
        logo = request.app.state.finder.brand_logo
        if logo is None:
            raise NotFound("No logo file is configured.")
        return FileResponse(logo, headers={"Cache-Control": "public, max-age=3600"})

    return app
