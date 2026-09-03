import { useEffect, useMemo, useState } from 'react'
import { AlertCircle, CheckCircle2, Clock3, Database, Loader2, MinusCircle, Sparkles, TimerReset, XCircle } from 'lucide-react'

import DataSourceDialog from '@/components/DataSourceDialog'
import type { FastAnalysisDetail } from '@/types'
import { buildFastAnalysisDataSourceBundle, buildFastAnalysisDataSourceBundleFromProgress, FAST_FEATURE_SLOT_COUNT, sortFastSnapshotSources } from '@/utils/fastAnalysisDataSources'

const STAGE_ORDER: Array<{ key: string; label: string; iconColor: string }> = [
    { key: 'queued', label: '排队等待', iconColor: 'text-slate-400' },
    { key: 'collecting_data', label: '数据快照', iconColor: 'text-blue-500' },
    { key: 'extracting_features', label: '特征抽取', iconColor: 'text-purple-500' },
    { key: 'llm_reasoning', label: 'AI 推断', iconColor: 'text-pink-500' },
    { key: 'finalizing', label: '结果落库', iconColor: 'text-emerald-500' },
]

const STATUS_ICON: Record<string, { icon: typeof CheckCircle2; cls: string }> = {
    ok: { icon: CheckCircle2, cls: 'text-emerald-500' },
    timeout: { icon: TimerReset, cls: 'text-amber-500' },
    unavailable: { icon: XCircle, cls: 'text-rose-500' },
    skipped: { icon: MinusCircle, cls: 'text-slate-400' },
    pending: { icon: Loader2, cls: 'text-blue-500 animate-spin' },
}

type ProgressShape = {
    stage?: string
    stage_label?: string
    percent?: number
    started_at?: string
    sources_total?: number
    sources_done?: number
    sources?: Array<{ key: string; label: string; status: string; latency_ms?: number; rows?: number }>
    logs?: Array<{ ts: string; level: string; msg: string }>
    feature_count?: number
    feature_populated_count?: number
    expected_features?: number
    llm_model?: string
    llm_provider?: string
    llm_elapsed_sec?: number
    llm_error?: string | null
    elapsed_ms?: number
    waiting_ahead_count?: number
    final_status?: string
    error?: string
}

function formatSec(ms?: number): string {
    if (!ms || ms < 0) return '0.0s'
    return `${(ms / 1000).toFixed(1)}s`
}

interface Props {
    detail: FastAnalysisDetail | null
    budgetSec?: number
}

