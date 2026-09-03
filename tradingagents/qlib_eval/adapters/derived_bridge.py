"""Bridge result_data.derived_signals into qlib_eval feature snapshots."""

from __future__ import annotations

from typing import Any

from tradingagents.qlib_eval.schema import FeatureSnapshot, build_feature_snapshot


def from_result_data(
    *,
    symbol: str,
    trade_date: str,
    result_data: dict[str, Any] | None,
    marketdata_row: dict[str, Any] | None = None,
) -> FeatureSnapshot:
    payload = dict(result_data or {})
    derived = dict(payload.get("derived_signals") or {})
    intraday = {
        "intraday_vwap_dev": payload.get("intraday_vwap_dev"),
        "intraday_pos_in_range": payload.get("intraday_pos_in_range"),
        "relative_strength_vs_index": payload.get("relative_strength_vs_index"),
    }
    # Some collectors stash intraday feats only inside derived_signals context
    if not any(v is not None for v in intraday.values()):
        intraday = dict(payload.get("intraday_features") or {})
    return build_feature_snapshot(
        symbol=symbol,
        trade_date=trade_date,
        derived_signals=derived,
        intraday_features=intraday,
        marketdata_row=marketdata_row,
    )


def batch_from_reports(
    reports: list[dict[str, Any]],
    marketdata_by_key: dict[tuple[str, str], dict[str, Any]] | None = None,
) -> list[FeatureSnapshot]:
    md = marketdata_by_key or {}
    out: list[FeatureSnapshot] = []
    for r in reports:
        sym = str(r.get("symbol") or "").strip()
        td = str(r.get("trade_date") or r.get("created_at") or "")[:10]
        if not sym:
            continue
        md_row = md.get((sym, td))
        out.append(
            from_result_data(
                symbol=sym,
                trade_date=td,
                result_data=dict(r.get("result_data") or {}),
                marketdata_row=md_row,
            )
        )
    return out
