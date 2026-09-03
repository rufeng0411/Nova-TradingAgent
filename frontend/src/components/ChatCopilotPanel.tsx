import { FormEvent, useState, useRef, useEffect, useCallback } from 'react'
import {
    Bot, Loader2, Send, Sparkles, FileText, ChevronRight, Trash2,
    TrendingUp, MessageCircle, Newspaper, Calculator, BarChart2, DollarSign,
    ArrowBigUp, ArrowBigDown, Brain, Briefcase, Flame, Scale, Shield, CheckCircle2,
    Activity,
} from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { api } from '@/services/api'
import { perUserLocalStorageKey } from '@/lib/perUserLocalKey'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useAuthStore } from '@/stores/authStore'
import type {
    AgentReportEvent,
    AgentSnapshotEvent,
    AgentStatusEvent,
    AnalysisReport,
    ReportChunkEvent,
    Report,
} from '@/types'
import { lookupStockName, stockDisplayLabel } from '@/utils/stockDisplay'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { consumeSseStream } from '@/lib/consumeSseStream'
import { sanitizeReportMarkdown } from '@/utils/reportText'
import {
    JOB_COMPLETION_POLL_INTERVAL_MS,
    JOB_COMPLETION_POLL_MAX_ROUNDS,
    JOB_RESUME_PRE_POLL_DELAY_MS,
    MOUNT_RESUME_PRE_POLL_DELAY_MS,
} from '@/lib/analysisResumePolicy'

/** 与 agentMessageMapRef 的 key 规则一致：agent 名 + horizon 段（缺省为 main） */
function horizonKeySegment(horizon?: string | null): string {
    const h = horizon != null && String(horizon).trim() ? String(horizon).trim() : 'main'
    return h
}

/**
 * 同一 job 下每个 analyst+horizon 唯一气泡 id（勿用 Date.now，否则 token/status 乱序、重放或重复 in_progress 会叠两行）
 */
function stableAgentBubbleMessageId(jobId: string, agent: string, horizon?: string | null): string {
    const j = jobId.trim() || 'unknown'
    const safe = agent.replace(/\s+/g, '-')
    return `agent-bubble:${j}:${safe}:${horizonKeySegment(horizon)}`
}

/**
 * report section → owning agent 名称映射。
 * 当 LangGraph 从 checkpoint 恢复时，对应节点不会重新执行，也就不会发送 `agent.token`，
 * `sectionToMsgIdsRef[section]` 会为空。此映射用于 `agent.report.chunk` 完成时
 * 兜底找回该 section 对应 agent 的占位气泡，把它原地转成 ReportCard，避免「研究总监 正在思考...」
 * 这种永久性占位文案误导用户。
 */
const REPORT_SECTION_OWNER_AGENT: Record<string, string> = {
    market_report: 'Market Analyst',
    sentiment_report: 'Social Analyst',
    news_report: 'News Analyst',
    fundamentals_report: 'Fundamentals Analyst',
    macro_report: 'Macro Analyst',
    smart_money_report: 'Smart Money Analyst',
    volume_price_report: 'Volume Price Analyst',
    investment_plan: 'Research Manager',
    trader_investment_plan: 'Trader',
    final_trade_decision: 'Portfolio Manager',
}

/** 「正在思考并撰写报告中...」占位气泡的识别正则（与首次创建时格式对齐） */
const AGENT_PLACEHOLDER_PATTERN = /^\*\*[^*]+\*\*\s*(?:\([^)]*\))?\s*正在思考并撰写报告中/

/** 研究/风控辩论类 agent：未走 token 流时让占位文案指向辩论面板，而不是说「报告」 */
const DEBATE_PANEL_AGENTS = new Set([
    'Bull Researcher',
    'Bear Researcher',
    'Aggressive Analyst',
    'Neutral Analyst',
    'Conservative Analyst',
])

interface ChatCopilotPanelProps {
    onSymbolDetected: (symbol: string) => void
    onShowReport?: (section?: string) => void
    initialInput?: string
    /** 由分析页在绑定服务端执行中任务后递增，用于触发事件流续订 */
    resumeSignal?: number
}

interface StreamEvent {
    event: string
    data: Record<string, unknown>
}

/** 轮询 / SSE job.failed：服务端已对技术性失败脱敏，此处不再展开堆栈或异常类型 */
function formatJobFailedUserMessage(serverError?: string | null): string {
    const err = (serverError ?? '').trim()
    if (!err) {
        return '任务未能完成，请稍后重试或重新发起分析。'
    }
    const generic =
        err === '任务未能完成，请稍后重试。' ||
        err.startsWith('任务超时') ||
        err.includes('点数不足')
    if (generic) {
        return `${err}\n\n若仍无法完成，请稍后重试或联系管理员。`
    }
    const maxLen = 900
    const compact = err.replace(/\s+/g, ' ')
    const truncated = compact.length > maxLen ? `${compact.slice(0, maxLen)}…` : compact
    return `任务未能完成。\n\n**原因**：${truncated}\n\n若为偶发网络或数据源问题，可稍后重试；持续失败请查看后台日志或联系管理员。`
}

const PRESET_PROMPTS = [
    '分析一下贵州茅台(600519.SH)今天走势',
    '请分析稀土ETF嘉实(516150)在2026-03-03的情况',
    '分析宁德时代300750.SZ，做一轮投研沙盘梳理',
]

const REPORT_SECTION_TITLES: Record<string, string> = {
    market_report: '市场分析报告',
    sentiment_report: '舆情分析报告',
    news_report: '新闻分析报告',
    fundamentals_report: '基本面分析报告',
    macro_report: '宏观板块报告',
    smart_money_report: '主力资金分析报告',
    volume_price_report: '量价分析报告',
    investment_plan: '研究团队研判结论',
    trader_investment_plan: '路径推演草稿',
    final_trade_decision: '沙盘综合研判结论',
}

// Section → Lucide 图标 + 颜色（与 AGENT_META_MAP 保持一致）
const SECTION_META: Record<string, { Icon: React.FC<{ className?: string }>; iconCls: string; bgCls: string }> = {
    market_report:          { Icon: TrendingUp,    iconCls: 'text-blue-500',    bgCls: 'bg-blue-100 dark:bg-blue-500/20' },
    sentiment_report:       { Icon: MessageCircle, iconCls: 'text-fuchsia-500', bgCls: 'bg-fuchsia-100 dark:bg-fuchsia-500/20' },
    news_report:            { Icon: Newspaper,     iconCls: 'text-cyan-500',    bgCls: 'bg-cyan-100 dark:bg-cyan-500/20' },
    fundamentals_report:    { Icon: Calculator,    iconCls: 'text-emerald-500', bgCls: 'bg-emerald-100 dark:bg-emerald-500/20' },
    macro_report:           { Icon: BarChart2,     iconCls: 'text-violet-500',  bgCls: 'bg-violet-100 dark:bg-violet-500/20' },
    smart_money_report:     { Icon: DollarSign,    iconCls: 'text-amber-500',   bgCls: 'bg-amber-100 dark:bg-amber-500/20' },
    volume_price_report:    { Icon: Activity,      iconCls: 'text-rose-500',    bgCls: 'bg-rose-100 dark:bg-rose-500/20' },
    investment_plan:        { Icon: Brain,         iconCls: 'text-indigo-500',  bgCls: 'bg-indigo-100 dark:bg-indigo-500/20' },
    trader_investment_plan: { Icon: Briefcase,     iconCls: 'text-orange-500',  bgCls: 'bg-orange-100 dark:bg-orange-500/20' },
    final_trade_decision:   { Icon: CheckCircle2,  iconCls: 'text-teal-500',    bgCls: 'bg-teal-100 dark:bg-teal-500/20' },
}

