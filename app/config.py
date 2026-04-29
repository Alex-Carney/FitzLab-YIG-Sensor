"""Settings loaded from environment variables."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    password: str
    secret: str
    db_path: Path
    cadence_sec: float
    dev_mode: bool
    log_level: str
    cookie_name: str = "yig_session"
    cookie_max_age_sec: int = 30 * 24 * 3600
    range_max_days: int = 7
    api_max_rows_default: int = 2000
    api_max_rows_hard_cap: int = 10000
    ws_ping_interval_sec: float = 30.0
    db_connect_max_wait_sec: float = 300.0

    @classmethod
    def from_env(cls) -> "Settings":
        password = os.environ.get("YIG_DASHBOARD_PASSWORD")
        if not password:
            raise RuntimeError("YIG_DASHBOARD_PASSWORD is required")
        secret = os.environ.get("YIG_DASHBOARD_SECRET")
        if not secret:
            raise RuntimeError("YIG_DASHBOARD_SECRET is required")
        if len(secret) < 16:
            raise RuntimeError("YIG_DASHBOARD_SECRET must be at least 16 chars")

        db_path_str = os.environ.get("YIG_DB_PATH", "spectrum_data_ovn.sqlite")
        cadence = float(os.environ.get("YIG_COLLECTION_CADENCE_SEC", "1.0"))
        dev_mode = os.environ.get("YIG_DEV_MODE", "").strip() not in ("", "0", "false", "False")
        log_level = os.environ.get("LOG_LEVEL", "INFO")

        return cls(
            password=password,
            secret=secret,
            db_path=Path(db_path_str),
            cadence_sec=cadence,
            dev_mode=dev_mode,
            log_level=log_level,
        )
