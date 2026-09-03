from __future__ import annotations

import argparse

from dotenv import load_dotenv

load_dotenv()

from api.database import get_db_ctx
from api.services import admin_metrics_service


def main() -> None:
    parser = argparse.ArgumentParser(description="Roll up admin daily metrics.")
    parser.add_argument("--days", type=int, default=32, help="回填近 N 天，默认 32")
    args = parser.parse_args()

    days = max(1, min(args.days, 365))
    with get_db_ctx() as db:
        admin_metrics_service.rollup_recent_days(db, days=days)
    print(f"[admin-rollup] done days={days}")


if __name__ == "__main__":
    main()
