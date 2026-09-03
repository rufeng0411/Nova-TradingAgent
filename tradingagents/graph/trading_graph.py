# TradingAgents/graph/trading_graph.py

import asyncio
import inspect
import logging
import os
import re
from pathlib import Path
import json
from datetime import date
from typing import Dict, Any, Tuple, List, Optional
import sqlite3

from langgraph.prebuilt import ToolNode
from langgraph.checkpoint.memory import MemorySaver

from tradingagents.llm_clients import create_llm_client

logger = logging.getLogger(__name__)

from tradingagents.default_config import DEFAULT_CONFIG
from tradingagents.agents.utils.memory import FinancialSituationMemory
from tradingagents.agents.utils.agent_states import (
    AgentState,
    InvestDebateState,
    RiskDebateState,
)
from tradingagents.dataflows.config import set_config

# Import the new abstract tool methods from agent_utils
from tradingagents.agents.utils.agent_utils import (
    get_stock_data,
    get_indicators,
    get_fundamentals,
    get_balance_sheet,
    get_cashflow,
    get_income_statement,
    get_news,
    get_insider_transactions,
    get_global_news,
    get_board_fund_flow,
    get_individual_fund_flow,
    get_lhb_detail,
    get_daily_basic,
    get_individual_money_flow_detail,
    get_margin_detail,
    get_hsgt_top10,
    get_opening_auction,
    get_top_list_history,
    get_stk_factor_pro_window,
    get_cyq_perf,
    get_cyq_chips,
    get_l2_orderqueue_window,
    get_fina_indicator,
    get_forecast,
    get_express,
    get_holdernumber_series,
)

from .conditional_logic import ConditionalLogic
from .data_collector import DataCollector
from .intent_parser import parse_intent
from .setup import GraphSetup
from .propagation import Propagator
from .reflection import Reflector
from .signal_processing import SignalProcessor


_langgraph_shared_cp_lock = asyncio.Lock()


def _sqlite_connect_arg(db_path: str) -> str:
    """Return a database location that sqlite3.connect(check_same_thread=False) accepts.

    LangGraph's SqliteSaver.from_conn_string is a context manager; graphs need a real
    SqliteSaver instance with a long-lived connection. We also avoid sqlalchemy-style
    ``sqlite:///C:/...`` strings here because stdlib sqlite3 rejects them without uri=True.
    """
    s = (db_path or "").strip()
    if not s:
        raise ValueError("SQLite checkpointer path is empty")
    if s.lower() == ":memory:":
        return ":memory:"
    if s.startswith("sqlite:///"):
        return s[len("sqlite:///") :]
    if s.startswith("sqlite://"):
        return s[len("sqlite://") :]
    return str(Path(s).expanduser().resolve())


def _langgraph_checkpointer_mode() -> str:
    return (os.getenv("LANGGRAPH_CHECKPOINTER") or "sqlite").strip().lower()


def _sqlite_checkpoint_path() -> str:
    raw_path = (os.getenv("LANGGRAPH_CHECKPOINT_SQLITE") or "").strip()
    if raw_path:
        return raw_path
    base_dir = Path(os.getenv("TA_PROJECT_DIR") or DEFAULT_CONFIG.get("project_dir") or ".").resolve()
    data_dir = base_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    return str(data_dir / "langgraph_checkpoints.sqlite")


def _postgres_checkpoint_uri() -> str:
    uri = (os.getenv("LANGGRAPH_POSTGRES_URI") or "").strip()
    if not uri:
        raise ValueError("LANGGRAPH_POSTGRES_URI is empty")
    # psycopg expects postgresql://... rather than sqlalchemy-style postgresql+psycopg://...
    if uri.startswith("postgresql+psycopg://"):
        base = "postgresql://" + uri[len("postgresql+psycopg://") :]
    elif uri.startswith("postgres+psycopg://"):
        base = "postgres://" + uri[len("postgres+psycopg://") :]
    else:
        base = uri
    # 避免 Postgres 未启动/网络黑洞时整段 lifespan 卡数分钟；可用 LANGGRAPH_PG_CONNECT_TIMEOUT 覆盖（秒）
    ct = _langgraph_pg_connect_timeout_sec()
    if "connect_timeout=" in base.lower():
        return base
    sep = "&" if "?" in base else "?"
    return f"{base}{sep}connect_timeout={ct}"


