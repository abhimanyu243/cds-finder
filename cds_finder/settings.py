"""Application settings, read from environment variables prefixed with CDS_FINDER_.

  CDS_FINDER_DATA_DIR      folder with the metadata CSV files         (default: ./data)
  CDS_FINDER_DB_PATH       SQLite file that holds the table mapping   (default: ./data/cds_finder.db)
  CDS_FINDER_HOST          address to listen on                       (default: 127.0.0.1)
  CDS_FINDER_PORT          port                                       (default: 8000)
  CDS_FINDER_LOG_LEVEL     DEBUG, INFO, WARNING or ERROR              (default: INFO)
  CDS_FINDER_LOG_JSON      1 for one JSON object per log line         (default: 0)
  CDS_FINDER_DOCS_ENABLED  0 to hide the API docs at /api/docs        (default: 1)
  CDS_FINDER_BRAND_LOGO    image file shown as the logo in the header (default: a brand-logo.svg or .png
                           file in the data folder, otherwise the bundled Deloitte logo)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict

PACKAGE_DIR = Path(__file__).resolve().parent
ENV_PREFIX = "CDS_FINDER_"


class Settings(BaseModel):
    model_config = ConfigDict(frozen=True)

    data_dir: Path = Path("data")
    db_path: Path = Path("data/cds_finder.db")
    initial_mapping: Path = PACKAGE_DIR / "initial_mapping.csv"
    web_dir: Path = PACKAGE_DIR / "web"
    host: str = "127.0.0.1"
    port: int = 8000
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_json: bool = False
    docs_enabled: bool = True
    brand_logo: Path | None = None

    @classmethod
    def from_env(cls, **overrides: object) -> Settings:
        """Environment variables first, then explicit overrides (for example from the command line)."""
        values = {name: os.environ[ENV_PREFIX + name.upper()]
                  for name in cls.model_fields if ENV_PREFIX + name.upper() in os.environ}
        values.update({k: v for k, v in overrides.items() if v is not None})
        return cls.model_validate(values)
