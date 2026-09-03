// Agent Types
export type AgentStatus = 'pending' | 'in_progress' | 'completed' | 'error' | 'skipped'

export interface Agent {
    id: string
    name: string
    team: string
    status: AgentStatus
    description?: string
    startedAt?: number
    finishedAt?: number
}

export interface AgentTeam {
    name: string
    agents: Agent[]
}

// Analysis Types
export interface InstrumentContext {
    symbol: string
    security_name: string
    market_country: string
    exchange: string
    currency: string
    asset_type: string
    display_label?: string
}

export interface MarketContext {
    trade_date: string
    timezone: string
    market_country: string
    exchange: string
    market_session: string
    market_is_open: boolean
    analysis_mode: string
    data_as_of: string
    session_note: string
}

export interface UserContext {
    objective?: string
    risk_profile?: string
    investment_horizon?: string
    cash_available?: number
    current_position?: number
    current_position_pct?: number
    average_cost?: number
    max_loss_pct?: number
    constraints?: string[]
    user_notes?: string
}

export interface WorkflowContext {
    context_version: string
    request_source: string
    selected_analysts: string[]
}

export interface GameTheorySignals {
    board?: string
    players?: string[]
    player_states?: Record<string, string>
    likely_actions?: Record<string, string[]>
    dominant_strategy?: string
    fragile_equilibrium?: string
    counter_consensus_signal?: string
    confidence?: number
}

export interface RiskFeedbackState {
    retry_count: number
    max_retries: number
    revision_required: boolean
    latest_risk_verdict: string
    hard_constraints: string[]
    soft_constraints: string[]
    execution_preconditions: string[]
    de_risk_triggers: string[]
    revision_reason: string
}

export interface AnalysisRequest {
    symbol: string
    trade_date: string
    selected_analysts: string[]
    objective?: string
    risk_profile?: string
    investment_horizon?: string
    cash_available?: number
    current_position?: number
    current_position_pct?: number
    average_cost?: number
    max_loss_pct?: number
    constraints?: string[]
    user_notes?: string
    config_overrides?: Record<string, unknown>
    dry_run?: boolean
}

export interface AnalysisResponse {
    job_id: string
    status: 'pending' | 'queued' | 'paused' | 'running' | 'completed' | 'failed'
    created_at: string
}

export interface JobStatus {
    job_id: string
    status: 'pending' | 'queued' | 'paused' | 'running' | 'completed' | 'failed'
    created_at: string
    started_at?: string
    finished_at?: string
    symbol: string
    trade_date: string
    error?: string
    waiting_ahead_count?: number | null
    scheduled_running_count?: number | null
    scheduled_concurrency_limit?: number | null
    display_label?: string | null
}

export interface TaskCenterItem {
    job_id: string
    task_kind: string
    task_name: string
    description?: string | null
    symbol?: string | null
    trade_date?: string | null
    status: 'queued' | 'paused' | 'running' | 'completed' | 'failed'
    queue_status?: 'queued' | 'paused' | null
    created_at?: string | null
    updated_at?: string | null
    error?: string | null
    waiting_ahead_count?: number | null
}

export interface TaskCenterListResponse {
    running: TaskCenterItem[]
    queued: TaskCenterItem[]
    recent: TaskCenterItem[]
}

export interface TaskSubmitResponse {
    job_id: string
    status: 'pending' | 'queued' | 'rejected' | 'failed'
    symbol?: string | null
    trade_date?: string | null
    task_label?: string | null
    waiting_ahead_count: number
    message?: string | null
}

export interface FastAnalyzeRequest {
    symbol: string
    intent_hint?: string
    current_position?: {
        shares?: number
        avg_cost?: number
        portfolio_pct?: number
        available_cash_pct?: number
    }
    risk_profile?: 'conservative' | 'balanced' | 'aggressive'
    include_market_context?: boolean
    model_override?: string | null
}

export interface FastAnalyzeResponse {
    fast_analysis_id: string
    job_id: string
    status: 'pending' | 'queued' | 'running' | 'succeeded' | 'degraded' | 'failed'
}

