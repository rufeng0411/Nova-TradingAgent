import { useCallback, useEffect, useRef, useState } from 'react'
import { BarChart3, CalendarClock, GripVertical, Maximize2, Minimize2, X } from 'lucide-react'

import { api } from '@/services/api'
import type { OutcomeGroupBy, QlibEvalGateSummaryResponse, ReportOutcomeSummaryResponse } from '@/types'
import { CHART_INSIGHT_HISTORY_MAX, type ChartInsightHistoryItem } from '@/lib/chartInsightHistory'
import { computeKlineOutcomeLocal } from '@/utils/reportOutcome'

type Kind = 'full' | 'fast' | 'kline'

type Props = {
    open: boolean
    onClose: () => void
    kind: Kind
    onKindChange: (k: Kind) => void
    klineRows: ChartInsightHistoryItem[]
}

const MIN_W = 760
const MIN_H = 460
const LS_KEY = 'ta-outcome-dashboard-bounds'

function clamp(x: number, y: number, w: number, h: number) {
    const margin = 8
    const vw = window.innerWidth
    const vh = window.innerHeight
    const cw = Math.min(Math.max(w, MIN_W), vw - margin * 2)
    const ch = Math.min(Math.max(h, MIN_H), vh - margin * 2)
    const cx = Math.min(Math.max(x, margin), vw - cw - margin)
    const cy = Math.min(Math.max(y, margin), vh - ch - margin)
    return { x: cx, y: cy, w: cw, h: ch }
}

function percent(v?: number | null): string {
    if (typeof v !== 'number' || Number.isNaN(v)) return '--'
    return `${v.toFixed(1)}%`
}

