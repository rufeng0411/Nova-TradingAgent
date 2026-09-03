#!/usr/bin/env python3
"""Copy all application tables from SQLite to MySQL (schema + data).

Prerequisites:
  - Target MySQL database already exists (e.g. CREATE DATABASE tradingagents CHARACTER SET utf8mb4).
  - pip install pymysql
  - MySQL URL example:
      mysql+pymysql://USER:PASSWORD@127.0.0.1:3306/tradingagents?charset=utf8mb4

Usage (from repo root):
  python scripts/migrate_sqlite_to_mysql.py --from-url sqlite:///./tradingagents.db \\
      --to-url mysql+pymysql://root:pass@127.0.0.1:3306/tradingagents?charset=utf8mb4

After success, set DATABASE_URL in .env to the same MySQL URL and restart the API.
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

# Repo root = parent of scripts/
REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

try:
    from dotenv import load_dotenv

    load_dotenv(REPO_ROOT / ".env")
except ImportError:
    pass

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("migrate_sqlite_to_mysql")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--from-url",
        default=os.getenv("SQLITE_MIGRATE_SOURCE", "sqlite:///./tradingagents.db"),
        help="Source SQLite SQLAlchemy URL (default: ./tradingagents.db under cwd)",
    )
    parser.add_argument(
        "--to-url",
        default=os.getenv("MYSQL_MIGRATE_TARGET") or os.getenv("DATABASE_URL", ""),
        help="Target MySQL URL (or set MYSQL_MIGRATE_TARGET / DATABASE_URL to mysql+pymysql://...)",
    )
    parser.add_argument(
        "--no-truncate",
        action="store_true",
        help="Do not TRUNCATE target tables before copy (append / duplicate risk)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only print row counts, no writes to MySQL")
    parser.add_argument("--batch-size", type=int, default=500, help="Rows per INSERT batch")
    args = parser.parse_args()

    if not args.to_url or not args.to_url.startswith("mysql"):
        logger.error("Target must be MySQL. Pass --to-url mysql+pymysql://... or set MYSQL_MIGRATE_TARGET.")
        return 2

    os.chdir(REPO_ROOT)

    from sqlalchemy import create_engine, func, inspect, insert, select, text

    # Full module import registers all ORM tables on Base.metadata
    import api.database  # noqa: F401
    from api.database import Base

    src_engine = create_engine(
        args.from_url,
        connect_args={"check_same_thread": False},
        echo=False,
    )
    dst_engine = create_engine(
        args.to_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    try:
        insp = inspect(src_engine)
        names = insp.get_table_names()
    except Exception as e:
        logger.error("Cannot open SQLite source: %s", e)
        return 1

    if not names:
        logger.warning("Source SQLite has no tables (empty or new DB). Nothing to migrate.")
        return 0

    metadata = Base.metadata
    model_tables = {t.name for t in metadata.tables.values()}
    present = sorted(model_tables.intersection(names))
    missing_in_source = sorted(model_tables - set(names))
    if missing_in_source:
        logger.info("Tables defined in models but absent in SQLite (skipped): %s", ", ".join(missing_in_source))

    if args.dry_run:
        with src_engine.connect() as conn:
            for tname in present:
                tbl = metadata.tables[tname]
                n = conn.execute(select(func.count()).select_from(tbl)).scalar()
                logger.info("[dry-run] %s: %s rows", tname, int(n or 0))
        logger.info("Dry run complete; no changes to MySQL.")
        return 0

    # Create / update schema on MySQL
    try:
        metadata.create_all(dst_engine)
    except Exception as e:
        logger.error("Cannot connect or create schema on MySQL: %s", e)
        logger.error("Check host/port/user/password, database exists, and URL uses ?charset=utf8mb4")
        return 1

    if not args.no_truncate:
        with dst_engine.begin() as conn:
            conn.execute(text("SET FOREIGN_KEY_CHECKS=0"))
            for table in reversed(list(metadata.sorted_tables)):
                if table.name not in model_tables:
                    continue
                conn.execute(text(f"TRUNCATE TABLE `{table.name}`"))
            conn.execute(text("SET FOREIGN_KEY_CHECKS=1"))
        logger.info("Truncated all model tables on MySQL target.")

    # Copy in FK-friendly order (parents before children); fetch in chunks to limit memory
    order = [t for t in metadata.sorted_tables if t.name in present]
    batch_size = max(1, args.batch_size)

    total_rows = 0
    for table in order:
        tname = table.name
        ins = insert(table)
        copied = 0
        with src_engine.connect() as sconn:
            result = sconn.execution_options(stream_results=True).execute(select(table))
            while True:
                chunk = result.fetchmany(batch_size)
                if not chunk:
                    break
                dicts = [dict(r._mapping) for r in chunk]
                with dst_engine.begin() as dconn:
                    dconn.execute(ins, dicts)
                copied += len(dicts)
        if copied == 0:
            logger.info("%s: 0 rows (skip)", tname)
        else:
            logger.info("%s: copied %s rows", tname, copied)
        total_rows += copied

    # Fix AUTO_INCREMENT for integer PK tables when explicit ids were inserted
    with dst_engine.begin() as conn:
        for tname in ("job_events", "version_stats"):
            if tname not in present:
                continue
            mx = conn.execute(text(f"SELECT MAX(id) FROM `{tname}`")).scalar()
            if mx is not None:
                nxt = int(mx) + 1
                conn.execute(text(f"ALTER TABLE `{tname}` AUTO_INCREMENT = {nxt}"))
                logger.info("Set AUTO_INCREMENT on `%s` to %s", tname, nxt)

    logger.info("Done. Migrated %s rows from %s source tables.", total_rows, len(order))
    logger.info("Set DATABASE_URL in .env to your MySQL URL and restart the API.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
