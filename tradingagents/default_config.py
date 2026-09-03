import os

_TIER3_ON = os.getenv("TA_DATASOURCE_TIER3_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TUSHARE_READY = (
    _TIER3_ON
    and os.getenv("TA_TUSHARE_REGISTER", "0").strip().lower() in ("1", "true", "yes", "on")
    and bool((os.getenv("TUSHARE_TOKEN") or "").strip())
)
_CORE_STOCK_CHAIN = "cn_tushare,cn_akshare,cn_baostock,yfinance" if _TUSHARE_READY else "cn_akshare,cn_baostock,yfinance"
_FUND_CHAIN = "cn_tushare,cn_akshare,cn_baostock,yfinance" if _TUSHARE_READY else "cn_akshare,cn_baostock,yfinance"
_VALUATION_CHAIN = "cn_tushare,cn_akshare,cn_baostock" if _TUSHARE_READY else "cn_akshare,cn_baostock"
_CN_MARKET_CHAIN = "cn_tushare,cn_akshare" if _TUSHARE_READY else "cn_akshare"
_FACTOR_CHAIN = "cn_tushare" if _TUSHARE_READY else "cn_akshare"
_L2_CHAIN = "cn_tushare" if _TUSHARE_READY else "cn_akshare"
_TS_AUCTION_ENABLED = os.getenv("TA_TS_AUCTION_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_CYQ_ENABLED = os.getenv("TA_TS_CYQ_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_MONEYFLOW_ENABLED = os.getenv("TA_TS_MONEYFLOW_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_FACTOR_PRO_ENABLED = os.getenv("TA_TS_FACTOR_PRO_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_LIMIT_ENABLED = os.getenv("TA_TS_LIMIT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_TOPLIST_ENABLED = os.getenv("TA_TS_TOPLIST_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_HSGT_ENABLED = os.getenv("TA_TS_HSGT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")
_TS_FIN_EVENT_ENABLED = os.getenv("TA_TS_FIN_EVENT_ENABLED", "0").strip().lower() in ("1", "true", "yes", "on")

DEFAULT_CONFIG = {
    "project_dir": os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
    "results_dir": os.getenv("TA_RESULTS_DIR", "./results"),
    "data_cache_dir": os.path.join(
        os.path.abspath(os.path.join(os.path.dirname(__file__), ".")),
        "dataflows/data_cache",
    ),
    # LLM settings
    "llm_provider": os.getenv("TA_LLM_PROVIDER", "openai"),
    "deep_think_llm": os.getenv("TA_LLM_DEEP", "gpt-4o"),
    "quick_think_llm": os.getenv("TA_LLM_QUICK", "gpt-4o-mini"),
    "backend_url": os.getenv("TA_BASE_URL", "https://api.openai.com/v1"),
    "api_key": os.getenv("TA_API_KEY", ""),
    
    # Provider-specific thinking configuration
    "google_thinking_level": None,      # "high", "minimal", etc.
    "openai_reasoning_effort": None,    # "medium", "high", "low"
    
    # Debate and discussion settings
    "max_debate_rounds": int(os.getenv("TA_MAX_DEBATE") or "2"),
    "max_risk_discuss_rounds": int(os.getenv("TA_MAX_RISK") or "1"),
    "max_recur_limit": 100,
    
    # Prompt language control: zh, en, or auto
    "prompt_language": os.getenv("TA_LANGUAGE", "zh"),
    "prompt_language_by_provider": {},
    
    # Provider routing trace logs
    "provider_trace": os.getenv("TA_TRACE", "1").lower() in ("1", "true", "yes", "on"),
    
    # Data vendor configuration
    "data_vendors": {
        "core_stock_apis": _CORE_STOCK_CHAIN,
        "technical_indicators": "cn_akshare,cn_baostock,yfinance",
        "fundamental_data": _FUND_CHAIN,
        "news_data": "cn_akshare,cn_baostock,yfinance",
        "realtime_data": "cn_akshare",
        "cn_market_data": _CN_MARKET_CHAIN,
        "valuation_data": _VALUATION_CHAIN,
        "factor_data": _FACTOR_CHAIN,
        "l2_data": _L2_CHAIN,
    },
    "tool_vendors": {
        # A股日线RT 仅由 Tushare 提供，避免每次先尝试不支持的 provider
        "fetch_rt_daily_bar_df": "cn_tushare",
        **({"fetch_stk_auction": "cn_tushare"} if _TS_AUCTION_ENABLED else {}),
        **({"fetch_cyq_perf_df": "cn_tushare", "fetch_cyq_chips_df": "cn_tushare"} if _TS_CYQ_ENABLED else {}),
        **({"fetch_individual_moneyflow_df": "cn_tushare"} if _TS_MONEYFLOW_ENABLED else {}),
        **({"fetch_stk_factor_pro_df": "cn_tushare"} if _TS_FACTOR_PRO_ENABLED else {}),
        **({"fetch_limit_list_d": "cn_tushare"} if _TS_LIMIT_ENABLED else {}),
        **({"fetch_top_list_df": "cn_tushare", "fetch_block_trade_df": "cn_tushare"} if _TS_TOPLIST_ENABLED else {}),
        **({"fetch_north_money_df": "cn_tushare", "fetch_hsgt_top10_df": "cn_tushare"} if _TS_HSGT_ENABLED else {}),
        **(
            {
                "fetch_daily_basic_df": "cn_tushare",
                "fetch_forecast_df": "cn_tushare",
                "fetch_express_df": "cn_tushare",
                "fetch_dividend_df": "cn_tushare",
                "fetch_stk_holdertrade_df": "cn_tushare",
            }
            if _TS_FIN_EVENT_ENABLED
            else {}
        ),
    },
}

# --- Upgrade feature flags (default off) ---
_UPGRADE_LLM_CATALOG = os.getenv("TA_UPGRADE_LLM_CATALOG", "0").strip().lower() in ("1", "true", "yes", "on")
_UPGRADE_STRUCTURED = os.getenv("TA_UPGRADE_STRUCTURED_OUTPUT", "0").strip().lower() in ("1", "true", "yes", "on")
_UPGRADE_MEMORY = os.getenv("TA_UPGRADE_PERSISTENT_MEMORY", "0").strip().lower() in ("1", "true", "yes", "on")
_UPGRADE_CHECKPOINT_UI = os.getenv("TA_UPGRADE_CHECKPOINT_UI", "0").strip().lower() in ("1", "true", "yes", "on")

DEFAULT_CONFIG.update(
    {
        "output_language": os.getenv("TA_OUTPUT_LANGUAGE")
        or os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE")
        or "Simplified Chinese",
        "benchmark_ticker": os.getenv("TA_BENCHMARK_TICKER", "000300.SH"),
        "benchmark_map": {
            ".SH": "000300.SH",
            ".SZ": "000300.SH",
            ".BJ": "000300.SH",
            ".HK": "^HSI",
            ".T": "^N225",
            ".L": "^FTSE",
            "": "SPY",
        },
        "memory_log_path": os.getenv(
            "TA_MEMORY_LOG_PATH",
            os.path.expanduser("~/.tradingagents/memory/trading_memory.md"),
        ),
        "memory_log_max_entries": int(os.getenv("TA_MEMORY_LOG_MAX_ENTRIES") or "200"),
        "memory_log_inject_max_chars": int(os.getenv("TA_MEMORY_LOG_INJECT_MAX_CHARS") or "8000"),
        "news_article_limit": int(os.getenv("TA_NEWS_ARTICLE_LIMIT") or "20"),
        "global_news_article_limit": int(os.getenv("TA_GLOBAL_NEWS_ARTICLE_LIMIT") or "10"),
        "global_news_lookback_days": int(os.getenv("TA_GLOBAL_NEWS_LOOKBACK_DAYS") or "7"),
        "global_news_queries": [
            "央行利率",
            "GDP 经济展望",
            "中美贸易",
            "产业链",
            "监管政策",
        ],
        "checkpoint_enabled": os.getenv("TA_CHECKPOINT_ENABLED", "1").strip().lower()
        in ("1", "true", "yes", "on"),
        "analyst_concurrency_limit": int(os.getenv("TA_ANALYST_CONCURRENCY_LIMIT") or "3"),
        "anthropic_effort": os.getenv("TA_ANTHROPIC_EFFORT") or os.getenv("TRADINGAGENTS_ANTHROPIC_EFFORT"),
        "llm_region": os.getenv("TA_LLM_REGION", "cn"),
        "upgrade_llm_catalog": _UPGRADE_LLM_CATALOG,
        "upgrade_structured_output": _UPGRADE_STRUCTURED,
        "upgrade_persistent_memory": _UPGRADE_MEMORY,
        "upgrade_checkpoint_ui": _UPGRADE_CHECKPOINT_UI,
    }
)


def _env_chain(ta_key: str, upstream_key: str, default: str) -> str:
    return (os.getenv(ta_key) or os.getenv(upstream_key) or default).strip()


def apply_env_overrides(config: dict | None = None) -> dict:
    """Apply TA_* > TRADINGAGENTS_* > defaults priority chain."""
    cfg = dict(config or DEFAULT_CONFIG)
    cfg["llm_provider"] = _env_chain("TA_LLM_PROVIDER", "TRADINGAGENTS_LLM_PROVIDER", cfg.get("llm_provider", "openai"))
    cfg["deep_think_llm"] = _env_chain("TA_LLM_DEEP", "TRADINGAGENTS_DEEP_THINK_LLM", cfg.get("deep_think_llm", "gpt-4o"))
    cfg["quick_think_llm"] = _env_chain("TA_LLM_QUICK", "TRADINGAGENTS_QUICK_THINK_LLM", cfg.get("quick_think_llm", "gpt-4o-mini"))
    backend = os.getenv("TA_BASE_URL") or os.getenv("TRADINGAGENTS_LLM_BACKEND_URL")
    if backend:
        cfg["backend_url"] = backend
    lang = os.getenv("TA_LANGUAGE") or os.getenv("TRADINGAGENTS_OUTPUT_LANGUAGE")
    if lang:
        cfg["prompt_language"] = lang
    if os.getenv("TA_MAX_DEBATE") or os.getenv("TRADINGAGENTS_MAX_DEBATE_ROUNDS"):
        cfg["max_debate_rounds"] = int(_env_chain("TA_MAX_DEBATE", "TRADINGAGENTS_MAX_DEBATE_ROUNDS", str(cfg.get("max_debate_rounds", 2))))
    if os.getenv("TA_MAX_RISK") or os.getenv("TRADINGAGENTS_MAX_RISK_ROUNDS"):
        cfg["max_risk_discuss_rounds"] = int(_env_chain("TA_MAX_RISK", "TRADINGAGENTS_MAX_RISK_ROUNDS", str(cfg.get("max_risk_discuss_rounds", 1))))
    return cfg
