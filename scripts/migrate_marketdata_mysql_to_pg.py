from __future__ import annotations

import argparse
from typing import Iterable

from sqlalchemy import MetaData, Table, create_engine, select, text


DEFAULT_TABLES = [
    "marketdata_daily_bar",
    "marketdata_north_money",
    "marketdata_company_basic",
    "marketdata_financial_report",
    "marketdata_disclosure",
    "marketdata_macro_indicator",
    "marketdata_vendor_call_log",
    "marketdata_recon_anomaly",
]


def _stream_rows(conn, table: Table, batch_size: int) -> Iterable[list[dict]]:
    result = conn.execution_options(stream_results=True).execute(select(table))
    while True:
        batch = result.fetchmany(batch_size)
        if not batch:
            break
        yield [dict(row._mapping) for row in batch]


def migrate(mysql_url: str, pg_url: str, tables: list[str], batch_size: int, truncate: bool) -> None:
    mysql_engine = create_engine(mysql_url)
    pg_engine = create_engine(pg_url)

    src_md = MetaData()
    dst_md = MetaData()
    src_md.reflect(bind=mysql_engine, only=tables)
    dst_md.reflect(bind=pg_engine, only=tables)

    with mysql_engine.connect() as src, pg_engine.begin() as dst:
        for name in tables:
            if name not in src_md.tables:
                print(f"[skip] source table missing: {name}")
                continue
            if name not in dst_md.tables:
                print(f"[skip] target table missing: {name}")
                continue

            src_table = src_md.tables[name]
            dst_table = dst_md.tables[name]
            if truncate:
                dst.execute(text(f'TRUNCATE TABLE "{name}" RESTART IDENTITY'))
            inserted = 0
            for rows in _stream_rows(src, src_table, batch_size):
                if not rows:
                    continue
                dst.execute(dst_table.insert(), rows)
                inserted += len(rows)
            print(f"[ok] migrated {name}: {inserted} rows")


def main() -> int:
    parser = argparse.ArgumentParser(description="Migrate marketdata_* tables from MySQL to PostgreSQL.")
    parser.add_argument("--mysql-url", required=True)
    parser.add_argument("--pg-url", required=True)
    parser.add_argument("--batch-size", type=int, default=1000)
    parser.add_argument("--no-truncate", action="store_true")
    parser.add_argument("--tables", default=",".join(DEFAULT_TABLES))
    args = parser.parse_args()

    tables = [x.strip() for x in args.tables.split(",") if x.strip()]
    migrate(args.mysql_url, args.pg_url, tables, args.batch_size, truncate=not args.no_truncate)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
