import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type {
    Agent,
    JobStatus,
    AnalysisReport,
    LogEntry,
    AgentStatusEvent,
    AgentMessageEvent,
    AgentToolCallEvent,
    AgentReportEvent,
    AgentSnapshotEvent,
    ReportChunkEvent,
    AgentMilestoneEvent,
    AgentTokenEvent,
    StreamingSectionState,
    MilestoneMessage,
    RiskItem,
    KeyMetric,
    DebateMessage,
} from '@/types'
import { perUserLocalStorageKey } from '@/lib/perUserLocalKey'
import {
    isPersistableAgentList,
    trimDebateMessagesForPersist,
    trimStreamingSectionsForPersist,
} from '@/lib/analysisPersistTrim'
import { pickExchangeListedSymbol, resolveExchangeListedSymbol } from '@/utils/stockDisplay'
import { useChartStore } from '@/stores/chartStore'

export interface ChatMessage {
    id: string
    role: 'user' | 'assistant' | 'system' | 'report'
    content: string
    timestamp: string
    agent?: string      // The name of the agent who sent the message
    section?: string    // only for role='report'
    complete?: boolean  // only for role='report'
}

const createInitialChatMessages = (): ChatMessage[] => [
    {
        id: 'init',
        role: 'assistant',
        content: '我是你的 A 股多智能体投研助手。直接告诉我你想分析的标的和日期。',
        timestamp: new Date().toISOString(),
    },
]

interface AnalysisState {
    // Current Job
    currentJobId: string | null
    currentSymbol: string
    jobStatus: JobStatus | null

    // Agents
    agents: Agent[]

    // Report
    report: AnalysisReport | null

    // Structured data from job.completed SSE event (LLM-extracted)
    riskItems: RiskItem[]
    keyMetrics: KeyMetric[]
    jobConfidence: number | null
    jobTargetPrice: number | null
    jobStopLoss: number | null

    // Streaming Report State (for typewriter effect)
    streamingSections: Record<string, StreamingSectionState>

    // Milestones for chat display
    milestones: MilestoneMessage[]

    // Debate messages (transient, for battle view)
    debateMessages: Record<string, DebateMessage[]>
    debateScrollTick: number

    // Chat messages (persisted across route changes)
    chatMessages: ChatMessage[]

    // Logs (kept for system messages only)
    logs: LogEntry[]

    // Loading States
    isAnalyzing: boolean
    isConnected: boolean
    analysisRunState: 'idle' | 'running' | 'completed' | 'failed'
    analysisRunError: string | null

    // Current analysis horizon (for badge display)
    currentHorizon: string | null

    // Current analysis — resolved Chinese name (instrument_context or client map), optional
    currentSymbolDisplayName: string | null

    /** Server SSE monotonic id per job (for ?after= / Last-Event-ID replay) */
    lastEventIdByJob: Record<string, number>

    /** 当前智能分析任务绑定的标的（与 K 线/页面 currentSymbol 解耦，避免提示与真实任务不一致） */
    activeAnalysisJobSymbol: string | null
    activeAnalysisJobDisplayName: string | null

    // Actions
    setCurrentJobId: (jobId: string | null) => void
    setActiveAnalysisJobFocus: (symbol: string | null, displayName?: string | null) => void
    setCurrentSymbol: (symbol: string) => void
    setCurrentSymbolDisplayName: (name: string | null) => void
    setJobStatus: (status: JobStatus | null) => void
    updateAgentStatus: (event: AgentStatusEvent) => void
    updateAgentSnapshot: (event: AgentSnapshotEvent) => void
    addAgentMessage: (event: AgentMessageEvent) => void
    addAgentToolCall: (event: AgentToolCallEvent) => void
    addAgentReport: (event: AgentReportEvent) => void
    addReportChunk: (event: ReportChunkEvent) => void
    addAgentToken: (event: AgentTokenEvent) => void
    addMilestone: (event: AgentMilestoneEvent) => void
    addLog: (log: LogEntry) => void
    setReport: (report: AnalysisReport | null) => void
    setStructuredData: (data: {
        riskItems?: RiskItem[]
        keyMetrics?: KeyMetric[]
        confidence?: number | null
        targetPrice?: number | null
        stopLoss?: number | null
    }) => void
    setIsAnalyzing: (isAnalyzing: boolean) => void
    setIsConnected: (isConnected: boolean) => void
    setAnalysisRunState: (state: 'idle' | 'running' | 'completed' | 'failed', error?: string | null) => void
    setCurrentHorizon: (horizon: string | null) => void
    setLastEventIdForJob: (jobId: string, eventId: number) => void
    clearJobEventCursor: (jobId: string) => void
    addChatMessage: (message: ChatMessage) => void
    appendToChatMessage: (id: string, chunk: string) => void
    setMessageContent: (id: string, content: string) => void
    markAgentMessagesComplete: (msgIds?: string[]) => void
    addDebateMessage: (msg: DebateMessage) => void
    appendDebateToken: (debate: string, agent: string, round: number, token: string, horizon?: string) => void
    clearChatMessages: () => void
    clearSession: () => void
    reset: () => void
}

