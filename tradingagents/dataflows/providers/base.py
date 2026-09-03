from abc import ABC, abstractmethod
import pandas as pd


class BaseMarketDataProvider(ABC):
    """Abstract interface for market data providers."""

    @property
    @abstractmethod
    def name(self) -> str:
        """Provider identifier used by config routing."""
        raise NotImplementedError

    @abstractmethod
    def get_stock_data(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_indicators(
        self, symbol: str, indicator: str, curr_date: str, look_back_days: int
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_fundamentals(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_balance_sheet(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_cashflow(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_income_statement(
        self, ticker: str, freq: str = "quarterly", curr_date: str = None
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_news(self, ticker: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_global_news(
        self, curr_date: str, look_back_days: int = 7, limit: int = 50
    ) -> str:
        raise NotImplementedError

    @abstractmethod
    def get_insider_transactions(self, symbol: str) -> str:
        raise NotImplementedError

    def get_realtime_quotes(self, symbols: list[str]) -> str:
        """Return real-time quotes for a list of symbols as a JSON string.

        Keys are original symbols (e.g. "600519.SH"), values are dicts with:
        price, open, high, low, previous_close, change, change_pct, volume, amount.
        """
        raise NotImplementedError

    # --- Extended market/factor/L2 tool methods ---
    def get_daily_basic(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_limit_list_summary(self, date: str) -> str:
        raise NotImplementedError

    def get_individual_money_flow_detail(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_margin_detail(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_hsgt_top10(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_opening_auction(self, symbol: str, date: str) -> str:
        raise NotImplementedError

    def get_top_list_history(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_stk_factor_pro_window(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_cyq_perf(self, symbol: str, start_date: str, end_date: str) -> str:
        raise NotImplementedError

    def get_cyq_chips(self, symbol: str, date: str) -> str:
        raise NotImplementedError

    def get_l2_orderqueue_window(self, symbol: str, date: str) -> str:
        raise NotImplementedError

    def get_fina_indicator(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError

    def get_forecast(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError

    def get_express(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError

    def get_holdernumber_series(self, ticker: str, curr_date: str = None) -> str:
        raise NotImplementedError

    # --- Tier-3 structured fetch helpers (optional for providers) ---
    def fetch_daily_bar_df(
        self, symbol: str, start_date: str, end_date: str, adjust: str = "qfq"
    ) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} does not support fetch_daily_bar_df"
        )

    def fetch_north_money_df(self, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} does not support fetch_north_money_df"
        )

    def fetch_company_basic_df(self) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} does not support fetch_company_basic_df"
        )

    def fetch_financial_report_df(
        self,
        report_type: str,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> pd.DataFrame:
        raise NotImplementedError(
            f"{self.name} does not support fetch_financial_report_df"
        )

    def fetch_daily_basic_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_daily_basic_df")

    def fetch_limit_list_df(self, trade_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_limit_list_df")

    def fetch_individual_moneyflow_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_individual_moneyflow_df")

    def fetch_margin_detail_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_margin_detail_df")

    def fetch_hsgt_top10_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_hsgt_top10_df")

    def fetch_opening_auction_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_opening_auction_df")

    def fetch_top_list_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_top_list_df")

    def fetch_block_trade_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_block_trade_df")

    def fetch_stk_factor_pro_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_stk_factor_pro_df")

    def fetch_cyq_perf_df(self, symbol: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_cyq_perf_df")

    def fetch_cyq_chips_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_cyq_chips_df")

    def fetch_l2_orderqueue_df(self, symbol: str, trade_date: str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_l2_orderqueue_df")

    def fetch_fina_indicator_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_fina_indicator_df")

    def fetch_forecast_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_forecast_df")

    def fetch_express_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_express_df")

    def fetch_dividend_df(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_dividend_df")

    def fetch_stk_holdertrade_df(
        self, symbol: str, start_date: str | None = None, end_date: str | None = None
    ) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_stk_holdertrade_df")

    def fetch_holdernumber_df(self, symbol: str, end_date: str | None = None) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_holdernumber_df")

    def fetch_rt_daily_bar_df(self, ts_codes: list[str] | str) -> pd.DataFrame:
        raise NotImplementedError(f"{self.name} does not support fetch_rt_daily_bar_df")