// 与 AgentCollaboration.tsx 保持一致的图标 + 颜色体系
const AGENT_META_MAP: Record<string, { Icon: React.FC<{ className?: string }>; iconCls: string; bgCls: string; label: string }> = {
    'Market Analyst':       { Icon: TrendingUp,   iconCls: 'text-blue-500',    bgCls: 'bg-blue-100 dark:bg-blue-500/20',    label: '技术面' },
    'Social Analyst':       { Icon: MessageCircle, iconCls: 'text-fuchsia-500', bgCls: 'bg-fuchsia-100 dark:bg-fuchsia-500/20', label: '舆情' },
    'News Analyst':         { Icon: Newspaper,     iconCls: 'text-cyan-500',    bgCls: 'bg-cyan-100 dark:bg-cyan-500/20',    label: '新闻' },
    'Fundamentals Analyst': { Icon: Calculator,    iconCls: 'text-emerald-500', bgCls: 'bg-emerald-100 dark:bg-emerald-500/20', label: '基本面' },
    'Macro Analyst':        { Icon: BarChart2,     iconCls: 'text-violet-500',  bgCls: 'bg-violet-100 dark:bg-violet-500/20', label: '宏观' },
    'Smart Money Analyst':  { Icon: DollarSign,    iconCls: 'text-amber-500',   bgCls: 'bg-amber-100 dark:bg-amber-500/20',  label: '主力资金' },
    'Volume Price Analyst': { Icon: Activity,      iconCls: 'text-rose-500',    bgCls: 'bg-rose-100 dark:bg-rose-500/20',    label: '量价' },
    'Bull Researcher':      { Icon: ArrowBigUp,    iconCls: 'text-emerald-500', bgCls: 'bg-emerald-100 dark:bg-emerald-500/20', label: '多头' },
    'Bear Researcher':      { Icon: ArrowBigDown,  iconCls: 'text-rose-500',    bgCls: 'bg-rose-100 dark:bg-rose-500/20',    label: '空头' },
    'Research Manager':     { Icon: Brain,         iconCls: 'text-indigo-500',  bgCls: 'bg-indigo-100 dark:bg-indigo-500/20', label: '研究总监' },
    'Trader':               { Icon: Briefcase,     iconCls: 'text-orange-500',  bgCls: 'bg-orange-100 dark:bg-orange-500/20', label: '交易员' },
    'Aggressive Analyst':   { Icon: Flame,         iconCls: 'text-red-500',     bgCls: 'bg-red-100 dark:bg-red-500/20',      label: '激进' },
    'Neutral Analyst':      { Icon: Scale,         iconCls: 'text-slate-500',   bgCls: 'bg-slate-100 dark:bg-slate-500/20',  label: '中性' },
    'Conservative Analyst': { Icon: Shield,        iconCls: 'text-amber-500',   bgCls: 'bg-amber-100 dark:bg-amber-500/20',  label: '稳健' },
    'Portfolio Manager':    { Icon: CheckCircle2,  iconCls: 'text-teal-500',    bgCls: 'bg-teal-100 dark:bg-teal-500/20',    label: '组合经理' },
    '意图解析':             { Icon: Bot,            iconCls: 'text-slate-400',   bgCls: 'bg-slate-100 dark:bg-slate-700',     label: '意图解析' },
}

