"""
Technical analysis features extracted from OHLCV series (numpy/pandas).
Used by chart insight API for structured prompts and LLM-failure fallback.
"""

from __future__ import annotations

from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd


def _ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def _sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=window).mean()


def candles_to_df(candles: List[Dict[str, Any]]) -> pd.DataFrame:
    if not candles:
        return pd.DataFrame()
    df = pd.DataFrame(candles)
    if "date" not in df.columns:
        return pd.DataFrame()
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"]).sort_values("date")
    for col in ("open", "high", "low", "close", "volume"):
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    return df.dropna(subset=["open", "high", "low", "close"]).reset_index(drop=True)


def cluster_levels(prices: np.ndarray, bins: int = 12) -> Tuple[List[float], List[float]]:
    """Rough support / resistance from price histogram peaks."""
    if len(prices) < 5:
        return [], []
    lo, hi = float(np.min(prices)), float(np.max(prices))
    if hi <= lo:
        return [], []
    hist, edges = np.histogram(prices, bins=bins, range=(lo, hi))
    idx = np.argsort(hist)[::-1][:3]
    centers = (edges[:-1] + edges[1:]) / 2
    levels = sorted({float(round(centers[i], 2)) for i in idx})
    mid = (lo + hi) / 2
    supports = sorted([x for x in levels if x <= mid])[-2:]
    resistances = sorted([x for x in levels if x >= mid])[:2]
    return supports, resistances


def detect_ma_alignment(close: pd.Series, ma_short: pd.Series, ma_long: pd.Series) -> str:
    if ma_short.isna().iloc[-1] or ma_long.isna().iloc[-1]:
        return "unknown"
    if ma_short.iloc[-1] > ma_long.iloc[-1]:
        return "bullish_stack"
    if ma_short.iloc[-1] < ma_long.iloc[-1]:
        return "bearish_stack"
    return "neutral"


def _rsi_last(close: pd.Series, period: int = 14) -> float | None:
    if len(close) < period + 2:
        return None
    delta = close.diff()
    up = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    roll_up = up.ewm(alpha=1.0 / period, adjust=False).mean()
    roll_down = down.ewm(alpha=1.0 / period, adjust=False).mean()
    rs = roll_up / roll_down.replace(0, np.nan)
    rsi = 100 - (100 / (1 + rs))
    v = rsi.iloc[-1]
    if pd.isna(v):
        return None
    return float(round(float(v), 2))


