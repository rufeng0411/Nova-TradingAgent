#!/usr/bin/env python3
"""Import completed Qlib bridge outbox results into main system DB."""

from __future__ import annotations

import argparse
import json
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> int:
    parser = argparse.ArgumentParser(description="Import Qlib bridge outbox")
    parser.add_argument("--run-id", default=None, help="Specific run_id; default import all pending")
    args = parser.parse_args()

    from api.database import SessionLocal, init_db
    from api.services import qlib_eval_service

    init_db()
    db = SessionLocal()
    try:
        if args.run_id:
            result = qlib_eval_service.import_bridge_result(db, run_id=args.run_id)
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("imported") else 1
        result = qlib_eval_service.import_all_pending_outbox(db)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result.get("enabled") else 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