export default function FastAnalysisProgress({ detail, budgetSec = 120 }: Props) {
    const [dataDialogOpen, setDataDialogOpen] = useState(false)
    const progress = ((detail?.snapshot_json as Record<string, unknown>)?.progress || {}) as ProgressShape
    const status = detail?.status || 'pending'
    const isTerminal = ['succeeded', 'degraded', 'failed'].includes(status)
    const isRunning = !isTerminal && !!detail
    const startedAt = progress.started_at ? new Date(progress.started_at).getTime() : null

    const [tickMs, setTickMs] = useState<number>(progress.elapsed_ms || 0)
    useEffect(() => {
        if (!isRunning || !startedAt) return
        let raf = 0
        const loop = () => {
            setTickMs(Date.now() - startedAt)
            raf = window.requestAnimationFrame(loop)
        }
        raf = window.requestAnimationFrame(loop)
        return () => window.cancelAnimationFrame(raf)
    }, [isRunning, startedAt])

    useEffect(() => {
        if (isTerminal) setTickMs(progress.elapsed_ms || tickMs)
    }, [isTerminal, progress.elapsed_ms, tickMs])

    const percent = Math.max(0, Math.min(100, Math.round(progress.percent || 0)))
    const stageKey = String(progress.stage || (isTerminal ? (status === 'failed' ? 'failed' : 'finalizing') : 'queued'))
    const stageLabel = progress.stage_label || (
        status === 'failed' ? '已失败' : status === 'succeeded' ? '已完成' : status === 'degraded' ? '降级完成' : '进行中'
    )

    const sourcesByKey = new Map<string, { label: string; status: string; latency_ms?: number; rows?: number }>()
    for (const s of progress.sources || []) sourcesByKey.set(s.key, s)

    const sourcesTotal = progress.sources_total || 0
    const sourcesDone = progress.sources_done || 0
    const featureCount = progress.feature_count || 0
    const featurePopulated =
        typeof progress.feature_populated_count === 'number' ? progress.feature_populated_count : null
    const featureTotal = progress.expected_features || FAST_FEATURE_SLOT_COUNT

    const dsBundle = useMemo(() => {
        if (!detail) return null
        const s = detail.snapshot_json as Record<string, unknown> | undefined
        if (s && typeof s === 'object') {
            const fromSnap = buildFastAnalysisDataSourceBundle(s, {
                symbol: detail.symbol,
                trade_date: detail.trade_date,
                created_at: detail.created_at,
                finished_at: detail.finished_at,
            })
            if (fromSnap?.items.length) return fromSnap
        }
        return buildFastAnalysisDataSourceBundleFromProgress(progress, {
            symbol: detail.symbol,
            trade_date: detail.trade_date,
            created_at: detail.created_at,
            finished_at: detail.finished_at,
        })
    }, [detail, progress.sources])

    const sortedSources = useMemo(() => sortFastSnapshotSources(progress.sources || []), [progress.sources])
    const elapsedSec = Math.max(0, Math.floor(tickMs / 1000))
    const remainingSec = Math.max(0, budgetSec - elapsedSec)

    const barColor =
        status === 'failed'
            ? 'from-rose-500 to-rose-600'
            : status === 'succeeded'
            ? 'from-emerald-500 to-teal-500'
            : status === 'degraded'
            ? 'from-amber-400 to-amber-500'
            : 'from-blue-500 via-purple-500 to-pink-500'

    const headerIcon =
        status === 'failed' ? (
            <XCircle className="h-5 w-5 text-rose-500" />
        ) : status === 'succeeded' ? (
            <CheckCircle2 className="h-5 w-5 text-emerald-500" />
        ) : status === 'degraded' ? (
            <AlertCircle className="h-5 w-5 text-amber-500" />
        ) : (
            <Loader2 className="h-5 w-5 text-blue-500 animate-spin" />
        )

    const featureBarPct = isTerminal && featurePopulated !== null
        ? Math.min(100, Math.round((featurePopulated / Math.max(1, featureTotal)) * 100))
        : Math.min(100, Math.round((featureCount / Math.max(1, featureTotal)) * 100))

    return (
        <section className="card space-y-4">
            <p className="rounded-lg border border-slate-200 bg-slate-50/80 px-3 py-2 text-[11px] leading-relaxed text-slate-600 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-400">
                快速分析使用 <strong className="text-slate-800 dark:text-slate-200">Tushare Pro 直连</strong>
                快照（不走智能分析的多源 <code className="rounded bg-slate-200/80 px-0.5 dark:bg-slate-800">route_to_vendor</code>
                降级链）。并行拉取含 <strong>60 日日 K</strong>、<strong>日线 RT（rt_k）</strong>、
                <strong>集合竞价 stk_auction</strong>（仅交易日 9:25 后有数据）等。
                完成后可点「数据源明细」查看折叠样例与命中状态。
            </p>

            <header className="flex flex-wrap items-center justify-between gap-3">
                <div className="flex items-center gap-2">
                    {headerIcon}
                    <h2 className="text-base font-semibold text-slate-900 dark:text-slate-100">
                        实时进度 · {stageLabel}
                    </h2>
                    {progress.llm_model ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 text-xs text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                            <Sparkles className="h-3 w-3" /> {progress.llm_model}
                        </span>
                    ) : null}
                </div>
                <div className="flex items-center gap-3 text-xs text-slate-500">
                    <span className="inline-flex items-center gap-1">
                        <Clock3 className="h-3.5 w-3.5" /> 已耗时 {formatSec(tickMs)}
                    </span>
                    {!isTerminal ? (
                        <span className="inline-flex items-center gap-1 rounded-full bg-amber-50 px-2 py-0.5 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                            <TimerReset className="h-3.5 w-3.5" /> 剩余 {remainingSec}s
                        </span>
                    ) : null}
                    <span className="font-mono text-sm font-semibold text-slate-700 dark:text-slate-200">{percent}%</span>
                </div>
            </header>

            {/* Global progress bar */}
            <div className="space-y-1">
                <div className="relative h-3 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                    <div
                        className={`relative h-full bg-gradient-to-r ${barColor} transition-all duration-500 ease-out`}
                        style={{ width: `${percent}%` }}
                    >
                        {isRunning ? (
                            <span className="absolute inset-0 animate-pulse bg-white/10" />
                        ) : null}
                    </div>
                </div>
                <div className="flex justify-between text-[11px] text-slate-400">
                    <span>开始</span>
                    <span>数据快照</span>
                    <span>特征抽取</span>
                    <span>AI 推断</span>
                    <span>完成</span>
                </div>
            </div>

            {/* Stage steps */}
            <ol className="grid grid-cols-2 gap-3 md:grid-cols-5">
                {STAGE_ORDER.map((s) => {
                    const reached = stageOrderIndex(stageKey) >= stageOrderIndex(s.key)
                    const isCurrent = s.key === stageKey && isRunning
                    return (
                        <li
                            key={s.key}
                            className={`flex items-center gap-2 rounded-lg border px-3 py-2 text-sm transition ${
                                isCurrent
                                    ? 'border-blue-500/60 bg-blue-50/60 shadow-sm dark:bg-blue-900/20'
                                    : reached
                                    ? 'border-emerald-300/60 bg-emerald-50/60 dark:border-emerald-700/40 dark:bg-emerald-900/10'
                                    : 'border-slate-200 bg-slate-50/40 dark:border-slate-700 dark:bg-slate-900/30'
                            }`}
                        >
                            {isCurrent ? (
                                <Loader2 className={`h-4 w-4 animate-spin ${s.iconColor}`} />
                            ) : reached ? (
                                <CheckCircle2 className="h-4 w-4 text-emerald-500" />
                            ) : (
                                <Clock3 className="h-4 w-4 text-slate-400" />
                            )}
                            <span className={`${reached ? 'text-slate-700 dark:text-slate-100' : 'text-slate-400'}`}>{s.label}</span>
                        </li>
                    )
                })}
            </ol>

            {/* Source grid + Feature counters */}
            <div className="grid gap-3 md:grid-cols-2">
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                        <h3 className="text-sm font-semibold">📡 数据源（{sourcesDone}/{sourcesTotal || '?'}）</h3>
                        <div className="flex items-center gap-2">
                            {sourcesTotal ? (
                                <span className="text-xs text-slate-500">
                                    ok {countByStatus(progress.sources, 'ok')} · timeout {countByStatus(progress.sources, 'timeout')} ·
                                    unavailable {countByStatus(progress.sources, 'unavailable')} · skipped {countByStatus(progress.sources, 'skipped')}
                                </span>
                            ) : null}
                            {dsBundle?.items.length ? (
                                <button
                                    type="button"
                                    className="inline-flex items-center gap-1 rounded-md border border-slate-300 bg-white px-2 py-1 text-xs font-medium text-slate-700 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-900 dark:text-slate-200 dark:hover:bg-slate-800"
                                    onClick={() => setDataDialogOpen(true)}
                                >
                                    <Database className="h-3.5 w-3.5" />
                                    数据源明细
                                </button>
                            ) : null}
                        </div>
                    </div>
                    <ul className="grid grid-cols-1 gap-1.5">
                        {sortedSources.map((s) => {
                            const entry = STATUS_ICON[s.status] || STATUS_ICON.pending
                            const Icon = entry.icon
                            return (
                                <li
                                    key={s.key}
                                    className="flex items-center justify-between rounded border border-slate-200/70 px-2 py-1 text-xs dark:border-slate-700/70"
                                >
                                    <span className="flex items-center gap-2 truncate">
                                        <Icon className={`h-3.5 w-3.5 flex-shrink-0 ${entry.cls}`} />
                                        <span className="truncate">{s.label}</span>
                                    </span>
                                    <span className="ml-2 flex shrink-0 items-center gap-2 text-slate-500">
                                        <span>{s.rows ?? 0} 行</span>
                                        <span>· {s.latency_ms ?? 0}ms</span>
                                    </span>
                                </li>
                            )
                        })}
                        {sourcesByKey.size === 0 && sourcesTotal === 0 ? (
                            <li className="text-xs text-slate-400">等待开始采集…</li>
                        ) : null}
                    </ul>
                </div>

                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <h3 className="mb-2 text-sm font-semibold">🧮 特征 / 模型</h3>
                    <div className="space-y-2 text-sm">
                        <div className="flex flex-col gap-0.5">
                            <div className="flex items-center justify-between">
                                <span className="text-slate-500">特征槽位</span>
                                <span className="font-mono text-slate-700 dark:text-slate-200">
                                    {featureCount}/{featureTotal}
                                    {isTerminal && featurePopulated !== null ? (
                                        <span className="ml-1 text-xs font-sans text-slate-500">
                                            （有效数值 {featurePopulated}）
                                        </span>
                                    ) : null}
                                </span>
                            </div>
                            {isTerminal && featurePopulated !== null ? (
                                <p className="text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                                    「槽位」= 已计算的特征字段数；部分字段因接口返回空行保持为空，不代表抽取未完成。
                                </p>
                            ) : null}
                        </div>
                        <div className="h-1.5 w-full overflow-hidden rounded-full bg-slate-200 dark:bg-slate-800">
                            <div
                                className="h-full rounded-full bg-purple-500 transition-all duration-500"
                                style={{ width: `${featureBarPct}%` }}
                            />
                        </div>
                        <div className="flex items-center justify-between pt-2">
                            <span className="text-slate-500">LLM</span>
                            <span className="font-mono text-slate-700 dark:text-slate-200">
                                {progress.llm_provider || '-'} · {progress.llm_model || '-'}
                            </span>
                        </div>
                        {progress.llm_elapsed_sec ? (
                            <div className="flex items-center justify-between text-xs text-slate-500">
                                <span>推断耗时</span>
                                <span>{progress.llm_elapsed_sec}s</span>
                            </div>
                        ) : null}
                        {progress.llm_error ? (
                            <div className="rounded border border-rose-300 bg-rose-50 px-2 py-1 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300">
                                LLM 出错：{progress.llm_error}（已返回降级结论）
                            </div>
                        ) : null}
                        {progress.waiting_ahead_count ? (
                            <div className="text-xs text-amber-600 dark:text-amber-300">前方 {progress.waiting_ahead_count} 个任务等待</div>
                        ) : null}
                    </div>
                </div>
            </div>

            {/* Live log feed */}
            <div className="rounded-lg border border-slate-200 dark:border-slate-700">
                <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 text-xs text-slate-500 dark:border-slate-700">
                    <span>实时日志</span>
                    <span>{(progress.logs || []).length} 条</span>
                </div>
                <div className="max-h-48 overflow-y-auto px-3 py-2 font-mono text-xs leading-relaxed">
                    {(progress.logs || []).slice().reverse().map((l, i) => (
                        <div
                            key={`${l.ts}-${i}`}
                            className={
                                l.level === 'error'
                                    ? 'text-rose-500'
                                    : l.level === 'warn'
                                    ? 'text-amber-500'
                                    : 'text-slate-600 dark:text-slate-300'
                            }
                        >
                            <span className="text-slate-400">{l.ts.slice(11, 19)}</span>{' '}
                            <span>{l.msg}</span>
                        </div>
                    ))}
                    {(progress.logs || []).length === 0 ? (
                        <div className="text-slate-400">等待执行…</div>
                    ) : null}
                </div>
            </div>

            {/* Error banner */}
            {status === 'failed' && progress.error ? (
                <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-sm text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300">
                    <span className="font-medium">分析失败：</span>
                    <span className="break-all">{progress.error}</span>
                </div>
            ) : null}

            {dsBundle && detail ? (
                <DataSourceDialog
                    open={dataDialogOpen}
                    onClose={() => setDataDialogOpen(false)}
                    dataSources={dsBundle}
                    derivedSignals={undefined}
                    symbol={detail.symbol}
                    tradeDate={detail.trade_date}
                />
            ) : null}
        </section>
    )
}

function stageOrderIndex(key: string): number {
    const i = STAGE_ORDER.findIndex((s) => s.key === key)
    if (i >= 0) return i
    if (key === 'failed') return STAGE_ORDER.length
    return -1
}

function countByStatus(sources: ProgressShape['sources'], status: string): number {
    if (!sources) return 0
    return sources.filter((s) => s.status === status).length
}
