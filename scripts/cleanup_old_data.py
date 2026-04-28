"""Daily cleanup: delete spectra older than 7 days.

Run via Windows Task Scheduler. Independent of the API. Opens its own
*write* connection - only safe to run when the tracker is paused, OR
DuckDB will queue the writer behind the tracker (single-writer constraint).

In practice: schedule this for a time when the tracker is briefly stopped,
OR accept that it may block until the tracker releases the file.
"""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import duckdb
from dotenv import load_dotenv


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.environ.get("YIG_DB_PATH", "spectrum_data_ovn.duckdb"))
    p.add_argument("--retention-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("cleanup")

    if not Path(args.db).exists():
        log.error("DB not found: %s", args.db)
        return 1

    import datetime as dt
    cutoff = dt.datetime.now() - dt.timedelta(days=args.retention_days)
    conn = duckdb.connect(args.db)
    try:
        n_before = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        n_to_delete = conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created < ?",
            [cutoff],
        ).fetchone()[0]
        log.info("DB has %d rows; %d older than %s", n_before, n_to_delete, cutoff)

        if args.dry_run:
            log.info("--dry-run: not deleting")
            return 0

        conn.execute("DELETE FROM spectra WHERE time_created < ?", [cutoff])
        n_after = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        log.info("deleted %d rows; now %d", n_before - n_after, n_after)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
