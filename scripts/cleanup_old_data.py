"""Daily cleanup: delete spectra older than 7 days.

Run via Windows Task Scheduler. Independent of the API.

SQLite WAL mode allows this script to open a writer while the tracker is
also writing - SQLite serializes writers internally. Readers (the API) see
a consistent snapshot during deletion and pick up the post-DELETE state on
their next transaction.
"""
from __future__ import annotations

import argparse
import datetime as dt
import logging
import os
import sqlite3
import sys
from pathlib import Path

from dotenv import load_dotenv


sqlite3.register_adapter(dt.datetime, lambda d: d.isoformat(sep=" "))
sqlite3.register_converter(
    "TIMESTAMP", lambda b: dt.datetime.fromisoformat(b.decode("utf-8"))
)


def main() -> int:
    load_dotenv()
    p = argparse.ArgumentParser()
    p.add_argument("--db", default=os.environ.get("YIG_DB_PATH", "spectrum_data_ovn.sqlite"))
    p.add_argument("--retention-days", type=int, default=7)
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    log = logging.getLogger("cleanup")

    if not Path(args.db).exists():
        log.error("DB not found: %s", args.db)
        return 1

    cutoff = dt.datetime.now() - dt.timedelta(days=args.retention_days)
    conn = sqlite3.connect(args.db, detect_types=sqlite3.PARSE_DECLTYPES)
    try:
        n_before = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        n_to_delete = conn.execute(
            "SELECT count(*) FROM spectra WHERE time_created < ?",
            (cutoff,),
        ).fetchone()[0]
        log.info("DB has %d rows; %d older than %s", n_before, n_to_delete, cutoff)

        if args.dry_run:
            log.info("--dry-run: not deleting")
            return 0

        conn.execute("DELETE FROM spectra WHERE time_created < ?", (cutoff,))
        conn.commit()
        n_after = conn.execute("SELECT count(*) FROM spectra").fetchone()[0]
        log.info("deleted %d rows; now %d", n_before - n_after, n_after)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
