"""Errors the API turns into a JSON response: {"detail": "...", "current": ...}.

Messages are written for the people using the app, so they are safe to show as they are.
"""

from __future__ import annotations

from typing import Any


class AppError(Exception):
    status_code = 400

    def __init__(self, message: str, current: Any = None) -> None:
        super().__init__(message)
        self.message = message
        self.current = current          # the stored record, sent back with a conflict


class BadRequest(AppError):
    status_code = 400


class NotFound(AppError):
    status_code = 404


class Conflict(AppError):
    status_code = 409


class Unavailable(AppError):
    status_code = 503


FIELD_LABELS = {
    "ecc": "ECC table", "s4": "S/4HANA tables", "note": "Note", "changedBy": "Your name", "tables": "Tables",
    "name": "View name", "version": "Version", "rows": "Rows", "q": "Search text", "page": "Page",
    "pageSize": "Page size", "priority": "Priority", "sort": "Sort order", "status": "Status",
}

REQUIRED_LISTS = {"s4": "Enter at least one S/4HANA table.", "tables": "Enter at least one ECC table."}


def describe_validation_error(errors: list[dict]) -> str:
    """One readable sentence for the first problem in a pydantic error list."""
    if not errors:
        return "The request is not valid."
    err = errors[0]
    if err["type"] == "json_invalid":
        return "The request body is not valid JSON."
    names = [p for p in err.get("loc", ()) if isinstance(p, str) and p not in ("body", "query", "path")]
    if not names:
        return "The request body must be a JSON object."
    label = FIELD_LABELS.get(names[-1], names[-1])
    if names[-1] in REQUIRED_LISTS and err["type"] in ("missing", "too_short"):
        return REQUIRED_LISTS[names[-1]]
    if err["type"] == "missing":
        return f"{label} is required."
    return f"{label}: {err['msg'].removeprefix('Value error, ')}."