/** 流式 UI 合并：减少每个 token 触发的 Zustand + persist 序列化次数 */
let streamFlushRaf = 0
const pendingChatReplace = new Map<string, string>()
const pendingChatAppend = new Map<string, string>()
const pendingSectionAppend = new Map<string, string>()

function mergePendingStreamUIIntoState(state: AnalysisState): Partial<AnalysisState> | null {
    if (!pendingChatReplace.size && !pendingChatAppend.size && !pendingSectionAppend.size) {
        return null
    }
    const repl = new Map(pendingChatReplace)
    const app = new Map(pendingChatAppend)
    const sec = new Map(pendingSectionAppend)
    pendingChatReplace.clear()
    pendingChatAppend.clear()
    pendingSectionAppend.clear()

    let chatMessages = state.chatMessages
    let streamingSections = state.streamingSections
    let touchedChat = false
    let touchedSec = false

    const touchChat = () => {
        if (!touchedChat) {
            chatMessages = [...state.chatMessages]
            touchedChat = true
        }
    }
    const touchSec = () => {
        if (!touchedSec) {
            streamingSections = { ...state.streamingSections }
            touchedSec = true
        }
    }

    const byId = new Map(chatMessages.map((m, i) => [m.id, i] as const))
    for (const [id, content] of repl) {
        const idx = byId.get(id)
        if (idx === undefined) continue
        touchChat()
        const prev = chatMessages[idx]!
        chatMessages[idx] = { ...prev, content }
    }
    for (const [id, chunk] of app) {
        const idx = byId.get(id)
        if (idx === undefined) continue
        touchChat()
        const prev = chatMessages[idx]!
        chatMessages[idx] = { ...prev, content: prev.content + chunk }
    }
    for (const [section, add] of sec) {
        touchSec()
        const cur = streamingSections[section] || {
            buffer: '',
            displayed: '',
            isTyping: false,
            isComplete: false,
        }
        const newBuf = cur.buffer + add
        streamingSections[section] = {
            ...cur,
            buffer: newBuf,
            displayed: newBuf,
            isTyping: true,
            isComplete: false,
        }
    }

    const out: Partial<AnalysisState> = {}
    if (touchedChat) out.chatMessages = chatMessages
    if (touchedSec) out.streamingSections = streamingSections
    return Object.keys(out).length ? out : null
}

function discardPendingStreamUI(): void {
    if (streamFlushRaf) {
        cancelAnimationFrame(streamFlushRaf)
        streamFlushRaf = 0
    }
    pendingChatReplace.clear()
    pendingChatAppend.clear()
    pendingSectionAppend.clear()
}

let flushPendingAnalysisStreamUIImpl: () => void = () => {}