export default function OutcomeDashboardDialog({ open, onClose, kind, onKindChange, klineRows }: Props) {
    const [tab, setTab] = useState<OutcomeGroupBy>('overall')
    const [days, setDays] = useState(30)
    const [fullscreen, setFullscreen] = useState(false)
    const [loading, setLoading] = useState(false)
    const [payload, setPayload] = useState<ReportOutcomeSummaryResponse | null>(null)
    const [klinePayload, setKlinePayload] = useState<ReportOutcomeSummaryResponse | null>(null)
    const [quantGates, setQuantGates] = useState<QlibEvalGateSummaryResponse | null>(null)
    const [bounds, setBounds] = useState({ x: 80, y: 64, w: 980, h: 680 })
    const dragRef = useRef<{ active: boolean; kind: 'move' | 'resize'; sx: number; sy: number; ox: number; oy: number; ow: number; oh: number } | null>(null)

    const loadKlineSummary = useCallback(async (groupBy: OutcomeGroupBy, sinceDays: number) => {
        const rows = klineRows.slice(0, CHART_INSIGHT_HISTORY_MAX)
        const details = await Promise.all(
            rows.map((x) =>
                computeKlineOutcomeLocal(
                    x,
                    async (symbol, startDate, endDate) => api.getKline(symbol, startDate, endDate, { period: '1d', adjust: 'none' }),
                ),
            ),
        )
        const items = details.filter((x): x is NonNullable<typeof x> => !!x)
        const cutoff = sinceDays > 0 ? Date.now() - sinceDays * 86400000 : 0
        const filtered = items.filter((x) => {
            const t = Date.parse(String(x.atr_window_end || ''))
            return !sinceDays || (!Number.isNaN(t) && t >= cutoff)
        })
        const base = filtered.map((x) => ({
            key: x.release_version || 'local',
            score: Number(x.weighted_score || 0),
            status: String(x.primary_status || 'pending'),
            trade_date: String(x.atr_window_end || ''),
        }))
        const aggregate = (arr: typeof base) => {
            const sample = arr.length
            const pending = arr.filter((x) => x.status === 'pending').length
            const miss = arr.filter((x) => x.status === 'miss').length
            const hitLike = arr.reduce((acc, x) => acc + (x.status === 'hit' ? 1 : x.status === 'neutral' ? 0.5 : 0), 0)
            const den = Math.max(1, sample - pending)
            return {
                sample_count: sample,
                settled_count: sample - pending,
                pending_count: pending,
                hit_rate: sample ? (hitLike / den) * 100 : null,
                avg_weighted_score: sample ? arr.reduce((a, b) => a + b.score, 0) / sample : null,
                miss_count: miss,
            }
        }
        if (groupBy === 'overall') return { group_by: 'overall' as const, summary: aggregate(base), items: [] }
        if (groupBy === 'version') return { group_by: 'version' as const, summary: aggregate(base), items: [{ key: 'local', ...aggregate(base) }] }
        const byWeek = new Map<string, typeof base>()
        for (const b of base) {
            const dt = new Date(`${b.trade_date}T00:00:00`)
            const year = dt.getFullYear()
            const week = Math.ceil((((dt.getTime() - new Date(year, 0, 1).getTime()) / 86400000) + new Date(year, 0, 1).getDay() + 1) / 7)
            const k = `${year}-W${String(week).padStart(2, '0')}`
            const list = byWeek.get(k) || []
            list.push(b)
            byWeek.set(k, list)
        }
        return { group_by: 'week' as const, summary: aggregate(base), items: Array.from(byWeek.entries()).sort((a, b) => a[0].localeCompare(b[0])).map(([k, v]) => ({ key: k, ...aggregate(v) })) }
    }, [klineRows])

    useEffect(() => {
        if (!open) return
        try {
            const raw = localStorage.getItem(LS_KEY)
            if (raw) {
                const b = JSON.parse(raw)
                setBounds(clamp(b.x, b.y, b.w, b.h))
            }
        } catch {}
    }, [open])

    useEffect(() => {
        if (!open) return
        const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose()
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [open, onClose])

    useEffect(() => {
        const onMove = (e: MouseEvent) => {
            const d = dragRef.current
            if (!d?.active) return
            const dx = e.clientX - d.sx
            const dy = e.clientY - d.sy
            if (d.kind === 'move') setBounds((prev) => clamp(d.ox + dx, d.oy + dy, prev.w, prev.h))
            else setBounds((prev) => clamp(prev.x, prev.y, d.ow + dx, d.oh + dy))
        }
        const onUp = () => {
            if (dragRef.current) dragRef.current.active = false
            try { localStorage.setItem(LS_KEY, JSON.stringify(bounds)) } catch {}
        }
        window.addEventListener('mousemove', onMove)
        window.addEventListener('mouseup', onUp)
        return () => {
            window.removeEventListener('mousemove', onMove)
            window.removeEventListener('mouseup', onUp)
        }
    }, [bounds])

    useEffect(() => {
        if (!open) return
        let mounted = true
        setLoading(true)
        ;(async () => {
            try {
                if (kind === 'kline') {
                    const local = await loadKlineSummary(tab, days)
                    if (mounted) setKlinePayload(local)
                    return
                }
                const tk = kind === 'fast' ? 'fast_analysis' : 'full_analysis'
                const res = await api.getReportOutcomeSummary({ taskKind: tk, sinceDays: days, groupBy: tab })
                if (mounted) setPayload(res)
                if (tab === 'version') {
                    try {
                        const gates = await api.getQlibEvalGates({ sinceDays: days })
                        if (mounted) setQuantGates(gates.enabled ? gates : null)
                    } catch {
                        if (mounted) setQuantGates(null)
                    }
                } else if (mounted) {
                    setQuantGates(null)
                }
            } finally {
                if (mounted) setLoading(false)
            }
        })()
        return () => { mounted = false }
    }, [open, kind, tab, days, loadKlineSummary])

    const active = kind === 'kline' ? klinePayload : payload
    const startMove = (e: React.MouseEvent) => {
        if (fullscreen) return
        dragRef.current = { active: true, kind: 'move', sx: e.clientX, sy: e.clientY, ox: bounds.x, oy: bounds.y, ow: bounds.w, oh: bounds.h }
    }
    const startResize = (e: React.MouseEvent) => {
        if (fullscreen) return
        e.preventDefault()
        e.stopPropagation()
        dragRef.current = { active: true, kind: 'resize', sx: e.clientX, sy: e.clientY, ox: bounds.x, oy: bounds.y, ow: bounds.w, oh: bounds.h }
    }

    const panelStyle = fullscreen ? undefined : ({ left: bounds.x, top: bounds.y, width: bounds.w, height: bounds.h } as React.CSSProperties)
    const panelCls = fullscreen
        ? 'fixed inset-4 z-[141] flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900'
        : 'fixed z-[141] flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900'

    if (!open) return null

    return (
        <div className="fixed inset-0 z-[140] bg-slate-900/45" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
            <div className={panelCls} style={panelStyle} onMouseDown={(e) => e.stopPropagation()} role="dialog" aria-modal="true">
                <div className={`flex items-center justify-between gap-2 border-b border-slate-200 px-3 py-2 dark:border-slate-700 ${fullscreen ? '' : 'cursor-move'}`} onMouseDown={startMove}>
                    <div className="flex items-center gap-2 text-sm font-semibold text-slate-800 dark:text-slate-100">
                        <GripVertical className="h-4 w-4 text-slate-400" />
                        <BarChart3 className="h-4 w-4 text-cyan-500" />
                        兑现度看板
                        {kind === 'kline' ? <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] text-slate-500 dark:bg-slate-800 dark:text-slate-300">本地</span> : null}
                    </div>
                    <div className="flex items-center gap-1">
                        <button
                            type="button"
                            title={fullscreen ? '退出全屏' : '全屏'}
                            aria-label={fullscreen ? '退出全屏' : '全屏'}
                            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                            onClick={() => setFullscreen((v) => !v)}
                        >
                            {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                        </button>
                        <button
                            type="button"
                            title="关闭"
                            aria-label="关闭"
                            className="rounded p-1.5 text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800"
                            onClick={onClose}
                        >
                            <X className="h-4 w-4" />
                        </button>
                    </div>
                </div>
                <div className="flex flex-wrap items-center gap-2 border-b border-slate-200 px-3 py-2 text-sm dark:border-slate-700">
                    {([
                        ['full', '智能分析'],
                        ['fast', '快速分析'],
                        ['kline', 'K线解读'],
                    ] as const).map(([k, label]) => (
                        <button key={k} type="button" onClick={() => onKindChange(k)} className={`rounded px-2 py-1 ${kind === k ? 'bg-cyan-500/15 text-cyan-700 dark:text-cyan-300' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>{label}</button>
                    ))}
                    <div className="mx-2 h-4 w-px bg-slate-200 dark:bg-slate-700" />
                    {([
                        ['overall', '总体'],
                        ['week', '阶段性'],
                        ['version', '版本对比'],
                    ] as const).map(([k, label]) => (
                        <button key={k} type="button" onClick={() => setTab(k)} className={`rounded px-2 py-1 ${tab === k ? 'bg-indigo-500/15 text-indigo-700 dark:text-indigo-300' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>{label}</button>
                    ))}
                    <div className="ml-auto flex items-center gap-1">
                        <CalendarClock className="h-4 w-4 text-slate-400" />
                        {[7, 30, 90, 365, 0].map((d) => (
                            <button key={d} type="button" onClick={() => setDays(d)} className={`rounded px-2 py-1 text-xs ${days === d ? 'bg-blue-500/15 text-blue-700 dark:text-blue-300' : 'text-slate-500 hover:bg-slate-100 dark:hover:bg-slate-800'}`}>{d === 0 ? '全部' : d === 365 ? '今年' : `${d}天`}</button>
                        ))}
                    </div>
                </div>
                <div className="flex-1 overflow-auto p-3">
                    {loading ? (
                        <p className="text-sm text-slate-500">加载中...</p>
                    ) : !active ? (
                        <p className="text-sm text-slate-500">暂无数据</p>
                    ) : (
                        <div className="space-y-3">
                            <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
                                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-xs text-slate-500">命中率</p><p className="mt-1 text-lg font-semibold">{percent(active.summary.hit_rate)}</p></div>
                                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-xs text-slate-500">平均分</p><p className="mt-1 text-lg font-semibold">{active.summary.avg_weighted_score != null ? active.summary.avg_weighted_score.toFixed(1) : '--'}</p></div>
                                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-xs text-slate-500">已结算样本</p><p className="mt-1 text-lg font-semibold">{active.summary.settled_count}</p></div>
                                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700"><p className="text-xs text-slate-500">待观察</p><p className="mt-1 text-lg font-semibold">{active.summary.pending_count}</p></div>
                            </div>
                            <div className="rounded-lg border border-slate-200 dark:border-slate-700">
                                <table className="w-full text-sm">
                                    <thead>
                                        <tr className="border-b border-slate-200 text-left text-xs text-slate-500 dark:border-slate-700">
                                            <th className="px-3 py-2">分组</th>
                                            <th className="px-3 py-2">命中率</th>
                                            <th className="px-3 py-2">平均分</th>
                                            <th className="px-3 py-2">样本</th>
                                            <th className="px-3 py-2">待观察</th>
                                        </tr>
                                    </thead>
                                    <tbody>
                                        {(active.items.length ? active.items : [{ key: '当前筛选', ...active.summary }]).map((it) => (
                                            <tr key={it.key} className="border-b border-slate-100 last:border-b-0 dark:border-slate-800">
                                                <td className="px-3 py-2">{it.key}</td>
                                                <td className="px-3 py-2">{percent(it.hit_rate)}</td>
                                                <td className="px-3 py-2">{it.avg_weighted_score != null ? it.avg_weighted_score.toFixed(1) : '--'}</td>
                                                <td className="px-3 py-2">{it.sample_count}</td>
                                                <td className="px-3 py-2">{it.pending_count}</td>
                                            </tr>
                                        ))}
                                    </tbody>
                                </table>
                            </div>
                            {tab === 'version' && quantGates?.version_gates?.items?.length ? (
                                <div className="rounded-lg border border-emerald-200 bg-emerald-50/60 p-3 dark:border-emerald-900/50 dark:bg-emerald-950/20">
                                    <p className="mb-2 text-xs font-medium text-emerald-800 dark:text-emerald-300">量化评估门禁（IC / 命中率 / 覆盖率）</p>
                                    <table className="w-full text-sm">
                                        <thead>
                                            <tr className="border-b border-emerald-200 text-left text-xs text-emerald-700 dark:border-emerald-900/50 dark:text-emerald-400">
                                                <th className="px-2 py-1">版本</th>
                                                <th className="px-2 py-1">门禁</th>
                                                <th className="px-2 py-1">未通过原因</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            {quantGates.version_gates.items.map((it) => (
                                                <tr key={it.release_version} className="border-b border-emerald-100 last:border-b-0 dark:border-emerald-900/30">
                                                    <td className="px-2 py-1.5">{it.release_version}</td>
                                                    <td className="px-2 py-1.5">
                                                        <span className={`rounded px-1.5 py-0.5 text-xs ${it.gate.passed ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-300' : 'bg-amber-500/15 text-amber-700 dark:text-amber-300'}`}>
                                                            {it.gate.passed ? '通过' : '未通过'}
                                                        </span>
                                                    </td>
                                                    <td className="px-2 py-1.5 text-xs text-slate-600 dark:text-slate-300">{it.gate.reasons?.length ? it.gate.reasons.join(' · ') : '—'}</td>
                                                </tr>
                                            ))}
                                        </tbody>
                                    </table>
                                </div>
                            ) : null}
                        </div>
                    )}
                </div>
                {!fullscreen ? <button type="button" className="absolute bottom-0 right-0 h-4 w-4 cursor-se-resize text-slate-400" onMouseDown={startResize} aria-label="Resize" /> : null}
            </div>
        </div>
    )
}