def _langgraph_pg_connect_timeout_sec() -> int:
    raw = (os.getenv("LANGGRAPH_PG_CONNECT_TIMEOUT") or "12").strip()
    try:
        n = int(raw)
    except ValueError:
        return 12
    return max(2, min(n, 120))


def _build_sync_checkpointer():
    """Sync checkpointer for CLI / threads (invoke/stream). Not compatible with graph.astream on same event loop."""
    mode = _langgraph_checkpointer_mode()
    if mode in ("memory", "mem", "none", "off", "false", "0"):
        logger.info("LangGraph checkpointer: MemorySaver (LANGGRAPH_CHECKPOINTER=%s)", mode)
        return MemorySaver()
    if mode in ("postgres", "pg", "postgresql"):
        try:
            import psycopg
            from langgraph.checkpoint.postgres import PostgresSaver

            conn = psycopg.connect(_postgres_checkpoint_uri(), autocommit=True)
            saver = PostgresSaver(conn)
            saver.setup()
            logger.info("LangGraph checkpointer: PostgresSaver sync")
            return saver
        except Exception as exc:
            logger.warning("LangGraph PostgresSaver unavailable (%s); falling back to sqlite/memory", exc)

    connect_arg = _sqlite_connect_arg(_sqlite_checkpoint_path())
    try:
        from langgraph.checkpoint.sqlite import SqliteSaver

        conn = sqlite3.connect(connect_arg, check_same_thread=False)
        saver = SqliteSaver(conn)
        logger.info("LangGraph checkpointer: SqliteSaver sync (%s)", connect_arg)
        return saver
    except Exception as exc:
        logger.warning("LangGraph SqliteSaver unavailable (%s); using MemorySaver", exc)
        return MemorySaver()


async def init_shared_langgraph_checkpointer_async() -> None:
    """Initialize process-wide LangGraph checkpointer for FastAPI (supports graph.astream).

    Uses AsyncSqliteSaver / AsyncPostgresSaver depending on LANGGRAPH_CHECKPOINTER.
    API async streaming requires async checkpoint I/O. Safe to call multiple times.
    """
    async with _langgraph_shared_cp_lock:
        if TradingAgentsGraph._shared_checkpointer is not None:
            return
        mode = _langgraph_checkpointer_mode()
        if mode in ("memory", "mem", "none", "off", "false", "0"):
            TradingAgentsGraph._shared_checkpointer = MemorySaver()
            logger.info("LangGraph checkpointer: MemorySaver (async API init, LANGGRAPH_CHECKPOINTER=%s)", mode)
            return
        if mode in ("postgres", "pg", "postgresql"):
            try:
                import psycopg
                from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

                conn = await psycopg.AsyncConnection.connect(_postgres_checkpoint_uri(), autocommit=True)
                saver = AsyncPostgresSaver(conn)
                await saver.setup()
                TradingAgentsGraph._shared_checkpointer = saver
                logger.info("LangGraph checkpointer: AsyncPostgresSaver")
                return
            except Exception as exc:
                logger.warning(
                    "LangGraph AsyncPostgresSaver unavailable (%s); "
                    "falling back to AsyncSqlite/Memory (skip sync PostgresSaver in async runtime)",
                    exc,
                )

        connect_arg = _sqlite_connect_arg(_sqlite_checkpoint_path())
        try:
            import aiosqlite
            from langgraph.checkpoint.sqlite.aio import AsyncSqliteSaver

            conn = await aiosqlite.connect(connect_arg)
            TradingAgentsGraph._shared_checkpointer = AsyncSqliteSaver(conn)
            logger.info("LangGraph checkpointer: AsyncSqliteSaver (%s)", connect_arg)
        except Exception as exc:
            logger.warning("LangGraph AsyncSqliteSaver unavailable (%s); using MemorySaver", exc)
            TradingAgentsGraph._shared_checkpointer = MemorySaver()


async def close_shared_langgraph_checkpointer_async() -> None:
    """Close async SQLite connection if present; reset singleton for clean shutdown."""
    async with _langgraph_shared_cp_lock:
        saver = TradingAgentsGraph._shared_checkpointer
        TradingAgentsGraph._shared_checkpointer = None
    if saver is None:
        return
    conn = getattr(saver, "conn", None)
    if conn is None:
        return
    try:
        closer = getattr(conn, "close", None)
        if closer is None:
            return
        out = closer()
        if inspect.isawaitable(out):
            await out
    except Exception as exc:
        logger.debug("LangGraph checkpointer shutdown: %s", exc)