export interface FastRiskProfile {
    risk_profile: 'conservative' | 'balanced' | 'aggressive'
    fast_model?: string | null
}

export interface FastAnalysisDetail {
    id: string
    status: string
    symbol: string
    symbol_name?: string | null
    trade_date: string
    created_at?: string | null
    finished_at?: string | null
    elapsed_ms?: number | null
    request_context_json: Record<string, unknown>
    snapshot_json: Record<string, unknown>
    features_json: Record<string, unknown>
    kline_features_json: Record<string, unknown>
    verdict_json: Record<string, unknown>
    time_phased_json: Record<string, unknown>
    position_advice_json: Record<string, unknown>
    executability_json: Record<string, unknown>
    kline_insight_json: Record<string, unknown>
}

// SSE Event Types
export type SSEEventType =
    | 'job.created'
    | 'job.running'
    | 'job.completed'
    | 'job.failed'
    | 'agent.status'
    | 'agent.message'
    | 'agent.tool_call'
    | 'agent.report'
    | 'agent.report.chunk'
    | 'agent.snapshot'
    | 'agent.milestone'
    | 'agent.writing'
    | 'agent.activity'
    | 'agent.activity_complete'
    | 'agent.token'
    | 'agent.debate'
    | 'agent.debate.token'

export interface SSEEvent {
    event: SSEEventType
    data: Record<string, unknown>
    timestamp: string
}

export interface AgentStatusEvent {
    agent: string
    status: AgentStatus
    previous_status?: AgentStatus
}

export interface AgentMessageEvent {
    agent: string | null
    message_type: string | null
    content: string
}

export interface AgentToolCallEvent {
    agent: string | null
    tool_call: {
        name: string
        args: Record<string, unknown>
    }
}

export interface AgentReportEvent {
    section: string
    content: string
}

export interface ReportChunkEvent {
    section: string
    chunk: string
    index: number
    is_complete: boolean
    /** dual_horizon 路径下后端会带上当前周期，前端用于 fallback 找回 owner agent 的占位气泡 */
    horizon?: string | null
}

export interface AgentMilestoneEvent {
    stage: string
    title: string
    summary: string
    timestamp: string
}

export interface AgentToolCallDisplayEvent {
    agent: string
    tool: string
    description: string
}

export interface AgentWritingEvent {
    agent: string
    report: string
    report_name: string
    status: 'writing' | 'completed'
}

export interface AgentTokenEvent {
    agent: string
    report: string
    token: string
    horizon?: string
}

export interface AgentActivityEvent {
    agent: string
    type: 'data_fetch' | 'data_analysis' | 'writing' | 'thinking'
    details: string
    tools?: string[]
    is_update?: boolean
}

export interface AgentActivityCompleteEvent {
    agent: string
    type: string
}

export interface AgentSnapshotEvent {
    agents: Array<{
        team: string
        agent: string
        status: AgentStatus
    }>
}

// Streaming Report State
export interface StreamingSectionState {
    buffer: string
    displayed: string
    isTyping: boolean
    isComplete: boolean
}

export interface MilestoneMessage {
    id: string
    stage: string
    title: string
    summary: string
    timestamp: string
}

export type DataSourceStatus =
    | 'hit'
    | 'fallback'
    | 'error'
    | 'internal'
    | 'skipped'
    | 'unsupported_channel'
    | 'hint'

export interface DataSourceItem {
    key: string
    display_name: string
    category: string
    vendor: string | null
    vendor_display?: string
    vendor_site?: string
    status: DataSourceStatus
    fetched_at: string
    latency_ms: number | null
    fallback_chain?: string[]
    error?: string | null
    /** 后端采集的文本预览（Markdown/CSV/JSON），用于弹窗内折叠展示 */
    detail_preview?: string | null
    /** 路由方法名，如 get_daily_basic */
    method?: string | null
}

export interface DataSourceBundle {
    generated_at: string
    total_latency_ms: number
    items: DataSourceItem[]
}

