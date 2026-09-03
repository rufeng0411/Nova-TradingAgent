from __future__ import annotations

import argparse
import json
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import load_only

from api.database import ReportDB, ReportOutcomeDB, get_db_ctx
from api.services.report_outcome_service import FAST_WEIGHTS, FULL_WEIGHTS


KEYWORDS: dict[str, list[str]] = {
    "stk_factor_pro": ["vol_ratio", "turnover_rate_f", "pe_ttm", "dv_ratio", "pb", "ps_ttm"],
    "moneyflow_dc": ["主力净流入", "net_mf_amount", "buy_lg_amount", "sell_lg_amount"],
    "top_list": ["龙虎榜", "机构净买", "top_list"],
    "limit_list_d": ["涨停", "封板", "炸板", "limit_list"],
    "l2_orderqueue": ["委托队列", "orderqueue", "l2"],
    "orderbook_pressure_signal_v1": ["卖三档", "卖五档", "上方挂单", "承接力", "卖压"],
    "active_buy_proxy_v1": ["主动买入", "大单占比", "净流入占比", "买盘主导", "资金净流入"],
    "moneyflow_structure_v1": ["主力净流入", "行业资金", "梯队", "龙虎榜", "机构净买"],
    "financial_health_v1": ["健康度", "行业分位", "ROE", "毛利率", "现金流质量"],
    "auction_intraday_strength_v1": ["抢筹", "9:20", "9:25", "竞价激增", "尾盘竞价"],
}


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Audit provenance + weighted hit rate.")
    p.add_argument("--since", type=str, default=None, help="Start date, format YYYY-MM-DD")
    p.add_argument("--release", type=str, default=None, help="Filter release_version")
    p.add_argument("--limit", type=int, default=300, help="Max reports to scan")
    p.add_argument("--json", action="store_true", help="Print JSON payload")
    return p.parse_args()


def _to_dt(s: str | None) -> datetime | None:
    if not s:
        return None
    return datetime.fromisoformat(f"{s}T00:00:00+00:00")


def _weighted_from_outcome(row: ReportOutcomeDB | None) -> float | None:
    if row is None:
        return None
    outcomes = dict(row.outcomes_json or {})
    weights = FAST_WEIGHTS if row.task_kind == "fast_analysis" else FULL_WEIGHTS
    score = 0.0
    wsum = 0.0
    for h, w in weights.items():
        status = str((outcomes.get(h) or {}).get("status") or "pending")
        if status == "hit":
            s = 1.0
        elif status == "neutral":
            s = 0.5
        elif status == "miss":
            s = 0.0
        else:
            continue
        score += s * w
        wsum += w
    return (score / wsum) if wsum > 0 else None


def main() -> int:
    load_dotenv()
    args = _parse_args()
    since = _to_dt(args.since)

    per_method: dict[str, dict[str, Any]] = defaultdict(
        lambda: {
            "total": 0,
            "report_total": 0,
            "hit": 0,
            "empty": 0,
            "failed": 0,
            "unsupported": 0,
            "llm_ref_report_hits": 0,
            "weighted_values": [],
        }
    )

    with get_db_ctx() as db:
        q = (
            db.query(ReportDB)
            .options(
                load_only(
                    ReportDB.id,
                    ReportDB.created_at,
                    ReportDB.data_sources_json,
                    ReportDB.market_report,
                    ReportDB.sentiment_report,
                    ReportDB.fundamentals_report,
                    ReportDB.volume_price_report,
                    ReportDB.final_decision_summary,
                )
            )
            .filter(ReportDB.status == "completed")
            .order_by(ReportDB.created_at.desc())
        )
        if since is not None:
            q = q.filter(ReportDB.created_at >= since)
        if args.release:
            try:
                q_try = q.filter(ReportDB.release_version == args.release)
                rows = q_try.limit(max(1, args.limit)).all()
            except OperationalError:
                rows = q.limit(max(1, args.limit)).all()
        else:
            rows = q.limit(max(1, args.limit)).all()

        try:
            outcome_rows = (
                db.query(ReportOutcomeDB)
                .filter(ReportOutcomeDB.id.in_([x.id for x in rows]))
                .all()
            )
        except OperationalError:
            outcome_rows = []
        outcome_map = {r.id: r for r in outcome_rows}

        for r in rows:
            bundle = dict(getattr(r, "data_sources_json", None) or {})
            items = list(bundle.get("items") or [])
            report_text = "\n".join(
                [
                    str(getattr(r, "market_report", "") or ""),
                    str(getattr(r, "sentiment_report", "") or ""),
                    str(getattr(r, "fundamentals_report", "") or ""),
                    str(getattr(r, "volume_price_report", "") or ""),
                    str(getattr(r, "final_decision_summary", "") or ""),
                ]
            ).lower()
            weighted = _weighted_from_outcome(outcome_map.get(r.id))
            methods_in_report: set[str] = set()

            for item in items:
                method = str(item.get("method") or item.get("key") or "unknown")
                status = str(item.get("status") or "")
                preview = str(item.get("detail_preview") or "").strip()
                stat = per_method[method]
                methods_in_report.add(method)
                stat["total"] += 1
                if status in {"hit", "fallback"}:
                    stat["hit"] += 1
                    if not preview or preview in {"[]", "{}", "无预览"}:
                        stat["empty"] += 1
                elif status in {"unsupported_channel"}:
                    stat["unsupported"] += 1
                elif status in {"error", "failed", "unavailable", "timeout"}:
                    stat["failed"] += 1
                if weighted is not None:
                    stat["weighted_values"].append(weighted)
            for method in methods_in_report:
                stat = per_method[method]
                stat["report_total"] += 1
                kws = KEYWORDS.get(method, [])
                if kws and any(k.lower() in report_text for k in kws):
                    stat["llm_ref_report_hits"] += 1

    items_out: list[dict[str, Any]] = []
    for method, x in sorted(per_method.items()):
        report_total = max(1, int(x["report_total"] or 0))
        weighted_vals: list[float] = list(x["weighted_values"])
        items_out.append(
            {
                "method": method,
                "total": int(x["total"]),
                "report_total": int(x["report_total"]),
                "hit": int(x["hit"]),
                "empty": int(x["empty"]),
                "failed": int(x["failed"]),
                "unsupported": int(x["unsupported"]),
                "llm_ref_rate": round(float(x["llm_ref_report_hits"]) / report_total, 4),
                "weighted_hit_rate": round(sum(weighted_vals) / len(weighted_vals), 4) if weighted_vals else None,
            }
        )

    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "since": args.since,
        "release": args.release,
        "count_methods": len(items_out),
        "items": items_out,
    }
    Path("logs").mkdir(parents=True, exist_ok=True)
    out_path = Path("logs") / f"audit_provenance_{datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')}.json"
    out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    if args.json:
        print(json.dumps(payload, ensure_ascii=False))
    else:
        print("| method | total | report_total | hit | empty | failed | unsupported | llm_ref_rate | weighted_hit_rate |")
        print("|---|---:|---:|---:|---:|---:|---:|---:|---:|")
        for row in items_out:
            wr = "n/a" if row["weighted_hit_rate"] is None else f"{row['weighted_hit_rate']:.4f}"
            print(
                f"| {row['method']} | {row['total']} | {row['report_total']} | {row['hit']} | {row['empty']} | "
                f"{row['failed']} | {row['unsupported']} | {row['llm_ref_rate']:.4f} | {wr} |"
            )
        print(f"\n写入：{out_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

