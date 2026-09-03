import { useMemo, useCallback, useState, useEffect, type MouseEvent } from 'react'
import type { Node } from '@xyflow/react'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useWorkflowViewStore } from '@/stores/workflowViewStore'
import { META, type AgentWorkflowCard } from '@/components/agentWorkflowModel'
import type { AgentStatus } from '@/types'
import { extractVerdict } from '@/utils/reportText'
import { pickExchangeListedSymbol, stockDisplayLabel } from '@/utils/stockDisplay'
import AgentWorkflowOriginal from '@/components/AgentWorkflowOriginal'
import AgentWorkflowN8n from '@/components/AgentWorkflowN8n'
import { api } from '@/services/api'

interface AgentCollaborationProps {
    onSelectSection: (section?: string) => void
    onOpenDebate: (debate: 'research' | 'risk') => void
    selectedSection?: string
}

export default function AgentCollaboration({ onSelectSection, onOpenDebate, selectedSection }: AgentCollaborationProps) {
    const {
        agents,
        isAnalyzing,
        streamingSections,
        report,
        currentHorizon,
        currentSymbol,
        currentSymbolDisplayName,
        currentJobId,
        setIsAnalyzing,
        setAnalysisRunState,
    } = useAnalysisStore()
    const [cancelBusy, setCancelBusy] = useState(false)
    const [checkpointStep, setCheckpointStep] = useState<number | null>(null)
    const [checkpointBusy, setCheckpointBusy] = useState(false)
    const style = useWorkflowViewStore((s) => s.style)
    const setWorkflowStyle = useWorkflowViewStore((s) => s.setStyle)

    const workflowTargetLabel = stockDisplayLabel({
        symbol: pickExchangeListedSymbol(currentSymbol, report?.symbol ?? null),
        name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
        display_label: report?.instrument_context?.display_label,
    })

    const cards: AgentWorkflowCard[] = useMemo(
        () =>
            META.map((meta) => {
                const agent = agents.find((a) => a.name === meta.name)
                const streamState = meta.section ? streamingSections[meta.section] : undefined
                const stored = meta.section ? (report?.[meta.section as keyof typeof report] as string | undefined) : undefined
                const src = streamState?.displayed || stored || ''
                const isParticipating = isAnalyzing ? (agent ? agent.status !== 'skipped' : false) : true

                return {
                    meta,
                    status: (agent?.status ?? 'pending') as AgentStatus,
                    isStreaming: !!streamState?.isTyping,
                    verdict: extractVerdict(src),
                    isParticipating,
                }
            }),
        [agents, report, streamingSections, isAnalyzing],
    )

    const cardMap = useMemo(() => new Map(cards.map((c) => [c.meta.name, c])), [cards])
    const doneN = cards.filter((c) => c.status === 'completed').length
    const participatingCount = cards.filter((c) => c.status !== 'skipped').length

    useEffect(() => {
        if (!isAnalyzing || !currentJobId) {
            setCheckpointStep(null)
            return
        }
        let cancelled = false
        void api.getJobCheckpoint(currentJobId).then((cp) => {
            if (!cancelled && cp.resumable && cp.step != null) setCheckpointStep(cp.step)
        }).catch(() => {})
        return () => { cancelled = true }
    }, [isAnalyzing, currentJobId])

    const handleForceRerun = useCallback(async () => {
        const jid = useAnalysisStore.getState().currentJobId
        if (!jid || checkpointBusy) return
        if (!window.confirm('确定清 checkpoint 并强制重跑吗？')) return
        setCheckpointBusy(true)
        try {
            await api.deleteJobCheckpoint(jid)
            setCheckpointStep(null)
        } finally {
            setCheckpointBusy(false)
        }
    }, [checkpointBusy])

    const handleForceCancel = useCallback(async () => {
        const jid = useAnalysisStore.getState().currentJobId
        if (!jid || cancelBusy) return
        if (
            !window.confirm(
                '确定要强制终止当前分析任务吗？终止后将无法继续本次进度，未完成的报告不会生成。',
            )
        ) {
            return
        }
        setCancelBusy(true)
        try {
            await api.cancelAnalysisJob(jid)
            setIsAnalyzing(false)
            setAnalysisRunState('failed', '用户已终止分析')
        } catch (e) {
            const msg = e instanceof Error ? e.message : String(e)
            window.alert(`终止失败：${msg}`)
        } finally {
            setCancelBusy(false)
        }
    }, [cancelBusy, setAnalysisRunState, setIsAnalyzing])

    const handleNodeClick = useCallback(
        (_: MouseEvent, node: Node) => {
            const card = cardMap.get(node.id)
            if (!card) return
            if (card.status !== 'completed' && card.status !== 'in_progress') return

            if (card.meta.debate) {
                onOpenDebate(card.meta.debate)
                if (card.meta.section) onSelectSection(card.meta.section)
            } else if (card.meta.section) {
                onSelectSection(card.meta.section === selectedSection ? undefined : card.meta.section)
            }
        },
        [cardMap, selectedSection, onSelectSection, onOpenDebate],
    )

    const sharedProps = {
        cards,
        cardMap,
        doneN,
        participatingCount,
        workflowTargetLabel,
        selectedSection,
        handleNodeClick,
        isAnalyzing,
        currentHorizon,
    }

    const btnBase =
        'rounded-md px-2.5 py-1 text-[11px] font-black transition-colors border focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500/40'
    const btnInactive =
        'border-transparent text-slate-500 hover:text-slate-800 dark:text-slate-400 dark:hover:text-slate-100'
    const btnActive = 'border-blue-400/40 bg-blue-600/10 text-blue-700 dark:text-blue-300'

    return (
        <section className="card relative overflow-hidden bg-white dark:bg-slate-900 border-slate-200 dark:border-slate-800">
            <div className="relative z-10 mb-2 flex flex-wrap items-start justify-between gap-3 border-b border-slate-100 pb-4 dark:border-slate-800">
                <div className="flex min-w-0 flex-1 flex-col gap-1 pr-2">
                    <div className="flex min-w-0 flex-wrap items-center gap-2 sm:gap-3">
                        <div
                            className={`h-3 w-3 shrink-0 rounded-full ${isAnalyzing ? 'animate-pulse bg-blue-500 shadow-[0_0_12px_#3b82f6]' : 'bg-slate-300'}`}
                        />
                        <h3 className="min-w-0 text-lg font-black uppercase tracking-tighter text-slate-900 dark:text-white">
                            多Agents量化研究分析
                        </h3>
                        <div className="ml-auto flex shrink-0 flex-wrap items-center gap-2 sm:ml-0">
                            {isAnalyzing && currentJobId ? (
                                <>
                                    {checkpointStep != null ? (
                                        <span className="rounded-md border border-emerald-400/35 bg-emerald-600/10 px-2.5 py-1 text-[11px] font-black text-emerald-700 dark:text-emerald-300">
                                            已从第 {checkpointStep} 步恢复
                                        </span>
                                    ) : null}
                                    <button
                                        type="button"
                                        disabled={checkpointBusy}
                                        className="rounded-md border border-amber-400/35 bg-amber-600/10 px-2.5 py-1 text-[11px] font-black text-amber-800 dark:text-amber-300"
                                        onClick={() => void handleForceRerun()}
                                    >
                                        强制重跑
                                    </button>
                                    <button
                                    type="button"
                                    disabled={cancelBusy}
                                    className="rounded-md border border-red-400/35 bg-red-600/10 px-2.5 py-1 text-[11px] font-black text-red-700 transition-colors hover:bg-red-600/15 disabled:opacity-50 dark:border-red-500/30 dark:bg-red-500/10 dark:text-red-300 dark:hover:bg-red-500/15"
                                    onClick={() => void handleForceCancel()}
                                >
                                    {cancelBusy ? '终止中…' : '强制终止'}
                                </button>
                                </>
                            ) : null}
                            <div
                                className="flex shrink-0 rounded-lg border border-slate-200/80 bg-slate-50/80 p-0.5 dark:border-slate-700 dark:bg-slate-800/60"
                                role="group"
                                aria-label="工作流风格"
                            >
                            <button
                                type="button"
                                className={`${btnBase} ${style === 'original' ? btnActive : btnInactive}`}
                                onClick={() => setWorkflowStyle('original')}
                            >
                                原风格
                            </button>
                            <button
                                type="button"
                                className={`${btnBase} ${style === 'n8n' ? btnActive : btnInactive}`}
                                onClick={() => setWorkflowStyle('n8n')}
                            >
                                n8n风格
                            </button>
                            </div>
                        </div>
                    </div>
                    <p className="pl-[22px] text-[13px] font-medium tracking-normal text-slate-600 normal-case dark:text-slate-400">
                        <span className="text-slate-400 dark:text-slate-500">{isAnalyzing ? '当前分析' : '当前标的'}</span>
                        <span className="mx-1.5 text-slate-300 dark:text-slate-600">·</span>
                        <span className="tabular-nums text-slate-800 dark:text-slate-100">{workflowTargetLabel}</span>
                    </p>
                </div>
                {isAnalyzing && (
                    <div className="flex shrink-0 flex-wrap items-center gap-4">
                        {currentHorizon && (
                            <span
                                className={`animate-in fade-in rounded-full border px-3 py-1 text-[11px] font-black tracking-widest duration-300 ${
                                    currentHorizon === 'short'
                                        ? 'border-blue-400/30 bg-blue-600/10 text-blue-600 dark:text-blue-400'
                                        : 'border-purple-400/30 bg-purple-600/10 text-purple-600 dark:text-purple-400'
                                }`}
                            >
                                {currentHorizon === 'short' ? '⚡ 短线视角' : '🔭 中线视角'}
                            </span>
                        )}
                        <div className="text-right">
                            <div className="text-2xl font-black tabular-nums text-blue-600 dark:text-blue-400">
                                {participatingCount > 0 ? Math.round((doneN / participatingCount) * 100) : 0}%
                            </div>
                            <p className="text-[10px] font-black uppercase tracking-tighter text-slate-400">分析总进度</p>
                        </div>
                    </div>
                )}
            </div>

            {style === 'n8n' ? <AgentWorkflowN8n {...sharedProps} /> : <AgentWorkflowOriginal {...sharedProps} />}
        </section>
    )
}
