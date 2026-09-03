import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { FileText, ArrowRight, Brain, Zap, Sparkles, LineChart, Trash2 } from 'lucide-react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { api } from '@/services/api'
import type { Report } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'
import {
    CHART_INSIGHT_HISTORY_MAX,
    loadChartInsightHistory,
    removeChartInsightHistoryItem,
} from '@/lib/chartInsightHistory'
import { reportListKindFromSearchParams, type ReportListKind } from '@/utils/reportListUrlKind'
import { OUTCOME_STATUS_CLASS, OUTCOME_STATUS_LABEL, pickOutcomeStatus } from '@/utils/reportOutcome'

export default function MobileReports() {
    const navigate = useNavigate()
    const [searchParams, setSearchParams] = useSearchParams()
    const [reports, setReports] = useState<Report[]>([])
    const [loading, setLoading] = useState(true)
    const [klineVersion, setKlineVersion] = useState(0)
    const reportsFetchGenRef = useRef(0)

    const listKind: ReportListKind = useMemo(
        () => reportListKindFromSearchParams(searchParams),
        [searchParams],
    )

    const klineRows = useMemo(() => {
        if (listKind !== 'kline') return []
        return loadChartInsightHistory()
    }, [listKind, klineVersion])

    const setListKind = useCallback(
        (kind: ReportListKind) => {
            setSearchParams(
                (prev) => {
                    const next = new URLSearchParams(prev)
                    next.set('kind', kind)
                    next.delete('report')
                    return next
                },
                { replace: true },
            )
        },
        [setSearchParams],
    )

    const load = useCallback(async () => {
        const gen = ++reportsFetchGenRef.current
        setLoading(true)
        try {
            if (listKind === 'kline') {
                if (gen !== reportsFetchGenRef.current) return
                setReports([])
            } else {
                const taskKind = listKind === 'fast' ? 'fast_analysis' : 'full_analysis'
                const res = await api.getReports(undefined, 0, 30, taskKind)
                if (gen !== reportsFetchGenRef.current) return
                setReports(res.reports)
            }
        } catch {
            setReports([])
        } finally {
            setLoading(false)
        }
    }, [listKind])

    useEffect(() => {
        void load()
    }, [load])

    return (
        <div className="flex flex-col gap-4 p-4 min-h-[100dvh] bg-slate-50 dark:bg-slate-950">
            <div className="mb-2">
                <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">我的报告</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    {listKind === 'kline'
                        ? `本机 K 线解读 · 最多 ${CHART_INSIGHT_HISTORY_MAX} 条`
                        : '查看历史智能分析与快速分析'}
                </p>
            </div>

            <div className="flex flex-wrap gap-2">
                {(
                    [
                        { id: 'full' as const, label: '智能分析' },
                        { id: 'fast' as const, label: '快速分析' },
                        { id: 'kline' as const, label: 'K线解读' },
                    ] as const
                ).map((tab) => (
                    <button
                        key={tab.id}
                        type="button"
                        onClick={() => setListKind(tab.id)}
                        className={`rounded-full border px-3 py-1 text-xs font-medium ${
                            listKind === tab.id
                                ? 'border-cyan-500/60 bg-cyan-500/15 text-cyan-900 dark:border-cyan-400/50 dark:bg-cyan-500/10 dark:text-cyan-100'
                                : 'border-slate-200 bg-white text-slate-600 dark:border-slate-700 dark:bg-slate-900 dark:text-slate-300'
                        }`}
                    >
                        {tab.label}
                    </button>
                ))}
            </div>

            {loading ? (
                <div className="text-center text-slate-400 py-10">加载中...</div>
            ) : listKind === 'kline' ? (
                klineRows.length === 0 ? (
                    <div className="text-center text-slate-400 py-10 space-y-2">
                        <p>暂无 K 线解读</p>
                        <Link to="/m/chart" className="text-cyan-600 underline text-sm dark:text-cyan-400">
                            前往看盘（K 线）
                        </Link>
                    </div>
                ) : (
                    <div className="flex flex-col gap-3">
                        {klineRows.map((row) => {
                            const biasLabel =
                                row.insight.bias === 'bullish'
                                    ? '偏多'
                                    : row.insight.bias === 'bearish'
                                      ? '偏空'
                                      : '中性'
                            return (
                                <div
                                    key={row.id}
                                    className="bg-white dark:bg-slate-900 rounded-2xl p-4 shadow-sm border border-slate-100 dark:border-slate-800"
                                >
                                    <div className="flex justify-between items-start gap-2">
                                        <div className="flex items-center gap-2 min-w-0">
                                            <div className="w-8 h-8 rounded-full bg-violet-50 dark:bg-violet-500/20 flex items-center justify-center shrink-0">
                                                <Sparkles className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                                            </div>
                                            <div className="min-w-0">
                                                <div className="font-semibold text-slate-900 dark:text-slate-100 truncate">
                                                    {stockDisplayLabel({
                                                        symbol: row.symbol,
                                                        name: row.symbolName,
                                                        display_label: row.display_label,
                                                    })}
                                                </div>
                                                <div className="text-xs text-slate-500 mt-0.5">
                                                    {row.rangePreset} · {row.period} · {row.adjust}
                                                </div>
                                            </div>
                                        </div>
                                        <span className="text-xs font-medium text-slate-600 dark:text-slate-300 shrink-0">
                                            {biasLabel}
                                        </span>
                                    </div>
                                    <div className="mt-3 flex justify-between items-center text-xs text-slate-500 border-t border-slate-100 dark:border-slate-800 pt-3">
                                        <span>
                                            {new Date(row.at).toLocaleString('zh-CN', {
                                                month: '2-digit',
                                                day: '2-digit',
                                                hour: '2-digit',
                                                minute: '2-digit',
                                                hour12: false,
                                            })}
                                        </span>
                                        <div className="flex items-center gap-2">
                                            <Link
                                                to={`/m/chart?insight=${encodeURIComponent(row.id)}`}
                                                className="p-1.5 rounded-lg text-slate-400 hover:text-cyan-600"
                                                title="打开 K 线"
                                            >
                                                <LineChart className="w-4 h-4" />
                                            </Link>
                                            <button
                                                type="button"
                                                className="p-1.5 rounded-lg text-slate-400 hover:text-red-600"
                                                title="移除"
                                                onClick={() => {
                                                    if (!confirm('从本机移除该条解读？')) return
                                                    removeChartInsightHistoryItem(row.id)
                                                    setKlineVersion((v) => v + 1)
                                                }}
                                            >
                                                <Trash2 className="w-4 h-4" />
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            )
                        })}
                    </div>
                )
            ) : reports.length === 0 ? (
                <div className="text-center text-slate-400 py-10">暂无报告</div>
            ) : (
                <div className="flex flex-col gap-3">
                    {reports.map((report) => {
                        const isFast = String(report.task_kind || '').trim() === 'fast_analysis'
                        const outcome = report.outcome_summary
                        const outcomeStatus = pickOutcomeStatus(String(outcome?.primary_status || 'pending'))
                        const decisionColor =
                            report.decision?.toUpperCase().includes('BUY') || report.decision?.includes('增持')
                                ? 'text-red-600 dark:text-red-400 bg-red-50 dark:bg-red-500/10'
                                : report.decision?.toUpperCase().includes('SELL') || report.decision?.includes('减持')
                                  ? 'text-green-600 dark:text-green-400 bg-green-50 dark:bg-green-500/10'
                                  : 'text-slate-600 dark:text-slate-400 bg-slate-100 dark:bg-slate-800'

                        return (
                            <div
                                key={report.id}
                                onClick={() => navigate(`/m/reports?report=${report.id}&kind=${listKind}`)}
                                className="bg-white dark:bg-slate-900 rounded-2xl p-4 shadow-sm border border-slate-100 dark:border-slate-800 active:scale-[0.98] transition-transform"
                            >
                                <div className="flex justify-between items-start mb-3">
                                    <div className="flex items-center gap-2">
                                        <div className="w-8 h-8 rounded-full bg-blue-50 dark:bg-blue-900/30 flex items-center justify-center">
                                            <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                        </div>
                                        <div>
                                            <div className="font-semibold text-slate-900 dark:text-slate-100 text-base">
                                                {stockDisplayLabel({
                                                    symbol: report.symbol,
                                                    name: report.name,
                                                    display_label: report.display_label,
                                                })}
                                            </div>
                                            <div className="mt-0.5 flex items-center gap-1.5">
                                                <span className="text-xs text-slate-500">{report.trade_date}</span>
                                                <span
                                                    className={`inline-flex items-center gap-1 rounded-full px-1.5 py-0.5 text-[10px] ${
                                                        isFast
                                                            ? 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300'
                                                            : 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300'
                                                    }`}
                                                >
                                                    {isFast ? <Zap className="h-3 w-3" /> : <Brain className="h-3 w-3" />}
                                                    {isFast ? '快速分析' : '智能分析'}
                                                </span>
                                            </div>
                                        </div>
                                    </div>
                                    <div className={`px-2.5 py-1 rounded-lg text-xs font-bold ${decisionColor}`}>
                                        {report.decision || '-'}
                                    </div>
                                </div>
                                <div className="mb-3 flex items-center gap-2">
                                    <span className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] ${OUTCOME_STATUS_CLASS[outcomeStatus]}`}>
                                        {OUTCOME_STATUS_LABEL[outcomeStatus]}
                                    </span>
                                    <span className="text-xs text-slate-500 dark:text-slate-400">
                                        兑现分：{typeof outcome?.weighted_score === 'number' ? `${Math.round(outcome.weighted_score)}` : '--'}
                                        {outcome?.primary_horizon ? ` · ${outcome.primary_horizon.toUpperCase()}` : ''}
                                    </span>
                                </div>
                                <div className="flex justify-between items-center text-xs text-slate-500 border-t border-slate-100 dark:border-slate-800 pt-3 mt-1">
                                    <div>
                                        <span className="mr-3">
                                            置信度:{' '}
                                            <span className="font-semibold text-slate-700 dark:text-slate-300">
                                                {report.confidence ?? '--'}%
                                            </span>
                                        </span>
                                        <span>
                                            方向:{' '}
                                            {report.direction === 'long' ? '做多' : report.direction === 'short' ? '做空' : '无'}
                                        </span>
                                    </div>
                                    <ArrowRight className="w-4 h-4 text-slate-300 dark:text-slate-600" />
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
