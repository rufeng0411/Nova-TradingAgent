from __future__ import annotations

import asyncio
import os
import time
from datetime import datetime
from typing import Any, Callable

import pandas as pd

SOURCE_LABELS: dict[str, str] = {
    "rt_k": "实时行情 rt_k",
    "index_pulse": "大盘指数 index_realtime",
    "mins": "分钟K线 stk_mins",
    "moneyflow": "个股资金流 moneyflow_dc",
    "industry_flow": "行业资金流 moneyflow_industry_dc",
    "factor": "技术因子 stk_factor_pro",
    "top_list": "龙虎榜 top_list",
    "limit_list": "涨停池 limit_list_d",
    "anns": "公告 anns_d",
    "basic": "估值 daily_basic",
    "kline_60d": "60日日K kline",
    "auction": "集合竞价 stk_auction",
}

from tradingagents.dataflows.providers.cn_tushare_provider import CnTushareProvider
from tradingagents.dataflows.trade_calendar import cn_market_phase, is_cn_trading_day


# 仅在盘后才发布当日数据的源；T 日盘中查 trade_date=T 必然空，需直接 skipped 而不是「命中 0 行」。
_EOD_ONLY_LABELS: tuple[str, ...] = (
    "moneyflow",
    "industry_flow",
    "basic",
    "limit_list",
    "top_list",
    "cyq_chips",
    "hsgt_top10",
)
_EOD_SKIP_HINT = "日终类源：T 日盘后（约 15:30 起）才发布当日数据，盘中查 T 日为空属正常"
_TOP_LIST_HINT = "龙虎榜：交易所通常 18:00 前后发布；盘中/未发布前查为空属正常"
_CYQ_HINT = "筹码分布：通常盘后更新，盘中查当日为空属正常"
_HSGT_TOP10_HINT = "沪深股通十大成交：通常 T+1 早盘发布前一交易日数据"


def _eod_skip_for_phase(label: str, trade_date: str, now: datetime) -> dict[str, Any] | None:
    """若该源在当前时段（针对查询的 trade_date）必然为空，返回 skipped payload；否则 None。"""
    if label not in _EOD_ONLY_LABELS:
        return None
    today_str = now.strftime("%Y-%m-%d")
    if trade_date != today_str:
        return None
    if not is_cn_trading_day(trade_date):
        return None
    phase = cn_market_phase(now)
    if phase in ("pre_open", "in_session", "lunch_break"):
        if label == "top_list":
            hint = _TOP_LIST_HINT
        elif label == "cyq_chips":
            hint = _CYQ_HINT
        elif label == "hsgt_top10":
            hint = _HSGT_TOP10_HINT
        else:
            hint = _EOD_SKIP_HINT
        return {"status": "skipped", "latency_ms": 0, "data": [], "hint": hint}
    return None


def _env_enabled(key: str, default: str = "1") -> bool:
    return os.getenv(key, default).strip().lower() in ("1", "true", "yes", "on")


def _to_ymd(date_str: str) -> str:
    return date_str.replace("-", "")


def _today_ymd() -> str:
    return datetime.now().strftime("%Y%m%d")


def _auction_available(trade_date: str, now_ymd: str, now_hhmm: str) -> bool:
    ymd = _to_ymd(trade_date)
    if not is_cn_trading_day(trade_date):
        return False
    if ymd < now_ymd:
        return True
    if ymd > now_ymd:
        return False
    return now_hhmm >= "0925"


def _df_to_records(df: pd.DataFrame | None, limit: int = 200) -> list[dict[str, Any]]:
    if df is None or df.empty:
        return []
    view = df.head(limit).copy()
    for col in view.columns:
        if pd.api.types.is_datetime64_any_dtype(view[col]):
            view[col] = view[col].astype(str)
    return view.to_dict(orient="records")


async def _safe_call(
    label: str,
    fn,
    *args,
    timeout_sec: float = 8.0,
) -> tuple[str, dict[str, Any]]:
    started = time.perf_counter()
    try:
        result = await asyncio.wait_for(asyncio.to_thread(fn, *args), timeout=timeout_sec)
        elapsed = int((time.perf_counter() - started) * 1000)
        return label, {"status": "ok", "latency_ms": elapsed, "data": _df_to_records(result)}
    except asyncio.TimeoutError:
        elapsed = int((time.perf_counter() - started) * 1000)
        return label, {"status": "timeout", "latency_ms": elapsed, "data": []}
    except NotImplementedError as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return label, {"status": "unsupported_channel", "latency_ms": elapsed, "error": str(exc), "data": []}
    except Exception as exc:
        elapsed = int((time.perf_counter() - started) * 1000)
        return label, {"status": "unavailable", "latency_ms": elapsed, "error": str(exc), "data": []}


def _build_provider() -> CnTushareProvider:
    token = (os.getenv("TUSHARE_TOKEN") or "").strip()
    return CnTushareProvider(token=token)


