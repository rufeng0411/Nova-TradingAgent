"""IC / RankIC and stratified stability metrics."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd


def spearman_ic(factor: pd.Series, label: pd.Series) -> float | None:
    df = pd.DataFrame({"f": factor, "y": label}).dropna()
    if len(df) < 5:
        return None
    try:
        return float(df["f"].corr(df["y"], method="spearman"))
    except Exception:
        ranked = df.rank(method="average")
        return float(ranked["f"].corr(ranked["y"], method="pearson"))


def pearson_ic(factor: pd.Series, label: pd.Series) -> float | None:
    df = pd.DataFrame({"f": factor, "y": label}).dropna()
    if len(df) < 5:
        return None
    return float(df["f"].corr(df["y"], method="pearson"))


def compute_ic_metrics(
    panel: pd.DataFrame,
    *,
    factor_col: str,
    label_col: str,
    group_col: str | None = None,
) -> dict[str, Any]:
    if panel.empty or factor_col not in panel.columns or label_col not in panel.columns:
        return {"ic": None, "rank_ic": None, "sample_count": 0, "groups": []}

    base = panel[[factor_col, label_col] + ([group_col] if group_col and group_col in panel.columns else [])].copy()
    ic = pearson_ic(base[factor_col], base[label_col])
    rank_ic = spearman_ic(base[factor_col], base[label_col])
    out: dict[str, Any] = {
        "ic": ic,
        "rank_ic": rank_ic,
        "sample_count": int(base.dropna(subset=[factor_col, label_col]).shape[0]),
        "groups": [],
    }
    if group_col and group_col in base.columns:
        groups = []
        for key, g in base.groupby(group_col):
            if g.dropna(subset=[factor_col, label_col]).shape[0] < 5:
                continue
            groups.append(
                {
                    "key": str(key),
                    "ic": pearson_ic(g[factor_col], g[label_col]),
                    "rank_ic": spearman_ic(g[factor_col], g[label_col]),
                    "sample_count": int(g.dropna(subset=[factor_col, label_col]).shape[0]),
                }
            )
        out["groups"] = groups
        if groups:
            ics = [g["ic"] for g in groups if g.get("ic") is not None]
            out["ic_stability_std"] = float(np.std(ics)) if ics else None
    return out


def quintile_spread(panel: pd.DataFrame, *, factor_col: str, label_col: str) -> dict[str, Any]:
    df = panel[[factor_col, label_col]].dropna()
    if len(df) < 10:
        return {"top_quintile_mean": None, "bottom_quintile_mean": None, "spread": None}
    df = df.copy()
    df["q"] = pd.qcut(df[factor_col], 5, labels=False, duplicates="drop")
    top = df[df["q"] == df["q"].max()][label_col].mean()
    bottom = df[df["q"] == df["q"].min()][label_col].mean()
    spread = float(top - bottom) if top is not None and bottom is not None else None
    return {
        "top_quintile_mean": float(top) if top is not None else None,
        "bottom_quintile_mean": float(bottom) if bottom is not None else None,
        "spread": spread,
    }


def direction_hit_rate(
    panel: pd.DataFrame,
    *,
    signal_col: str,
    label_col: str,
    threshold: float = 0.0,
) -> dict[str, Any]:
    df = panel[[signal_col, label_col]].dropna()
    if df.empty:
        return {"hit_rate_pct": None, "sample_count": 0, "coverage_pct": None}
    long_mask = df[signal_col] > threshold
    short_mask = df[signal_col] < -threshold
    neutral_mask = ~(long_mask | short_mask)
    hits = 0.0
    for _, row in df.iterrows():
        sig = float(row[signal_col])
        ret = float(row[label_col])
        if sig > threshold and ret > 0:
            hits += 1
        elif sig < -threshold and ret < 0:
            hits += 1
        elif abs(sig) <= threshold and abs(ret) < 0.005:
            hits += 0.5
    denom = max(1, len(df) - int(neutral_mask.sum()))
    return {
        "hit_rate_pct": (hits / denom) * 100.0,
        "sample_count": int(len(df)),
        "coverage_pct": ((len(df) - int(neutral_mask.sum())) / max(1, len(df))) * 100.0,
    }
