import os
from typing import Dict

from .base import BaseMarketDataProvider


class DataProviderRegistry:
    """Simple in-memory provider registry."""

    def __init__(self):
        self._providers: Dict[str, BaseMarketDataProvider] = {}

    def register(self, provider: BaseMarketDataProvider) -> None:
        self._providers[provider.name] = provider

    def get(self, provider_name: str) -> BaseMarketDataProvider | None:
        return self._providers.get(provider_name)

    def list_names(self) -> list[str]:
        return list(self._providers.keys())


def build_default_registry() -> DataProviderRegistry:
    registry = DataProviderRegistry()
    from .china_equity_provider import CnStubProvider
    from .juchao_provider import JuChaoProvider
    from .stats_cn_provider import StatsCnProvider
    from .fred_provider import FredProvider

    try:
        from .cn_akshare_provider import CnAkshareProvider

        registry.register(CnAkshareProvider())
    except Exception:
        pass

    try:
        from .cn_baostock_provider import CnBaoStockProvider

        registry.register(CnBaoStockProvider())
    except Exception:
        pass
    tier3_on = os.getenv("TA_DATASOURCE_TIER3_ENABLED", "0").strip() in ("1", "true", "yes", "on")
    if tier3_on and os.getenv("TA_TUSHARE_REGISTER", "0").strip() in ("1", "true", "yes", "on"):
        token = (os.getenv("TUSHARE_TOKEN") or "").strip()
        if token:
            from .cn_tushare_provider import CnTushareProvider

            registry.register(CnTushareProvider(token=token))
    try:
        from .yfinance_provider import YFinanceProvider

        registry.register(YFinanceProvider())
    except Exception:
        # Optional dependency (yfinance) may be unavailable in minimal env.
        pass

    try:
        from .alpha_vantage_provider import AlphaVantageProvider

        registry.register(AlphaVantageProvider())
    except Exception:
        pass
    registry.register(JuChaoProvider())
    registry.register(StatsCnProvider())
    registry.register(FredProvider())
    registry.register(CnStubProvider())
    return registry