function ReportCard({
    section,
    content,
    streaming,
    onOpen,
}: {
    section: string
    content: string
    streaming: boolean
    onOpen: () => void
}) {
    const title = REPORT_SECTION_TITLES[section] || section
    const meta = SECTION_META[section]
    const preview = sanitizeReportMarkdown(content).replace(/^#+\s*/gm, '').replace(/\*\*/g, '').slice(0, 80)

    const IconEl = meta?.Icon || FileText
    const iconCls = meta?.iconCls || 'text-slate-400'
    const bgCls = meta?.bgCls || 'bg-slate-100 dark:bg-slate-700'

    if (streaming) {
        return (
            <div className="flex items-center gap-2.5 px-3 py-2 rounded-xl bg-blue-500/10 border border-blue-500/20 text-sm">
                <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg ${bgCls} shrink-0`}>
                    <IconEl className={`w-4 h-4 ${iconCls}`} />
                </span>
                <span className="text-blue-300 font-medium text-xs">{title}</span>
                <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin shrink-0 ml-auto" />
            </div>
        )
    }

    return (
        <button
            onClick={onOpen}
            className="w-full flex items-center gap-2.5 px-3 py-2.5 rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/50 hover:border-blue-400 dark:hover:border-blue-500/40 hover:bg-blue-50 dark:hover:bg-slate-800 transition-all text-left group"
        >
            <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg ${bgCls} shrink-0`}>
                <IconEl className={`w-4 h-4 ${iconCls}`} />
            </span>
            <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-slate-700 dark:text-slate-200 group-hover:text-blue-600 dark:group-hover:text-blue-300 transition-colors">{title}</p>
                <p className="text-xs text-slate-500 truncate mt-0.5">{preview}...</p>
            </div>
            <ChevronRight className="w-4 h-4 text-slate-500 group-hover:text-blue-400 shrink-0 transition-colors" />
        </button>
    )
}

export default function ChatCopilotPanel({ onSymbolDetected, onShowReport, initialInput, resumeSignal = 0 }: ChatCopilotPanelProps) {
    const [input, setInput] = useState(initialInput || '')
    const [submitting, setSubmitting] = useState(false)
    const pendingSubmitPromptsRef = useRef<string[]>([])
    const navigate = useNavigate()
    const publicFeatures = useAuthStore(s => s.publicFeatures)
    // Tracks agent bubbles waiting for their first token (shows "正在推理分析中..." spinner)
    const pendingAgentMsgIdsRef = useRef<Set<string>>(new Set())
    // Only used to trigger re-render when pending status changes
    const [, forceUpdate] = useState(0)
    const [expandedAgentMsgId, setExpandedAgentMsgId] = useState<string | null>(null)
    // Use global default analysts from Settings (read-only here)
    const selectedAnalysts = (() => {
        try {
            const stored = localStorage.getItem(perUserLocalStorageKey('tradingagents-settings'))
            if (!stored) return ['market', 'social', 'news', 'fundamentals', 'macro', 'smart_money', 'volume_price']
            const parsed = JSON.parse(stored) as { defaultAnalysts?: string[] }
            if (Array.isArray(parsed.defaultAnalysts) && parsed.defaultAnalysts.length > 0) {
                return parsed.defaultAnalysts
            }
        } catch {}
        return ['market', 'social', 'news', 'fundamentals', 'macro', 'smart_money', 'volume_price']
    })()
    // track which section IDs have been added to chatMessages and whether they're done
    const streamingReportIds = useRef<Map<string, boolean>>(new Map()) // section → isComplete
    const agentMessageMapRef = useRef<Record<string, string>>({})
    const firstTokenMapRef = useRef<Record<string, boolean>>({})
    const sectionToMsgIdsRef = useRef<Record<string, string[]>>({}) // section → all agent bubble msgIds
    const typingIndicatorIdRef = useRef<string | null>(null)
    /** 单次 SSE 流结束时：completed / failed / 仍为 running 表示未收到终态 */
    const streamOutcomeRef = useRef<'running' | 'completed' | 'failed'>('running')
    const streamOutcome = () => streamOutcomeRef.current
    const lastJobErrorRef = useRef<string | null>(null)
    const messagesEndRef = useRef<HTMLDivElement>(null)
    const messagesContainerRef = useRef<HTMLDivElement>(null)
    /** 页面刷新后后台恢复任务时，避免用户误触「再发一条」与恢复逻辑抢跑 */
    const resumeInProgressRef = useRef(false)
    /** 避免 SSE job.failed 与轮询失败各弹一条重复话术 */
    const failureNoticeShownRef = useRef(false)
    /** 避免同一不存在任务重复提示 */
    const missingJobNoticeForRef = useRef<string | null>(null)
    /** 队列任务（前方 0）等待转执行时的轮询句柄 */
    const queuedWatchTimerRef = useRef<number | null>(null)
    const queuedWatchJobIdRef = useRef<string | null>(null)
    /** 已经为某个 jobId 完整跑过 hydrateCompletedJob，避免 mount/守护/续订 effect 三路同时触发重复推送 */
    const hydratedJobIdRef = useRef<string | null>(null)

    const resetStreamSessionRefs = () => {
        failureNoticeShownRef.current = false
        streamingReportIds.current.clear()
        agentMessageMapRef.current = {}
        firstTokenMapRef.current = {}
        sectionToMsgIdsRef.current = {}
        pendingAgentMsgIdsRef.current = new Set()
        hydratedJobIdRef.current = null
        forceUpdate(n => n + 1)
        if (typingIndicatorIdRef.current) {
            useAnalysisStore.setState(state => ({
                chatMessages: state.chatMessages.filter(m => m.id !== typingIndicatorIdRef.current),
            }))
            typingIndicatorIdRef.current = null
        }
    }

    /** 防止并行多次打开同一 job 的 dedicated events 流 */
    const dedicatedResumeInFlightRef = useRef(false)
    /**
     * 任意 SSE 事件流（chat completion 主流 / dedicated job events 流）正在消费中。
     * 在 `processJobEventStreamBody` 内会同步置 true/false。
     * 任何「再开一条流」的路径都必须检查此 ref，避免并行双流写入同一 store。
     */
    const streamActiveRef = useRef(false)

    const {
        chatMessages,
        isAnalyzing,
        currentSymbol,
        currentSymbolDisplayName,
        activeAnalysisJobSymbol,
        activeAnalysisJobDisplayName,
        currentJobId,
        setCurrentJobId,
        setActiveAnalysisJobFocus,
        setCurrentSymbol,
        setCurrentSymbolDisplayName,
        setIsAnalyzing,
        setIsConnected,
        setAnalysisRunState,
        setCurrentHorizon,
        updateAgentStatus,
        updateAgentSnapshot,
        addAgentReport,
        addReportChunk,
        addChatMessage,
        appendToChatMessage,
        setMessageContent,
        setReport,
        setStructuredData,
        markAgentMessagesComplete,
        clearSession,
        addDebateMessage,
        appendDebateToken,
        setLastEventIdForJob,
        clearJobEventCursor,
        analysisRunState,
    } = useAnalysisStore()

    /** 指数本地表优先，其余 A 股走 stock-search，避免多 Agents 标题只显示代码 */
    const enrichAnalysisSymbolDisplayName = useCallback(
        (symbol: string) => {
            const at = symbol.trim().toUpperCase()
            if (!at) return
            const quick = lookupStockName(at)
            if (quick) {
                const st = useAnalysisStore.getState()
                if (st.currentSymbol.trim().toUpperCase() === at) {
                    setCurrentSymbolDisplayName(quick)
                }
                if (st.activeAnalysisJobSymbol === at) {
                    setActiveAnalysisJobFocus(at, quick)
                }
                return
            }
            void fetchAshareDisplayName(at).then((name) => {
                if (!name) return
                const st = useAnalysisStore.getState()
                if (st.currentSymbol.trim().toUpperCase() === at) {
                    setCurrentSymbolDisplayName(name)
                }
                if (st.activeAnalysisJobSymbol === at) {
                    setActiveAnalysisJobFocus(at, name)
                }
            })
        },
        [setCurrentSymbolDisplayName, setActiveAnalysisJobFocus],
    )

    const sleep = (ms: number) => new Promise(resolve => setTimeout(resolve, ms))
    const isJobNotFoundError = (error: unknown) =>
        error instanceof Error && /job not found|任务不存在|报告不存在|HTTP error! status: 404|404/i.test(error.message)

    const pushAssistant = (content: string) => {
        addChatMessage({
            id: `${Date.now()}-${Math.random()}`,
            role: 'assistant',
            content,
            timestamp: new Date().toISOString(),
        })
    }

    const pushSystem = (content: string) => {
        addChatMessage({
            id: `${Date.now()}-${Math.random()}`,
            role: 'system',
            content,
            timestamp: new Date().toISOString(),
        })
    }

    const submitV2Enabled = (() => {
        const envOn = String(import.meta.env.VITE_TASK_SUBMIT_V2 ?? '1').toLowerCase()
        const envEnabled = !['0', 'false', 'no', 'off'].includes(envOn)
        const featureEnabled = publicFeatures?.chat_task_submit_v2_enabled !== false
        return envEnabled && featureEnabled
    })()

    const handleSystemActionLink = useCallback(async (href?: string) => {
        const target = String(href || '').trim()
        if (!target) return
        if (target === '/tasks') {
            navigate('/tasks')
            return
        }
        if (target.startsWith('ta://cancel-queued/')) {
            const jobId = target.replace('ta://cancel-queued/', '').trim()
            if (!jobId) return
            try {
                await api.cancelQueueTask(jobId)
                pushSystem(`已取消排队任务：${jobId.slice(0, 8)}…`)
            } catch (error) {
                const msg = error instanceof Error ? error.message : String(error)
                pushSystem(`取消排队任务失败：${msg}`)
            }
        }
    }, [navigate, pushSystem])

    const stopQueuedWatcher = () => {
        if (queuedWatchTimerRef.current !== null) {
            window.clearInterval(queuedWatchTimerRef.current)
            queuedWatchTimerRef.current = null
        }
        queuedWatchJobIdRef.current = null
    }

    const startQueuedWatcher = (jobId: string) => {
        const jid = (jobId || '').trim()
        if (!jid) return
        if (queuedWatchJobIdRef.current === jid && queuedWatchTimerRef.current !== null) return
        stopQueuedWatcher()
        queuedWatchJobIdRef.current = jid

        const tick = async () => {
            if (queuedWatchJobIdRef.current !== jid) return
            try {
                const status = await api.getJobStatus(jid)
                if (queuedWatchJobIdRef.current !== jid) return
                if (status.status === 'queued' || status.status === 'paused') return
                if (status.status === 'pending' || status.status === 'running') {
                    stopQueuedWatcher()
                    streamOutcomeRef.current = 'running'
                    setAnalysisRunState('running')
                    setIsAnalyzing(true)
                    void tryResumeJobViaDedicatedEvents({ quiet: true })
                    return
                }
                if (status.status === 'completed') {
                    stopQueuedWatcher()
                    await hydrateCompletedJob(jid, { quiet: true })
                    return
                }
                if (status.status === 'failed') {
                    stopQueuedWatcher()
                    setAnalysisRunState('failed', status.error || 'unknown error')
                    setIsAnalyzing(false)
                }
            } catch {
                // 网络抖动时继续等待，下一轮再查
            }
        }

        void tick()
        queuedWatchTimerRef.current = window.setInterval(() => {
            void tick()
        }, 2000)
    }

    const hydrateCompletedJob = async (jobId: string, options?: { quiet?: boolean }) => {
        if (hydratedJobIdRef.current === jobId) {
            // 已经回填过同一任务：mount effect / 守护 tick / dedicated resume 三路并发都会到这里，去重避免 3 条「已恢复」
            return
        }
        hydratedJobIdRef.current = jobId
        const result = await api.getJobResult(jobId)
        streamOutcomeRef.current = 'completed'
        setCurrentHorizon(null)
        setIsAnalyzing(false)
        setAnalysisRunState('completed')
        pendingAgentMsgIdsRef.current = new Set()
        forceUpdate(n => n + 1)
        markAgentMessagesComplete()

        const symbol = result.result.symbol
        const tradeDate = result.result.trade_date
        if (symbol) {
            setCurrentSymbol(symbol)
            setActiveAnalysisJobFocus(symbol, null)
            enrichAnalysisSymbolDisplayName(symbol)
            onSymbolDetected(symbol)
        }

        setReport(result.result)
        try {
            if (symbol) {
                const history = await api.getReports(symbol, 0, 10)
                const matched = history.reports.find((item: Report) => item.trade_date === tradeDate) ?? history.reports[0]
                if (matched) {
                    setStructuredData({
                        riskItems: matched.risk_items,
                        keyMetrics: matched.key_metrics,
                        confidence: matched.confidence,
                        targetPrice: matched.target_price,
                        stopLoss: matched.stop_loss_price,
                    })
                }
            }
        } catch {
            // 历史报告回填失败时，至少保留主报告正文
        }

        {
            const st = useAnalysisStore.getState()
            const sym = st.currentSymbol.trim().toUpperCase()
            if (sym && !st.currentSymbolDisplayName?.trim()) {
                enrichAnalysisSymbolDisplayName(sym)
            }
        }

        if (options?.quiet) {
            pushSystem(
                `已恢复：任务 ${jobId.slice(0, 8)}… 已在后台完成，报告与结论已同步（${String(result.result.direction || '未知')} · ${String(result.decision || 'HOLD')}）。`,
            )
        } else {
            pushAssistant(
                `**分析完成（已从中断连接恢复）**\n\n方向倾向：**${String(result.result.direction || '未知')}**\n\n沙盘标签：**${String(result.decision || 'HOLD')}**\n\n> 免责声明：以上内容由模型基于公开数据与规则生成，仅供研究参考，不构成任何投资建议或收益承诺。`,
            )
        }
    }

    const recoverInterruptedJob = async () => {
        const { currentJobId } = useAnalysisStore.getState()
        if (!currentJobId) return false

        pushSystem(`分析流中断，正在回查任务状态：${currentJobId}`)

        for (let attempt = 0; attempt < JOB_COMPLETION_POLL_MAX_ROUNDS; attempt += 1) {
            let status
            try {
                status = await api.getJobStatus(currentJobId)
            } catch (error) {
                if (isJobNotFoundError(error)) {
                    pushAssistant('分析任务已中断且后端无法找到该任务记录。已保留当前页面上的阶段性报告，请重新发起分析。')
                    setCurrentJobId(null)
                    setActiveAnalysisJobFocus(null)
                    setCurrentHorizon(null)
                    setIsAnalyzing(false)
                    setIsConnected(false)
                    setAnalysisRunState('failed', 'job not found after interrupted stream')
                    streamOutcomeRef.current = 'failed'
                    return true
                }
                throw error
            }

            if (status.status === 'completed') {
                await hydrateCompletedJob(currentJobId)
                return true
            }

            if (status.status === 'failed') {
                const detail = status.error || 'unknown error'
                if (!failureNoticeShownRef.current) {
                    failureNoticeShownRef.current = true
                    pushAssistant(formatJobFailedUserMessage(detail))
                }
                setAnalysisRunState('failed', detail)
                streamOutcomeRef.current = 'failed'
                return true
            }

            await sleep(JOB_COMPLETION_POLL_INTERVAL_MS)
        }

        return false
    }

    useEffect(() => {
        const container = messagesContainerRef.current
        if (!container) return
        container.scrollTo({
            top: container.scrollHeight,
            behavior: 'smooth',
        })
    }, [chatMessages])

    const parseAndDispatch = (event: StreamEvent) => {
        const { event: eventName, data } = event
        switch (eventName) {
            case 'job.ready': {
                setIsConnected(true)
                const jid = String(data.job_id || '')
                if (jid) setCurrentJobId(jid)
                // 把 typing indicator 换成"解析中"提示，告知用户正在识别标的
                if (typingIndicatorIdRef.current) {
                    setMessageContent(typingIndicatorIdRef.current, '__parsing__')
                }
                break
            }
            case 'job.created': {
                failureNoticeShownRef.current = false
                const jobId = String(data.job_id || '')
                if (jobId && hydratedJobIdRef.current && hydratedJobIdRef.current !== jobId) {
                    hydratedJobIdRef.current = null
                }
                const symbol = String(data.symbol || '')
                if (jobId) setCurrentJobId(jobId)
                if (symbol) {
                    setCurrentSymbol(symbol)
                    useAnalysisStore.getState().setActiveAnalysisJobFocus(symbol, null)
                    enrichAnalysisSymbolDisplayName(symbol)
                    onSymbolDetected(symbol)
                } else {
                    setCurrentSymbolDisplayName(null)
                    useAnalysisStore.getState().setActiveAnalysisJobFocus(null)
                }
                // 切换 indicator 到"采集数据"阶段
                if (typingIndicatorIdRef.current) {
                    setMessageContent(typingIndicatorIdRef.current, `__status:collecting:${symbol}__`)
                }
                streamingReportIds.current.clear()
                agentMessageMapRef.current = {}
                firstTokenMapRef.current = {}
                sectionToMsgIdsRef.current = {}
                pendingAgentMsgIdsRef.current = new Set(); forceUpdate(n => n + 1)
                break
            }
            case 'job.resumed': {
                pushSystem(
                    `服务端已从检查点继续执行分析任务（恢复序号 ${Number((data as Record<string, unknown>).attempt ?? 0)}）…`,
                )
                setIsAnalyzing(true)
                setAnalysisRunState('running')
                break
            }
            case 'job.running':
                setIsAnalyzing(true)
                setAnalysisRunState('running')
                // 切换 indicator 到"分析启动"阶段
                if (typingIndicatorIdRef.current) {
                    setMessageContent(typingIndicatorIdRef.current, '__status:analyzing__')
                }
                break
            case 'job.queued': {
                const waitingAheadCount = Number(data.waiting_ahead_count || 0)
                // 队列非终态：勿标 completed，否则续订/兜底会误判已结束
                streamOutcomeRef.current = 'running'
                setIsAnalyzing(false)
                setIsConnected(false)
                setAnalysisRunState('idle')
                if (typingIndicatorIdRef.current) {
                    useAnalysisStore.setState(state => ({
                        chatMessages: state.chatMessages.filter(m => m.id !== typingIndicatorIdRef.current),
                    }))
                    typingIndicatorIdRef.current = null
                }
                pushAssistant(
                    `任务已进入队列，当前前方约 **${waitingAheadCount}** 个任务。你可以在左侧「任务中心」中查看状态、拖拽排序、暂停或继续。`,
                )
                const queuedJobId = String(data.job_id || '') || useAnalysisStore.getState().currentJobId || ''
                if (queuedJobId && waitingAheadCount <= 0) {
                    // 前方 0 时，主动等待队列转执行并自动续订实时流
                    startQueuedWatcher(queuedJobId)
                }
                break
            }
            case 'agent.horizon_start': {
                const h = String(data.horizon || '')
                setCurrentHorizon(h || null)
                break
            }
            case 'agent.horizon_done':
                // keep currentHorizon until job completes so badge stays visible
                break
            case 'job.heartbeat':
                break
            case 'job.completed': {
                streamOutcomeRef.current = 'completed'
                setCurrentHorizon(null)
                setIsAnalyzing(false)
                setAnalysisRunState('completed')
                const doneId = String(data.job_id || '') || useAnalysisStore.getState().currentJobId || ''
                if (doneId) clearJobEventCursor(doneId)
                // 任务结束：所有 agent 消息标记为已完成（持久化到 store）
                pendingAgentMsgIdsRef.current = new Set()
                forceUpdate(n => n + 1)
                markAgentMessagesComplete()
                if (typeof data.result === 'object' && data.result && 'symbol' in data.result) {
                    const symbol = String((data.result as Record<string, unknown>).symbol || '')
                    if (symbol) {
                        setCurrentSymbol(symbol)
                        setActiveAnalysisJobFocus(symbol, null)
                        onSymbolDetected(symbol)
                    }
                }
                setReport((data.result || null) as AnalysisReport | null)
                setStructuredData({
                    riskItems: data.risk_items as never,
                    keyMetrics: data.key_metrics as never,
                    confidence: data.confidence as number | null,
                    targetPrice: data.target_price as number | null,
                    stopLoss: data.stop_loss_price as number | null,
                })
                {
                    const st = useAnalysisStore.getState()
                    const sym = st.currentSymbol.trim().toUpperCase()
                    if (sym && !st.currentSymbolDisplayName?.trim()) {
                        enrichAnalysisSymbolDisplayName(sym)
                    }
                }
                pushAssistant(
                    `**分析完成**\n\n方向倾向：**${String(data.direction || '未知')}**\n\n沙盘标签：**${String(data.decision || 'HOLD')}**\n\n> 免责声明：以上内容由模型基于公开数据与规则生成，仅供研究参考，不构成任何投资建议或收益承诺。`
                )
                if ('Notification' in window && Notification.permission === 'granted') {
                    new Notification('Nova-TradingAgent 分析完成', {
                        body: data.direction ? `方向：${String(data.direction)} · 动作：${String(data.decision || 'HOLD')}` : '点击查看完整报告',
                        icon: '/favicon.ico',
                    })
                }
                break
            }
            case 'job.retrying': {
                const msg = String((data as Record<string, unknown>).message || '正在自动重试并从断点继续…')
                pushAssistant(`_${msg}_`)
                break
            }
            case 'job.failed': {
                const errText = String(data.error || 'unknown error')
                streamOutcomeRef.current = 'failed'
                lastJobErrorRef.current = errText
                setCurrentHorizon(null)
                setIsAnalyzing(false)
                setIsConnected(false)
                setAnalysisRunState('failed', errText)
                if (!failureNoticeShownRef.current) {
                    failureNoticeShownRef.current = true
                    pushAssistant(formatJobFailedUserMessage(errText))
                }
                const fid = String((data as Record<string, unknown>).job_id || '') || useAnalysisStore.getState().currentJobId || ''
                if (fid) clearJobEventCursor(fid)
                break
            }
            case 'agent.status': {
                const statusData = data as unknown as { agent: string; status: string; horizon?: string }
                const agentKey2 = `${statusData.agent}-${horizonKeySegment(statusData.horizon)}`

                if (statusData.status === 'in_progress') {
                    // 第一个 agent 开始工作，移除状态指示器
                    if (typingIndicatorIdRef.current) {
                        useAnalysisStore.setState(state => ({
                            chatMessages: state.chatMessages.filter(m => m.id !== typingIndicatorIdRef.current)
                        }))
                        typingIndicatorIdRef.current = null
                    }

                    const agentName = statusData.agent
                    const horizon = statusData.horizon ? `(${statusData.horizon === 'short' ? '短线' : '中线'})` : ''
                    const jid = useAnalysisStore.getState().currentJobId || ''
                    const msgId = stableAgentBubbleMessageId(jid, agentName, statusData.horizon)

                    agentMessageMapRef.current[agentKey2] = msgId
                    const already = useAnalysisStore.getState().chatMessages.some(m => m.id === msgId)
                    if (!already) {
                        firstTokenMapRef.current[msgId] = true
                        addChatMessage({
                            id: msgId,
                            role: 'assistant',
                            agent: agentName,
                            content: `**${agentName}** ${horizon} 正在思考并撰写报告中...`,
                            timestamp: new Date().toISOString()
                        })
                    } else {
                        const c = useAnalysisStore.getState().chatMessages.find(m => m.id === msgId)?.content || ''
                        firstTokenMapRef.current[msgId] = !/^###\s/m.test(c)
                    }
                    pendingAgentMsgIdsRef.current.add(msgId); forceUpdate(n => n + 1)
                } else if (statusData.status === 'completed' || statusData.status === 'skipped') {
                    // Agent 完成/跳过 → 移出 pending，标记为已完成（持久化）
                    const existingMsgId = agentMessageMapRef.current[agentKey2]
                    if (existingMsgId) {
                        pendingAgentMsgIdsRef.current.delete(existingMsgId)
                        forceUpdate(n => n + 1)
                        markAgentMessagesComplete([existingMsgId])
                        // checkpoint 恢复场景：节点不会重新执行，没有 agent.token 抵达；
                        // 占位文案「正在思考并撰写报告中...」会一直挂着像没跑完。
                        // 此处把仍是占位文案的气泡换成「已完成」提示，引导用户去看辩论 / 报告面板。
                        if (statusData.status === 'completed') {
                            const cur = useAnalysisStore.getState().chatMessages.find(m => m.id === existingMsgId)?.content || ''
                            if (AGENT_PLACEHOLDER_PATTERN.test(cur.trim())) {
                                const horizonText = statusData.horizon ? `(${statusData.horizon === 'short' ? '短线' : '中线'})` : ''
                                const tip = DEBATE_PANEL_AGENTS.has(statusData.agent)
                                    ? '_本节为辩论发言，完整内容请见右侧「辩论面板」。_'
                                    : '_本节已完成，详细输出请见下方「报告面板」。_'
                                setMessageContent(existingMsgId, `### ${statusData.agent} ${horizonText}\n\n${tip}`)
                                firstTokenMapRef.current[existingMsgId] = false
                            }
                        }
                    }
                }
                updateAgentStatus(statusData as unknown as AgentStatusEvent)
                break
            }
            case 'agent.token': {
                const tokenData = data as unknown as { agent: string; report: string; token: string; horizon?: string }

                // 意图解析的原始 JSON 不在对话框显示（parsing indicator 已提供 UX）
                if (tokenData.agent === '意图解析') break

                // 第一个 agent token 到达时移除 parsing/typing indicator
                if (typingIndicatorIdRef.current) {
                    useAnalysisStore.setState(state => ({
                        chatMessages: state.chatMessages.filter(m => m.id !== typingIndicatorIdRef.current)
                    }))
                    typingIndicatorIdRef.current = null
                }

                const agentKey = `${tokenData.agent}-${horizonKeySegment(tokenData.horizon)}`
                let targetMsgId = agentMessageMapRef.current[agentKey]

                // Fallback: create bubble on first token if agent.status was missed or arrived late
                if (!targetMsgId) {
                    const horizonSuffix = tokenData.horizon ? `(${tokenData.horizon === 'short' ? '短线' : '中线'})` : ''
                    const jid = useAnalysisStore.getState().currentJobId || ''
                    targetMsgId = stableAgentBubbleMessageId(jid, tokenData.agent, tokenData.horizon)
                    agentMessageMapRef.current[agentKey] = targetMsgId
                    const existed = useAnalysisStore.getState().chatMessages.some(m => m.id === targetMsgId)
                    if (!existed) {
                        firstTokenMapRef.current[targetMsgId] = true
                        addChatMessage({
                            id: targetMsgId,
                            role: 'assistant',
                            agent: tokenData.agent,
                            content: `**${tokenData.agent}** ${horizonSuffix} 正在思考并撰写报告中...`,
                            timestamp: new Date().toISOString(),
                        })
                    } else {
                        const c = useAnalysisStore.getState().chatMessages.find(m => m.id === targetMsgId)?.content || ''
                        firstTokenMapRef.current[targetMsgId] = !/^###\s/m.test(c)
                    }
                    pendingAgentMsgIdsRef.current.add(targetMsgId); forceUpdate(n => n + 1)
                }

                // 记录 section → msgId 映射（多值），用于后续转换成 ReportCard
                if (tokenData.report) {
                    const ids = sectionToMsgIdsRef.current[tokenData.report] ||= []
                    if (!ids.includes(targetMsgId)) ids.push(targetMsgId)
                }

                if (firstTokenMapRef.current[targetMsgId]) {
                    const horizonText = tokenData.horizon ? `(${tokenData.horizon === 'short' ? '短线' : '中线'})` : ''
                    setMessageContent(targetMsgId, `### ${tokenData.agent} ${horizonText}\n\n${tokenData.token}`)
                    firstTokenMapRef.current[targetMsgId] = false
                    // 第一个 token 到达，移出 pending 状态
                    pendingAgentMsgIdsRef.current.delete(targetMsgId)
                } else {
                    appendToChatMessage(targetMsgId, tokenData.token)
                }
                break
            }
            case 'agent.snapshot':
                updateAgentSnapshot(data as unknown as AgentSnapshotEvent)
                break
            case 'agent.report':
                addAgentReport(data as unknown as AgentReportEvent)
                break
            case 'agent.report.chunk': {
                const chunkData = data as unknown as ReportChunkEvent
                const { section, is_complete } = chunkData
                addReportChunk(chunkData) // 更新报告面板的打字机效果

                if (is_complete && !streamingReportIds.current.get(section)) {
                    streamingReportIds.current.set(section, true)
                    const msgIds = sectionToMsgIdsRef.current[section] || []
                    let lastMsgId = msgIds[msgIds.length - 1]
                    const earlierMsgIds = msgIds.slice(0, -1)

                    // 兜底：checkpoint 恢复时该 section 的 agent 没走 token 流，sectionToMsgIdsRef 为空。
                    // 这里按 section→agent 映射，到 agentMessageMapRef 里找该 agent 在任意 horizon 的占位气泡，
                    // 让该气泡原地转成 ReportCard，避免出现「研究总监 正在思考...」永远不结束的视觉。
                    if (!lastMsgId) {
                        const ownerAgent = REPORT_SECTION_OWNER_AGENT[section]
                        if (ownerAgent) {
                            const horizonHint =
                                typeof chunkData.horizon === 'string' && chunkData.horizon.trim()
                                    ? chunkData.horizon
                                    : undefined
                            const candidateKeys = [
                                `${ownerAgent}-${horizonKeySegment(horizonHint)}`,
                                `${ownerAgent}-short`,
                                `${ownerAgent}-medium`,
                                `${ownerAgent}-main`,
                            ]
                            for (const ck of candidateKeys) {
                                const candidateId = agentMessageMapRef.current[ck]
                                if (candidateId) {
                                    lastMsgId = candidateId
                                    break
                                }
                            }
                        }
                    }

                    if (lastMsgId) {
                        // 最后一个 agent bubble 转换成已完成的 ReportCard
                        useAnalysisStore.setState(state => ({
                            chatMessages: state.chatMessages.map(m =>
                                m.id === lastMsgId
                                    ? { ...m, role: 'report' as const, section, complete: true }
                                    : m
                            )
                        }))
                        // 早期 agent bubble 标记为已完成（保留为 assistant 卡片）
                        if (earlierMsgIds.length > 0) {
                            markAgentMessagesComplete(earlierMsgIds)
                        }
                    } else {
                        // 兜底：没找到对应气泡，直接创建 ReportCard
                        const buffer = useAnalysisStore.getState().streamingSections[section]?.buffer || ''
                        addChatMessage({
                            id: `stream:${section}`,
                            role: 'report',
                            section,
                            content: buffer,
                            complete: true,
                            timestamp: new Date().toISOString(),
                        })
                    }
                }
                break
            }
            case 'agent.tool_call':
                // 工具调用信息不再在对话框显示，减少噪音
                break
            case 'agent.writing':
                // 气泡已经表示 agent 正在撰写，不再额外发系统消息
                break
            case 'agent.milestone': {
                const { stage, title, summary } = data as { stage: string; title: string; summary: string }
                if (stage === 'final_decision') {
                    pushAssistant(`**${title}**\n\n${summary}`)
                }
                break
            }
            case 'agent.debate.token': {
                const raw = data as Record<string, unknown>
                const debate = raw.debate
                const token = raw.token
                if (
                    (debate !== 'research' && debate !== 'risk') ||
                    typeof raw.agent !== 'string' ||
                    typeof raw.round !== 'number' ||
                    typeof token !== 'string'
                ) break
                appendDebateToken(
                    debate, raw.agent, raw.round, token,
                    typeof raw.horizon === 'string' ? raw.horizon : undefined,
                )
                break
            }
            case 'agent.debate': {
                const raw = data as Record<string, unknown>
                const debate = raw.debate
                const agent = raw.agent
                const round = raw.round
                const content = raw.content
                if (
                    (debate !== 'research' && debate !== 'risk') ||
                    typeof agent !== 'string' ||
                    typeof round !== 'number' ||
                    typeof content !== 'string'
                ) {
                    console.warn('[SSE] Malformed agent.debate payload, skipping:', raw)
                    break
                }
                addDebateMessage({
                    debate,
                    agent,
                    round,
                    content,
                    isVerdict: raw.is_verdict === true,
                    horizon: typeof raw.horizon === 'string' ? raw.horizon : undefined,
                })
                break
            }
            default:
                break
        }
    }

    const processJobEventStreamBody = async (response: Response) => {
        if (!response.body) throw new Error('SSE stream unavailable')
        streamActiveRef.current = true
        setIsConnected(true)
        const jid = useAnalysisStore.getState().currentJobId?.trim()
        if (jid) {
            const prefix = `agent-bubble:${jid}:`
            for (const m of useAnalysisStore.getState().chatMessages) {
                if (m.role !== 'assistant' || !m.agent || !m.id.startsWith(prefix)) continue
                const rest = m.id.slice(prefix.length)
                const colon = rest.lastIndexOf(':')
                if (colon < 0) continue
                const horizonSeg = rest.slice(colon + 1)
                const agentKey = `${m.agent}-${horizonSeg}`
                agentMessageMapRef.current[agentKey] = m.id
                const c = m.content || ''
                firstTokenMapRef.current[m.id] = !/^###\s/m.test(c)
            }
        }
        try {
            const end = await consumeSseStream(
                response.body,
                (eventName, data) => {
                    parseAndDispatch({ event: eventName, data })
                },
                {
                    onEventId: (id) => {
                        const jid = useAnalysisStore.getState().currentJobId
                        if (jid) setLastEventIdForJob(jid, id)
                    },
                },
            )
            return end
        } finally {
            streamActiveRef.current = false
            setIsConnected(false)
        }
    }

    /** 主连接断开后，用独立 /v1/jobs/:id/events 续订直至完成或轮询兜底 */
    const tryResumeJobViaDedicatedEvents = async (
        options?: { quiet?: boolean; skipPrePoll?: boolean },
    ) => {
        const jobId = useAnalysisStore.getState().currentJobId
        if (!jobId) return false
        if (dedicatedResumeInFlightRef.current) return false
        // 已有任意活跃 SSE 流（如 chat completion 主流）时不再开第二条，避免双流写入同一 store。
        if (streamActiveRef.current) return false
        if (useAnalysisStore.getState().isConnected) return false
        dedicatedResumeInFlightRef.current = true
        try {
            // 表单提交直后已知任务为 pending：跳过 pre-poll 延迟与状态查询，立刻开 SSE，
            // 让工作流卡片与对话气泡尽早出现。
            if (!options?.skipPrePoll) {
                await sleep(JOB_RESUME_PRE_POLL_DELAY_MS)
                const status = await api.getJobStatus(jobId)
                if (status.status === 'completed') {
                    await hydrateCompletedJob(jobId, { quiet: options?.quiet })
                    return true
                }
                if (status.status === 'failed') {
                    const detail = status.error || 'unknown error'
                    if (!failureNoticeShownRef.current) {
                        failureNoticeShownRef.current = true
                        pushAssistant(formatJobFailedUserMessage(detail))
                    }
                    setAnalysisRunState('failed', detail)
                    streamOutcomeRef.current = 'failed'
                    setIsAnalyzing(false)
                    return true
                }
            }

            const response = await api.openJobEventStream(
                jobId,
                useAnalysisStore.getState().lastEventIdByJob[jobId] ?? 0,
            )
            await processJobEventStreamBody(response)

            if (streamOutcome() === 'completed') return true

            return await recoverInterruptedJob()
        } catch (e) {
            console.error('[resume job events]', e)
            return await recoverInterruptedJob()
        } finally {
            dedicatedResumeInFlightRef.current = false
        }
    }

    /**
     * 统一的「任务恢复」effect：进入页面/挂载新 jobId/收到 resumeSignal 时执行一次。
     *
     * - 已有活跃 SSE 流时（streamActiveRef）直接跳过，避免与 chat 主流并行打开第二条事件流。
     * - 根据 `GET /v1/jobs/:id` 的状态分支：completed→回填；failed→标记；queued→排队监视；
     *   pending/running→强制运行态 + 续订事件流。
     */
    useEffect(() => {
        if (!currentJobId) return undefined
        let cancelled = false

        const run = async () => {
            if (cancelled) return
            if (streamActiveRef.current || dedicatedResumeInFlightRef.current || resumeInProgressRef.current) return
            if (useAnalysisStore.getState().isConnected) return

            resumeInProgressRef.current = true
            try {
                await sleep(MOUNT_RESUME_PRE_POLL_DELAY_MS)
                if (cancelled) return

                let status
                try {
                    status = await api.getJobStatus(currentJobId)
                } catch (error) {
                    if (isJobNotFoundError(error)) {
                        if (missingJobNoticeForRef.current !== currentJobId) {
                            missingJobNoticeForRef.current = currentJobId
                            pushSystem(`上次分析任务 ${currentJobId.slice(0, 8)}… 已不存在，可能是后端服务重启导致。已结束恢复流程。`)
                        }
                        setCurrentJobId(null)
                        setActiveAnalysisJobFocus(null)
                        setCurrentHorizon(null)
                        setIsAnalyzing(false)
                        setIsConnected(false)
                        setAnalysisRunState('failed', 'job not found on mount resume')
                        streamOutcomeRef.current = 'failed'
                        return
                    }
                    return
                }
                if (cancelled) return

                if (status.status === 'completed') {
                    await hydrateCompletedJob(currentJobId, { quiet: true })
                    return
                }

                if (status.status === 'failed') {
                    if (!failureNoticeShownRef.current) {
                        failureNoticeShownRef.current = true
                        pushAssistant(formatJobFailedUserMessage(status.error || 'unknown error'))
                    }
                    setAnalysisRunState('failed', status.error || 'unknown error')
                    setIsAnalyzing(false)
                    streamOutcomeRef.current = 'failed'
                    return
                }

                if (status.status === 'queued' || status.status === 'paused') {
                    setAnalysisRunState('idle')
                    setIsAnalyzing(false)
                    startQueuedWatcher(currentJobId)
                    return
                }

                // pending / running
                stopQueuedWatcher()
                setAnalysisRunState('running')
                setIsAnalyzing(true)
                streamOutcomeRef.current = 'running'
                await tryResumeJobViaDedicatedEvents({ quiet: true })
            } finally {
                // 若在 sleep/await 期间 jobId 切换导致 cancelled，也必须释放锁，否则会永久挡住后续恢复与排队监视
                resumeInProgressRef.current = false
            }
        }

        void run()
        return () => {
            cancelled = true
            resumeInProgressRef.current = false
        }
    }, [currentJobId, resumeSignal])

    /** 健康守护：分析进行中且无活跃流时，每 5s 尝试续订一次（不会与已活跃流冲突）。 */
    useEffect(() => {
        if (!currentJobId || analysisRunState !== 'running') return undefined
        let cancelled = false
        const tick = () => {
            if (cancelled) return
            if (streamActiveRef.current || dedicatedResumeInFlightRef.current || resumeInProgressRef.current) return
            if (useAnalysisStore.getState().isConnected) return
            void tryResumeJobViaDedicatedEvents({ quiet: true })
        }
        const timer = window.setInterval(tick, 5000)
        return () => {
            cancelled = true
            window.clearInterval(timer)
        }
    }, [currentJobId, analysisRunState])

    useEffect(() => {
        return () => {
            stopQueuedWatcher()
        }
    }, [])

    const submitPrompt = async (prompt: string) => {
        // Inject custom analysis prompt from settings if set
        const customPrompt = localStorage.getItem(perUserLocalStorageKey('ta-custom-prompt'))?.trim() || ''
        const fullPrompt = customPrompt ? `${prompt}\n\n[分析要求] ${customPrompt}` : prompt

        setSubmitting(true)
        const submittingId = `submitting-${Date.now()}`
        typingIndicatorIdRef.current = submittingId
        addChatMessage({
            id: submittingId,
            role: 'system',
            content: '__submitting__',
            timestamp: new Date().toISOString(),
        })

        const clearSubmittingIndicator = () => {
            useAnalysisStore.setState(state => ({
                chatMessages: state.chatMessages.filter(m => m.id !== submittingId),
            }))
            if (typingIndicatorIdRef.current === submittingId) {
                typingIndicatorIdRef.current = null
            }
        }

        try {
            const runLegacySubmit = async () => {
                const legacyResp = await api.chatCompletion(
                    [{ role: 'user', content: fullPrompt }],
                    false,
                    selectedAnalysts,
                )
                const payload = (await legacyResp.json().catch(() => null)) as
                    | { id?: string; choices?: Array<{ message?: { content?: string } }> }
                    | null
                const message = payload?.choices?.[0]?.message?.content || ''
                const legacyJobId = String(payload?.id || '').replace(/^chatcmpl-/, '')
                const focusJobId = useAnalysisStore.getState().currentJobId
                if (legacyJobId && !focusJobId && /已启动分析任务|analysis task/i.test(message)) {
                    resetStreamSessionRefs()
                    setCurrentJobId(legacyJobId)
                    setAnalysisRunState('running')
                    setIsAnalyzing(true)
                    setIsConnected(false)
                    streamOutcomeRef.current = 'running'
                    pushSystem('任务已提交（旧通道），正在切换到该任务实时进度。')
                    void tryResumeJobViaDedicatedEvents({ quiet: true })
                    return
                }
                if (legacyJobId && /进入队列|排队任务/i.test(message)) {
                    pushSystem(
                        `任务已入队（旧通道）：${legacyJobId.slice(0, 8)}…\n\n[去任务中心](/tasks) · [取消该排队任务](ta://cancel-queued/${legacyJobId})`,
                    )
                    return
                }
                pushSystem(message || '任务已提交（旧通道）。')
            }

            const applySubmitFeedback = (resp: {
                job_id: string
                status: 'pending' | 'queued' | 'rejected' | 'failed'
                symbol?: string | null
                task_label?: string | null
                waiting_ahead_count: number
                message?: string | null
            }) => {
                const label = (resp.task_label || resp.symbol || `任务 ${resp.job_id.slice(0, 8)}…`).trim()
                const focusJobId = useAnalysisStore.getState().currentJobId
                const stFocus = useAnalysisStore.getState()
                const focusLabel = stockDisplayLabel({
                    symbol: stFocus.activeAnalysisJobSymbol ?? stFocus.currentSymbol,
                    name: stFocus.activeAnalysisJobDisplayName ?? stFocus.currentSymbolDisplayName,
                })
                if (resp.status === 'failed' || resp.status === 'rejected') {
                    pushAssistant(resp.message || '提交失败，请稍后重试。')
                    return
                }
                if (resp.status === 'queued') {
                    const ahead = Math.max(0, Number(resp.waiting_ahead_count || 0))
                    pushSystem(
                        `已入队：${label}（前方 ${ahead} 个）。\n\n[去任务中心](/tasks) · [取消该排队任务](ta://cancel-queued/${resp.job_id})`,
                    )
                    // 本次表单提交的任务必须挂到当前会话：persist 里可能残留旧 currentJobId，不能再用 !focusJobId 判断
                    resetStreamSessionRefs()
                    setCurrentJobId(resp.job_id)
                    if (resp.symbol) {
                        setCurrentSymbol(resp.symbol)
                        setActiveAnalysisJobFocus(resp.symbol, null)
                        enrichAnalysisSymbolDisplayName(resp.symbol)
                        onSymbolDetected(resp.symbol)
                    }
                    setIsAnalyzing(false)
                    setIsConnected(false)
                    setAnalysisRunState('idle')
                    streamOutcomeRef.current = 'running'
                    startQueuedWatcher(resp.job_id)
                    return
                }
                // pending
                if (!focusJobId || focusJobId !== resp.job_id) {
                    resetStreamSessionRefs()
                    setCurrentJobId(resp.job_id)
                    if (resp.symbol) {
                        setCurrentSymbol(resp.symbol)
                        setActiveAnalysisJobFocus(resp.symbol, null)
                        enrichAnalysisSymbolDisplayName(resp.symbol)
                        onSymbolDetected(resp.symbol)
                    }
                    setAnalysisRunState('running')
                    setIsAnalyzing(true)
                    setIsConnected(false)
                    streamOutcomeRef.current = 'running'
                    pushSystem(`已开始执行：${label}`)
                    // 表单提交直后任务已确定为 pending：跳过 pre-poll，立即开 SSE。
                    void tryResumeJobViaDedicatedEvents({ quiet: true, skipPrePoll: true })
                    return
                }
                pushSystem(
                    `已受理新任务：${label}。当前仍在查看「${focusLabel || '执行中任务'}」的实时进度。\n\n[去任务中心](/tasks)`,
                )
            }

            if (submitV2Enabled) {
                try {
                    const resp = await api.submitAnalysisTask({
                        text: fullPrompt,
                        selected_analysts: selectedAnalysts,
                    })
                    applySubmitFeedback(resp)
                    return
                } catch (error) {
                    const message = error instanceof Error ? error.message : String(error)
                    // 兼容旧后端：未部署 /v1/me/tasks/submit 时常见 404/405；此时自动回退旧提交通道。
                    if (!/503|404|405|disabled|method not allowed|not found|v2/i.test(message.toLowerCase())) {
                        throw error
                    }
                }
            }
            await runLegacySubmit()
        } catch {
            pushAssistant('发生意外错误，请稍后重试。')
        } finally {
            clearSubmittingIndicator()
            setSubmitting(false)
            const nextPrompt = pendingSubmitPromptsRef.current.shift()
            if (nextPrompt) {
                void submitPrompt(nextPrompt)
            }
        }
    }

    const handleSubmit = async (e: FormEvent) => {
        e.preventDefault()
        const prompt = input.trim()
        if (!prompt) return

        setInput('')
        addChatMessage({
            id: `${Date.now()}-${Math.random()}`,
            role: 'user',
            content: prompt,
            timestamp: new Date().toISOString(),
        })

        if (submitting) {
            pendingSubmitPromptsRef.current.push(prompt)
            return
        }
        await submitPrompt(prompt)
    }

    const hasAnyReport = chatMessages.some(m => m.role === 'report')
    const runningTaskDisplay = stockDisplayLabel({
        symbol: activeAnalysisJobSymbol ?? currentSymbol,
        name: activeAnalysisJobDisplayName ?? currentSymbolDisplayName,
    })

    return (
        <aside className="card h-full min-h-0 flex flex-col overflow-hidden" data-tone="chat">
            <div className="flex items-center justify-between mb-3">
                <div className="flex items-center gap-2">
                    <Bot className="w-5 h-5 text-cyan-500" />
                    <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">智能分析</h2>
                </div>
                <div className="flex items-center gap-2">
                    {onShowReport && hasAnyReport && (
                        <button
                            onClick={() => onShowReport()}
                            className="text-xs px-2 py-1 rounded bg-blue-100 dark:bg-blue-500/20 text-blue-600 dark:text-blue-400 hover:bg-blue-200 dark:hover:bg-blue-500/30 transition-colors flex items-center gap-1"
                        >
                            <FileText className="w-3 h-3" />
                            查看报告
                        </button>
                    )}
                    <button
                        onClick={() => {
                            if (window.confirm('确定要清空对话和分析结果吗？')) {
                                clearSession()
                            }
                        }}
                        disabled={submitting}
                        className="text-xs px-2 py-1 rounded bg-slate-100 dark:bg-slate-700 text-slate-500 dark:text-slate-400 hover:bg-red-100 dark:hover:bg-red-500/20 hover:text-red-600 dark:hover:text-red-400 transition-colors flex items-center gap-1 disabled:opacity-30 disabled:cursor-not-allowed disabled:hover:bg-slate-100 dark:disabled:hover:bg-slate-700 disabled:hover:text-slate-500"
                        title="清空对话"
                    >
                        <Trash2 className="w-3 h-3" />
                    </button>
                    {(submitting || isAnalyzing) && (
                        <span className="badge-blue inline-flex items-center gap-1">
                            <Loader2 className="w-3 h-3 animate-spin" />
                            分析中
                        </span>
                    )}
                </div>
            </div>

            <div className="text-xs text-slate-500 dark:text-slate-400 mb-3 flex items-center gap-1">
                <Sparkles className="w-3 h-3" />
                示例：分析贵州茅台 600519.SH 今天走势
            </div>

            {(submitting || isAnalyzing) && (
                <div className="mb-3 rounded-xl border border-amber-200 dark:border-amber-900/50 bg-amber-50/90 dark:bg-amber-950/40 px-3 py-2.5 flex items-start gap-2 text-xs text-amber-900 dark:text-amber-100/95 leading-snug">
                    <Loader2 className="w-3.5 h-3.5 shrink-0 mt-0.5 animate-spin text-amber-600 dark:text-amber-400" />
                    <span>
                        {currentJobId ? (
                            <>
                                有「<strong className="font-semibold">{runningTaskDisplay}</strong>
                                」智能分析任务进行中。你可以继续提交新任务，新任务会自动进入队列，并可在「任务中心」查看和调整顺序。
                            </>
                        ) : (
                            <>正在提交任务并识别标的，请稍候…</>
                        )}
                    </span>
                </div>
            )}

            {/* 快速提示 */}
            <div className="flex flex-wrap gap-2 mb-3">
                {PRESET_PROMPTS.map((prompt) => (
                    <button
                        key={prompt}
                        type="button"
                        disabled={submitting}
                        onClick={() => setInput(prompt)}
                        className="text-xs px-2.5 py-1 rounded-md border border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400 hover:border-blue-400 dark:hover:border-blue-500 hover:text-slate-900 dark:hover:text-slate-200 disabled:opacity-40 disabled:cursor-not-allowed disabled:hover:border-slate-200 dark:disabled:hover:border-slate-600"
                    >
                        {prompt}
                    </button>
                ))}
            </div>

            {/* 聊天内容 */}
            <div ref={messagesContainerRef} className="flex-1 min-h-0 overflow-y-auto space-y-2 pr-1">
                {chatMessages.map((msg) => {
                    // Report card
                    if (msg.role === 'report' && msg.section) {
                        return (
                            <ReportCard
                                key={msg.id}
                                section={msg.section}
                                content={msg.content}
                                streaming={!msg.complete}
                                onOpen={() => onShowReport?.(msg.section)}
                            />
                        )
                    }

                    // Status indicator（提交后立即显示，随 SSE 事件切换阶段）
                    if (msg.content.startsWith('__')) {
                        const c = msg.content
                        let label = ''
                        let icon: 'dots' | 'spin' = 'dots'
                        let colorCls = 'bg-slate-100 dark:bg-slate-800 border-slate-200 dark:border-slate-700 text-slate-500'

                        if (c === '__typing__') {
                            label = ''
                            icon = 'dots'
                        } else if (c === '__submitting__') {
                            label = '正在提交任务...'
                            icon = 'spin'
                            colorCls = 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/30 text-blue-500 dark:text-blue-400'
                        } else if (c === '__parsing__') {
                            label = '正在识别标的与意图...'
                            icon = 'spin'
                            colorCls = 'bg-blue-50 dark:bg-blue-500/10 border-blue-200 dark:border-blue-500/30 text-blue-500 dark:text-blue-400'
                        } else if (c.startsWith('__status:collecting:')) {
                            const sym = c.replace('__status:collecting:', '').replace('__', '')
                            label = `已识别 ${sym}，正在采集行情数据...`
                            icon = 'spin'
                            colorCls = 'bg-cyan-50 dark:bg-cyan-500/10 border-cyan-200 dark:border-cyan-500/30 text-cyan-500 dark:text-cyan-400'
                        } else if (c === '__status:analyzing__') {
                            label = '数据就绪，多智能体协作分析启动中...'
                            icon = 'spin'
                            colorCls = 'bg-emerald-50 dark:bg-emerald-500/10 border-emerald-200 dark:border-emerald-500/30 text-emerald-500 dark:text-emerald-400'
                        }

                        return (
                            <div key={msg.id} className="flex items-center gap-2">
                                <div className={`flex items-center gap-2 px-3 py-2 rounded-xl border text-xs transition-colors duration-300 ${colorCls}`}>
                                    {icon === 'spin' ? (
                                        <>
                                            <Loader2 className="w-3.5 h-3.5 animate-spin shrink-0" />
                                            <span className="animate-pulse">{label}</span>
                                        </>
                                    ) : (
                                        <>
                                            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '0ms' }} />
                                            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '150ms' }} />
                                            <span className="w-1.5 h-1.5 rounded-full bg-current animate-bounce" style={{ animationDelay: '300ms' }} />
                                        </>
                                    )}
                                </div>
                            </div>
                        )
                    }

                    // Agent streaming messages → compact card with live preview
                    const agentMeta = msg.agent ? AGENT_META_MAP[msg.agent] : null
                    const isPending = pendingAgentMsgIdsRef.current.has(msg.id)
                    const isCompleted = !!msg.complete
                    const isExpanded = expandedAgentMsgId === msg.id

                    if (msg.agent && agentMeta && msg.role === 'assistant') {
                        // Extract preview text: strip markdown headers, bold, collapse whitespace
                        const textOnly = sanitizeReportMarkdown(msg.content)
                            .replace(/^#{1,4}\s+.*$/gm, '')
                            .replace(/\*\*/g, '')
                            .replace(/\n{2,}/g, ' ')
                            .trim()
                        const preview = textOnly.slice(0, 80)

                        // 已完成的 agent 卡片 → 和 ReportCard 视觉统一
                        if (isCompleted) {
                            return (
                                <div key={msg.id} className="rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/50 overflow-hidden transition-all">
                                    <button
                                        onClick={() => setExpandedAgentMsgId(prev => prev === msg.id ? null : msg.id)}
                                        className="w-full flex items-center gap-2.5 px-3 py-2.5 text-left hover:border-blue-400 dark:hover:bg-slate-800 transition-colors group"
                                    >
                                        <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg ${agentMeta.bgCls} shrink-0`}>
                                            <agentMeta.Icon className={`w-4 h-4 ${agentMeta.iconCls}`} />
                                        </span>
                                        <div className="flex-1 min-w-0">
                                            <p className="text-sm font-medium text-slate-700 dark:text-slate-200 group-hover:text-blue-600 dark:group-hover:text-blue-300 transition-colors">{agentMeta.label}</p>
                                            <p className="text-xs text-slate-500 truncate mt-0.5">{preview}...</p>
                                        </div>
                                        <ChevronRight className={`w-4 h-4 shrink-0 transition-transform ${isExpanded ? 'rotate-90 text-blue-400' : 'text-slate-500 group-hover:text-blue-400'}`} />
                                    </button>
                                    {isExpanded && (
                                        <div className="px-3 pb-2 border-t border-slate-200 dark:border-slate-700/50 max-h-60 overflow-y-auto">
                                            <div className="prose dark:prose-invert prose-xs max-w-none mt-2 text-[12px] leading-relaxed">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                    {sanitizeReportMarkdown(msg.content)}
                                                </ReactMarkdown>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )
                        }

                        // 进行中的 agent 卡片（pending / streaming）
                        return (
                            <div key={msg.id} className="rounded-xl bg-slate-50 dark:bg-slate-800/60 border border-slate-200 dark:border-slate-700/50 transition-all overflow-hidden">
                                <button
                                    onClick={() => !isPending && setExpandedAgentMsgId(prev => prev === msg.id ? null : msg.id)}
                                    className="w-full flex items-center gap-2.5 px-3 py-2 text-left hover:bg-slate-100 dark:hover:bg-slate-700/30 transition-colors"
                                >
                                    <span className={`inline-flex items-center justify-center w-7 h-7 rounded-lg ${agentMeta.bgCls} shrink-0`}>
                                        <agentMeta.Icon className={`w-4 h-4 ${agentMeta.iconCls}`} />
                                    </span>
                                    <div className="flex-1 min-w-0">
                                        <p className="text-xs font-medium text-slate-600 dark:text-slate-300">{agentMeta.label}</p>
                                        {isPending ? (
                                            <p className="text-[11px] text-slate-400 dark:text-slate-500 animate-pulse">正在推理分析中...</p>
                                        ) : (
                                            <p className="text-[11px] text-slate-500 dark:text-slate-400 truncate" dir="rtl">
                                                <bdi>{textOnly.slice(-120) || '撰写中...'}</bdi>
                                            </p>
                                        )}
                                    </div>
                                    {isPending ? (
                                        <Loader2 className="w-3.5 h-3.5 text-blue-400 animate-spin shrink-0" />
                                    ) : (
                                        <span className="text-[10px] text-emerald-500 dark:text-emerald-400 font-medium shrink-0 animate-pulse">撰写中</span>
                                    )}
                                </button>
                                {isExpanded && !isPending && (
                                    <div className="px-3 pb-2 border-t border-slate-200 dark:border-slate-700/50 max-h-60 overflow-y-auto">
                                        <div className="prose dark:prose-invert prose-xs max-w-none mt-2 text-[12px] leading-relaxed">
                                            <ReactMarkdown remarkPlugins={[remarkGfm]}>
                                                {sanitizeReportMarkdown(msg.content)}
                                            </ReactMarkdown>
                                        </div>
                                    </div>
                                )}
                            </div>
                        )
                    }

                    // Normal messages (user / assistant without agent / system)
                    return (
                        <div key={msg.id} className={`flex flex-col ${msg.role === 'user' ? 'items-end' : 'items-start'}`}>
                            <div
                                className={`max-w-[92%] rounded-xl px-3 py-2 text-sm leading-relaxed ${
                                    msg.role === 'user'
                                        ? 'bg-blue-100 dark:bg-blue-500/20 border border-blue-300 dark:border-blue-500/30 text-slate-900 dark:text-slate-100'
                                        : msg.role === 'system'
                                            ? 'bg-slate-50 dark:bg-slate-800/50 border border-slate-200 dark:border-slate-700 text-slate-500 dark:text-slate-400 italic text-xs'
                                            : 'bg-slate-100 dark:bg-slate-800 border border-slate-200 dark:border-slate-700 text-slate-700 dark:text-slate-300'
                                }`}
                            >
                                {msg.role === 'user' ? (
                                    msg.content
                                ) : (
                                    <div className="prose dark:prose-invert prose-sm max-w-none">
                                        <ReactMarkdown
                                            remarkPlugins={[remarkGfm]}
                                            components={{
                                                table: ({ children }) => (
                                                    <table className="w-full border-collapse border border-slate-300 dark:border-slate-600 my-2 text-xs">{children}</table>
                                                ),
                                                thead: ({ children }) => (
                                                    <thead className="bg-slate-100 dark:bg-slate-700">{children}</thead>
                                                ),
                                                th: ({ children }) => (
                                                    <th className="border border-slate-300 dark:border-slate-600 px-2 py-1 text-left font-semibold text-slate-700 dark:text-slate-300">{children}</th>
                                                ),
                                                td: ({ children }) => (
                                                    <td className="border border-slate-300 dark:border-slate-600 px-2 py-1 text-slate-600 dark:text-slate-400">{children}</td>
                                                ),
                                                tr: ({ children }) => (
                                                    <tr className="even:bg-slate-50 dark:even:bg-slate-800/50">{children}</tr>
                                                ),
                                                a: ({ href, children }) => (
                                                    <a
                                                        href={href}
                                                        onClick={(event) => {
                                                            if (!href) return
                                                            if (href.startsWith('/')) {
                                                                event.preventDefault()
                                                                void handleSystemActionLink(href)
                                                                return
                                                            }
                                                            if (href.startsWith('ta://')) {
                                                                event.preventDefault()
                                                                void handleSystemActionLink(href)
                                                            }
                                                        }}
                                                        className="text-blue-600 dark:text-blue-400 hover:underline"
                                                    >
                                                        {children}
                                                    </a>
                                                ),
                                            }}
                                        >
                                            {msg.role === 'assistant'
                                                ? sanitizeReportMarkdown(msg.content)
                                                : msg.content}
                                        </ReactMarkdown>
                                    </div>
                                )}
                            </div>
                        </div>
                    )
                })}
                <div ref={messagesEndRef} />
            </div>

            {/* 输入框 */}
            <form onSubmit={handleSubmit} className="mt-3 shrink-0">
                <div className="flex items-center gap-2">
                    <input
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => {
                            if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') {
                                e.preventDefault()
                                handleSubmit(e as unknown as FormEvent)
                            }
                        }}
                        placeholder="直接描述你的分析需求..."
                        className="input flex-1"
                        title="Enter 发送，Ctrl+Enter 也可发送"
                    />
                    <button
                        type="submit"
                        disabled={!input.trim() || submitting}
                        className="btn-primary shrink-0 inline-flex items-center justify-center p-2.5"
                        title="发送"
                        aria-label="发送"
                    >
                        <Send className="w-4 h-4" />
                    </button>
                </div>
            </form>
        </aside>
    )
}
