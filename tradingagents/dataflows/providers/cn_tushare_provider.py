from __future__ import annotations

from datetime import datetime, timedelta
import re
from typing import Callable
import os
import threading
import time

import pandas as pd

from .base import BaseMarketDataProvider
from ..trade_calendar import cn_market_phase, cn_no_data_reason, cn_today_str, is_cn_trading_day


class CnTushareProvider(BaseMarketDataProvider):
    """A-share provider backed by Tushare Pro."""

    def __init__(self, token: str | None = None):
        self._token = (token or "").strip()
        self._client = None
        self._rate_limit = int(os.getenv("TUSHARE_RPS", "500") or "500")
        self._rt_rate_limit = int(os.getenv("TA_TUSHARE_RT_RPS", "200") or "200")
        self._calls: list[float] = []
        self._rt_calls: list[float] = []
        self._calls_lock = threading.Lock()

    @property
    def name(self) -> str:
        return "cn_tushare"

    def _normalize_symbol(self, symbol: str) -> str:
        s = (symbol or "").strip().upper()
        if re.fullmatch(r"\d{6}\.(SH|SZ|BJ)", s):
            return s
        m = re.search(r"(\d{6})", s)
        if not m:
            raise NotImplementedError(
                f"cn_tushare only supports A-share 6-digit symbols, got: {symbol}"
            )
        code = m.group(1)
        if code.startswith(("4", "8")):
            return f"{code}.BJ"
        if code.startswith(("5", "6", "9")):
            return f"{code}.SH"
        return f"{code}.SZ"

    @staticmethod
    def _to_ymd(date_str: str | None) -> str | None:
        if not date_str:
            return None
        return date_str.replace("-", "")

    def _pro(self):
        if not self._token:
            raise NotImplementedError(
                "cn_tushare requires TUSHARE_TOKEN. Please configure it in .env"
            )
        if self._client is not None:
            return self._client
        try:
            import tushare as ts  # type: ignore
        except ImportError as exc:
            raise NotImplementedError(
                "cn_tushare requires tushare. Install with: pip install tushare"
            ) from exc
        ts.set_token(self._token)
        self._client = ts.pro_api(self._token)
        return self._client

    def _throttle(self) -> None:
        if self._rate_limit <= 0:
            return
        while True:
            with self._calls_lock:
                now = time.monotonic()
                self._calls = [x for x in self._calls if now - x < 60.0]
                if len(self._calls) < self._rate_limit:
                    self._calls.append(now)
                    return
                wait_sec = max(0.01, 60.0 - (now - self._calls[0]))
            time.sleep(min(wait_sec, 0.2))

    def _call(self, fn: Callable, **kwargs):
        self._throttle()
        return fn(**kwargs)

    def _throttle_rt(self) -> None:
        if self._rt_rate_limit <= 0:
            return
        while True:
            with self._calls_lock:
                now = time.monotonic()
                self._rt_calls = [x for x in self._rt_calls if now - x < 60.0]
                if len(self._rt_calls) < self._rt_rate_limit:
                    self._rt_calls.append(now)
                    return
                wait_sec = max(0.01, 60.0 - (now - self._rt_calls[0]))
            time.sleep(min(wait_sec, 0.2))

    def _call_rt(self, fn: Callable, **kwargs):
        self._throttle_rt()
        return fn(**kwargs)

    def _format_csv(self, df: pd.DataFrame, symbol: str, start: str, end: str) -> str:
        if df is None:
            df = pd.DataFrame()
        out = df.copy()
        if not out.empty and "Date" in out.columns:
            out["Date"] = pd.to_datetime(out["Date"]).dt.strftime("%Y-%m-%d")
        header = f"# Stock data for {symbol} from {start} to {end}\n"
        header += f"# Total records: {len(out)}\n"
        header += f"# Data retrieved on: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
        return header + out.to_csv(index=False)

    @staticmethod
    def _df_or_empty(df: pd.DataFrame | None) -> pd.DataFrame:
        return df if df is not None else pd.DataFrame()

    def fetch_daily_bar_df(
        self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq"
    ) -> pd.DataFrame:
        pro = self._pro()
        code = self._normalize_symbol(symbol)
        start_ymd = self._to_ymd(start_date)
        end_ymd = self._to_ymd(end_date)

        daily = self._call(pro.daily, ts_code=code, start_date=start_ymd, end_date=end_ymd)
        if daily is None or daily.empty:
            return pd.DataFrame(columns=["Date", "Open", "High", "Low", "Close", "Volume", "Amount", "AdjFactor"])

        daily["trade_date"] = pd.to_datetime(daily["trade_date"], format="%Y%m%d", errors="coerce")
        daily = daily.dropna(subset=["trade_date"]).sort_values("trade_date").reset_index(drop=True)

        # Prefer Tushare A 股日线 RT when current query includes "today" and the market
        # is in-session/lunch-break/post-close. If unavailable, keep classic daily data.
        rt_enabled = os.getenv("TA_TUSHARE_RT_DAILY_ENABLED", "1").strip().lower() in ("1", "true", "yes", "on")
        today = cn_today_str()
        can_try_rt = (
            rt_enabled
            and end_date == today
            and is_cn_trading_day(today)
            and cn_market_phase() in ("in_session", "lunch_break", "post_close")
        )
        if can_try_rt:
            rt_today = self._fetch_rt_daily_today(code)
            if rt_today is not None and not rt_today.empty:
                daily = self._merge_today_rt_into_daily(daily, rt_today)

        adj_factor = pd.DataFrame()
        try:
            adj_factor = self._call(pro.adj_factor, ts_code=code, start_date=start_ymd, end_date=end_ymd)
        except Exception:
            adj_factor = pd.DataFrame()

        if adj_factor is not None and not adj_factor.empty:
            adj_factor["trade_date"] = pd.to_datetime(adj_factor["trade_date"], format="%Y%m%d", errors="coerce")
            adj_factor = adj_factor.dropna(subset=["trade_date"])
            daily = daily.merge(
                adj_factor[["trade_date", "adj_factor"]],
                how="left",
                on="trade_date",
            )
            daily["adj_factor"] = pd.to_numeric(daily["adj_factor"], errors="coerce")
            if adjust == "qfq" and daily["adj_factor"].notna().any():
                latest_factor = daily["adj_factor"].dropna().iloc[-1]
                scale = (daily["adj_factor"] / latest_factor).fillna(1.0)
                for col in ("open", "high", "low", "close"):
                    daily[col] = pd.to_numeric(daily[col], errors="coerce") * scale
        else:
            daily["adj_factor"] = None

        out = pd.DataFrame(
            {
                "Date": daily["trade_date"],
                "Open": pd.to_numeric(daily["open"], errors="coerce"),
                "High": pd.to_numeric(daily["high"], errors="coerce"),
                "Low": pd.to_numeric(daily["low"], errors="coerce"),
                "Close": pd.to_numeric(daily["close"], errors="coerce"),
                "Volume": pd.to_numeric(daily["vol"], errors="coerce"),
                "Amount": pd.to_numeric(daily.get("amount"), errors="coerce"),
                "AdjFactor": pd.to_numeric(daily.get("adj_factor"), errors="coerce"),
            }
        )
        return out.dropna(subset=["Date"]).reset_index(drop=True)

    def fetch_rt_daily_bar_df(self, ts_codes: list[str] | str) -> pd.DataFrame:
        """Fetch realtime daily-k snapshots via tushare rt_k."""
        pro = self._pro()
        if isinstance(ts_codes, list):
            joined = ",".join(str(x or "").strip().upper() for x in ts_codes if str(x or "").strip())
        else:
            joined = str(ts_codes or "").strip().upper()
        if not joined:
            return pd.DataFrame()
        return self._df_or_empty(self._call_rt(pro.rt_k, ts_code=joined))

    # ---- Fast-analysis snapshot helpers -------------------------------------------------
    def fetch_rt_k(self, ts_codes: list[str] | str) -> pd.DataFrame:
        return self.fetch_rt_daily_bar_df(ts_codes)

    def fetch_index_realtime(self) -> pd.DataFrame:
        # 常用 A 股市场指数。注意：`rt_k` 仅支持个股，指数实时需走 `rt_idx`（or `realtime_quote`），
        # 若仍不可用则降级到 `index_daily` 取最近一根作为参考脉搏。
        index_codes = [
            "000001.SH",
            "399001.SZ",
            "399006.SZ",
            "000688.SH",
            "000300.SH",
            "000905.SH",
        ]
        joined = ",".join(index_codes)
        pro = self._pro()

        for fn_name in ("rt_idx_k", "rt_idx", "realtime_quote", "realtime_index"):
            fn = getattr(pro, fn_name, None)
            if fn is None:
                continue
            try:
                df = self._df_or_empty(self._call_rt(fn, ts_code=joined))
            except Exception:
                continue
            if not df.empty:
                return df

        # 降级：用 index_daily 拼接每个指数的最近一根 K（盘中/接口未开通时的兜底）
        end_ymd = self._to_ymd(cn_today_str())
        start_ymd = self._to_ymd(
            (datetime.strptime(cn_today_str(), "%Y-%m-%d") - timedelta(days=10)).strftime("%Y-%m-%d")
        )
        frames: list[pd.DataFrame] = []
        idx_daily = getattr(pro, "index_daily", None)
        if callable(idx_daily):
            for code in index_codes:
                try:
                    df = self._call(idx_daily, ts_code=code, start_date=start_ymd, end_date=end_ymd)
                except Exception:
                    continue
                if df is None or df.empty:
                    continue
                df = df.sort_values("trade_date", ascending=False).head(1)
                frames.append(df)
        if frames:
            return pd.concat(frames, ignore_index=True, sort=False)
        return pd.DataFrame()

    def fetch_stk_auction(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        return self.fetch_opening_auction_df(ts_code, trade_date)

    def fetch_stk_mins(self, ts_code: str, freq: str = "1min", start: str | None = None, end: str | None = None) -> pd.DataFrame:
        pro = self._pro()
        kwargs = {
            "ts_code": self._normalize_symbol(ts_code),
            "freq": str(freq or "1min"),
        }
        if start:
            kwargs["start_date"] = self._to_ymd(start)
        if end:
            kwargs["end_date"] = self._to_ymd(end)
        return self._df_or_empty(self._call(pro.stk_mins, **kwargs))

    def fetch_moneyflow_dc(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(
            self._call(
                pro.moneyflow_dc,
                ts_code=self._normalize_symbol(ts_code),
                trade_date=self._to_ymd(trade_date),
            )
        )

    def fetch_moneyflow_industry_dc(self, trade_date: str) -> pd.DataFrame:
        """东方财富行业资金流。Tushare 实际接口名为 ``moneyflow_ind_dc``（doc_id=290）；
        历史代码里曾误写为 ``moneyflow_industry_dc`` 导致 "请指定正确的接口名"。本方法
        按可能的名字依次尝试，全部失败时返回空 DataFrame（软失败）。"""
        pro = self._pro()
        kwargs = {"trade_date": self._to_ymd(trade_date)}
        candidates = ("moneyflow_ind_dc", "moneyflow_ind_ths", "moneyflow_industry_dc")
        last_exc: Exception | None = None
        for name in candidates:
            fn = getattr(pro, name, None)
            if fn is None:
                continue
            try:
                return self._df_or_empty(self._call(fn, **kwargs))
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise last_exc
        return pd.DataFrame()

    def fetch_stk_factor_pro(self, ts_code: str, start: str, end: str) -> pd.DataFrame:
        return self.fetch_stk_factor_pro_df(ts_code, start, end)

    def fetch_top_list(self, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        trade_ymd = self._to_ymd(trade_date)
        base = self._df_or_empty(self._call(pro.top_list, trade_date=trade_ymd))
        inst = pd.DataFrame()
        top_inst_fn = getattr(pro, "top_inst", None)
        if callable(top_inst_fn):
            try:
                inst = self._df_or_empty(self._call(top_inst_fn, trade_date=trade_ymd))
            except Exception:
                inst = pd.DataFrame()
        if base.empty:
            return inst
        if inst.empty:
            return base
        return pd.concat([base, inst], ignore_index=True, sort=False)

    def fetch_limit_list_d(self, trade_date: str) -> pd.DataFrame:
        return self.fetch_limit_list_df(trade_date)

    def fetch_anns_d(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(
            self._call(
                pro.anns_d,
                ts_code=self._normalize_symbol(ts_code),
                ann_date=self._to_ymd(trade_date),
            )
        )

    def fetch_daily_basic(self, ts_code: str, trade_date: str) -> pd.DataFrame:
        ymd = self._to_ymd(trade_date)
        return self._df_or_empty(
            self._call(
                self._pro().daily_basic,
                ts_code=self._normalize_symbol(ts_code),
                start_date=ymd,
                end_date=ymd,
            )
        )

    def _fetch_rt_daily_today(self, ts_code: str) -> pd.DataFrame:
        pro = self._pro()
        rt_fn = getattr(pro, "rt_daily", None)
        if rt_fn is None:
            return pd.DataFrame()

        today_ymd = self._to_ymd(cn_today_str())
        candidates = (
            {"ts_code": ts_code},
            {"ts_code": ts_code, "trade_date": today_ymd},
        )
        for kwargs in candidates:
            try:
                rt_df = self._call(rt_fn, **kwargs)
            except Exception:
                continue
            if rt_df is None or rt_df.empty or "trade_date" not in rt_df.columns:
                continue
            rt_df = rt_df.copy()
            rt_df["trade_date"] = pd.to_datetime(rt_df["trade_date"], format="%Y%m%d", errors="coerce")
            rt_df = rt_df.dropna(subset=["trade_date"])
            rt_df = rt_df[rt_df["trade_date"] == pd.to_datetime(cn_today_str())]
            if "ts_code" in rt_df.columns:
                rt_df = rt_df[rt_df["ts_code"] == ts_code]
            if not rt_df.empty:
                return rt_df.sort_values("trade_date").tail(1)
        return pd.DataFrame()

    @staticmethod
    def _merge_today_rt_into_daily(daily: pd.DataFrame, rt_today: pd.DataFrame) -> pd.DataFrame:
        if daily is None or daily.empty or rt_today is None or rt_today.empty:
            return daily

        daily = daily.copy()
        rt = rt_today.copy()

        def _pick(df: pd.DataFrame, names: tuple[str, ...], default=None):
            for name in names:
                if name in df.columns:
                    return df[name].iloc[-1]
            return default

        trade_date = pd.to_datetime(_pick(rt, ("trade_date",)))
        rt_row = {
            "trade_date": trade_date,
            "open": _pick(rt, ("open", "o")),
            "high": _pick(rt, ("high", "h")),
            "low": _pick(rt, ("low", "l")),
            "close": _pick(rt, ("close", "price", "c")),
            "vol": _pick(rt, ("vol", "volume")),
            "amount": _pick(rt, ("amount", "amt", "turnover")),
        }
        if "adj_factor" in daily.columns:
            today_existing = daily[daily["trade_date"] == trade_date]
            rt_row["adj_factor"] = (
                today_existing["adj_factor"].iloc[-1]
                if not today_existing.empty and "adj_factor" in today_existing.columns
                else None
            )

        daily = daily[daily["trade_date"] != trade_date]
        daily = pd.concat([daily, pd.DataFrame([rt_row])], ignore_index=True)
        return daily.sort_values("trade_date").reset_index(drop=True)

    def fetch_north_money_df(self, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        start_ymd = self._to_ymd(start_date)
        end_ymd = self._to_ymd(end_date)
        df = self._call(pro.moneyflow_hsgt, start_date=start_ymd, end_date=end_ymd)
        return df if df is not None else pd.DataFrame()

    def fetch_company_basic_df(self) -> pd.DataFrame:
        pro = self._pro()
        df = self._call(pro.stock_basic,
            exchange="",
            list_status="L",
            fields="ts_code,symbol,name,area,industry,market,list_date,is_hs",
        )
        return df if df is not None else pd.DataFrame()

    def fetch_financial_report_df(
        self,
        report_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        pro = self._pro()
        endpoint_map: dict[str, Callable] = {
            "balancesheet": pro.balancesheet,
            "income": pro.income,
            "cashflow": pro.cashflow,
        }
        func = endpoint_map.get(report_type)
        if func is None:
            raise NotImplementedError(f"Unsupported report_type: {report_type}")
        kwargs = {}
        if start_date:
            kwargs["start_date"] = self._to_ymd(start_date)
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        df = self._call(func, **kwargs)
        return df if df is not None else pd.DataFrame()

    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        df = self.fetch_daily_bar_df(symbol, start_date, end_date, adjust="qfq")
        return self._format_csv(df, symbol, start_date, end_date)

    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int
    ) -> str:
        end_dt = datetime.strptime(curr_date, "%Y-%m-%d")
        start_dt = end_dt - timedelta(days=max(look_back_days, 260))
        df = self.fetch_daily_bar_df(symbol, start_dt.strftime("%Y-%m-%d"), curr_date)
        if df is None or df.empty:
            return f"No data found for {symbol} for indicator {indicator}"
        ind_df = df.rename(
            columns={
                "Date": "date",
                "Open": "open",
                "High": "high",
                "Low": "low",
                "Close": "close",
                "Volume": "volume",
            }
        )[["date", "open", "high", "low", "close", "volume"]]
        try:
            from stockstats import wrap  # type: ignore
        except ImportError as exc:
            raise NotImplementedError("cn_tushare indicators require stockstats") from exc
        ss = wrap(ind_df)
        try:
            series = ss[indicator]
        except Exception as exc:
            raise NotImplementedError(f"indicator not supported by stockstats: {indicator}") from exc
        curr_key = end_dt.strftime("%Y-%m-%d")
        values = {}
        for i, dt in enumerate(ind_df["date"]):
            values[pd.to_datetime(dt).strftime("%Y-%m-%d")] = series.iloc[i]
        val = values.get(curr_key)
        if val is None or pd.isna(val):
            return cn_no_data_reason(curr_key)
        return str(val)

    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        code = self._normalize_symbol(ticker)
        pro = self._pro()
        basic = pro.stock_basic(
            ts_code=code,
            fields="ts_code,name,industry,market,list_date,is_hs",
        )
        if basic is None or basic.empty:
            return f"No fundamentals found for {ticker}"
        return self._format_df_markdown(f"## Fundamentals ({ticker})", basic.head(1))

    def _financial_table(self, ticker: str, report_type: str) -> str:
        code = self._normalize_symbol(ticker)
        df = self.fetch_financial_report_df(report_type)
        if df is None or df.empty:
            return f"No {report_type} data found for {ticker}"
        if "ts_code" in df.columns:
            df = df[df["ts_code"] == code]
        if df.empty:
            return f"No {report_type} data found for {ticker}"
        cols = [c for c in ("ts_code", "ann_date", "end_date", "update_flag") if c in df.columns]
        view = df[cols].head(10) if cols else df.head(10)
        try:
            return view.to_markdown(index=False)
        except (ImportError, Exception):
            return view.to_csv(index=False)

    def get_balance_sheet(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        del freq, curr_date
        return f"## Balance Sheet ({ticker})\n\n{self._financial_table(ticker, 'balancesheet')}"

    def get_cashflow(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        del freq, curr_date
        return f"## Cashflow ({ticker})\n\n{self._financial_table(ticker, 'cashflow')}"

    def get_income_statement(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        del freq, curr_date
        return f"## Income Statement ({ticker})\n\n{self._financial_table(ticker, 'income')}"

    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        del ticker, start_date, end_date
        raise NotImplementedError("cn_tushare does not provide unified news endpoint in current implementation")

    def get_global_news(
        self, curr_date: str, look_back_days: int = 7, limit: int = 50
    ) -> str:
        del curr_date, look_back_days, limit
        raise NotImplementedError("cn_tushare does not provide global news endpoint in current implementation")

    def get_insider_transactions(self, symbol: str) -> str:
        del symbol
        raise NotImplementedError("cn_tushare insider transactions are not implemented in current version")

    def _format_df_markdown(self, title: str, df: pd.DataFrame, head: int = 30) -> str:
        if df is None or df.empty:
            return f"{title}\n\n无数据"
        view = df.head(head)
        try:
            return f"{title}\n\n{view.to_markdown(index=False)}"
        except (ImportError, Exception):
            return f"{title}\n\n{view.to_csv(index=False)}"

    def fetch_daily_basic_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(self._call(pro.daily_basic,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_limit_list_df(self, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(self._call(pro.limit_list_d, trade_date=self._to_ymd(trade_date)))

    def fetch_individual_moneyflow_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(self._call(pro.moneyflow,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_margin_detail_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(self._call(pro.margin_detail,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_hsgt_top10_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(self._call(pro.hsgt_top10,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_opening_auction_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        code = self._normalize_symbol(symbol)
        trade_ymd = self._to_ymd(trade_date)
        fields = "ts_code,trade_date,vol,price,amount,pre_close,turnover_rate,volume_ratio,float_share"
        try:
            return self._df_or_empty(self._call(pro.stk_auction, ts_code=code, trade_date=trade_ymd, fields=fields))
        except Exception:
            return self._df_or_empty(self._call(pro.stk_auction, ts_code=code, start_date=trade_ymd, end_date=trade_ymd, fields=fields))

    def fetch_opening_auction_o_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        code = self._normalize_symbol(symbol)
        trade_ymd = self._to_ymd(trade_date)
        # 用户已确认开通；不同账户字段集可能不同，优先拉常用列。
        fields = "ts_code,trade_time,price,vol,amount,bid_amount,ask_amount"
        fn = getattr(pro, "stk_auction_o", None)
        if fn is None:
            return pd.DataFrame()
        return self._df_or_empty(self._call(fn, ts_code=code, trade_date=trade_ymd, fields=fields))

    def fetch_opening_auction_c_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        pro = self._pro()
        code = self._normalize_symbol(symbol)
        trade_ymd = self._to_ymd(trade_date)
        fields = "ts_code,trade_time,price,vol,amount,bid_amount,ask_amount"
        fn = getattr(pro, "stk_auction_c", None)
        if fn is None:
            return pd.DataFrame()
        return self._df_or_empty(self._call(fn, ts_code=code, trade_date=trade_ymd, fields=fields))

    def fetch_top_list_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        """Tushare top_list 接口必须按 trade_date 单日传入，因此我们用 trade_cal
        枚举区间内的交易日，逐日抓取后过滤目标 ts_code。"""
        pro = self._pro()
        code = self._normalize_symbol(symbol)
        start_ymd = self._to_ymd(start_date)
        end_ymd = self._to_ymd(end_date)
        try:
            cal = self._call(
                pro.trade_cal,
                exchange="SSE",
                start_date=start_ymd,
                end_date=end_ymd,
                is_open="1",
            )
        except Exception:
            return pd.DataFrame()
        if cal is None or cal.empty:
            return pd.DataFrame()
        trade_dates = cal["cal_date"].astype(str).sort_values().tolist()
        max_days = int(os.getenv("TA_TUSHARE_TOPLIST_MAX_DAYS", "60") or "60")
        trade_dates = trade_dates[-max_days:]
        frames: list[pd.DataFrame] = []
        for td in trade_dates:
            try:
                df = self._call(pro.top_list, trade_date=td)
            except Exception:
                continue
            if df is None or df.empty:
                continue
            if "ts_code" in df.columns:
                df = df[df["ts_code"] == code]
            if df is None or df.empty:
                continue
            frames.append(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_block_trade_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        pro = self._pro()
        return self._df_or_empty(
            self._call(
                pro.block_trade,
                ts_code=self._normalize_symbol(symbol),
                start_date=self._to_ymd(start_date),
                end_date=self._to_ymd(end_date),
            )
        )

    def fetch_stk_factor_pro_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        if os.getenv("TA_TUSHARE_FACTOR_ENABLED", "1").strip().lower() not in ("1", "true", "yes", "on"):
            return pd.DataFrame()
        pro = self._pro()
        return self._df_or_empty(self._call(pro.stk_factor_pro,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_cyq_perf_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        if os.getenv("TA_TUSHARE_FACTOR_ENABLED", "1").strip().lower() not in ("1", "true", "yes", "on"):
            return pd.DataFrame()
        pro = self._pro()
        return self._df_or_empty(self._call(pro.cyq_perf,
            ts_code=self._normalize_symbol(symbol),
            start_date=self._to_ymd(start_date),
            end_date=self._to_ymd(end_date),
        ))

    def fetch_cyq_chips_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        if os.getenv("TA_TUSHARE_FACTOR_ENABLED", "1").strip().lower() not in ("1", "true", "yes", "on"):
            return pd.DataFrame()
        pro = self._pro()
        return self._df_or_empty(self._call(pro.cyq_chips,
            ts_code=self._normalize_symbol(symbol),
            trade_date=self._to_ymd(trade_date),
        ))

    def fetch_l2_orderqueue_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        """L2 委托队列：Tushare 不同积分档接口名不一致（stk_orderqueue / l2_orderqueue
        等），且 10000 积分档默认未开通该接口。无权限时软失败为空 DataFrame，避免
        阻塞分析主链路。可通过 TA_TUSHARE_L2_API 环境变量覆盖接口名。"""
        if os.getenv("TA_TUSHARE_L2_ENABLED", "0").strip().lower() not in ("1", "true", "yes", "on"):
            return pd.DataFrame()
        pro = self._pro()
        kwargs = {
            "ts_code": self._normalize_symbol(symbol),
            "trade_date": self._to_ymd(trade_date),
        }
        explicit = os.getenv("TA_TUSHARE_L2_API", "").strip()
        candidates = [explicit] if explicit else [
            "stk_orderqueue",
            "l2_orderqueue",
            "ts_l2",
            "stk_l2_orderqueue",
        ]
        last_exc: Exception | None = None
        for api_name in candidates:
            if not api_name:
                continue
            fn = getattr(pro, api_name, None)
            if fn is None:
                continue
            try:
                return self._df_or_empty(self._call(fn, **kwargs))
            except Exception as exc:
                last_exc = exc
                continue
        if last_exc is not None:
            raise NotImplementedError(
                f"L2 产品接口调用失败，可能未开通对应产品或需走专用 SDK 通道：{type(last_exc).__name__}: {last_exc}"
            )
        raise NotImplementedError("L2 产品未开通或当前 SDK 未暴露可用的 pro_api 接口名")

    def fetch_fina_indicator_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        pro = self._pro()
        kwargs = {"ts_code": self._normalize_symbol(symbol)}
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.fina_indicator_vip, **kwargs))

    def fetch_forecast_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        pro = self._pro()
        kwargs = {"ts_code": self._normalize_symbol(symbol)}
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.forecast_vip, **kwargs))

    def fetch_express_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        pro = self._pro()
        kwargs = {"ts_code": self._normalize_symbol(symbol)}
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.express_vip, **kwargs))

    def fetch_dividend_df(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        pro = self._pro()
        kwargs: dict[str, str] = {"ts_code": self._normalize_symbol(symbol)}
        if start_date:
            kwargs["start_date"] = self._to_ymd(start_date)
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.dividend, **kwargs))

    def fetch_stk_holdertrade_df(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        pro = self._pro()
        kwargs: dict[str, str] = {"ts_code": self._normalize_symbol(symbol)}
        if start_date:
            kwargs["start_date"] = self._to_ymd(start_date)
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.stk_holdertrade, **kwargs))

    def fetch_holdernumber_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        pro = self._pro()
        kwargs = {"ts_code": self._normalize_symbol(symbol)}
        if end_date:
            kwargs["end_date"] = self._to_ymd(end_date)
        return self._df_or_empty(self._call(pro.stk_holdernumber, **kwargs))

    def get_daily_basic(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## Daily Basic ({symbol})",
            self.fetch_daily_basic_df(symbol, start_date, end_date),
        )

    def get_limit_list_summary(self, date: str) -> str:
        return self._format_df_markdown(
            f"## Limit List ({date})",
            self.fetch_limit_list_df(date),
        )

    def get_individual_money_flow_detail(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## Moneyflow ({symbol})",
            self.fetch_individual_moneyflow_df(symbol, start_date, end_date),
        )

    def get_margin_detail(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## Margin Detail ({symbol})",
            self.fetch_margin_detail_df(symbol, start_date, end_date),
        )

    def get_hsgt_top10(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## HSGT Top10 ({symbol})",
            self.fetch_hsgt_top10_df(symbol, start_date, end_date),
        )

    def get_opening_auction(self, symbol: str, date: str) -> str:
        df = self.fetch_opening_auction_df(symbol, date)
        if df is None or df.empty:
            return (
                f"## 开盘集合竞价（{symbol}，{date}）\n\n"
                f"无数据。说明：集合竞价数据通常在 09:25-09:29 可见，历史日期依赖权限与数据源可用性。"
            )

        view = df.copy()
        for col in ("vol", "price", "amount", "pre_close", "turnover_rate", "volume_ratio", "float_share"):
            if col in view.columns:
                view[col] = pd.to_numeric(view[col], errors="coerce")

        row = view.iloc[-1]
        price = float(row["price"]) if "price" in row and pd.notna(row["price"]) else None
        pre_close = float(row["pre_close"]) if "pre_close" in row and pd.notna(row["pre_close"]) else None
        gap_pct = ((price / pre_close - 1.0) * 100.0) if (price and pre_close and pre_close > 0) else None
        turnover_rate = float(row["turnover_rate"]) if "turnover_rate" in row and pd.notna(row["turnover_rate"]) else None
        volume_ratio = float(row["volume_ratio"]) if "volume_ratio" in row and pd.notna(row["volume_ratio"]) else None
        amount = float(row["amount"]) if "amount" in row and pd.notna(row["amount"]) else None
        vol = float(row["vol"]) if "vol" in row and pd.notna(row["vol"]) else None

        summary = [
            f"- 竞价均价: {price:.3f}" if price is not None else "- 竞价均价: 无数据",
            f"- 较昨收涨跌: {gap_pct:+.2f}%" if gap_pct is not None else "- 较昨收涨跌: 无数据",
            f"- 竞价成交额: {amount:,.0f} 元" if amount is not None else "- 竞价成交额: 无数据",
            f"- 竞价成交量: {vol:,.0f} 股" if vol is not None else "- 竞价成交量: 无数据",
            f"- 竞价换手率: {turnover_rate:.4f}%" if turnover_rate is not None else "- 竞价换手率: 无数据",
            f"- 竞价量比: {volume_ratio:.3f}" if volume_ratio is not None else "- 竞价量比: 无数据",
        ]
        return (
            f"## 开盘集合竞价（{symbol}，{date}）\n\n"
            + "\n".join(summary)
            + "\n\n### 明细\n\n"
            + self._df_or_empty(view).head(10).to_markdown(index=False)
        )

    def get_lhb_detail(self, symbol: str, date: str) -> str:
        df = self.fetch_top_list_df(symbol, date, date)
        if df is None or df.empty:
            return f"{symbol} 在 {date} 无龙虎榜数据（非异动日属正常）。"
        return f"{symbol} 龙虎榜明细（{date}）：\n{df.head(20).to_string(index=False)}"

    def get_zt_pool(self, date: str) -> str:
        df = self.fetch_limit_list_df(date)
        if df is None or df.empty:
            return f"{date} 涨停板情绪池数据暂不可用。"
        count = len(df)
        out = f"{date} 涨停家数：{count}\n"
        for candidate in ("连板数", "lianban", "limit_times"):
            if candidate in df.columns:
                dist = df[candidate].value_counts().sort_index()
                out += f"连板分布：\n{dist.head(10).to_string()}"
                break
        return out

    def get_board_fund_flow(self) -> str:
        trade_date = cn_today_str()
        try:
            df = self.fetch_moneyflow_industry_dc(trade_date)
        except Exception as exc:
            return f"板块资金流向数据获取失败：{type(exc).__name__}: {exc}"
        if df is None or df.empty:
            return "今日板块资金流向数据暂不可用。"

        sort_col = None
        for col in ("主力净流入", "主力净流入-净额", "net_amount", "net_mf_amount"):
            if col in df.columns:
                sort_col = col
                break
        if sort_col:
            df_sorted = df.sort_values(sort_col, ascending=False).reset_index(drop=True)
        else:
            df_sorted = df.reset_index(drop=True)
        df_sorted.insert(0, "排名", range(1, len(df_sorted) + 1))
        total = len(df_sorted)
        return f"板块资金流向排名（共{total}个板块，前10名）：\n{df_sorted.head(10).to_string(index=False)}"

    def get_top_list_history(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## Top List ({symbol})",
            self.fetch_top_list_df(symbol, start_date, end_date),
        )

    def get_stk_factor_pro_window(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## Stk Factor Pro ({symbol})",
            self.fetch_stk_factor_pro_df(symbol, start_date, end_date),
        )

    def get_cyq_perf(self, symbol: str, start_date: str, end_date: str) -> str:
        return self._format_df_markdown(
            f"## CYQ Perf ({symbol})",
            self.fetch_cyq_perf_df(symbol, start_date, end_date),
        )

    def get_cyq_chips(self, symbol: str, date: str) -> str:
        return self._format_df_markdown(
            f"## CYQ Chips ({symbol})",
            self.fetch_cyq_chips_df(symbol, date),
        )

    def get_l2_orderqueue_window(self, symbol: str, date: str) -> str:
        return self._format_df_markdown(
            f"## L2 OrderQueue ({symbol})",
            self.fetch_l2_orderqueue_df(symbol, date),
        )

    def get_fina_indicator(self, ticker: str, curr_date: str = None) -> str:
        return self._format_df_markdown(
            f"## Fina Indicator ({ticker})",
            self.fetch_fina_indicator_df(ticker, curr_date),
        )

    def get_forecast(self, ticker: str, curr_date: str = None) -> str:
        return self._format_df_markdown(
            f"## Forecast ({ticker})",
            self.fetch_forecast_df(ticker, curr_date),
        )

    def get_express(self, ticker: str, curr_date: str = None) -> str:
        return self._format_df_markdown(
            f"## Express ({ticker})",
            self.fetch_express_df(ticker, curr_date),
        )

    def get_holdernumber_series(self, ticker: str, curr_date: str = None) -> str:
        return self._format_df_markdown(
            f"## Holder Number ({ticker})",
            self.fetch_holdernumber_df(ticker, curr_date),
        )

