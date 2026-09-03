"""LightGBM baseline experiment (optional deps: lightgbm; qlib not required)."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd

from tradingagents.qlib_eval.metrics.ic import compute_ic_metrics, direction_hit_rate, quintile_spread
from tradingagents.qlib_eval.schema import all_feature_names


def _pick_features(df: pd.DataFrame) -> list[str]:
    cols = [c for c in all_feature_names() if c in df.columns]
    return [c for c in cols if df[c].notna().sum() >= max(5, int(len(df) * 0.05))]


def run_lightgbm_baseline(
    panel: pd.DataFrame,
    *,
    label_col: str = "label_t2",
    test_ratio: float = 0.25,
) -> dict[str, Any]:
    if panel.empty:
        return {"status": "empty", "error": "panel_empty"}

    features = _pick_features(panel)
    if not features:
        return {"status": "failed", "error": "no_usable_features"}

    df = panel.dropna(subset=[label_col], how="any").copy()
    if len(df) < 20:
        return {"status": "failed", "error": "insufficient_samples", "sample_count": len(df)}

    df = df.sort_values("trade_date").reset_index(drop=True)
    split_idx = max(1, int(len(df) * (1.0 - test_ratio)))
    train = df.iloc[:split_idx]
    test = df.iloc[split_idx:]
    if test.empty:
        test = train
        train = df.iloc[: max(1, len(df) // 2)]

    X_train = train[features].fillna(0.0)
    y_train = train[label_col].astype(float)
    X_test = test[features].fillna(0.0)
    y_test = test[label_col].astype(float)

    model_info: dict[str, Any] = {"backend": "numpy_mean", "features": features}
    predictions: pd.Series

    try:
        import lightgbm as lgb

        reg = lgb.LGBMRegressor(
            n_estimators=80,
            learning_rate=0.05,
            num_leaves=31,
            subsample=0.8,
            colsample_bytree=0.8,
            random_state=42,
            verbose=-1,
        )
        reg.fit(X_train, y_train)
        predictions = pd.Series(reg.predict(X_test), index=test.index)
        model_info["backend"] = "lightgbm"
        try:
            importances = dict(zip(features, [float(x) for x in reg.feature_importances_], strict=False))
            model_info["feature_importance"] = importances
        except Exception:
            pass
    except ImportError:
        # Fallback: simple z-scored linear combo
        weights = {}
        for col in features:
            ic = train[col].corr(train[label_col], method="spearman")
            weights[col] = float(ic) if ic is not None and not np.isnan(ic) else 0.0
        score = np.zeros(len(test))
        for col, w in weights.items():
            std = float(train[col].std() or 1.0)
            score += w * (X_test[col].values / (std if std > 1e-9 else 1.0))
        predictions = pd.Series(score, index=test.index)
        model_info["linear_weights"] = weights

    eval_df = test.copy()
    eval_df["pred"] = predictions.values

    ic_metrics = compute_ic_metrics(eval_df, factor_col="pred", label_col=label_col)
    quint = quintile_spread(eval_df, factor_col="pred", label_col=label_col)
    hit = direction_hit_rate(eval_df, signal_col="pred", label_col=label_col, threshold=0.0)

    return {
        "status": "ok",
        "model": model_info,
        "label_col": label_col,
        "train_samples": int(len(train)),
        "test_samples": int(len(test)),
        "ic": ic_metrics.get("ic"),
        "rank_ic": ic_metrics.get("rank_ic"),
        "quintile_spread": quint,
        "hit_rate_pct": hit.get("hit_rate_pct"),
        "coverage_pct": hit.get("coverage_pct"),
        "evaluated_at": datetime.now(timezone.utc).isoformat(),
    }


def try_init_qlib(provider_uri: str | None = None) -> dict[str, Any]:
    """Optional Qlib init helper; returns status without raising."""
    try:
        import qlib
        from qlib.config import REG_CN

        uri = provider_uri or "~/.qlib/qlib_data/cn_data"
        qlib.init(provider_uri=uri, region=REG_CN)
        return {"qlib_available": True, "provider_uri": uri}
    except ImportError:
        return {"qlib_available": False, "reason": "qlib_not_installed"}
    except Exception as exc:
        return {"qlib_available": False, "reason": str(exc)}


def save_baseline_result(result: dict[str, Any], path) -> None:
    from pathlib import Path

    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