const initialAgents: Agent[] = [
    // Analyst Team
    { id: 'market', name: 'Market Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'social', name: 'Social Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'news', name: 'News Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'fundamentals', name: 'Fundamentals Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'macro', name: 'Macro Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'smart_money', name: 'Smart Money Analyst', team: 'Analyst Team', status: 'pending' },
    { id: 'volume_price', name: 'Volume Price Analyst', team: 'Analyst Team', status: 'pending' },

    // Research Team
    { id: 'bull', name: 'Bull Researcher', team: 'Research Team', status: 'pending' },
    { id: 'bear', name: 'Bear Researcher', team: 'Research Team', status: 'pending' },
    { id: 'research_manager', name: 'Research Manager', team: 'Research Team', status: 'pending' },

    // Trading Team
    { id: 'trader', name: 'Trader', team: 'Trading Team', status: 'pending' },

    // Risk Management
    { id: 'aggressive', name: 'Aggressive Analyst', team: 'Risk Management', status: 'pending' },
    { id: 'conservative', name: 'Conservative Analyst', team: 'Risk Management', status: 'pending' },
    { id: 'neutral', name: 'Neutral Analyst', team: 'Risk Management', status: 'pending' },

    // Portfolio Management
    { id: 'portfolio_manager', name: 'Portfolio Manager', team: 'Portfolio Management', status: 'pending' },
]

// Debounced localStorage storage to avoid blocking the main thread on every token
function createDebouncedStorage(delay = 800) {
    let pending: [string, string] | null = null
    let timer: ReturnType<typeof setTimeout> | null = null
    return {
        getItem: (name: string) => localStorage.getItem(perUserLocalStorageKey(name)),
        setItem: (name: string, value: string) => {
            const key = perUserLocalStorageKey(name)
            pending = [key, value]
            if (timer) clearTimeout(timer)
            timer = setTimeout(() => {
                if (pending) { localStorage.setItem(pending[0], pending[1]); pending = null }
                timer = null
            }, delay)
        },
        removeItem: (name: string) => {
            pending = null
            if (timer) { clearTimeout(timer); timer = null }
            localStorage.removeItem(perUserLocalStorageKey(name))
        },
    }
}
const debouncedStorage = createDebouncedStorage()

export const useAnalysisStore = create<AnalysisState>()(persist((set) => {
    let scheduleStreamFlush: () => void = () => {}
    const applyMergedStream = (state: AnalysisState) => {
        const patch = mergePendingStreamUIIntoState(state)
        return patch ? { ...state, ...patch } : state
    }
    flushPendingAnalysisStreamUIImpl = () => {
        if (streamFlushRaf) {
            cancelAnimationFrame(streamFlushRaf)
            streamFlushRaf = 0
        }
        set(applyMergedStream)
    }
    scheduleStreamFlush = () => {
        if (streamFlushRaf) return
        streamFlushRaf = requestAnimationFrame(() => {
            streamFlushRaf = 0
            set(applyMergedStream)
        })
    }

    return {
    currentJobId: null,
    activeAnalysisJobSymbol: null,
    activeAnalysisJobDisplayName: null,
    currentSymbol: '000001.SH',
    jobStatus: null,
    agents: initialAgents,
    report: null,
    riskItems: [],
    keyMetrics: [],
    jobConfidence: null,
    jobTargetPrice: null,
    jobStopLoss: null,
    streamingSections: {},
    milestones: [],
    debateMessages: {},
        debateScrollTick: 0,
    chatMessages: createInitialChatMessages(),
    logs: [],
    isAnalyzing: false,
    isConnected: false,
    analysisRunState: 'idle',
    analysisRunError: null,
    currentHorizon: null,
    currentSymbolDisplayName: null,
    lastEventIdByJob: {},

    setCurrentJobId: (jobId) => set({ currentJobId: jobId }),

    setActiveAnalysisJobFocus: (symbol, displayName) =>
        set(() => {
            if (!symbol || !String(symbol).trim()) {
                return { activeAnalysisJobSymbol: null, activeAnalysisJobDisplayName: null }
            }
            const sym = resolveExchangeListedSymbol(symbol.trim()).trim().toUpperCase()
            const dn = displayName != null && String(displayName).trim() ? String(displayName).trim() : null
            return { activeAnalysisJobSymbol: sym, activeAnalysisJobDisplayName: dn }
        }),

    setCurrentSymbol: (symbol) =>
        set((state) => {
            const next = resolveExchangeListedSymbol(symbol.trim()).trim().toUpperCase()
            const prev = state.currentSymbol.trim().toUpperCase()
            if (prev === next) return { currentSymbol: next }
            queueMicrotask(() => {
                try {
                    const { currentSymbolDisplayName } = useAnalysisStore.getState()
                    useChartStore.getState().pushKlineQueryHistory(next, {
                        name: currentSymbolDisplayName?.trim() || undefined,
                    })
                } catch {
                    /* ignore */
                }
            })
            return { currentSymbol: next, currentSymbolDisplayName: null }
        }),

    setCurrentSymbolDisplayName: (name) => set({ currentSymbolDisplayName: name }),

    setJobStatus: (status) => set({ jobStatus: status }),

    updateAgentStatus: (event) => set((state) => ({
        agents: state.agents.map(agent => {
            if (agent.name !== event.agent) return agent
            const updates: Partial<Agent> = { status: event.status }
            if (event.status === 'in_progress' && !agent.startedAt) updates.startedAt = Date.now()
            if ((event.status === 'completed' || event.status === 'skipped') && !agent.finishedAt) updates.finishedAt = Date.now()
            return { ...agent, ...updates }
        })
    })),

    updateAgentSnapshot: (event) => set((state) => {
        const agentMap = new Map(event.agents.map(a => [a.agent, a.status]))
        return {
            agents: state.agents.map(agent => ({
                ...agent,
                status: agentMap.get(agent.name) || agent.status
            }))
        }
    }),

    // 不再将消息和工具调用添加到日志（已移至后端）
    addAgentMessage: () => {
        // 消息已移至后端日志，前端不再显示
    },

    addAgentToolCall: () => {
        // 工具调用已移至后端日志，前端不再显示
    },

    addAgentReport: (event) => set((state) => ({
        report: {
            ...state.report,
            [event.section]: event.content
        } as AnalysisReport
    })),

    // 处理报告分片（支持打字机效果）；增量分片 rAF 合并，降低主线程压力
    addReportChunk: (event) => {
        const { section, chunk, is_complete } = event
        if (is_complete) {
            flushPendingAnalysisStreamUIImpl()
            set((state) => {
                const current = state.streamingSections[section] || {
                    buffer: '',
                    displayed: '',
                    isTyping: false,
                    isComplete: false,
                }
                return {
                    streamingSections: {
                        ...state.streamingSections,
                        [section]: {
                            ...current,
                            buffer: current.buffer,
                            displayed: current.buffer,
                            isTyping: false,
                            isComplete: true,
                        },
                    },
                }
            })
            return
        }
        pendingSectionAppend.set(section, (pendingSectionAppend.get(section) || '') + chunk)
        scheduleStreamFlush()
    },

    addAgentToken: (event) => {
        const { report: section, token } = event
        if (!section) return
        pendingSectionAppend.set(section, (pendingSectionAppend.get(section) || '') + token)
        scheduleStreamFlush()
    },

    // 添加里程碑消息（用于对话框显示）
    addMilestone: (event) => set((state) => {
        const milestone: MilestoneMessage = {
            id: `${Date.now()}-${Math.random()}`,
            stage: event.stage,
            title: event.title,
            summary: event.summary,
            timestamp: event.timestamp
        }
        return {
            milestones: [...state.milestones, milestone]
        }
    }),

    // 添加聊天记录（持久化）
    addChatMessage: (message) => {
        flushPendingAnalysisStreamUIImpl()
        set((state) => ({
            chatMessages: [...state.chatMessages, message],
        }))
    },

    // 追加内容到已有消息（用于流式 token；rAF 批量合并）
    appendToChatMessage: (id, chunk) => {
        pendingChatAppend.set(id, (pendingChatAppend.get(id) || '') + chunk)
        scheduleStreamFlush()
    },

    setMessageContent: (id, content) => {
        pendingChatReplace.set(id, content)
        pendingChatAppend.delete(id)
        scheduleStreamFlush()
    },

    // 批量标记 agent 消息为已完成；不传 msgIds 则标记所有 agent assistant 消息
    markAgentMessagesComplete: (msgIds?: string[]) => {
        flushPendingAnalysisStreamUIImpl()
        set((state) => ({
            chatMessages: state.chatMessages.map(m => {
                if (m.role !== 'assistant' || !m.agent || m.complete) return m
                if (msgIds && !msgIds.includes(m.id)) return m
                return { ...m, complete: true }
            }),
        }))
    },
    // upsert: 同 agent+round 则替换（流式结束时用完整内容覆盖）
    addDebateMessage: (msg) => set((state) => {
        const key = msg.debate
        const existing = state.debateMessages[key] || []
        const idx = existing.findIndex(m => m.agent === msg.agent && m.round === msg.round)
        const updated = idx >= 0
            ? existing.map((m, i) => i === idx ? msg : m)
            : [...existing, msg]
        return {
            debateMessages: { ...state.debateMessages, [key]: updated }
        }
    }),

    // 流式 token 追加：找到已有消息则追加 content，否则创建新消息
    appendDebateToken: (debate, agent, round, token, horizon) => set((state) => {
        const key = debate
        const tick = state.debateScrollTick + 1
        const existing = state.debateMessages[key] || []
        const idx = existing.findIndex(m => m.agent === agent && m.round === round)
        if (idx >= 0) {
            const updated = existing.map((m, i) =>
                i === idx ? { ...m, content: m.content + token } : m
            )
            return { debateMessages: { ...state.debateMessages, [key]: updated }, debateScrollTick: tick }
        }
        const isVerdict = round === -1
        return {
            debateMessages: {
                ...state.debateMessages,
                [key]: [...existing, { debate: debate as 'research' | 'risk', agent, round, content: token, isVerdict, horizon }],
            },
            debateScrollTick: tick,
        }
    }),

    // 清空聊天记录
    clearChatMessages: () => {
        discardPendingStreamUI()
        set({
            chatMessages: createInitialChatMessages(),
        })
    },

    clearSession: () => {
        discardPendingStreamUI()
        set({
        currentJobId: null,
        activeAnalysisJobSymbol: null,
        activeAnalysisJobDisplayName: null,
        currentSymbol: '000001.SH',
        jobStatus: null,
        agents: initialAgents.map(a => ({ ...a, status: 'pending' })),
        report: null,
        riskItems: [],
        keyMetrics: [],
        jobConfidence: null,
        jobTargetPrice: null,
        jobStopLoss: null,
        streamingSections: {},
        debateMessages: {},
        debateScrollTick: 0,
        milestones: [],
        chatMessages: createInitialChatMessages(),
        logs: [],
        isAnalyzing: false,
        isConnected: false,
        analysisRunState: 'idle',
        analysisRunError: null,
        currentHorizon: null,
        currentSymbolDisplayName: null,
        lastEventIdByJob: {},
        })
    },
    addLog: (log) => set((state) => ({
        logs: [log, ...state.logs].slice(0, 100)
    })),

    setReport: (report) => set((state) => {
        const fromCtx = report?.instrument_context?.security_name?.trim()
        const rawSym = report?.symbol?.trim()
            ? report.symbol.trim()
            : state.currentSymbol
        const nextSymbol = resolveExchangeListedSymbol(rawSym).trim().toUpperCase()
        return {
            report,
            currentSymbol: nextSymbol,
            currentSymbolDisplayName: fromCtx || state.currentSymbolDisplayName,
        }
    }),

    setStructuredData: (data) => set({
        riskItems: data.riskItems ?? [],
        keyMetrics: data.keyMetrics ?? [],
        jobConfidence: data.confidence ?? null,
        jobTargetPrice: data.targetPrice ?? null,
        jobStopLoss: data.stopLoss ?? null,
    }),

    setIsAnalyzing: (isAnalyzing) => set({ isAnalyzing }),

    setIsConnected: (isConnected) => set({ isConnected }),

    setAnalysisRunState: (analysisRunState, error = null) => set({
        analysisRunState,
        analysisRunError: analysisRunState === 'failed' ? error : null,
    }),

    setCurrentHorizon: (horizon) => set({ currentHorizon: horizon }),

    setLastEventIdForJob: (jobId, eventId) =>
        set((state) => ({
            lastEventIdByJob: {
                ...state.lastEventIdByJob,
                [jobId]: Math.max(state.lastEventIdByJob[jobId] ?? 0, eventId),
            },
        })),

    clearJobEventCursor: (jobId) =>
        set((state) => {
            const next = { ...state.lastEventIdByJob }
            delete next[jobId]
            return { lastEventIdByJob: next }
        }),

    reset: () => set((state) => ({
        currentJobId: null,
        activeAnalysisJobSymbol: null,
        activeAnalysisJobDisplayName: null,
        currentSymbol: state.currentSymbol,
        jobStatus: null,
        agents: initialAgents.map(a => ({ ...a, status: 'pending' })),
        report: null,
        riskItems: [],
        keyMetrics: [],
        jobConfidence: null,
        jobTargetPrice: null,
        jobStopLoss: null,
        streamingSections: {},
        debateMessages: {},
        debateScrollTick: 0,
        milestones: [],
        // 注意：reset时不清空chatMessages，保持对话历史
        logs: [],
        isAnalyzing: false,
        isConnected: false,
        analysisRunState: 'idle',
        analysisRunError: null,
        currentHorizon: null,
        lastEventIdByJob: {},
    })),
  }
},
{
    name: 'tradingagents-analysis',
    version: 3,
    storage: createJSONStorage(() => debouncedStorage),
    partialize: (state) => ({
        currentSymbol: state.currentSymbol,
        currentSymbolDisplayName: state.currentSymbolDisplayName,
        currentJobId: state.currentJobId,
        activeAnalysisJobSymbol: state.activeAnalysisJobSymbol,
        activeAnalysisJobDisplayName: state.activeAnalysisJobDisplayName,
        analysisRunState: state.analysisRunState,
        currentHorizon: state.currentHorizon,
        agents: state.agents,
        streamingSections: trimStreamingSectionsForPersist(state.streamingSections),
        debateMessages: trimDebateMessagesForPersist(state.debateMessages),
        debateScrollTick: state.debateScrollTick,
        report: state.report,
        riskItems: state.riskItems,
        keyMetrics: state.keyMetrics,
        jobConfidence: state.jobConfidence,
        jobTargetPrice: state.jobTargetPrice,
        jobStopLoss: state.jobStopLoss,
        chatMessages: state.chatMessages.filter(m => !m.content.startsWith('__')),
        lastEventIdByJob: state.lastEventIdByJob,
    }),
    merge: (persistedState, currentState) => {
        const persisted = (persistedState ?? {}) as Partial<AnalysisState>
        const lastEventIdByJob =
            persisted.lastEventIdByJob && typeof persisted.lastEventIdByJob === 'object'
                ? persisted.lastEventIdByJob
                : {}
        const hasJob = Boolean(persisted.currentJobId?.trim())
        const chatMessages = persisted.chatMessages?.length
            ? persisted.chatMessages.filter(m => !m.content.startsWith('__'))
            : currentState.chatMessages

        if (!hasJob) {
            return {
                ...currentState,
                ...persisted,
                currentJobId: null,
                jobStatus: null,
                agents: initialAgents.map(a => ({ ...a, status: 'pending' as const })),
                streamingSections: {},
                debateMessages: {},
                debateScrollTick: 0,
                milestones: [],
                logs: [],
                isAnalyzing: false,
                isConnected: false,
                analysisRunState: 'idle',
                analysisRunError: null,
                lastEventIdByJob: {},
                chatMessages,
                activeAnalysisJobSymbol: null,
                activeAnalysisJobDisplayName: null,
                currentSymbol: pickExchangeListedSymbol(
                    persisted.currentSymbol ?? currentState.currentSymbol,
                    persisted.report?.symbol,
                ).trim().toUpperCase(),
            }
        }

        const agents = isPersistableAgentList(persisted.agents)
            ? persisted.agents
            : currentState.agents

        return {
            ...currentState,
            ...persisted,
            currentJobId: persisted.currentJobId ?? null,
            activeAnalysisJobSymbol:
                persisted.activeAnalysisJobSymbol != null && String(persisted.activeAnalysisJobSymbol).trim()
                    ? resolveExchangeListedSymbol(String(persisted.activeAnalysisJobSymbol).trim()).trim().toUpperCase()
                    : pickExchangeListedSymbol(
                          persisted.currentSymbol ?? currentState.currentSymbol,
                          persisted.report?.symbol,
                      ).trim().toUpperCase(),
            activeAnalysisJobDisplayName:
                persisted.activeAnalysisJobDisplayName ?? persisted.currentSymbolDisplayName ?? null,
            currentSymbol: pickExchangeListedSymbol(
                persisted.currentSymbol ?? currentState.currentSymbol,
                persisted.report?.symbol,
            ).trim().toUpperCase(),
            currentSymbolDisplayName: persisted.currentSymbolDisplayName ?? null,
            agents,
            streamingSections: persisted.streamingSections ?? {},
            debateMessages: persisted.debateMessages ?? {},
            debateScrollTick: persisted.debateScrollTick ?? 0,
            currentHorizon: persisted.currentHorizon ?? null,
            lastEventIdByJob,
            jobStatus: null,
            milestones: [],
            logs: [],
            // 刷新/重开页后立刻显示「执行中」工作流动画，SSE 续订由 ChatCopilot 负责
            isAnalyzing: persisted.analysisRunState === 'running',
            isConnected: false,
            analysisRunState:
                persisted.analysisRunState === 'running' ? 'running' : (persisted.analysisRunState ?? 'idle'),
            analysisRunError: null,
            chatMessages,
        }
    },
}
))