async def collect_snapshot(
    symbol: str,
    trade_date: str,
    *,
    timeout_sec: float = 30.0,
    on_progress: Callable[[str, dict[str, Any], int, int], None] | None = None,
) -> dict[str, Any]:
    """Concurrently fetch all snapshot sources.

    ``on_progress(label, payload, done, total)`` is called from the event loop each time a
    source finishes (status ok / timeout / unavailable). It is best-effort and exceptions
    inside the callback are swallowed so they cannot break the snapshot pipeline.
    """
    provider = _build_provider()
    now = datetime.now()
    now_ymd = now.strftime("%Y%m%d")
    now_hhmm = now.strftime("%H%M")
    start = time.perf_counter()

    symbol = str(symbol or "").strip().upper()
    # 拉 60 日 K，扣掉双休/节假日（≈30%），需要约 95 自然日才能稳定凑齐 60+ 根交易日，
    # 否则 MA60 / volume_ma20 / cluster_levels 等都会算不出来（之前 40 天只回 24 根的 bug 来源）。
    kline_lookback_start = (
        datetime.strptime(trade_date, "%Y-%m-%d") - pd.Timedelta(days=95)
    ).strftime("%Y-%m-%d")
    t_minus_20 = kline_lookback_start  # 旧别名保留，后续如需重命名再改用方调用点

    # 「日终类」源在盘中查当日为空属正常，提前 short-circuit 为 skipped + hint，避免「命中 0 行」误导。
    def _plan(label: str, fn, *args) -> asyncio.Task:
        skip = _eod_skip_for_phase(label, trade_date, now)
        if skip is not None:
            return asyncio.create_task(asyncio.sleep(0, result=(label, skip)))
        return asyncio.create_task(_safe_call(label, fn, *args))

    # 并行发起：优先日 K / 日线 RT / 集合竞价相关（与特征抽取权重一致）；实际完成顺序由接口耗时决定。
    coros: list[asyncio.Future] = [
        _plan("kline_60d", provider.fetch_daily_bar_df, symbol, t_minus_20, trade_date, "qfq"),
        _plan("rt_k", provider.fetch_rt_k, [symbol]),
        _plan("factor", provider.fetch_stk_factor_pro, symbol, t_minus_20, trade_date),
        _plan("mins", provider.fetch_stk_mins, symbol, "1min", trade_date, trade_date),
        _plan("moneyflow", provider.fetch_moneyflow_dc, symbol, trade_date),
        _plan("industry_flow", provider.fetch_moneyflow_industry_dc, trade_date),
        _plan("index_pulse", provider.fetch_index_realtime),
        _plan("top_list", provider.fetch_top_list, trade_date),
        _plan("limit_list", provider.fetch_limit_list_d, trade_date),
        _plan("anns", provider.fetch_anns_d, symbol, trade_date),
        _plan("basic", provider.fetch_daily_basic, symbol, trade_date),
    ]
    if _auction_available(trade_date, now_ymd, now_hhmm):
        coros.append(asyncio.create_task(_safe_call("auction", provider.fetch_stk_auction, symbol, trade_date)))
    else:
        coros.append(asyncio.create_task(asyncio.sleep(0, result=("auction", {"status": "skipped", "latency_ms": 0, "data": [], "hint": "集合竞价：9:25 后才有当日成交快照"}))))

    total = len(coros)
    snapshot: dict[str, Any] = {}
    timings: dict[str, Any] = {}
    done_count = 0

    pending = set(coros)
    deadline = time.perf_counter() + max(1.0, float(timeout_sec))
    while pending:
        remaining = deadline - time.perf_counter()
        if remaining <= 0:
            for task in pending:
                task.cancel()
            for task in list(pending):
                label = _label_for_task(task)
                done_count += 1
                snapshot[label] = {"status": "timeout", "latency_ms": int(timeout_sec * 1000), "data": []}
                timings[label] = {"status": "timeout", "latency_ms": int(timeout_sec * 1000)}
                if on_progress is not None:
                    try:
                        on_progress(label, snapshot[label], done_count, total)
                    except Exception:
                        pass
            break
        finished, pending = await asyncio.wait(pending, timeout=remaining, return_when=asyncio.FIRST_COMPLETED)
        for task in finished:
            try:
                label, payload = task.result()
            except Exception as exc:  # cancellation / unknown failure
                label = _label_for_task(task)
                payload = {"status": "unavailable", "latency_ms": 0, "error": str(exc), "data": []}
            snapshot[label] = payload
            timings[label] = {"status": payload.get("status"), "latency_ms": payload.get("latency_ms")}
            done_count += 1
            if on_progress is not None:
                try:
                    on_progress(label, payload, done_count, total)
                except Exception:
                    pass

    ok_count = sum(1 for v in snapshot.values() if v.get("status") == "ok")
    skipped_count = sum(1 for v in snapshot.values() if v.get("status") == "skipped")
    eligible = max(1, total - skipped_count)  # skipped 视为「按预期不可用」，不计入完整度分母
    data_completeness = float(ok_count / eligible)
    return {
        "symbol": symbol,
        "trade_date": trade_date,
        "data_completeness": round(data_completeness, 3),
        "timings": timings,
        "sources": snapshot,
        "elapsed_ms": int((time.perf_counter() - start) * 1000),
        "expected_sources": total,
        "provider": "cn_tushare_direct",
    }


def _label_for_task(task: asyncio.Task) -> str:
    # Best-effort retrieval of label from completed _safe_call results; falls back to unknown.
    try:
        if task.done() and not task.cancelled():
            res = task.result()
            if isinstance(res, tuple) and res:
                return str(res[0])
    except Exception:
        pass
    return "unknown"

