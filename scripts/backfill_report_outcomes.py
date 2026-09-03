"""一次性补齐 reports.outcome：
- 对所有 status=completed 报告：缺少 outcome 行 → 入队并评估；
- 已有 outcome 行但仍有未结算窗口 → 重新评估（直到 settled_count == total_windows，或 K 线无对应日期）。

用法：
    uv run python scripts/backfill_report_outcomes.py            # 全量
    uv run python scripts/backfill_report_outcomes.py --user <uid>  # 指定用户
    uv run python scripts/backfill_report_outcomes.py --task fast   # 仅快速分析
    uv run python scripts/backfill_report_outcomes.py --limit 500   # 限量
"""

from __future__ import annotations

import argparse
import time
from typing import Iterable

from dotenv import load_dotenv

load_dotenv()

from api.database import ReportDB, ReportOutcomeDB, get_db_ctx
from api.services import report_outcome_service


def _iter_target_report_ids(
    db,
    *,
    user_id: str | None,
    task_kind: str | None,
    limit: int | None,
) -> list[tuple[str, str]]:
    q = db.query(ReportDB.id, ReportDB.user_id).filter(ReportDB.status == "completed")
    if user_id:
        q = q.filter(ReportDB.user_id == str(user_id))
    q = q.order_by(ReportDB.created_at.desc())
    if limit and limit > 0:
        q = q.limit(int(limit))
    rows = q.all()

    if not task_kind:
        return [(str(rid), str(uid)) for rid, uid in rows]

    target_kind = task_kind
    pairs: list[tuple[str, str]] = []
    ids = [str(rid) for rid, _ in rows]
    tk_map = {}
    for chunk_start in range(0, len(ids), 500):
        chunk = ids[chunk_start : chunk_start + 500]
        if not chunk:
            continue
        from api.services.report_service import _load_effective_task_kind_map  # type: ignore[attr-defined]

        tk_map.update(_load_effective_task_kind_map(db, chunk))
    for rid, uid in rows:
        srid = str(rid)
        tk = tk_map.get(srid, "full_analysis")
        if target_kind == "full" and tk != "fast_analysis":
            pairs.append((srid, str(uid)))
        elif target_kind == "fast" and tk == "fast_analysis":
            pairs.append((srid, str(uid)))
    return pairs


def _backfill_one(db, report_id: str, user_id: str, *, force: bool = False) -> str:
    """返回简要状态：created/updated/skipped/error"""
    row = db.query(ReportOutcomeDB).filter(ReportOutcomeDB.id == report_id).first()
    if row is None:
        report = db.query(ReportDB).filter(ReportDB.id == report_id, ReportDB.user_id == user_id).first()
        if report is None:
            return "skipped"
        if str(report.status or "").strip() != "completed":
            return "skipped"
        report_outcome_service.enqueue_for_report(db, report)
        out = report_outcome_service.evaluate_report_outcome(db, report_id)
        if out is None:
            return "error"
        return "created" if int(out.settled_count or 0) > 0 or not (out.error or "") else "error"

    needs_eval = force or int(row.total_windows or 0) > int(row.settled_count or 0)
    if needs_eval:
        out = report_outcome_service.evaluate_report_outcome(db, report_id)
        if out is None:
            return "error"
        return "updated" if int(out.settled_count or 0) > 0 or not (out.error or "") else "error"
    return "skipped"


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill report outcomes for all completed reports.")
    parser.add_argument("--user", type=str, default=None, help="只处理指定 user_id；缺省全部")
    parser.add_argument(
        "--task",
        type=str,
        default=None,
        choices=["full", "fast"],
        help="仅处理 full（智能分析）或 fast（快速分析）；缺省全部",
    )
    parser.add_argument("--limit", type=int, default=0, help="最多处理 N 条；0 表示不限")
    parser.add_argument("--force", action="store_true", help="对已存在 outcome 行也强制重评（用于阈值/规则调整后回填）")
    args = parser.parse_args()

    started = time.perf_counter()
    counts = {"created": 0, "updated": 0, "skipped": 0, "error": 0}

    with get_db_ctx() as db:
        targets = _iter_target_report_ids(
            db,
            user_id=args.user,
            task_kind=args.task,
            limit=args.limit,
        )
        total = len(targets)
        print(f"[backfill] targets={total} user={args.user or '*'} task={args.task or '*'}")
        for idx, (rid, uid) in enumerate(targets, 1):
            try:
                status = _backfill_one(db, rid, uid, force=args.force)
            except Exception as exc:  # noqa: BLE001
                status = "error"
                print(f"[backfill] error rid={rid} err={type(exc).__name__}: {exc}")
            counts[status] = counts.get(status, 0) + 1
            if idx % 20 == 0 or idx == total:
                print(
                    f"[backfill] progress {idx}/{total} "
                    f"created={counts['created']} updated={counts['updated']} "
                    f"skipped={counts['skipped']} error={counts['error']}"
                )

    elapsed = time.perf_counter() - started
    print(
        f"[backfill] done elapsed={elapsed:.1f}s "
        f"created={counts['created']} updated={counts['updated']} "
        f"skipped={counts['skipped']} error={counts['error']}"
    )


if __name__ == "__main__":
    main()
