from __future__ import annotations

import json
from typing import Any
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

from api.database import ReportDB, get_db_ctx
from tradingagents.dataflows.data_source_catalog import enrich_data_source_item
from tradingagents.dataflows.interface import route_to_vendor_with_meta


def _as_dict(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            if isinstance(parsed, dict):
                return parsed
        except Exception:
            return None
    return None


def _patch_bundle(bundle: dict[str, Any], symbol: str) -> tuple[dict[str, Any], bool]:
    items = bundle.get("items")
    if not isinstance(items, list):
        return bundle, False

    changed = False
    for idx, item in enumerate(items):
        if not isinstance(item, dict):
            continue
        if item.get("key") != "insider_transactions":
            continue
        err = str(item.get("error") or "")
        if "unexpected keyword argument 'ticker'" not in err:
            continue

        _value, meta = route_to_vendor_with_meta("get_insider_transactions", symbol=symbol)
        enriched = enrich_data_source_item("insider_transactions", meta)
        items[idx] = enriched
        changed = True

    bundle["items"] = items
    return bundle, changed


def main() -> None:
    total_reports = 0
    patched_reports = 0
    patched_items = 0

    with get_db_ctx() as db:
        rows = db.query(ReportDB).all()
        total_reports = len(rows)

        for row in rows:
            bundle = _as_dict(row.data_sources_json)
            result_data = _as_dict(row.result_data)
            if bundle is None and isinstance(result_data, dict):
                bundle = _as_dict(result_data.get("data_sources"))
            if bundle is None:
                continue

            before = json.dumps(bundle, ensure_ascii=False, sort_keys=True)
            patched_bundle, changed = _patch_bundle(bundle, symbol=row.symbol)
            if not changed:
                continue

            after = json.dumps(patched_bundle, ensure_ascii=False, sort_keys=True)
            if before == after:
                continue

            row.data_sources_json = patched_bundle
            if isinstance(result_data, dict):
                result_data["data_sources"] = patched_bundle
                row.result_data = result_data
            patched_reports += 1
            patched_items += 1

        if patched_reports:
            db.commit()

    print(
        f"backfill done: total_reports={total_reports}, "
        f"patched_reports={patched_reports}, patched_items={patched_items}"
    )


if __name__ == "__main__":
    main()
