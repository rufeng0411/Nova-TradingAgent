#!/usr/bin/env python3
"""QLIB worker: read inbox packages, train/evaluate, write outbox results.

Run in QLIB/ independent environment. Does not import main FastAPI app.
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

# Resolve repo root (parent of QLIB/)
REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tradingagents.qlib_eval.bridge.contract import (  # noqa: E402
    BridgePaths,
    InboxManifest,
    inbox_dir,
    outbox_dir,
    processing_dir,
    read_status,
    write_status,
)
from tradingagents.qlib_eval.config import bridge_root  # noqa: E402
from tradingagents.qlib_eval.metrics.ic import compute_ic_metrics, direction_hit_rate, quintile_spread  # noqa: E402
from tradingagents.qlib_eval.schema import all_feature_names  # noqa: E402


def _pick_features(df: pd.DataFrame) -> list[str]:
    cols = [c for c in all_feature_names() if c in df.columns]
    return [c for c in cols if df[c].notna().sum() >= max(3, int(len(df) * 0.05))]


def _run_experiment(panel: pd.DataFrame, label_col: str) -> dict:
    import numpy as np

    features = _pick_features(panel)
    if not features:
        return {"status": "failed", "error": "no_usable_features"}

    df = panel.dropna(subset=[label_col], how="any").copy()
    if len(df) < 10:
        return {"status": "failed", "error": "insufficient_samples", "sample_count": len(df)}

    df = df.sort_values("trade_date").reset_index(drop=True)
    split = max(1, int(len(df) * 0.75))
    train, test = df.iloc[:split], df.iloc[split:]
    if test.empty:
        test = train
        train = df.iloc[: max(1, len(df) // 2)]

    X_train = train[features].fillna(0.0)
    y_train = train[label_col].astype(float)
    X_test = test[features].fillna(0.0)

    backend = "numpy_linear"
    importances: dict[str, float] = {}
    try:
        import lightgbm as lgb

        reg = lgb.LGBMRegressor(n_estimators=60, learning_rate=0.05, random_state=42, verbose=-1)
        reg.fit(X_train, y_train)
        preds = reg.predict(X_test)
        backend = "lightgbm"
        importances = {f: float(v) for f, v in zip(features, reg.feature_importances_, strict=False)}
    except ImportError:
        weights = {}
        score = np.zeros(len(test))
        for col in features:
            try:
                ic = train[col].corr(train[label_col], method="pearson")
            except Exception:
                ranked = train[[col, label_col]].rank(method="average")
                ic = ranked[col].corr(ranked[label_col], method="pearson")
            w = float(ic) if ic is not None and not np.isnan(ic) else 0.0
            weights[col] = w
            std = float(train[col].std() or 1.0)
            score += w * (X_test[col].values / (std if std > 1e-9 else 1.0))
        preds = score
        importances = weights

    eval_df = test.copy()
    eval_df["pred"] = preds
    ic_m = compute_ic_metrics(eval_df, factor_col="pred", label_col=label_col)
    quint = quintile_spread(eval_df, factor_col="pred", label_col=label_col)
    hit = direction_hit_rate(eval_df, signal_col="pred", label_col=label_col)

    predictions = eval_df[["symbol", "trade_date", "pred", label_col]].copy()
    predictions.rename(columns={label_col: "label", "pred": "score"}, inplace=True)
    predictions["direction"] = predictions["score"].apply(
        lambda x: "bull" if float(x) > 0.002 else ("bear" if float(x) < -0.002 else "neutral")
    )

    return {
        "status": "ok",
        "backend": backend,
        "label_col": label_col,
        "train_samples": int(len(train)),
        "test_samples": int(len(test)),
        "ic": ic_m.get("ic"),
        "rank_ic": ic_m.get("rank_ic"),
        "hit_rate_pct": hit.get("hit_rate_pct"),
        "coverage_pct": hit.get("coverage_pct"),
        "quintile_spread": quint,
        "mean_prediction": float(eval_df["pred"].mean()) if not eval_df.empty else None,
        "feature_importance": importances,
        "predictions": predictions,
    }


def _build_summary(manifest: InboxManifest, result: dict, metrics: dict) -> str:
    lines = [
        f"# Qlib Worker 评估摘要 ({manifest.run_id})",
        "",
        f"- 版本：{manifest.release_version}",
        f"- 标签窗口：{manifest.label_horizon}",
        f"- 样本：{manifest.rows} 行 / {manifest.symbol_count} 标的",
        f"- 模型：{result.get('backend', 'unknown')}",
        f"- IC：{metrics.get('ic')}，RankIC：{metrics.get('rank_ic')}",
        f"- 命中率：{metrics.get('hit_rate_pct')}%（覆盖率 {metrics.get('coverage_pct')}%）",
        "",
        "本摘要供多 Agent 读取，请勿直接依赖原始大表做二次推导。",
    ]
    return "\n".join(lines)


def process_run(run_id: str, paths: BridgePaths) -> dict:
    in_path = inbox_dir(paths, run_id)
    if not in_path.exists():
        return {"run_id": run_id, "status": "failed", "error": "inbox_missing"}

    proc_path = processing_dir(paths, run_id)
    if proc_path.exists():
        shutil.rmtree(proc_path, ignore_errors=True)
    shutil.copytree(in_path, proc_path)
    write_status(proc_path / "status.json", "processing", run_id=run_id)

    manifest = InboxManifest.from_dict(json.loads((proc_path / "manifest.json").read_text(encoding="utf-8")))
    csv_path = proc_path / manifest.feature_panel_csv
    panel = pd.read_csv(csv_path)
    label_col = f"label_{manifest.label_horizon}"

    result = _run_experiment(panel, label_col)
    out_path = outbox_dir(paths, run_id)
    out_path.mkdir(parents=True, exist_ok=True)

    if result.get("status") != "ok":
        write_status(out_path / "status.json", "failed", error=result.get("error"))
        write_status(in_path / "status.json", "failed", error=result.get("error"))
        return {"run_id": run_id, "status": "failed", **result}

    predictions = result.pop("predictions")
    metrics = {k: v for k, v in result.items() if k not in ("feature_importance", "status")}
    model_card = {
        "backend": result.get("backend"),
        "label_horizon": manifest.label_horizon,
        "features": list((result.get("feature_importance") or {}).keys()),
        "feature_importance": result.get("feature_importance"),
        "train_samples": result.get("train_samples"),
        "test_samples": result.get("test_samples"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }

    (out_path / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_path / "model_card.json").write_text(json.dumps(model_card, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_path / "summary.md").write_text(_build_summary(manifest, result, metrics), encoding="utf-8")
    predictions.to_csv(out_path / "predictions.csv", index=False, encoding="utf-8-sig")
    write_status(out_path / "status.json", "completed", run_id=run_id)
    write_status(in_path / "status.json", "completed", run_id=run_id)

    shutil.rmtree(proc_path, ignore_errors=True)
    return {"run_id": run_id, "status": "completed", "outbox_dir": str(out_path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="QLIB file-queue worker")
    parser.add_argument("--once", action="store_true", help="Process one pending inbox job")
    parser.add_argument("--daemon", action="store_true", help="Poll inbox continuously")
    parser.add_argument("--poll-sec", type=float, default=5.0, help="Daemon poll interval")
    parser.add_argument("--run-id", default=None, help="Process specific run_id")
    parser.add_argument("--bridge-dir", default=None)
    args = parser.parse_args()

    root = Path(args.bridge_dir) if args.bridge_dir else bridge_root()
    paths = BridgePaths.from_root(root)
    paths.ensure()

    if args.daemon:
        import time

        heartbeat = paths.root / "worker_heartbeat.json"
        print(json.dumps({"message": "daemon_started", "bridge_dir": str(paths.root)}, ensure_ascii=False))
        while True:
            pending = []
            for child in sorted(paths.inbox.iterdir()):
                if not child.is_dir():
                    continue
                st = read_status(child / "status.json")
                if str(st.get("status") or "pending") == "pending":
                    pending.append(child.name)
            heartbeat.write_text(
                json.dumps(
                    {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "pending": len(pending),
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            if pending:
                out = process_run(pending[0], paths)
                print(json.dumps(out, ensure_ascii=False))
            time.sleep(max(args.poll_sec, 1.0))
        return 0

    if args.run_id:
        out = process_run(args.run_id, paths)
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0 if out.get("status") == "completed" else 1

    pending = []
    for child in sorted(paths.inbox.iterdir()):
        if not child.is_dir():
            continue
        st = read_status(child / "status.json")
        if str(st.get("status") or "pending") == "pending":
            pending.append(child.name)

    if not pending:
        print(json.dumps({"message": "no_pending_jobs"}, ensure_ascii=False))
        return 0

    run_id = pending[0] if args.once else pending[-1]
    if not args.once:
        results = [process_run(rid, paths) for rid in pending]
        print(json.dumps({"processed": len(results), "results": results}, ensure_ascii=False, indent=2))
        return 0 if all(r.get("status") == "completed" for r in results) else 1

    out = process_run(run_id, paths)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    return 0 if out.get("status") == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