// Report Types
export interface AnalysisReport {
    symbol: string
    trade_date: string
    decision?: string
    direction?: string
    instrument_context?: InstrumentContext
    market_context?: MarketContext
    user_context?: UserContext
    workflow_context?: WorkflowContext
    market_report?: string
    sentiment_report?: string
    news_report?: string
    fundamentals_report?: string
    macro_report?: string
    smart_money_report?: string
    volume_price_report?: string
    game_theory_report?: string
    game_theory_signals?: GameTheorySignals
    investment_plan?: string
    trader_investment_plan?: string
    risk_feedback_state?: RiskFeedbackState
    final_trade_decision?: string
    /** 后端 LLM 生成的要点梳理（约 300–400 字） */
    final_decision_summary?: string | null
    data_sources?: DataSourceBundle
    derived_signals?: Record<string, unknown>
}

// UI Types
export interface LogEntry {
    id: string
    timestamp: string
    type: 'system' | 'agent' | 'tool' | 'data' | 'error'
    content: string
    agent?: string
}

export interface StockInfo {
    symbol: string
    name: string
    price: number
    change: number
    changePercent: number
}

export interface KlineCandle {
    date: string
    open: number
    high: number
    low: number
    close: number
    volume?: number | null
    amount?: number | null
    change?: number | null
    change_percent?: number | null
    turnover_rate?: number | null
}

export interface KlineResponse {
    symbol: string
    display_label?: string | null
    start_date: string
    end_date: string
    candles: KlineCandle[]
}

export interface RealtimeQuote {
    price?: number | null
    open?: number | null
    high?: number | null
    low?: number | null
    previous_close?: number | null
    change?: number | null
    change_pct?: number | null
    volume?: number | null
    amount?: number | null
    quote_time?: string | null
    source?: string | null
}

export interface RealtimeQuoteResponse {
    quotes: Record<string, RealtimeQuote>
    missing: string[]
    cache_ttl_seconds: number
}

export type KlinePeriod = '1d' | '1w' | '1mo'
export type KlineAdjust = 'none' | 'qfq' | 'hfq'
export type ChartRangePreset = '1M' | '3M' | '6M' | 'YTD' | '1Y' | '3Y' | '5Y' | 'ALL'
export type SubChartType =
    | 'macd'
    | 'kdj'
    | 'rsi'
    | 'atr'
    | 'obv'
    | 'moneyflow'
    | 'hsgt_flow'
    | 'chip_distribution'
    | 'none'

export type ChartBias = 'bullish' | 'bearish' | 'neutral'

export type ChartMarkerType =
    | 'golden_cross'
    | 'death_cross'
    | 'breakout'
    | 'breakdown'
    | 'support'
    | 'resistance'
    | 'divergence'

export interface ChartInsightSection {
    title: string
    points: string[]
    novice_hint?: string
}

export interface ChartInsightMarker {
    time: string
    type: ChartMarkerType
    price?: number
    label: string
}

export interface ChartInsightResult {
    summary_plain: string
    bias: ChartBias
    bias_confidence: number
    sections: {
        trend: ChartInsightSection
        moving_average: ChartInsightSection
        volume: ChartInsightSection
        momentum: ChartInsightSection
        volatility: ChartInsightSection
        pattern: ChartInsightSection
        support_resistance: ChartInsightSection
    }
    levels: {
        supports: number[]
        resistances: number[]
    }
    markers: ChartInsightMarker[]
    risks: string[]
    opportunities: string[]
    glossary: Record<string, string>
}

export interface ChartInsightResponsePayload {
    insight: ChartInsightResult
    fallback_only?: boolean
    cached?: boolean
}

export interface ChartInsightRequestPayload {
    symbol: string
    period?: KlinePeriod
    adjust?: KlineAdjust
    start_date?: string
    end_date?: string
    selected_indicators?: string[]
    level?: 'brief' | 'normal' | 'deep'
    language?: 'zh' | 'en'
    bypass_cache?: boolean
    /** basic：仅 K 线特征；advanced：并入分时/盘口等摘要（需高级 VIP 权益） */
    context_level?: 'basic' | 'advanced'
}