def extract_features(candles: List[Dict[str, Any]], *, level: str = "normal") -> Dict[str, Any]:
    df = candles_to_df(candles)
    if df.empty or len(df) < 5:
        return {"error": "insufficient_data", "bars": len(df), "insight_level": (level or "normal").strip().lower()}

    close = df["close"]
    high = df["high"]
    low = df["low"]
    vol = df["volume"] if "volume" in df.columns else pd.Series(np.nan, index=df.index)

    ret = close.pct_change()
    total_ret = float((close.iloc[-1] / close.iloc[0] - 1) * 100) if close.iloc[0] else 0.0
    max_dd = float((close / close.cummax() - 1).min() * 100)
    vol_pct = float(ret.std() * np.sqrt(252) * 100) if len(ret.dropna()) > 2 else 0.0

    ma5 = _sma(close, 5)
    ma10 = _sma(close, 10)
    ma20 = _sma(close, 20)
    ma60 = _sma(close, 60)

    alignment = detect_ma_alignment(close, ma20, ma60)

    macd_line = _ema(close, 12) - _ema(close, 26)
    signal = _ema(macd_line, 9)
    hist = macd_line - signal
    cross_up = False
    cross_down = False
    if len(hist) > 2 and hist.notna().iloc[-1] and hist.notna().iloc[-2]:
        cross_up = hist.iloc[-2] <= 0 < hist.iloc[-1]
        cross_down = hist.iloc[-2] >= 0 > hist.iloc[-1]

    period_high = float(high.tail(20).max())
    period_low = float(low.tail(20).min())
    supports, resistances = cluster_levels(close.tail(60).values)

    recent_window = df.tail(20)
    pattern_guess = "none"
    if len(recent_window) >= 10:
        hh = float(recent_window["high"].max())
        ll = float(recent_window["low"].min())
        first_half = recent_window.iloc[: len(recent_window) // 2]
        second_half = recent_window.iloc[len(recent_window) // 2 :]
        if float(first_half["high"].max()) > float(second_half["high"].max()) * 1.01:
            pattern_guess = "possible_distribution"
        elif float(second_half["low"].min()) > float(first_half["low"].min()) * 1.01:
            pattern_guess = "possible_accumulation"

    vol_ma = _sma(vol.fillna(0), 5)
    vol_spike = False
    if vol.notna().any() and vol_ma.notna().iloc[-1] and vol.iloc[-1] > 0:
        vol_spike = float(vol.iloc[-1]) > float(vol_ma.iloc[-1]) * 1.5

    lv = (level or "normal").strip().lower()
    if lv not in ("brief", "normal", "deep"):
        lv = "normal"
    bar_tail = 10 if lv == "brief" else 90 if lv == "deep" else 40
    tail = df.tail(bar_tail)[["date", "open", "high", "low", "close"]].copy()
    tail["date"] = tail["date"].dt.strftime("%Y-%m-%d")
    recent_bars = tail.to_dict(orient="records")

    # 基础派生特征：跨档位都有用（用于盘中 fast_analysis 特征槽位、kline_insight fallback）
    close_vs_ma20_pct: float | None = None
    if ma20.notna().iloc[-1] and close.iloc[-1] > 0 and float(ma20.iloc[-1]) > 0:
        close_vs_ma20_pct = round((float(close.iloc[-1]) / float(ma20.iloc[-1]) - 1) * 100, 3)

    out: Dict[str, Any] = {
        "insight_level": lv,
        "bars": len(df),
        "last_date": str(df["date"].iloc[-1].date()),
        "total_return_pct": round(total_ret, 2),
        "max_drawdown_pct": round(max_dd, 2),
        "annualized_vol_pct": round(vol_pct, 2),
        "ma_alignment": alignment,
        "last_close": float(close.iloc[-1]),
        "period_high_20": period_high,
        "period_low_20": period_low,
        "macd_cross_up": cross_up,
        "macd_cross_down": cross_down,
        "volume_spike": vol_spike,
        "pattern_guess": pattern_guess,
        "supports": supports,
        "resistances": resistances,
        "recent_bars": recent_bars,
        "close_vs_ma20_pct": close_vs_ma20_pct,
    }
    if lv == "deep":
        rsi = _rsi_last(close, 14)
        if rsi is not None:
            out["rsi14_last"] = rsi
        vma20 = _sma(vol.fillna(0), 20)
        if vol.notna().any() and vma20.notna().iloc[-1] and float(vma20.iloc[-1]) > 0:
            out["volume_vs_ma20_ratio"] = round(float(vol.iloc[-1]) / float(vma20.iloc[-1]), 3)
        ch = float(high.tail(20).max()) if len(high) >= 5 else None
        if ch and float(close.iloc[-1]) > 0:
            out["drawdown_from_20d_high_pct"] = round((float(close.iloc[-1]) / ch - 1) * 100, 3)
    return out


def build_fallback_insight(features: Dict[str, Any], symbol: str, *, level: str = "normal") -> Dict[str, Any]:
    """Deterministic insight when LLM is unavailable."""
    lv = (level or "normal").strip().lower()
    if lv not in ("brief", "normal", "deep"):
        lv = "normal"

    if features.get("error") == "insufficient_data":
        summary = f"{symbol} 数据不足，无法计算技术指标。"
        bias = "neutral"
        conf = 0.2
    else:
        align = features.get("ma_alignment", "neutral")
        tr = features.get("total_return_pct", 0)
        bias = "bullish" if align == "bullish_stack" and tr > 0 else "bearish" if align == "bearish_stack" and tr < 0 else "neutral"
        conf = 0.45
        summary = (
            f"{symbol} 近区间涨跌约 {tr:.2f}%，均线排列为 {align}。"
            f"近20日高 {features.get('period_high_20')} / 低 {features.get('period_low_20')}。"
            "以上为本地规则摘要，非投资建议。"
        )
        if lv == "brief":
            summary = f"{symbol} 区间涨跌约 {tr:.2f}%，均线{align}。非投资建议。"
        elif lv == "deep":
            rsi_note = ""
            r = features.get("rsi14_last")
            if r is not None:
                rsi_note = f" RSI(14)≈{r}。"
            summary = (
                f"{symbol} 区间收益约 {tr:.2f}%，均线 {align}；"
                f"近20日高 {features.get('period_high_20')} / 低 {features.get('period_low_20')}。{rsi_note}"
                "请核对量价与均线是否同向；以下为本地摘要，非投资建议。"
            )

    def sec(title: str, points: List[str], hint: str) -> Dict[str, Any]:
        return {"title": title, "points": points, "novice_hint": hint}

    mom_pts = [
        "MACD 柱转正" if features.get("macd_cross_up") else "MACD 柱转负" if features.get("macd_cross_down") else "MACD 无明显交叉信号",
    ]
    if lv == "deep" and features.get("rsi14_last") is not None:
        mom_pts.append(f"RSI(14) 约 {features['rsi14_last']}，仅作超买超卖参考。")

    sr_pts = [
        f"参考支撑：{features.get('supports', [])}",
        f"参考压力：{features.get('resistances', [])}",
    ]
    if lv == "brief":
        sr_pts = [f"支撑 {features.get('supports', [])} / 压力 {features.get('resistances', [])}"]

    glossary: Dict[str, str] = {
        "MACD": "快慢均线之差，用于观察动能。",
        "均线": "过去若干天收盘价的平均值，平滑短期波动。",
        "成交量": "一段时间内成交的股票数量。",
    }
    if lv == "deep":
        glossary.update(
            {
                "RSI": "衡量涨跌强弱相对幅度，极端值常引发回调关注。",
                "KDJ": "短线超买超卖类指标，震荡市参考意义更强。",
                "支撑": "价格下跌时买盘相对集中的区域（技术含义）。",
                "压力": "价格上涨时卖盘相对集中的区域（技术含义）。",
                "波动率": "价格起伏剧烈程度的度量。",
                "形态": "K 线组合形成的粗糙结构判断，易误判需谨慎。",
            }
        )

    risks_brief = ["市场波动与政策风险"]
    risks_norm = ["市场波动与政策风险", "技术指标滞后"]
    risks_deep = risks_norm + ["单一指标可能失效", "情景推演不等于预测"]

    risks = risks_brief if lv == "brief" else risks_deep if lv == "deep" else risks_norm
    opps: List[str] = [] if lv == "brief" else ["观察均线与量能是否同向"] if lv == "normal" else ["观察均线与量能是否同向", "关注关键位附近的多空换手"]

    return {
        "summary_plain": summary,
        "bias": bias,
        "bias_confidence": conf,
        "sections": {
            "trend": sec("趋势", [f"区间收益约 {features.get('total_return_pct', 0)}%"], "趋势看价格整体往哪边移动。"),
            "moving_average": sec(
                "均线",
                [f"MA 排列信号：{features.get('ma_alignment', 'unknown')}"],
                "短均线在长均线上方常被视为多头格局（非绝对）。",
            ),
            "volume": sec(
                "量能",
                ["近期放量" if features.get("volume_spike") else "量能平稳"],
                "放量表示当日成交更活跃。",
            ),
            "momentum": sec(
                "动量",
                mom_pts,
                "MACD 反映涨跌动能的变化。",
            ),
            "volatility": sec(
                "波动",
                [f"估算年化波动约 {features.get('annualized_vol_pct', 0)}%"],
                "波动越大，价格起伏越剧烈。",
            ),
            "pattern": sec("形态", [f"粗判：{features.get('pattern_guess', 'none')}"], "形态判断仅供参考。"),
            "support_resistance": sec(
                "关键位",
                sr_pts,
                "支撑/压力是多空博弈常见关注区间。",
            ),
        },
        "levels": {
            "supports": list(features.get("supports") or []),
            "resistances": list(features.get("resistances") or []),
        },
        "markers": [],
        "risks": risks,
        "opportunities": opps,
        "glossary": glossary,
    }
