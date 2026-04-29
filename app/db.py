"""Read-only SQLite access layer.

The API process opens SQLite with mode=ro. The tracker is the only writer.
SQLite WAL mode (set once by the writer) lets multiple readers coexist with
the writer across processes - unlike DuckDB, which enforces single-process
access.
"""
from __future__ import annotations

import datetime as dt
import logging
import sqlite3
import time
from pathlib import Path
from typing import Optional

import numpy as np

logger = logging.getLogger("yig.db")


def _adapt_datetime(d: dt.datetime) -> str:
    return d.isoformat(sep=" ")


def _convert_timestamp(b: bytes) -> dt.datetime:
    return dt.datetime.fromisoformat(b.decode("utf-8"))


sqlite3.register_adapter(dt.datetime, _adapt_datetime)
sqlite3.register_converter("TIMESTAMP", _convert_timestamp)


_TRACE_COLS = ["time_created", "center_freq", "span", "rbw", "n_points", "powers"]


class Database:
    def __init__(self, path: Path):
        self.path = Path(path)
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self, max_wait_sec: float = 300.0) -> None:
        """Open a read-only connection, retrying with backoff if missing."""
        deadline = time.monotonic() + max_wait_sec
        delay = 1.0
        last_err: Optional[Exception] = None
        uri = f"file:{self.path.as_posix()}?mode=ro"
        while time.monotonic() < deadline:
            try:
                self._conn = sqlite3.connect(
                    uri,
                    uri=True,
                    detect_types=sqlite3.PARSE_DECLTYPES,
                    check_same_thread=False,
                )
                logger.info("opened read-only connection to %s", self.path)
                return
            except sqlite3.Error as e:
                last_err = e
                logger.warning("DB connect failed (%s); retrying in %.1fs", e, delay)
                time.sleep(delay)
                delay = min(delay * 2, 30.0)
        raise RuntimeError(f"Could not open DB at {self.path}: {last_err}")

    def is_connected(self) -> bool:
        return self._conn is not None

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    @staticmethod
    def _decode_powers(blob: bytes) -> list[float]:
        return np.frombuffer(blob, dtype="<f4").tolist()

    def _row_to_dict(self, row, cols: list[str]) -> dict:
        d = {c: v for c, v in zip(cols, row)}
        if "powers" in d and isinstance(d["powers"], (bytes, memoryview)):
            d["powers"] = self._decode_powers(bytes(d["powers"]))
        return d

    def latest_row(self) -> Optional[dict]:
        assert self._conn is not None
        row = self._conn.execute(
            f"SELECT {', '.join(_TRACE_COLS)} FROM spectra "
            "ORDER BY time_created DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        return self._row_to_dict(row, _TRACE_COLS)

    def latest_row_age_seconds(self, now: Optional[dt.datetime] = None) -> Optional[float]:
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT time_created FROM spectra ORDER BY time_created DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        if now is None:
            now = dt.datetime.now()
        return (now - row[0]).total_seconds()

    def count_rows(self) -> int:
        assert self._conn is not None
        return self._conn.execute("SELECT count(*) FROM spectra").fetchone()[0]

    def rows_after(self, after: dt.datetime, limit: int = 200) -> list[dict]:
        """Rows strictly newer than `after`, ascending, capped at `limit`."""
        assert self._conn is not None
        rows = self._conn.execute(
            f"SELECT {', '.join(_TRACE_COLS)} FROM spectra "
            "WHERE time_created > ? ORDER BY time_created ASC LIMIT ?",
            (after, limit),
        ).fetchall()
        return [self._row_to_dict(r, _TRACE_COLS) for r in rows]

    def range_rows(
        self,
        t_from: dt.datetime,
        t_to: dt.datetime,
        max_rows: int = 2000,
    ) -> list[dict]:
        """Full traces between t_from and t_to (inclusive), stride-decimated to <=max_rows."""
        assert self._conn is not None

        total = self._conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created BETWEEN ? AND ?",
            (t_from, t_to),
        ).fetchone()[0]
        if total == 0:
            return []

        stride = max(1, (total + max_rows - 1) // max_rows)
        rows = self._conn.execute(
            f"""
            SELECT {", ".join(_TRACE_COLS)} FROM (
                SELECT {", ".join(_TRACE_COLS)},
                       row_number() OVER (ORDER BY time_created) AS rn
                FROM spectra
                WHERE time_created BETWEEN ? AND ?
            )
            WHERE (rn - 1) % ? = 0
            ORDER BY time_created
            """,
            (t_from, t_to, stride),
        ).fetchall()
        return [self._row_to_dict(r, _TRACE_COLS) for r in rows]

    def peak_track_range(
        self,
        t_from: dt.datetime,
        t_to: dt.datetime,
        max_rows: int = 2000,
    ) -> list[dict]:
        """Per-row (t, peak_freq, peak_power, snr, center_freq), stride-decimated.

        SQLite can't reduce a BLOB column in SQL, so we decode in Python.
        At max_rows=2000 with 201-point traces this is trivial.
        """
        assert self._conn is not None
        total = self._conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created BETWEEN ? AND ?",
            (t_from, t_to),
        ).fetchone()[0]
        if total == 0:
            return []

        stride = max(1, (total + max_rows - 1) // max_rows)
        rows = self._conn.execute(
            """
            SELECT time_created, center_freq, span, n_points, powers FROM (
                SELECT time_created, center_freq, span, n_points, powers,
                       row_number() OVER (ORDER BY time_created) AS rn
                FROM spectra
                WHERE time_created BETWEEN ? AND ?
            )
            WHERE (rn - 1) % ? = 0
            ORDER BY time_created
            """,
            (t_from, t_to, stride),
        ).fetchall()

        out = []
        for t, center, span, n_pts, powers_blob in rows:
            if n_pts is None or n_pts <= 1 or not powers_blob:
                continue
            powers = np.frombuffer(bytes(powers_blob), dtype="<f4")
            peak_idx = int(np.argmax(powers))
            peak_p = float(powers[peak_idx])
            med_p = float(np.median(powers))
            peak_freq = center - span / 2 + peak_idx * span / (n_pts - 1)
            out.append({
                "time_created": t,
                "center_freq": center,
                "peak_freq": peak_freq,
                "peak_power": peak_p,
                "snr": peak_p - med_p,
            })
        return out