class TradingAgentsGraph:
    """Main class that orchestrates the trading agents framework."""

    # Class-level cache for persistence to handle concurrency
    _shared_checkpointer = None

    def __init__(
        self,
        selected_analysts=["market", "social", "news", "fundamentals", "macro", "smart_money", "volume_price"],
        debug=False,
        config: Dict[str, Any] = None,
        callbacks: Optional[List] = None,
        data_collector: Optional["DataCollector"] = None,
    ):
        """Initialize the trading agents graph and components."""
        self.debug = debug
        self.config = config or DEFAULT_CONFIG
        self.callbacks = callbacks or []

        # Update the interface's config
        set_config(self.config)

        # Initialize persistence (Singleton Pattern for concurrency)
        if TradingAgentsGraph._shared_checkpointer is None:
            TradingAgentsGraph._shared_checkpointer = _build_sync_checkpointer()

        self.checkpointer = TradingAgentsGraph._shared_checkpointer

        # Create necessary directories
        os.makedirs(
            os.path.join(self.config["project_dir"], "dataflows/data_cache"),
            exist_ok=True,
        )

        # Initialize LLMs with provider-specific thinking configuration
        llm_kwargs = self._get_provider_kwargs()

        # Add callbacks to kwargs if provided (passed to LLM constructor)
        if self.callbacks:
            llm_kwargs["callbacks"] = self.callbacks

        deep_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["deep_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )
        quick_client = create_llm_client(
            provider=self.config["llm_provider"],
            model=self.config["quick_think_llm"],
            base_url=self.config.get("backend_url"),
            **llm_kwargs,
        )

        self.deep_thinking_llm = deep_client.get_llm()
        self.quick_thinking_llm = quick_client.get_llm()
        
        # Initialize memories
        self.bull_memory = FinancialSituationMemory("bull_memory", self.config)
        self.bear_memory = FinancialSituationMemory("bear_memory", self.config)
        self.trader_memory = FinancialSituationMemory("trader_memory", self.config)
        self.invest_judge_memory = FinancialSituationMemory("invest_judge_memory", self.config)
        self.risk_manager_memory = FinancialSituationMemory("risk_manager_memory", self.config)

        # Create tool nodes
        self.tool_nodes = self._create_tool_nodes()

        # Data collector — fetches once, shared across dual-horizon runs
        self.data_collector = data_collector if data_collector is not None else DataCollector()

        # Initialize components
        self.conditional_logic = ConditionalLogic(
            max_debate_rounds=self.config.get("max_debate_rounds", 1),
            max_risk_discuss_rounds=self.config.get("max_risk_discuss_rounds", 1),
        )
        self.graph_setup = GraphSetup(
            self.quick_thinking_llm,
            self.deep_thinking_llm,
            self.tool_nodes,
            self.bull_memory,
            self.bear_memory,
            self.trader_memory,
            self.invest_judge_memory,
            self.risk_manager_memory,
            self.conditional_logic,
            data_collector=self.data_collector,
        )

        self.propagator = Propagator(
            max_recur_limit=self.config.get("max_recur_limit", 100)
        )
        self.reflector = Reflector(self.quick_thinking_llm)
        self.signal_processor = SignalProcessor(self.quick_thinking_llm)

        # State tracking
        self.curr_state = None
        self.ticker = None
        self.log_states_dict = {}  # date to full state dict

        # Set up the graph with checkpointer
        self.graph = self.graph_setup.setup_graph(selected_analysts, checkpointer=self.checkpointer)

    def get_state(self, thread_id: str):
        """Retrieve the current state for a given thread_id."""
        config = {"configurable": {"thread_id": thread_id}}
        return self.graph.get_state(config)

    def _get_provider_kwargs(self) -> Dict[str, Any]:
        """Get provider-specific kwargs for LLM client creation."""
        kwargs = {}
        provider = self.config.get("llm_provider", "").lower()

        if provider == "google":
            thinking_level = self.config.get("google_thinking_level")
            if thinking_level:
                kwargs["thinking_level"] = thinking_level
            api_key = self.config.get("api_key")
            if api_key:
                kwargs["api_key"] = api_key

        elif provider == "openai":
            reasoning_effort = self.config.get("openai_reasoning_effort")
            if reasoning_effort:
                kwargs["reasoning_effort"] = reasoning_effort
            api_key = self.config.get("api_key")
            if api_key:
                kwargs["api_key"] = api_key

        elif provider == "anthropic":
            api_key = self.config.get("api_key")
            if api_key:
                kwargs["api_key"] = api_key
            effort = self.config.get("anthropic_effort")
            if effort:
                kwargs["effort"] = effort

        return kwargs

    def _create_tool_nodes(self) -> Dict[str, ToolNode]:
        """Create tool nodes for different data sources using abstract methods."""
        return {
            "market": ToolNode(
                [
                    # Core stock data tools
                    get_stock_data,
                    # Technical indicators
                    get_indicators,
                ]
            ),
            "social": ToolNode(
                [
                    # News tools for social media analysis
                    get_news,
                ]
            ),
            "news": ToolNode(
                [
                    # News and insider information
                    get_news,
                    get_global_news,
                    get_insider_transactions,
                ]
            ),
            "fundamentals": ToolNode(
                [
                    # Fundamental analysis tools
                    get_fundamentals,
                    get_balance_sheet,
                    get_cashflow,
                    get_income_statement,
                    get_fina_indicator,
                    get_forecast,
                    get_express,
                    get_holdernumber_series,
                ]
            ),
            "macro": ToolNode(
                [
                    # Macro analyst tools
                    get_board_fund_flow,
                    get_news,
                ]
            ),
            "smart_money": ToolNode(
                [
                    # Smart money analyst tools
                    get_individual_fund_flow,
                    get_lhb_detail,
                    get_individual_money_flow_detail,
                    get_margin_detail,
                    get_hsgt_top10,
                    get_opening_auction,
                    get_top_list_history,
                    get_indicators,
                ]
            ),
            "volume_price": ToolNode(
                [
                    # Volume price analyst tools (fallback, normally uses data_collector)
                    get_stock_data,
                    get_stk_factor_pro_window,
                    get_cyq_perf,
                    get_cyq_chips,
                    get_l2_orderqueue_window,
                    get_daily_basic,
                ]
            ),
        }

    def propagate(
        self,
        company_name,
        trade_date,
        user_context: Optional[Dict[str, Any]] = None,
        selected_analysts: Optional[List[str]] = None,
        request_source: str = "api",
        thread_id: Optional[str] = None,
        resume_from_checkpoint: bool = False,
    ):
        """Run the trading agents graph for a company on a specific date."""

        self.ticker = company_name

        from api.services import symbol_service

        canon = symbol_service.normalize_symbol(str(company_name or "").strip()) or str(company_name or "").strip()

        # Initialize state
        init_agent_state = self.propagator.create_initial_state(
            canon,
            trade_date,
            user_context=user_context,
            selected_analysts=selected_analysts,
            request_source=request_source,
        )
        args = self.propagator.get_graph_args()

        # Use thread_id for checkpointer
        if thread_id:
            args["config"]["configurable"] = {"thread_id": thread_id}
        elif not args["config"].get("configurable"):
            # Default fallback for standalone runs
            args["config"]["configurable"] = {"thread_id": f"{canon}_{trade_date}"}

        invoke_input: Any = init_agent_state
        if thread_id and resume_from_checkpoint:
            try:
                st = self.graph.get_state(args["config"])
                if st is not None and getattr(st, "values", None):
                    invoke_input = None
                    logger.info(
                        "[LangGraph] propagate resume_from_checkpoint thread_id=%s",
                        thread_id,
                    )
            except Exception as exc:
                logger.debug("propagate resume checkpoint probe failed: %s", exc)
                invoke_input = init_agent_state

        if self.debug:
            # Debug mode with tracing
            trace = []
            for chunk in self.graph.stream(invoke_input, **args):
                if len(chunk["messages"]) == 0:
                    pass
                else:
                    chunk["messages"][-1].pretty_print()
                    trace.append(chunk)

            final_state = trace[-1]
        else:
            # Standard mode without tracing
            final_state = self.graph.invoke(invoke_input, **args)

        # Store current state for reflection
        self.curr_state = final_state

        # Log state
        self._log_state(trade_date, final_state)

        # Return decision and processed signal
        return final_state, self.process_signal(final_state["final_trade_decision"])

    async def propagate_async(
        self,
        company_name: str,
        trade_date: str,
        query: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Run a single integrated analysis.

        Each analyst uses its own natural time window (technical/funds → short,
        fundamentals/macro → medium). The graph runs once; Research Manager
        synthesizes both short and long term perspectives.

        Returns a dict with short_term result and user_intent.
        """
        self.ticker = company_name

        # Parse intent from query, or build a minimal intent from ticker alone
        if query:
            user_intent = parse_intent(query, self.quick_thinking_llm, fallback_ticker=company_name)
            ticker = user_intent.get("ticker") or company_name
        else:
            ticker = company_name
            user_intent = {
                "raw_query": "",
                "ticker": ticker,
                "horizons": ["short"],
                "focus_areas": [],
                "specific_questions": [],
                "user_context": {},
            }

        from api.services import symbol_service

        canon_ticker = symbol_service.normalize_symbol(str(ticker or "").strip()) or str(ticker or "").strip()
        user_intent["ticker"] = canon_ticker

        # Pre-collect data once (always full data); analysts will read from cache
        print(f"[TradingAgentsGraph] Collecting data for {canon_ticker} {trade_date}…")
        self.data_collector.collect(canon_ticker, trade_date)

        graph_args = self.propagator.get_graph_args()

        state = self.propagator.create_initial_state(
            canon_ticker, trade_date, user_intent=user_intent, horizon="short"
        )
        final_state = await self.graph.ainvoke(state, **graph_args)

        # Evict cached data to free memory
        self.data_collector.evict(canon_ticker, trade_date)

        result = self._build_horizon_result("short", final_state)

        self._log_state_dual(trade_date, result, {}, user_intent)

        return {
            "short_term": result,
            "medium_term": None,
            "user_intent": user_intent,
        }

    def _build_horizon_result(self, horizon: str, final_state: Dict[str, Any]) -> Dict[str, Any]:
        """Extract a compact result dict from a completed graph state."""
        return {
            "horizon": horizon,
            "company_of_interest": final_state.get("company_of_interest", ""),
            "trade_date": final_state.get("trade_date", ""),
            "final_trade_decision": final_state.get("final_trade_decision", ""),
            "investment_plan": final_state.get("investment_plan", ""),
            "trader_investment_plan": final_state.get("trader_investment_plan", ""),
            "analyst_traces": final_state.get("analyst_traces", []),
            "market_report": final_state.get("market_report", ""),
            "sentiment_report": final_state.get("sentiment_report", ""),
            "news_report": final_state.get("news_report", ""),
            "fundamentals_report": final_state.get("fundamentals_report", ""),
            "macro_report": final_state.get("macro_report", ""),
            "smart_money_report": final_state.get("smart_money_report", ""),
            "volume_price_report": final_state.get("volume_price_report", ""),
        }

    @staticmethod
    def _safe_ticker(ticker: str) -> str:
        """Sanitize ticker for use in filesystem paths."""
        from tradingagents.dataflows.utils import safe_ticker_component

        try:
            return safe_ticker_component(ticker)
        except ValueError:
            return re.sub(r"[^A-Za-z0-9._-]", "_", ticker or "") or "unknown"

    def _log_state_dual(
        self,
        trade_date: str,
        short_result: Dict[str, Any],
        medium_result: Dict[str, Any],
        user_intent: Dict[str, Any],
    ) -> None:
        """Log dual-horizon results to a JSON file."""
        ticker = self._safe_ticker(
            short_result.get("company_of_interest") or self.ticker or "unknown"
        )
        entry = {
            "user_intent": user_intent,
            "short_term": short_result,
            "medium_term": medium_result,
        }
        self.log_states_dict[str(trade_date)] = entry

        directory = Path(f"eval_results/{ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)
        with open(
            f"eval_results/{ticker}/TradingAgentsStrategy_logs/dual_horizon_{trade_date}.json",
            "w",
        ) as f:
            json.dump(entry, f, indent=4, ensure_ascii=False)

    def _log_state(self, trade_date, final_state):
        """Log the final state to a JSON file."""
        self.log_states_dict[str(trade_date)] = {
            "company_of_interest": final_state["company_of_interest"],
            "trade_date": final_state["trade_date"],
            "instrument_context": final_state.get("instrument_context", {}),
            "market_context": final_state.get("market_context", {}),
            "user_context": final_state.get("user_context", {}),
            "workflow_context": final_state.get("workflow_context", {}),
            "market_report": final_state["market_report"],
            "sentiment_report": final_state["sentiment_report"],
            "news_report": final_state["news_report"],
            "fundamentals_report": final_state["fundamentals_report"],
            "macro_report": final_state.get("macro_report", ""),
            "smart_money_report": final_state.get("smart_money_report", ""),
            "volume_price_report": final_state.get("volume_price_report", ""),
            "investment_debate_state": {
                "bull_history": final_state["investment_debate_state"]["bull_history"],
                "bear_history": final_state["investment_debate_state"]["bear_history"],
                "history": final_state["investment_debate_state"]["history"],
                "current_speaker": final_state["investment_debate_state"].get("current_speaker", ""),
                "current_response": final_state["investment_debate_state"][
                    "current_response"
                ],
                "judge_decision": final_state["investment_debate_state"][
                    "judge_decision"
                ],
                "claims": final_state["investment_debate_state"].get("claims", []),
                "focus_claim_ids": final_state["investment_debate_state"].get("focus_claim_ids", []),
                "open_claim_ids": final_state["investment_debate_state"].get("open_claim_ids", []),
                "resolved_claim_ids": final_state["investment_debate_state"].get("resolved_claim_ids", []),
                "unresolved_claim_ids": final_state["investment_debate_state"].get("unresolved_claim_ids", []),
                "round_summary": final_state["investment_debate_state"].get("round_summary", ""),
                "round_goal": final_state["investment_debate_state"].get("round_goal", ""),
            },
            "trader_investment_decision": final_state["trader_investment_plan"],
            "risk_debate_state": {
                "aggressive_history": final_state["risk_debate_state"]["aggressive_history"],
                "conservative_history": final_state["risk_debate_state"]["conservative_history"],
                "neutral_history": final_state["risk_debate_state"]["neutral_history"],
                "history": final_state["risk_debate_state"]["history"],
                "judge_decision": final_state["risk_debate_state"]["judge_decision"],
                "claims": final_state["risk_debate_state"].get("claims", []),
                "focus_claim_ids": final_state["risk_debate_state"].get("focus_claim_ids", []),
                "open_claim_ids": final_state["risk_debate_state"].get("open_claim_ids", []),
                "resolved_claim_ids": final_state["risk_debate_state"].get("resolved_claim_ids", []),
                "unresolved_claim_ids": final_state["risk_debate_state"].get("unresolved_claim_ids", []),
                "round_summary": final_state["risk_debate_state"].get("round_summary", ""),
                "round_goal": final_state["risk_debate_state"].get("round_goal", ""),
            },
            "risk_feedback_state": final_state.get("risk_feedback_state", {}),
            "investment_plan": final_state["investment_plan"],
            "final_trade_decision": final_state["final_trade_decision"],
        }

        # Save to file
        safe_ticker = self._safe_ticker(self.ticker or "unknown")
        directory = Path(f"eval_results/{safe_ticker}/TradingAgentsStrategy_logs/")
        directory.mkdir(parents=True, exist_ok=True)

        with open(
            f"eval_results/{safe_ticker}/TradingAgentsStrategy_logs/full_states_log_{trade_date}.json",
            "w",
        ) as f:
            json.dump(self.log_states_dict, f, indent=4)

    def reflect_and_remember(self, returns_losses):
        """Reflect on decisions and update memory based on returns."""
        self.reflector.reflect_bull_researcher(
            self.curr_state, returns_losses, self.bull_memory
        )
        self.reflector.reflect_bear_researcher(
            self.curr_state, returns_losses, self.bear_memory
        )
        self.reflector.reflect_trader(
            self.curr_state, returns_losses, self.trader_memory
        )
        self.reflector.reflect_invest_judge(
            self.curr_state, returns_losses, self.invest_judge_memory
        )
        self.reflector.reflect_risk_manager(
            self.curr_state, returns_losses, self.risk_manager_memory
        )

    def process_signal(self, full_signal):
        """Process a signal to extract the core decision."""
        return self.signal_processor.process_signal(full_signal)
