from __future__ import annotations

import argparse
from datetime import datetime
from typing import Any

from dotenv import load_dotenv

from api.database import ReportDB, ReportOutcomeDB, get_db_ctx
from api.services.report_outcome_service import FAST_WEIGHTS, FULL_WEIGHTS


def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Sweep outcome threshold factor without writing DB.")
    p.add_argument("--since", type=str, default=None, help="YYYY-MM-DD")
    p.add_argument("--release", type=str, default=None, help="release_version filter")
    p.add_argument("--limit", type=int, default=500, help="max rows")
    return p.parse_args()


def _status_from_delta(direction: str, delta: float, threshold: float) -> str:
    if direction == "bull":
        if delta >= threshold:
            return "hit"
        if delta <= -threshold:
            return "miss"
        return "neutral"
    if direction == "bear":
        if delta <= -threshold:
            return "hit"
        if delta >= threshold:
            return "miss"
        return "neutral"
    return "hit" if abs(delta) < threshold else "miss"


def _direction(report: ReportDB) -> str:
    d = str(getattr(report, "direction", "") or "")
    dec = str(getattr(report, "decision", "") or "")
    text = f"{d}|{dec}".lower()
    if ("看多" in text) or ("偏多" in text) or ("buy" in text):
        return "bull"
    if ("看空" in text) or ("偏空" in text) or ("sell" in text):
        return "bear"
    return "neutral"


def _score(status: str) -> float:
    if status == "hit":
        return 1.0
    if status == "neutral":
        return 0.5
    return 0.0


def _weighted_for_factor(row: ReportOutcomeDB, direction: str, factor: float) -> float | None:
    outcomes = dict(row.outcomes_json or {})
    if not outcomes:
        return None
    # row.threshold 已不直接存储，这里从每个 horizon 的 delta 和 atr20/baseline 关系做比例缩放近似：
    # 使用原 status 对应阈值位于边界附近，乘以 factor 后重算命中/中性/失误。
    # 为保持 dry-run 简洁，这里采用 row.atr20 的线性近似阈值。
    baseline = float(row.baseline_price or 0.0)
    atr20 = float(row.atr20 or 0.0)
    base_threshold = max(1e-6, atr20 * 0.4) if atr20 > 0 else max(1e-6, baseline * 0.01)
    threshold = base_threshold * factor

    weights = FAST_WEIGHTS if row.task_kind == "fast_analysis" else FULL_WEIGHTS
    wsum = 0.0
    score_sum = 0.0
    for h, w in weights.items():
        cell = outcomes.get(h) or {}
        delta = cell.get("delta")
        if delta is None:
            continue
        status = _status_from_delta(direction, float(delta), threshold)
        score_sum += _score(status) * w
        wsum += w
    if wsum <= 0:
        return None
    return score_sum / wsum


def main() -> int:
    load_dotenv()
    args = _parse_args()
    since = datetime.fromisoformat(f"{args.since}T00:00:00+00:00") if args.since else None
    factors = [0.8, 1.0, 1.2]
    rows_count = 0
    bucket: dict[float, list[float]] = {f: [] for f in factors}

    with get_db_ctx() as db:
        oq = db.query(ReportOutcomeDB).order_by(ReportOutcomeDB.created_at.desc()).limit(max(1, args.limit))
        if since is not None:
            oq = oq.filter(ReportOutcomeDB.created_at >= since)
        if args.release:
            oq = oq.filter(ReportOutcomeDB.release_version == args.release)
        outcomes = oq.all()
        report_map = {
            r.id: r
            for r in db.query(ReportDB)
            .filter(ReportDB.id.in_([x.id for x in outcomes]))
            .all()
        }
        for row in outcomes:
            report = report_map.get(row.id)
            if report is None:
                continue
            direction = _direction(report)
            rows_count += 1
            for f in factors:
                v = _weighted_for_factor(row, direction, f)
                if v is not None:
                    bucket[f].append(v)

    print("| factor | weighted_hit_rate | sample_count |")
    print("|---:|---:|---:|")
    best_f = 1.0
    best_v = -1.0
    for f in factors:
        vals = bucket[f]
        avg = (sum(vals) / len(vals)) if vals else 0.0
        print(f"| {f:.1f} | {avg:.4f} | {len(vals)} |")
        if avg > best_v:
            best_v = avg
            best_f = f
    print(f"\n建议写入 .env.example 注释：TA_REPORT_OUTCOME_THRESHOLD_FACTOR={best_f:.1f}")
    print(f"扫描样本：{rows_count}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

