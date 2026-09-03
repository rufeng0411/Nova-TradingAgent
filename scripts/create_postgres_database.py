from __future__ import annotations

import argparse
import os

from sqlalchemy import create_engine, text


def _pg_url(db_name: str | None = None) -> str:
    host = os.getenv("TA_PG_HOST", "127.0.0.1")
    port = int(os.getenv("TA_PG_PORT", "5432") or "5432")
    user = os.getenv("TA_PG_USER", "postgres")
    password = os.getenv("TA_PG_PASSWORD", "")
    database = db_name or os.getenv("TA_PG_DATABASE", "postgres")
    return f"postgresql+psycopg://{user}:{password}@{host}:{port}/{database}"


def _ensure_database(admin_url: str, db_name: str) -> None:
    engine = create_engine(admin_url, isolation_level="AUTOCOMMIT")
    with engine.connect() as conn:
        exists = conn.execute(
            text("SELECT 1 FROM pg_database WHERE datname = :name"),
            {"name": db_name},
        ).scalar()
        if exists:
            print(f"[skip] database exists: {db_name}")
            return
        conn.execute(text(f'CREATE DATABASE "{db_name}" ENCODING \'UTF8\''))
        print(f"[ok] created database: {db_name}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Create Postgres databases for marketdata/langgraph.")
    parser.add_argument("--marketdata-db", default=os.getenv("TA_PG_MARKETDATA_DB", "tradingagents_marketdata"))
    parser.add_argument("--langgraph-db", default=os.getenv("TA_PG_LANGGRAPH_DB", "langgraph_checkpoint"))
    args = parser.parse_args()

    admin_url = _pg_url(os.getenv("TA_PG_ADMIN_DB", "postgres"))
    _ensure_database(admin_url, args.marketdata_db)
    _ensure_database(admin_url, args.langgraph_db)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
