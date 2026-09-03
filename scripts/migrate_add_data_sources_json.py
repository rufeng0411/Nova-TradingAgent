from __future__ import annotations

import os

from sqlalchemy import create_engine, text


DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./tradingagents.db")


def _has_column(conn) -> bool:
    if DATABASE_URL.startswith("sqlite"):
        rows = conn.execute(text("PRAGMA table_info(reports)")).fetchall()
        return any(str(row[1]) == "data_sources_json" for row in rows)
    if DATABASE_URL.startswith("mysql"):
        row = conn.execute(text("SHOW COLUMNS FROM reports LIKE 'data_sources_json'")).fetchone()
        return row is not None
    row = conn.execute(
        text(
            """
            SELECT 1
            FROM information_schema.columns
            WHERE table_name = 'reports' AND column_name = 'data_sources_json'
            LIMIT 1
            """
        )
    ).fetchone()
    return row is not None


def _alter_sql() -> str:
    if DATABASE_URL.startswith("sqlite"):
        return "ALTER TABLE reports ADD COLUMN data_sources_json TEXT"
    return "ALTER TABLE reports ADD COLUMN data_sources_json JSON NULL"


def main() -> None:
    engine = create_engine(DATABASE_URL)
    with engine.begin() as conn:
        if _has_column(conn):
            print("reports.data_sources_json already exists, skip")
            return
        conn.execute(text(_alter_sql()))
        print("added reports.data_sources_json")


if __name__ == "__main__":
    main()