export interface UserEntitlements {
    advanced_market: boolean
    tushare_rt?: boolean
    tushare_pro?: boolean
    fast_analysis?: boolean
    role: string
}

export interface RtDailyQuoteItem {
    name?: string | null
    pre_close?: number | null
    open?: number | null
    high?: number | null
    low?: number | null
    close?: number | null
    vol?: number | null
    amount?: number | null
    num?: number | null
    ask_price1?: number | null
    ask_volume1?: number | null
    bid_price1?: number | null
    bid_volume1?: number | null
    trade_time?: string | null
    change?: number | null
    change_pct?: number | null
    source?: string | null
}

export interface RtDailyResponse {
    quotes: Record<string, RtDailyQuoteItem>
    missing: string[]
    cache_ttl_seconds: number
}

export interface RtBoardResponse {
    pattern: string
    sort: 'change_pct' | 'change' | 'amount' | 'vol' | string
    limit: number
    items: Array<Record<string, unknown>>
}

export interface ChartSeriesResponse {
    enabled: boolean
    symbol: string
    snapshot?: Record<string, unknown> | null
    items: Array<Record<string, unknown>>
    market?: Array<Record<string, unknown>>
}

export interface ChartAuctionResponse {
    enabled: boolean
    symbol: string
    snapshot?: Record<string, unknown> | null
}

export interface ChartCyqResponse {
    enabled: boolean
    symbol: string
    trade_date?: string | null
    summary?: Record<string, unknown> | null
    distribution: Array<{ price: number; ratio: number }>
}

export interface RiskItem {
    name: string
    level: 'high' | 'medium' | 'low'
    description?: string
}

export interface KeyMetric {
    name: string
    value: string
    status: 'good' | 'neutral' | 'bad'
}

// Report Types (from database)
export interface Report {
    id: string
    user_id?: string
    task_kind?: string | null
    symbol: string
    name?: string
    display_label?: string | null
    trade_date: string
    status: 'pending' | 'running' | 'completed' | 'failed'
    error?: string
    decision?: string
    direction?: string
    rating_5tier?: string | null
    confidence?: number
    target_price?: number
    stop_loss_price?: number
    analysis_price?: number | null
    analysis_price_time?: string | null
    risk_items?: RiskItem[]
    key_metrics?: KeyMetric[]
    created_at?: string
    updated_at?: string
    waiting_ahead_count?: number | null
    scheduled_running_count?: number | null
    scheduled_concurrency_limit?: number | null
    /** 后端 LLM 生成的要点梳理（约 300–400 字） */
    final_decision_summary?: string | null
    derived_signals?: Record<string, unknown>
    release_version?: string | null
    outcome_summary?: ReportOutcomeSummaryLite | null
}

export interface ReportDetail extends Report {
    market_report?: string
    sentiment_report?: string
    news_report?: string
    fundamentals_report?: string
    macro_report?: string
    smart_money_report?: string
    volume_price_report?: string
    game_theory_report?: string
    investment_plan?: string
    trader_investment_plan?: string
    final_trade_decision?: string
    result_data?: AnalysisReport
    data_sources?: DataSourceBundle
}

export interface ReportListResponse {
    total: number
    reports: Report[]
}

export type OutcomeGroupBy = 'overall' | 'version' | 'week'
export type OutcomeStatus = 'hit' | 'neutral' | 'miss' | 'pending'

export interface ReportOutcomeHorizonItem {
    horizon: string
    target_date?: string | null
    close_price?: number | null
    delta?: number | null
    delta_pct?: number | null
    atr_mult?: number | null
    status: OutcomeStatus
    score?: number | null
}

