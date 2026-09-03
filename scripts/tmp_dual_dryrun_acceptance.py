from __future__ import annotations

import json
import os
import urllib.request


def _json_request(url: str, token: str, payload: dict | None = None) -> dict:
    data = None
    method = "GET"
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        method = "POST"
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    raw = urllib.request.urlopen(req, timeout=300).read().decode("utf-8")
    return json.loads(raw) if raw else {}


def main() -> int:
    token = os.getenv("TA_BATCH_TOKEN", "").strip()
    if not token:
        raise SystemExit("TA_BATCH_TOKEN is empty")

    base = "http://127.0.0.1:8001"
    pairs = [("600519.SH", "2026-05-16"), ("516150.SH", "2026-05-16")]
    runs: list[dict] = []

    for symbol, trade_date in pairs:
        for arm, enabled in (("on", "1"), ("off", "0")):
            payload = {
                "symbol": symbol,
                "trade_date": trade_date,
                "dry_run": True,
                "config_overrides": {
                    "env": {
                        "TA_TRANSLATOR_ENABLED": enabled,
                        "TA_TUSHARE_AUCTION_OC_ENABLED": "1",
                    }
                },
            }
            resp = _json_request(f"{base}/v1/analyze", token, payload)
            runs.append(
                {
                    "symbol": symbol,
                    "trade_date": trade_date,
                    "arm": arm,
                    "job_id": resp.get("job_id"),
                    "status": resp.get("status"),
                }
            )

    summary: list[dict] = []
    for run in runs:
        job_id = str(run["job_id"])
        result = _json_request(f"{base}/v1/jobs/{job_id}/result", token)
        payload = (result or {}).get("result_data") or (result or {}).get("result") or {}
        derived_signals = (payload or {}).get("derived_signals") or {}
        data_sources = (payload or {}).get("data_sources") or {}
        summary.append(
            {
                **run,
                "result_status": (result or {}).get("status"),
                "derived_count": len(derived_signals),
                "derived_keys": sorted(list(derived_signals.keys())),
                "data_sources_items": len((data_sources.get("items") or [])),
            }
        )

    out = {"runs": runs, "summary": summary}
    out_path = "logs/dual_samples_dryrun_results.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
