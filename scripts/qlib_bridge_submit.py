#!/usr/bin/env python3
"""Submit async Qlib bridge inbox job from main system."""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit Qlib bridge inbox job")
    parser.add_argument("--since-days", type=int, default=90)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--user-id", default=None)
    parser.add_argument("--label-horizon", default="t2")
    args = parser.parse_args()

    from api.database import SessionLocal, init_db
    from api.services import qlib_eval_service

    init_db()
    db = SessionLocal()
    try:
        result = qlib_eval_service.submit_bridge_job(
            db,
            user_id=args.user_id,
            since_days=args.since_days,
            limit=args.limit,
            label_horizon=args.label_horizon,
            created_by="cli",
        )
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("enabled") and result.get("status") == "queued" else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