export interface ReportOutcomeDetail {
    report_id: string
    task_kind: string
    release_version?: string | null
    baseline_price?: number | null
    baseline_source?: string | null
    atr20?: number | null
    atr_window_end?: string | null
    weighted_score?: number | null
    settled_count: number
    total_windows: number
    primary_horizon?: string | null
    primary_status?: OutcomeStatus | string | null
    outcomes: Record<string, ReportOutcomeHorizonItem>
    last_evaluated_at?: string | null
    next_evaluate_after?: string | null
    error?: string | null
}

export interface ReportOutcomeSummaryLite {
    weighted_score?: number | null
    primary_horizon?: string | null
    primary_status?: OutcomeStatus | string | null
    settled_count?: number
    total_windows?: number
    release_version?: string | null
    /** 基线价（分析当日收盘） */
    baseline_price?: number | null
    /** 20 日 ATR；与 baseline_price 配合换算阈值 */
    atr20?: number | null
    /** 列表行展示各窗口状态（由后端 outcomes_json 派生） */
    t0_status?: OutcomeStatus | string | null
    t1_status?: OutcomeStatus | string | null
    t2_status?: OutcomeStatus | string | null
    t3_status?: OutcomeStatus | string | null
    t5_status?: OutcomeStatus | string | null
    t0_close?: number | null
    t1_close?: number | null
    t2_close?: number | null
    t3_close?: number | null
    t5_close?: number | null
    t0_delta_pct?: number | null
    t1_delta_pct?: number | null
    t2_delta_pct?: number | null
    t3_delta_pct?: number | null
    t5_delta_pct?: number | null
    t0_atr_mult?: number | null
    t1_atr_mult?: number | null
    t2_atr_mult?: number | null
    t3_atr_mult?: number | null
    t5_atr_mult?: number | null
    t0_target_date?: string | null
    t1_target_date?: string | null
    t2_target_date?: string | null
    t3_target_date?: string | null
    t5_target_date?: string | null
}

export interface ReportOutcomeSummaryGroupItem {
    key: string
    sample_count: number
    settled_count: number
    pending_count: number
    hit_rate?: number | null
    avg_weighted_score?: number | null
    miss_count: number
}

export interface ReportOutcomeSummaryResponse {
    group_by: OutcomeGroupBy
    summary: {
        sample_count: number
        settled_count: number
        pending_count: number
        hit_rate?: number | null
        avg_weighted_score?: number | null
        miss_count: number
    }
    items: ReportOutcomeSummaryGroupItem[]
}

export interface QlibEvalGateCheck {
    hit_rate?: boolean
    ic?: boolean
    coverage?: boolean
}

export interface QlibEvalVersionGateItem {
    release_version: string
    runs: number
    gate: {
        passed: boolean
        checks: QlibEvalGateCheck
        thresholds: { min_hit_rate_pct: number; min_ic: number; min_coverage_pct: number }
        reasons: string[]
    }
}

export interface QlibEvalGateSummaryResponse {
    enabled: boolean
    release_version?: string
    quant_metrics?: Array<{
        release_version: string
        metric_kind: string
        hit_rate_pct?: number | null
        ic?: number | null
        rank_ic?: number | null
        coverage_pct?: number | null
        gate_passed: boolean
        label_horizon?: string | null
        created_at?: string | null
    }>
    version_gates?: { items: QlibEvalVersionGateItem[]; any_passed: boolean }
    report_outcomes_by_version?: ReportOutcomeSummaryResponse | null
    error?: string
}

export interface AnnouncementItem {
    title: string
    detail: string
}

export interface Announcement {
    id: string
    tag?: string
    title: string
    summary?: string
    published_at: string
    items: AnnouncementItem[]
    cta_label?: string
    cta_path?: string
}

export interface LatestAnnouncementResponse {
    announcement: Announcement | null
}

// Watchlist & Scheduled Analysis
export interface WatchlistItem {
    id: string
    symbol: string
    name: string
    display_label?: string | null
    sort_order: number
    created_at: string
    has_scheduled: boolean
}

export interface WatchlistBatchResult {
    input: string
    symbol?: string
    name?: string
    display_label?: string | null
    status: 'added' | 'duplicate' | 'invalid' | 'failed'
    message: string
    item?: WatchlistItem
}

