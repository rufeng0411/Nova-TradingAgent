from __future__ import annotations

import argparse
import json
import os
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


@dataclass
class PairRecord:
    symbol: str
    trade_date: str
    arm: str  # on|off
    status: str  # pending|submitted|failed|skipped
    job_id: str | None = None
    detail: str | None = None


def _post_json(url: str, payload: dict[str, Any], token: str | None) -> dict[str, Any]:
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url=url, data=body, method="POST")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with request.urlopen(req, timeout=45) as resp:
        data = resp.read().decode("utf-8")
        return json.loads(data) if data else {}


def _load_pairs(path: Path) -> list[tuple[str, str]]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        symbol, trade_date = [x.strip() for x in line.split(",", 1)]
        rows.append((symbol, trade_date))
    return rows


def main() -> int:
    parser = argparse.ArgumentParser(description="Submit paired A/B translator analysis jobs with resume checkpoint.")
    parser.add_argument("--pairs", required=True, help="CSV text file: symbol,trade_date (one pair per line)")
    parser.add_argument("--base-url", default="http://127.0.0.1:8001", help="API base URL")
    parser.add_argument("--token", default=None, help="Bearer token; can also use TA_BATCH_TOKEN")
    parser.add_argument("--dry-run", action="store_true", help="Only generate/print tasks, no API submission")
    parser.add_argument("--checkpoint", default="logs/batch_ab_translator_progress.json", help="Checkpoint path")
    parser.add_argument("--sleep-ms", type=int, default=800, help="Sleep between submissions")
    args = parser.parse_args()

    pairs_file = Path(args.pairs)
    cp_path = Path(args.checkpoint)
    cp_path.parent.mkdir(parents=True, exist_ok=True)
    token = args.token or os.getenv("TA_BATCH_TOKEN")
    rows = _load_pairs(pairs_file)
    if not rows:
        raise SystemExit("pairs 文件为空")

    records: list[PairRecord] = []
    if cp_path.exists():
        try:
            old = json.loads(cp_path.read_text(encoding="utf-8"))
            for r in old.get("records", []):
                records.append(PairRecord(**r))
        except Exception:
            records = []
    done_key = {(r.symbol, r.trade_date, r.arm): r for r in records}
    for symbol, trade_date in rows:
        for arm in ("on", "off"):
            if (symbol, trade_date, arm) in done_key:
                continue
            records.append(PairRecord(symbol=symbol, trade_date=trade_date, arm=arm, status="pending"))

    submit_url = f"{args.base_url.rstrip('/')}/v1/analyze"
    for rec in records:
        if rec.status in {"submitted", "skipped"}:
            continue
        if args.dry_run:
            rec.status = "skipped"
            rec.detail = "dry-run"
            continue
        payload = {
            "symbol": rec.symbol,
            "trade_date": rec.trade_date,
            "selected_analysts": [
                "market",
                "sentiment",
                "news",
                "fundamentals",
                "smart_money",
                "volume_price",
            ],
            "config_overrides": {
                "env": {
                    "TA_TRANSLATOR_ENABLED": "1" if rec.arm == "on" else "0",
                }
            },
        }
        try:
            resp = _post_json(submit_url, payload, token)
            rec.job_id = str(resp.get("job_id") or "")
            rec.status = "submitted"
            rec.detail = str(resp.get("status") or "ok")
        except error.HTTPError as exc:
            rec.status = "failed"
            rec.detail = f"HTTP {exc.code}"
        except Exception as exc:  # pragma: no cover
            rec.status = "failed"
            rec.detail = f"{type(exc).__name__}: {exc}"

        cp_path.write_text(
            json.dumps(
                {
                    "generated_at": int(time.time()),
                    "base_url": args.base_url,
                    "records": [asdict(x) for x in records],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        time.sleep(max(0, args.sleep_ms) / 1000.0)

    submitted = len([r for r in records if r.status == "submitted"])
    failed = len([r for r in records if r.status == "failed"])
    print(json.dumps({"total": len(records), "submitted": submitted, "failed": failed, "checkpoint": str(cp_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
