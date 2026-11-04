"""Logging to stdout, as plain text or one JSON object per line (CDS_FINDER_LOG_JSON=true)."""

from __future__ import annotations

import json
import logging
import sys


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        data = {"time": self.formatTime(record, "%Y-%m-%dT%H:%M:%S%z"), "level": record.levelname,
                "logger": record.name, "message": record.getMessage(), **getattr(record, "fields", {})}
        if record.exc_info:
            data["error"] = self.formatException(record.exc_info)
        return json.dumps(data, default=str)


def configure_logging(level: str = "INFO", as_json: bool = False) -> None:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(JsonFormatter() if as_json else
                         logging.Formatter("%(asctime)s %(levelname)-7s %(name)s  %(message)s"))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error"):          # send server messages through the same handler
        logging.getLogger(name).handlers.clear()
        logging.getLogger(name).propagate = True
    logging.getLogger("uvicorn.access").disabled = True   # the app logs each request itself