export interface WatchlistBatchResponse {
    message: string
    summary: {
        total: number
        added: number
        duplicate: number
        failed: number
    }
    results: WatchlistBatchResult[]
}

export interface ScheduledAnalysis {
    id: string
    symbol: string
    name: string
    display_label?: string | null
    horizon: string
    trigger_time: string
    is_active: boolean
    last_run_date: string | null
    last_run_status: string | null
    last_report_id: string | null
    consecutive_failures: number
    created_at: string
    has_imported_context?: boolean
    imported_current_position?: number | null
    imported_average_cost?: number | null
    imported_trade_points_count?: number
}

export interface ScheduledBatchUpdateResponse {
    items: ScheduledAnalysis[]
}

export interface ScheduledBatchDeleteResponse {
    deleted_ids: string[]
    missing_ids: string[]
}

export interface ScheduledBatchTriggerJob {
    item_id: string
    job_id: string
    symbol: string
    name: string
    display_label?: string | null
    status: 'pending' | 'running' | 'completed' | 'failed'
    created_at: string
    current_position?: number | null
    average_cost?: number | null
}

export interface ScheduledBatchTriggerResponse {
    summary: {
        total: number
        with_position_context: number
    }
    jobs: ScheduledBatchTriggerJob[]
}

export interface StockSearchResult {
    symbol: string
    name: string
    display_label?: string | null
}

export interface ImportedPortfolioPosition {
    symbol: string
    name: string
    display_label?: string | null
    current_position?: number | null
    available_position?: number | null
    average_cost?: number | null
    market_value?: number | null
    current_position_pct?: number | null
    trade_points_count: number
    latest_trade_at?: string | null
    latest_trade_action?: string | null
    last_imported_at?: string | null
    recent_trade_points?: Array<Record<string, unknown>>
}

export interface ImportedScheduledSyncSummary {
    created: string[]
    existing: string[]
    skipped_limit: string[]
}

export interface PortfolioImportState {
    auto_apply_scheduled: boolean
    last_synced_at?: string | null
    last_error?: string | null
    summary: {
        positions: number
    }
    scheduled_sync?: ImportedScheduledSyncSummary
    positions: ImportedPortfolioPosition[]
}

export interface PortfolioPositionInput {
    symbol: string
    name?: string
    display_label?: string | null
    current_position?: number | null
    available_position?: number | null
    average_cost?: number | null
    market_value?: number | null
    current_position_pct?: number | null
}

export interface PortfolioOverviewResponse {
    watchlist: WatchlistItem[]
    scheduled: ScheduledAnalysis[]
    latest_reports: Report[]
    portfolio_import: PortfolioImportState | null
}

export interface TrackingBoardAnalysis {
    report_id: string
    trade_date: string
    is_previous_trade_day: boolean
    decision?: string | null
    direction?: string | null
    high_price?: number | null
    low_price?: number | null
    trader_advice_summary?: string | null
    trader_investment_plan?: string | null
    final_trade_decision?: string | null
}

export interface TrackingBoardItem {
    symbol: string
    name: string
    display_label?: string | null
    current_position?: number | null
    available_position?: number | null
    average_cost?: number | null
    market_value?: number | null
    current_position_pct?: number | null
    live_market_value?: number | null
    floating_pnl?: number | null
    floating_pnl_pct?: number | null
    live_price?: number | null
    day_open?: number | null
    price_change?: number | null
    price_change_pct?: number | null
    day_high?: number | null
    day_low?: number | null
    previous_close?: number | null
    volume?: number | null
    amount?: number | null
    quote_time?: string | null
    quote_source?: string | null
    last_imported_at?: string | null
    analysis?: TrackingBoardAnalysis | null
}

export interface TrackingBoardResponse {
    previous_trade_date: string
    refresh_interval_seconds: number
    items: TrackingBoardItem[]
}

