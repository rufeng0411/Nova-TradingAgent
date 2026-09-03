"""dump 最新 1 条带 provenance 的报告：volume_price_report / market_report / smart_money_report 全文。"""
from __future__ import annotations
from sqlalchemy.orm import load_only
from dotenv import load_dotenv
load_dotenv()
from api.database import ReportDB, get_db_ctx

with get_db_ctx() as db:
    rows = (
        db.query(ReportDB)
        .options(load_only(
            ReportDB.id, ReportDB.symbol, ReportDB.created_at,
            ReportDB.data_sources_json, ReportDB.volume_price_report,
            ReportDB.market_report, ReportDB.smart_money_report,
            ReportDB.final_decision_summary, ReportDB.direction,
        ))
        .filter(ReportDB.status == "completed")
        .limit(400)
        .all()
    )
    rows = [r for r in rows if isinstance(r.data_sources_json, dict) and r.data_sources_json]
    rows.sort(key=lambda r: r.created_at or "", reverse=True)
    if not rows:
        print("none")
        raise SystemExit(0)
    candidates = [r for r in rows if (r.volume_price_report or "").strip()]
    r = candidates[0] if candidates else rows[0]
    print(f"id={r.id} symbol={r.symbol} created_at={r.created_at}")
    print(f"direction={r.direction!r}")
    print()
    print("=== final_decision_summary ===")
    print((r.final_decision_summary or "")[:600])
    print()
    print("=== volume_price_report (1500 chars) ===")
    print((r.volume_price_report or "")[:1500])
    print()
    print("=== smart_money_report (1500 chars) ===")
    print((r.smart_money_report or "")[:1500])
    print()
    print("=== market_report (head 1200) ===")
    print((r.market_report or "")[:1200])