// Runtime config
export interface RuntimeConfig {
    llm_provider: string
    deep_think_llm: string
    quick_think_llm: string
    backend_url: string
    max_debate_rounds: number
    max_risk_discuss_rounds: number
    has_api_key?: boolean
    has_wecom_webhook?: boolean
    wecom_webhook_display?: string | null
    server_fallback_enabled?: boolean
    email_report_enabled?: boolean
    wecom_report_enabled?: boolean
    default_analysts?: string[]
    llm_region?: string
}

export interface LlmCatalogModel {
    label: string
    id: string
}

export interface LlmCatalogResponse {
    providers: Record<string, { quick: LlmCatalogModel[]; deep: LlmCatalogModel[] }>
    regions: Array<{ id: string; label: string }>
    enabled?: boolean
}

export interface SystemVersionResponse {
    upstream: string
    fork: string
    version: string
    commit: string | null
}

export interface JobCheckpointStatus {
    step?: number | null
    resumable: boolean
    last_node?: string | null
    thread_id?: string | null
}

export interface DecisionArchiveEntry {
    rating_5tier?: string | null
    outcome_raw_pct?: number | null
    outcome_alpha_pct?: number | null
    holding_days?: number | null
    reflection_md?: string | null
    trade_date?: string | null
    decision_md?: string | null
}

export interface RuntimeConfigUpdateResponse {
    message: string
    applied: RuntimeConfigUpdate
    has_api_key: boolean
    current: RuntimeConfig
    warmup?: RuntimeConfigWarmup
}

export interface RuntimeConfigUpdate {
    llm_provider?: string
    deep_think_llm?: string
    quick_think_llm?: string
    backend_url?: string
    max_debate_rounds?: number
    max_risk_discuss_rounds?: number
    api_key?: string
    wecom_webhook_url?: string
    clear_api_key?: boolean
    clear_wecom_webhook?: boolean
    email_report_enabled?: boolean
    wecom_report_enabled?: boolean
    default_analysts?: string[]
    warmup?: boolean
    force_warmup?: boolean
}

export interface RuntimeWarmupRequest extends RuntimeConfigUpdate {
    prompt?: string
}

export interface RuntimeConfigWarmup {
    requested: boolean
    triggered: boolean
    status: 'scheduled' | 'skipped' | 'disabled'
    message: string
    models?: string[]
}

export interface RuntimeWarmupResult {
    model: string
    targets: string[]
    content?: string | null
    error?: string | null
}

export interface RuntimeWarmupResponse {
    prompt: string
    results: RuntimeWarmupResult[]
}

export interface WecomWarmupRequest {
    wecom_webhook_url?: string
    content?: string
}

export interface WecomWarmupResponse {
    sent: boolean
    message: string
    webhook_display?: string | null
}

export interface AuthUser {
    id: string
    email: string
    username?: string | null
    display_name?: string | null
    role?: string
    status?: string
    credits?: number
    plan_code?: string | null
    subscription_expires_at?: string | null
    phone_masked?: string | null
    created_at?: string
    last_login_at?: string
    email_report_enabled?: boolean
    wecom_report_enabled?: boolean
    admin_permissions?: string[] | null
    /** 由 GET /v1/users/entitlements 填充，用于前端 gate */
    entitlements?: UserEntitlements | null
}

export interface AuthVerifyResponse {
    access_token: string
    token_type: string
    user: AuthUser
}

export interface UserToken {
    id: string
    name: string
    token?: string
    token_hint?: string
    last_used_at?: string
    created_at: string
}

export interface UserTokenCreateRequest {
    name: string
}

// Feedback types
export interface FeedbackItem {
    id: string
    user_email: string
    subject: string
    content: string
    admin_reply?: string | null
    replied_at?: string | null
    is_read: boolean
    created_at?: string
    updated_at?: string
}

export interface FeedbackListResponse {
    total: number
    feedbacks: FeedbackItem[]
}

export interface FeedbackUnreadResponse {
    unread_count: number
}

// Debate message (for battle view)
export interface DebateMessage {
    debate: 'research' | 'risk'
    agent: string
    round: number        // -1 = verdict
    content: string
    isVerdict?: boolean
    horizon?: string
}
