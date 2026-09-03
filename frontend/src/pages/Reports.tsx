import { FileText, Download, Trash2, Search, ChevronLeft, ChevronRight, Loader2, History, Clock3, Brain, Zap, Sparkles, LineChart, BarChart3 } from 'lucide-react'
import { useState, useEffect, useCallback, useRef, useMemo } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import TaskProgressBanner from '@/components/TaskProgressBanner'
import { CHART_INSIGHT_HISTORY_MAX, loadChartInsightHistory, removeChartInsightHistoryItem } from '@/lib/chartInsightHistory'
import { api } from '@/services/api'
import type { Report, ReportDetail, ReportOutcomeDetail, ReportOutcomeSummaryResponse } from '@/types'
import DecisionCard from '@/components/DecisionCard'
import DecisionArchivePanel from '@/components/DecisionArchivePanel'
import ReportViewer from '@/components/ReportViewer'
import RiskRadar from '@/components/RiskRadar'
import KeyMetrics from '@/components/KeyMetrics'
import OutcomeDashboardDialog from '@/components/OutcomeDashboardDialog'
import { useAuthStore } from '@/stores/authStore'
import { advanceProgress, getReportRunProgress } from '@/utils/progressFeedback'
import { stockDisplayLabel, stockSafeFilename } from '@/utils/stockDisplay'
import { excerptForDecisionCard } from '@/utils/reportText'
import { reportListKindFromSearchParams, type ReportListKind } from '@/utils/reportListUrlKind'
import { OUTCOME_STATUS_CLASS, OUTCOME_STATUS_LABEL, pickOutcomeStatus } from '@/utils/reportOutcome'

type ProgressState = {
    status: 'idle' | 'loading' | 'success' | 'error'
    progress: number
    detail: string | null
}

const IDLE_PROGRESS: ProgressState = {
    status: 'idle',
    progress: 0,
    detail: null,
}

const parseDecision = (decisionText?: string): { action: 'add' | 'reduce' | 'hold'; label: string } => {
    if (!decisionText) return { action: 'hold', label: '中性' }
    const text = decisionText.toUpperCase()
    if (text.includes('BUY') || text.includes('增持') || text.includes('买入')) return { action: 'add', label: '偏多' }
    if (text.includes('SELL') || text.includes('减持') || text.includes('卖出')) return { action: 'reduce', label: '偏空' }
    return { action: 'hold', label: '中性' }
}

function getQueueHint(report: Pick<Report, 'status' | 'waiting_ahead_count' | 'scheduled_running_count' | 'scheduled_concurrency_limit'>): string | null {
    if (report.status !== 'pending') return null

    const waitingAhead = report.waiting_ahead_count ?? 0
    const runningCount = report.scheduled_running_count
    const limit = report.scheduled_concurrency_limit

    if (runningCount != null && limit != null) {
        return `前方还有 ${waitingAhead} 项等待，当前 ${runningCount}/${limit} 个任务执行中`
    }

    return `前方还有 ${waitingAhead} 项等待`
}

function reportTaskKindMeta(report: Report): { label: string; Icon: typeof Brain; cls: string } {
    if (String(report.task_kind || '').trim() === 'fast_analysis') {
        return {
            label: '快速分析',
            Icon: Zap,
            cls: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
        }
    }
    return {
        label: '智能分析',
        Icon: Brain,
        cls: 'bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-300',
    }
}

function tradeDateOnly(tradeDate: string): string {
    const s = (tradeDate || '').trim()
    if (!s) return '—'
    if (s.includes(' ')) return s.split(/\s+/)[0].slice(0, 10)
    if (s.includes('T')) return s.split('T')[0].slice(0, 10)
    return s.slice(0, 10)
}

type SandboxTri = '偏多' | '中性' | '偏空'

/** 列表「沙盘综合研判结论」列：仅三种文案，不展示摘要长文 */
function sandboxTriLabel(report: Report): SandboxTri {
    const dir = (report.direction || '').trim()
    if (dir) {
        const lower = dir.toLowerCase()
        if (lower === 'long' || lower === 'bull' || lower === 'bullish') return '偏多'
        if (lower === 'short' || lower === 'bear' || lower === 'bearish') return '偏空'
        const compact = dir.replace(/\s/g, '')
        const u = dir.toUpperCase()
        if (/多|涨|牛|BULL|LONG|买入|增持|看多/.test(compact) || u.includes('BULL')) return '偏多'
        if (/空|跌|熊|BEAR|SHORT|卖出|减持|看空/.test(compact) || u.includes('BEAR')) return '偏空'
        if (/中性|NEUTRAL|盘整|震荡/.test(compact) || u.includes('NEUTRAL')) return '中性'
    }
    const { action } = parseDecision(report.decision)
    if (action === 'add') return '偏多'
    if (action === 'reduce') return '偏空'
    return '中性'
}

const SANDBOX_TRI_CLASS: Record<SandboxTri, string> = {
    偏多: 'text-rose-600 dark:text-rose-400 font-medium',
    偏空: 'text-emerald-600 dark:text-emerald-400 font-medium',
    中性: 'text-slate-600 dark:text-slate-400 font-medium',
}

function renderSandboxConclusionCell(report: Report) {
    const label = sandboxTriLabel(report)
    return <span className={`text-sm whitespace-nowrap ${SANDBOX_TRI_CLASS[label]}`}>{label}</span>
}

type HorizonKey = 't0' | 't1' | 't2' | 't3' | 't5'

function pickHorizonField<T>(
    summary: Report['outcome_summary'],
    hk: HorizonKey,
    field: 'status' | 'close' | 'delta_pct' | 'atr_mult' | 'target_date',
): T | undefined {
    if (!summary) return undefined
    const key = `${hk}_${field}` as keyof typeof summary
    const v = summary[key] as unknown
    return v == null ? undefined : (v as T)
}

function renderHorizonOutcomeCell(summary: Report['outcome_summary'], hk: HorizonKey) {
    const status = pickHorizonField<string>(summary, hk, 'status')
    const close = pickHorizonField<number>(summary, hk, 'close')
    const deltaPct = pickHorizonField<number>(summary, hk, 'delta_pct')
    const atrMult = pickHorizonField<number>(summary, hk, 'atr_mult')
    const targetDate = pickHorizonField<string>(summary, hk, 'target_date')
    const baseline = summary?.baseline_price ?? undefined
    const atr20 = summary?.atr20 ?? undefined
    const st = pickOutcomeStatus(typeof status === 'string' ? status : null)

    if (st === 'pending') {
        const tip =
            targetDate
                ? `${hk.toUpperCase()} 窗口未结算（目标日：${targetDate}）`
                : `${hk.toUpperCase()} 窗口未结算`
        return (
            <span
                className="inline-block w-6 text-center text-slate-300 dark:text-slate-600 select-none"
                title={tip}
                aria-label={tip}
            >
                —
            </span>
        )
    }

    const sign = typeof deltaPct === 'number' && deltaPct > 0 ? '+' : ''
    const pctText = typeof deltaPct === 'number' ? `${sign}${deltaPct.toFixed(2)}%` : ''
    const priceText = typeof close === 'number' ? `¥${close.toFixed(2)}` : ''

    const tooltipParts: string[] = [`${hk.toUpperCase()} 窗口：${OUTCOME_STATUS_LABEL[st]}`]
    if (targetDate) tooltipParts.push(`目标日 ${targetDate}`)
    if (typeof baseline === 'number') tooltipParts.push(`基线 ¥${baseline.toFixed(2)}`)
    if (priceText) tooltipParts.push(`收盘 ${priceText}`)
    if (pctText) tooltipParts.push(`Δ ${pctText}`)
    if (typeof atrMult === 'number') tooltipParts.push(`ATR×${atrMult.toFixed(2)}`)
    if (typeof atr20 === 'number' && typeof baseline === 'number' && baseline > 0) {
        const atrPct = atr20 / baseline
        let thr: number
        if (atrPct < 0.015) thr = atr20 * 0.5
        else if (atrPct < 0.03) thr = atr20 * 0.4
        else {
            const cap = baseline * 0.04
            thr = Math.max(Math.min(atr20, cap) * 0.3, baseline * 0.015)
        }
        const thrPct = baseline > 0 ? (thr / baseline) * 100 : 0
        tooltipParts.push(`日波 ${(atrPct * 100).toFixed(2)}% · 阈值 ±${thrPct.toFixed(2)}%`)
    }
    const tip = tooltipParts.join(' · ')

    return (
        <div
            className={`inline-flex flex-col items-center justify-center min-w-[4.6rem] rounded px-1.5 py-0.5 leading-tight ${OUTCOME_STATUS_CLASS[st]}`}
            title={tip}
        >
            <span className="text-[11px] font-medium">{OUTCOME_STATUS_LABEL[st]}</span>
            <span className="text-[10.5px] tabular-nums opacity-90">
                {priceText || '--'}
                {pctText ? <span className="ml-1">{pctText}</span> : null}
            </span>
        </div>
    )
}

function ActiveDetailStatusCard({ report }: { report: ReportDetail }) {
    const progress = getReportRunProgress({
        status: report.status,
        createdAt: report.created_at,
    })
    const isPending = report.status === 'pending'
    const title = isPending ? '排队处理中...' : '深度分析中...'
    const queueHint = getQueueHint(report)
    const detail = isPending
        ? (queueHint || '任务已进入队列，正在等待分析资源。')
        : '正在汇总各路 Agent 的观点，请稍后。'

    return (
        <div className="card h-full min-h-[320px] p-8">
            <div className="flex h-full flex-col justify-center">
                <div className="mx-auto mb-5 flex h-14 w-14 items-center justify-center rounded-full bg-blue-50 text-blue-500 dark:bg-blue-500/10 dark:text-blue-300">
                    <Clock3 className="h-7 w-7" />
                </div>
                <div className="mx-auto w-full max-w-[280px] text-center">
                    <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">{title}</h3>
                    <p className="mt-2 text-sm text-slate-500">{detail}</p>
                    <div className="mt-6 text-left">
                        <div className="mb-2 flex items-center justify-between text-sm">
                            <span className="font-medium text-slate-600 dark:text-slate-300">当前进度</span>
                            <span className="font-semibold tabular-nums text-blue-600 dark:text-blue-300">{progress}%</span>
                        </div>
                        <div className="h-2.5 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                            <div
                                className="h-full rounded-full bg-gradient-to-r from-cyan-500 via-blue-500 to-indigo-500 transition-[width] duration-700 ease-out"
                                style={{ width: `${progress}%` }}
                            />
                        </div>
                    </div>
                    <p className="mt-4 text-xs text-slate-400">
                        页面会自动刷新任务状态，完成后这里会直接切换为分析结果。
                    </p>
                </div>
            </div>
        </div>
    )
}

function exportReport(report: ReportDetail) {
    const sections = [
        { key: 'market_report', title: '市场分析报告' },
        { key: 'sentiment_report', title: '舆情分析报告' },
        { key: 'news_report', title: '新闻分析报告' },
        { key: 'fundamentals_report', title: '基本面分析报告' },
        { key: 'investment_plan', title: '研究团队研判结论' },
        { key: 'trader_investment_plan', title: '执行路径草稿' },
        { key: 'final_trade_decision', title: '沙盘综合研判结论' },
    ]
    const text = sections
        .filter(s => report[s.key as keyof ReportDetail])
        .map(s => `## ${s.title}\n\n${report[s.key as keyof ReportDetail]}`)
        .join('\n\n---\n\n')
    const blob = new Blob([text], { type: 'text/markdown' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${stockSafeFilename({
        symbol: report.symbol,
        name: report.name,
        display_label: report.display_label,
    })}-${report.trade_date}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}

export default function Reports() {
    const { user } = useAuthStore()
    const [searchParams, setSearchParams] = useSearchParams()
    const setSearchParamsRef = useRef(setSearchParams)
    setSearchParamsRef.current = setSearchParams
    const PAGE_SIZE = 20
    const [searchQuery, setSearchQuery] = useState('')
    const [page, setPage] = useState(0)
    const [reports, setReports] = useState<Report[]>([])
    const [total, setTotal] = useState(0)
    const [selectedReport, setSelectedReport] = useState<ReportDetail | null>(null)
    const [loading, setLoading] = useState(false)
    const [detailLoading, setDetailLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [deleting, setDeleting] = useState<string | null>(null)
    const [symbolHistory, setSymbolHistory] = useState<Report[]>([])
    const [listProgress, setListProgress] = useState<ProgressState>(IDLE_PROGRESS)
    const [detailProgress, setDetailProgress] = useState<ProgressState>(IDLE_PROGRESS)
    const [realtimeQuotes, setRealtimeQuotes] = useState<Record<string, number | null>>({})
    const [historicalPrices, setHistoricalPrices] = useState<Record<string, number | null>>({})
    const [klineLocalVersion, setKlineLocalVersion] = useState(0)
    const reportsFetchGenRef = useRef(0)
    const [outcomeDialogOpen, setOutcomeDialogOpen] = useState(false)
    const [outcomeDetail, setOutcomeDetail] = useState<ReportOutcomeDetail | null>(null)
    const [outcomeSummary, setOutcomeSummary] = useState<ReportOutcomeSummaryResponse | null>(null)

    const reportListKind: ReportListKind = useMemo(
        () => reportListKindFromSearchParams(searchParams),
        [searchParams],
    )

    const klineInsightRows = useMemo(() => {
        if (reportListKind !== 'kline') return []
        return loadChartInsightHistory()
    }, [reportListKind, klineLocalVersion])

    const totalPages = Math.max(1, Math.ceil(total / PAGE_SIZE))

    useEffect(() => {
        let mounted = true
        if (reportListKind === 'kline') {
            setOutcomeSummary(null)
            return () => { mounted = false }
        }
        const tk = reportListKind === 'fast' ? 'fast_analysis' : 'full_analysis'
        void api.getReportOutcomeSummary({ taskKind: tk, sinceDays: 30, groupBy: 'overall' })
            .then((res) => {
                if (mounted) setOutcomeSummary(res)
            })
            .catch(() => {
                if (mounted) setOutcomeSummary(null)
            })
        return () => { mounted = false }
    }, [reportListKind, reports.length])

    useEffect(() => {
        if (listProgress.status !== 'loading') return

        const timer = window.setInterval(() => {
            setListProgress((prev) => prev.status === 'loading'
                ? { ...prev, progress: advanceProgress(prev.progress) }
                : prev)
        }, 180)

        return () => window.clearInterval(timer)
    }, [listProgress.status])

    useEffect(() => {
        if (detailProgress.status !== 'loading') return

        const timer = window.setInterval(() => {
            setDetailProgress((prev) => prev.status === 'loading'
                ? { ...prev, progress: advanceProgress(prev.progress) }
                : prev)
        }, 180)

        return () => window.clearInterval(timer)
    }, [detailProgress.status])

    const fetchReports = useCallback(async (targetPage: number, options?: { silent?: boolean }) => {
        const silent = options?.silent === true
        const gen = ++reportsFetchGenRef.current
        if (!silent) {
            setLoading(true)
            setError(null)
            setListProgress({
                status: 'loading',
                progress: 12,
                detail: `正在加载第 ${targetPage + 1} 页报告列表...`,
            })
        }
        try {
            if (reportListKind === 'kline') {
                const rows = loadChartInsightHistory()
                if (gen !== reportsFetchGenRef.current) return
                setReports([])
                setTotal(rows.length)
                if (!silent) {
                    setListProgress({
                        status: 'success',
                        progress: 100,
                        detail: `本地 K 线解读 ${rows.length} 条（最多 ${CHART_INSIGHT_HISTORY_MAX} 条）`,
                    })
                }
            } else {
                const taskKind = reportListKind === 'fast' ? 'fast_analysis' : 'full_analysis'
                const response = await api.getReports(undefined, targetPage * PAGE_SIZE, PAGE_SIZE, taskKind)
                if (gen !== reportsFetchGenRef.current) return
                setReports(response.reports)
                setTotal(response.total)
                if (!silent) {
                    setListProgress({
                        status: 'success',
                        progress: 100,
                        detail: `已获取 ${response.reports.length} 条报告记录`,
                    })
                }
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : '获取报告失败'
            if (!silent) {
                setError(message)
                setListProgress({
                    status: 'error',
                    progress: 100,
                    detail: message,
                })
            }
        } finally {
            if (!silent) {
                setLoading(false)
            }
        }
    }, [reportListKind])

    useEffect(() => {
        void fetchReports(page)
    }, [fetchReports, page, reportListKind])

    const fetchedHistoricalPricesRef = useRef<Set<string>>(new Set())

    // Fetch realtime quotes and historical prices for the current page of reports
    useEffect(() => {
        if (reports.length === 0) return

        let mounted = true

        const fetchPrices = async () => {
            try {
                // 1. Fetch realtime quotes
                const symbols = Array.from(new Set(reports.map(r => r.symbol)))
                if (symbols.length > 0) {
                    const quotesRes = await api.getRealtimeQuotes(symbols)
                    if (mounted) {
                        setRealtimeQuotes(prev => {
                            const next = { ...prev }
                            for (const [sym, quote] of Object.entries(quotesRes.quotes)) {
                                if (quote.price != null) {
                                    next[sym] = quote.price
                                }
                            }
                            return next
                        })
                    }
                }

                // 2. Fetch historical prices (analysis close price)
                const reportsToFetch = reports.filter(r => !fetchedHistoricalPricesRef.current.has(r.id))
                
                // Fetch in batches to avoid overwhelming the server
                const batchSize = 5
                for (let i = 0; i < reportsToFetch.length; i += batchSize) {
                    if (!mounted) break
                    const batch = reportsToFetch.slice(i, i + batchSize)
                    
                    // Mark as fetched immediately to prevent duplicate fetches
                    batch.forEach(r => fetchedHistoricalPricesRef.current.add(r.id))

                    await Promise.all(batch.map(async (report) => {
                        try {
                            // Fetch kline up to trade_date. Start date is 7 days before to ensure we get a candle even if trade_date is a weekend/holiday
                            const tradeDateObj = new Date(report.trade_date.split(' ')[0])
                            if (isNaN(tradeDateObj.getTime())) return

                            const startDateObj = new Date(tradeDateObj)
                            startDateObj.setUTCDate(startDateObj.getUTCDate() - 7)
                            
                            const formatISODate = (d: Date) => {
                                const y = d.getUTCFullYear()
                                const m = String(d.getUTCMonth() + 1).padStart(2, '0')
                                const day = String(d.getUTCDate()).padStart(2, '0')
                                return `${y}-${m}-${day}`
                            }
                            
                            const startDateStr = formatISODate(startDateObj)
                            const endDateStr = report.trade_date.split(' ')[0]
                            
                            const klineRes = await api.getKline(report.symbol, startDateStr, endDateStr, { period: '1d', adjust: 'none' })
                            
                            if (mounted && klineRes.candles && klineRes.candles.length > 0) {
                                // Get the last candle's close price
                                const lastCandle = klineRes.candles[klineRes.candles.length - 1]
                                setHistoricalPrices(prev => ({
                                    ...prev,
                                    [`${report.id}`]: lastCandle.close
                                }))
                            } else if (mounted) {
                                setHistoricalPrices(prev => ({
                                    ...prev,
                                    [`${report.id}`]: null
                                }))
                            }
                        } catch (err) {
                            console.error(`Failed to fetch historical price for ${report.symbol} on ${report.trade_date}`, err)
                            if (mounted) {
                                setHistoricalPrices(prev => ({
                                    ...prev,
                                    [`${report.id}`]: null
                                }))
                            }
                        }
                    }))
                }
            } catch (err) {
                console.error('Failed to fetch prices', err)
            }
        }

        void fetchPrices()

        return () => {
            mounted = false
        }
    }, [reports])

    const handleDelete = async (e: React.MouseEvent, reportId: string) => {
        e.stopPropagation()
        if (!confirm('确定删除该报告？若任务仍在排队或分析中，将一并终止。')) return
        setDeleting(reportId)
        try {
            await api.deleteReport(reportId)
            setReports(prev => prev.filter(r => r.id !== reportId))
            setTotal(prev => {
                const newTotal = prev - 1
                // Go to prev page if current page is now empty
                if (reports.length === 1 && page > 0) setPage(p => p - 1)
                return newTotal
            })
            if (selectedReport?.id === reportId) {
                setSelectedReport(null)
                setOutcomeDetail(null)
                setSearchParamsRef.current((prev) => {
                    const next = new URLSearchParams(prev)
                    next.delete('report')
                    return next
                })
            }
        } catch (err) {
            alert(err instanceof Error ? err.message : '删除失败')
        } finally {
            setDeleting(null)
        }
    }

    const handleDeleteKlineInsight = (e: React.MouseEvent, id: string) => {
        e.stopPropagation()
        if (!confirm('确定从本机移除该条 K 线解读记录？')) return
        removeChartInsightHistoryItem(id)
        setKlineLocalVersion((v) => v + 1)
        void fetchReports(page, { silent: true })
    }

    const loadReportDetail = useCallback(async (
        reportId: string,
        options?: { silent?: boolean; preserveHistory?: boolean },
    ) => {
        const silent = options?.silent === true
        const preserveHistory = options?.preserveHistory === true

        if (!silent) {
            setDetailLoading(true)
            if (!preserveHistory) {
                setSymbolHistory([])
            }
            setDetailProgress({
                status: 'loading',
                progress: 14,
                detail: preserveHistory ? '正在恢复你刚刚打开的报告...' : '正在打开报告详情...',
            })
        }

        try {
            const detail = await api.getReport(reportId)
            setSelectedReport(detail)
            setReports(prev => prev.map(report => report.id === detail.id ? { ...report, ...detail } : report))
            if (reportListKind !== 'kline') {
                try {
                    const od = await api.getReportOutcome(reportId)
                    setOutcomeDetail(od)
                } catch {
                    setOutcomeDetail(null)
                }
            } else {
                setOutcomeDetail(null)
            }

            if (reportListKind !== 'kline' && (!silent || !preserveHistory)) {
                const historyTaskKind = reportListKind === 'fast' ? 'fast_analysis' : 'full_analysis'
                const history = await api.getReports(detail.symbol, 0, 20, historyTaskKind)
                setSymbolHistory(history.reports)
            } else if (reportListKind === 'kline') {
                setSymbolHistory([])
            } else {
                setSymbolHistory(prev => prev.map(report => report.id === detail.id ? { ...report, ...detail } : report))
            }

            if (!silent) {
                setSearchParamsRef.current((prev) => {
                    const next = new URLSearchParams(prev)
                    next.set('report', reportId)
                    return next
                })
                setDetailProgress({
                    status: 'success',
                    progress: 100,
                    detail: `${stockDisplayLabel({ symbol: detail.symbol, name: detail.name, display_label: detail.display_label })} 报告已就绪`,
                })
            }
        } catch (err) {
            const message = err instanceof Error ? err.message : '获取报告详情失败'
            if (!silent) {
                setDetailProgress({
                    status: 'error',
                    progress: 100,
                    detail: message,
                })
                alert(message)
            }
            throw err
        } finally {
            if (!silent) {
                setDetailLoading(false)
            }
        }
    }, [reportListKind])

    const handleSelectReport = async (report: Pick<Report, 'id' | 'symbol'>) => {
        try {
            await loadReportDetail(report.id)
        } catch {}
    }

    // Only on mount: restore report from URL
    const initialReportId = useRef(searchParams.get('report'))
    useEffect(() => {
        const reportId = initialReportId.current
        if (reportId) {
            void loadReportDetail(reportId, { preserveHistory: true })
        }
    // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [])

    const filteredReports = reports.filter((r) => {
        const tk = String(r.task_kind || '').trim()
        if (reportListKind === 'full' && tk === 'fast_analysis') {
            return false
        }
        const q = searchQuery.toLowerCase()
        const label = (r.display_label || '').toLowerCase()
        return (
            r.symbol.toLowerCase().includes(q) ||
            (r.name?.toLowerCase().includes(q) ?? false) ||
            (q.length > 0 && label.includes(q))
        )
    })
    const filteredKlineRows = useMemo(() => {
        const q = searchQuery.toLowerCase().trim()
        return klineInsightRows.filter((row) => {
            if (!q) return true
            const lab = stockDisplayLabel({
                symbol: row.symbol,
                name: row.symbolName,
                display_label: row.display_label,
            }).toLowerCase()
            return lab.includes(q) || row.symbol.toLowerCase().includes(q)
        })
    }, [klineInsightRows, searchQuery])
    const hasActiveReport = reports.some(report => report.status === 'pending' || report.status === 'running')

    const setReportListKind = useCallback(
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
            setSelectedReport(null)
            setOutcomeDetail(null)
            setSymbolHistory([])
            setPage(0)
        },
        [setSearchParams],
    )

    useEffect(() => {
        if (loading || detailLoading || selectedReport || !hasActiveReport) return

        const timer = window.setInterval(() => {
            void fetchReports(page, { silent: true })
        }, 4000)

        return () => window.clearInterval(timer)
    }, [detailLoading, fetchReports, hasActiveReport, loading, page, selectedReport])

    const selectedReportRef = useRef(selectedReport)
    selectedReportRef.current = selectedReport

    useEffect(() => {
        if (!selectedReport || detailLoading) return
        if (selectedReport.status !== 'pending' && selectedReport.status !== 'running') return

        const timer = window.setInterval(() => {
            const current = selectedReportRef.current
            if (!current || (current.status !== 'pending' && current.status !== 'running')) return
            void loadReportDetail(current.id, { silent: true, preserveHistory: true })
        }, 4000)

        return () => window.clearInterval(timer)
    }, [detailLoading, loadReportDetail, selectedReport?.id, selectedReport?.status])

    // ─── 详情视图 ────────────────────────────────────────────────────────────
    if (detailLoading) {
        return (
            <div className="flex items-center justify-center py-24">
                <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
            </div>
        )
    }

    if (selectedReport) {
        const { action } = parseDecision(selectedReport.decision)
        const fdFull = selectedReport.final_trade_decision
        const decisionCardReasoning =
            (selectedReport.final_decision_summary && selectedReport.final_decision_summary.trim()) ||
            excerptForDecisionCard(fdFull, 420)
        const selectedReportProgressStatus = selectedReport.status === 'pending' || selectedReport.status === 'running'
            ? 'loading'
            : selectedReport.status === 'failed'
                ? 'error'
                : 'success'
        const selectedReportProgressValue = getReportRunProgress({
            status: selectedReport.status,
            createdAt: selectedReport.created_at,
        })
        const selectedReportProgressDetail = selectedReport.status === 'failed'
            ? (selectedReport.error || '任务执行失败')
            : selectedReport.status === 'completed'
                ? `${stockDisplayLabel({ symbol: selectedReport.symbol, name: selectedReport.name, display_label: selectedReport.display_label })} 报告已完成`
                : selectedReport.status === 'pending'
                    ? (getQueueHint(selectedReport) || '任务排队中 · 进度会自动刷新')
                    : '多智能体正在协同分析 · 进度会自动刷新'

        return (
            <div className="space-y-6">
                {(selectedReport.status === 'pending' || selectedReport.status === 'running') && (
                    <TaskProgressBanner
                        status={selectedReportProgressStatus}
                        progress={selectedReportProgressValue}
                        label={selectedReport.status === 'pending' ? '报告任务排队中...' : '报告生成中...'}
                        detail={selectedReportProgressDetail}
                    />
                )}
                {/* 返回按钮 + 标题 */}
                <div className="flex items-center gap-4">

                    <button
                        onClick={() => {
                            setSelectedReport(null)
                            setOutcomeDetail(null)
                            setSearchParams((prev) => {
                                const next = new URLSearchParams(prev)
                                next.delete('report')
                                return next
                            })
                        }}
                        className="flex items-center gap-2 px-4 py-2 rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                    >
                        <ChevronLeft className="w-4 h-4" />
                        返回列表
                    </button>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">
                        {stockDisplayLabel({
                            symbol: selectedReport.symbol,
                            name: selectedReport.name,
                            display_label: selectedReport.display_label,
                        })}{' '}
                        分析报告
                    </h1>
                    <button
                        onClick={() => exportReport(selectedReport)}
                        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 text-sm rounded-lg bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 hover:bg-slate-200 dark:hover:bg-slate-700 transition-colors"
                    >
                        <Download className="w-4 h-4" />
                        导出 Markdown
                    </button>
                </div>

                {/* 元信息 */}
                <div className="flex items-center gap-4 text-sm text-slate-500">
                    <span>分析日期：{selectedReport.trade_date.includes(':') ? selectedReport.trade_date : selectedReport.created_at ? new Date(selectedReport.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(/\//g, '-') : selectedReport.trade_date}</span>
                    <span>生成时间：{selectedReport.created_at ? new Date(selectedReport.created_at).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(/\//g, '-') : '-'}</span>
                    <span>分析当日价：{selectedReport.analysis_price != null ? (
                        `¥${selectedReport.analysis_price.toFixed(2)}${selectedReport.analysis_price_time ? ` (${new Date(selectedReport.analysis_price_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(/\//g, '-')})` : ''}`
                    ) : historicalPrices[selectedReport.id] !== undefined ? (
                        historicalPrices[selectedReport.id] !== null ? `¥${historicalPrices[selectedReport.id]?.toFixed(2)}` : '-'
                    ) : (
                        <Loader2 className="w-3 h-3 animate-spin text-slate-400 inline" />
                    )}</span>
                    <span>今日实时价格：{realtimeQuotes[selectedReport.symbol] !== undefined ? (
                        realtimeQuotes[selectedReport.symbol] !== null ? `¥${realtimeQuotes[selectedReport.symbol]?.toFixed(2)}` : '-'
                    ) : (
                        <Loader2 className="w-3 h-3 animate-spin text-slate-400 inline" />
                    )}</span>
                </div>

                {outcomeDetail ? (
                    <div className="card">
                        <div className="mb-3 flex items-center justify-between">
                            <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">兑现度跟踪</h3>
                            <span className="text-xs text-slate-500 dark:text-slate-400">
                                综合分 {outcomeDetail.weighted_score != null ? outcomeDetail.weighted_score.toFixed(1) : '--'}
                                {outcomeDetail.release_version ? ` · ${outcomeDetail.release_version}` : ''}
                            </span>
                        </div>
                        <div className="grid gap-2 md:grid-cols-3">
                            {Object.entries(outcomeDetail.outcomes || {}).map(([key, item]) => {
                                const st = pickOutcomeStatus(String(item.status || 'pending'))
                                return (
                                    <div key={key} className="rounded-lg border border-slate-200 p-2 dark:border-slate-700">
                                        <div className="flex items-center justify-between">
                                            <span className="text-xs font-medium text-slate-500">{key.toUpperCase()}</span>
                                            <span className={`inline-flex rounded-full px-1.5 py-0.5 text-[11px] ${OUTCOME_STATUS_CLASS[st]}`}>{OUTCOME_STATUS_LABEL[st]}</span>
                                        </div>
                                        <div className="mt-1 text-xs text-slate-600 dark:text-slate-300">
                                            目标日：{item.target_date || '--'}
                                        </div>
                                        <div className="text-xs text-slate-500 dark:text-slate-400">
                                            ΔP：{typeof item.delta_pct === 'number' ? `${item.delta_pct.toFixed(2)}%` : '--'} · ATRx{typeof item.atr_mult === 'number' ? item.atr_mult.toFixed(2) : '--'}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    </div>
                ) : null}

                {/* 历史沙盘记录时间线 */}
                {symbolHistory.length > 1 && (
                    <div className="card">
                        <div className="flex items-center gap-2 mb-3">
                            <History className="w-4 h-4 text-slate-400" />
                            <h3 className="text-sm font-semibold text-slate-700 dark:text-slate-300">
                                {stockDisplayLabel({
                                    symbol: selectedReport.symbol,
                                    name: selectedReport.name,
                                    display_label: selectedReport.display_label,
                                })}{' '}
                                历史沙盘记录
                            </h3>
                        </div>
                        <div className="flex items-center gap-2 overflow-x-auto pb-1">
                            {symbolHistory.slice().reverse().map(r => {
                                const { action: a } = parseDecision(r.decision)
                                const color = a === 'add' ? 'bg-red-500' : a === 'reduce' ? 'bg-green-500' : 'bg-slate-400'
                                const isCurrent = r.id === selectedReport.id
                                return (
                                    <button
                                        key={r.id}
                                        onClick={() => !isCurrent && handleSelectReport(r)}
                                        className={`flex flex-col items-center gap-1 shrink-0 px-2 py-1.5 rounded-lg transition-colors ${isCurrent ? 'bg-blue-50 dark:bg-blue-500/10' : 'hover:bg-slate-50 dark:hover:bg-slate-800/50'}`}
                                    >
                                        <div className={`w-3 h-3 rounded-full ${color}`} />
                                        <span className="text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">{r.trade_date.includes(':') ? r.trade_date.split(' ')[0] : r.trade_date}</span>
                                        {r.confidence != null && <span className="text-xs text-slate-400">{r.confidence}%</span>}
                                    </button>
                                )
                            })}
                        </div>
                    </div>
                )}

                {/* 主体：概要卡片 + 报告全文 */}
                <div className="grid grid-cols-1 xl:grid-cols-3 gap-6 items-start">
                    {selectedReport.status === 'completed' ? (
                        <DecisionCard
                            symbol={selectedReport.symbol}
                            name={selectedReport.name}
                            display_label={selectedReport.display_label}
                            decision={action}
                            direction={selectedReport.direction}
                            confidence={selectedReport.confidence ?? undefined}
                            rating5Tier={selectedReport.rating_5tier ?? undefined}
                            targetPrice={selectedReport.target_price ?? undefined}
                            stopLoss={selectedReport.stop_loss_price ?? undefined}
                            reasoning={decisionCardReasoning}
                            reasoningFull={fdFull ?? undefined}
                        />
                    ) : selectedReport.status === 'failed' ? (
                        <div className="card h-full flex flex-col items-center justify-center p-8 text-center min-h-[320px]">
                            <div className="mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-rose-50 text-rose-500 dark:bg-rose-500/10 dark:text-rose-300">
                                <Trash2 className="h-6 w-6" />
                            </div>
                            <h3 className="text-lg font-bold text-slate-900 dark:text-slate-100">分析失败</h3>
                            <p className="mt-2 max-w-[240px] text-sm text-slate-500">
                                {selectedReport.error?.slice(0, 80) || '未知错误'}
                            </p>
                        </div>
                    ) : (
                        <ActiveDetailStatusCard report={selectedReport} />
                    )}
                    <RiskRadar items={selectedReport.risk_items ?? undefined} />
                    <KeyMetrics items={selectedReport.key_metrics ?? undefined} />
                </div>

                {selectedReport.status === 'completed' && symbolHistory.length > 0 ? (
                    <DecisionArchivePanel
                        entries={symbolHistory.map(r => ({
                            trade_date: r.trade_date,
                            rating_5tier: r.rating_5tier ?? null,
                            outcome_raw_pct: null,
                            outcome_alpha_pct: null,
                            holding_days: null,
                            reflection_md: r.final_decision_summary ?? null,
                            decision_md: r.direction ?? r.decision ?? null,
                        }))}
                    />
                ) : null}

                <div className="card">
                    <ReportViewer reportData={selectedReport} />
                </div>
            </div>
        )
    }

    // ─── 列表视图 ────────────────────────────────────────────────────────────
    return (
        <>
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <div>
                    <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-100">历史报告</h1>
                    <p className="text-slate-500 dark:text-slate-400 mt-1">
                        {reportListKind === 'kline'
                            ? `本机保存的 K 线 Ai 解读 · 最多 ${CHART_INSIGHT_HISTORY_MAX} 条 · 当前 ${total} 条`
                            : user?.email
                              ? `${user.email} 的私有分析记录 · 共 ${total} 份`
                              : `共 ${total} 份分析报告`}
                    </p>
                </div>
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
                        onClick={() => setReportListKind(tab.id)}
                        className={`rounded-lg border px-3 py-1.5 text-sm font-medium transition-colors ${
                            reportListKind === tab.id
                                ? 'border-cyan-500/60 bg-cyan-500/15 text-cyan-900 dark:border-cyan-400/50 dark:bg-cyan-500/10 dark:text-cyan-100'
                                : 'border-slate-200 bg-white text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:bg-slate-800'
                        }`}
                    >
                        {tab.label}
                    </button>
                ))}
                <button
                    type="button"
                    onClick={() => setOutcomeDialogOpen(true)}
                    className="ml-auto inline-flex items-center gap-1 rounded-lg border border-slate-200 bg-white px-3 py-1.5 text-sm text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800/80 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                    <BarChart3 className="h-4 w-4" />
                    兑现度看板
                </button>
            </div>

            {reportListKind !== 'kline' && outcomeSummary ? (
                <div className="card py-3">
                    <div className="flex flex-wrap items-center gap-4 text-sm text-slate-600 dark:text-slate-300">
                        <span>近30天命中率：{outcomeSummary.summary.hit_rate != null ? `${outcomeSummary.summary.hit_rate.toFixed(1)}%` : '--'}</span>
                        <span>平均分：{outcomeSummary.summary.avg_weighted_score != null ? outcomeSummary.summary.avg_weighted_score.toFixed(1) : '--'}</span>
                        <span>样本：{outcomeSummary.summary.sample_count}</span>
                        <span>待观察：{outcomeSummary.summary.pending_count}</span>
                    </div>
                </div>
            ) : null}

            {/* 搜索 */}
            <div className="card">
                <div className="flex flex-col gap-4">
                    <div className="relative max-w-md">
                        <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                        <input
                            type="text"
                            value={searchQuery}
                            onChange={e => setSearchQuery(e.target.value)}
                            placeholder="搜索股票代码或名称..."
                            className="input w-full pl-10"
                        />
                    </div>

                </div>
            </div>

            {/* 加载中 */}
            {loading && (
                <div className="card py-12">
                    <div className="flex flex-col items-center gap-4">
                        <Loader2 className="w-8 h-8 text-blue-500 animate-spin" />
                        <p className="text-slate-500">加载报告中...</p>
                    </div>
                </div>
            )}

            {/* 错误 */}
            {error && !loading && (
                <div className="card py-12 text-center">
                    <p className="text-red-500 mb-4">{error}</p>
                    <button
                        onClick={() => fetchReports(page)}
                        className="px-4 py-2 bg-blue-500 text-white rounded-lg hover:bg-blue-600 transition-colors"
                    >
                        重试
                    </button>
                </div>
            )}

            {/* 报告表格 */}
            {!loading && !error && (
                <div className="card overflow-hidden">
                    <div className="overflow-x-auto">
                        {reportListKind === 'kline' ? (
                            <table className="w-full">
                                <thead>
                                    <tr className="border-b border-slate-200 dark:border-slate-700">
                                        {['标的', '图表区间', '生成时间', '技术倾向', '操作'].map((h) => (
                                            <th
                                                key={h}
                                                className={`py-3 px-4 text-sm font-medium text-slate-500 dark:text-slate-400 ${h === '操作' ? 'text-right' : 'text-left'}`}
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                                    {filteredKlineRows.map((row) => {
                                        const biasLabel =
                                            row.insight.bias === 'bullish'
                                                ? '偏多'
                                                : row.insight.bias === 'bearish'
                                                  ? '偏空'
                                                  : '中性'
                                        return (
                                            <tr key={row.id} className="hover:bg-slate-50 dark:hover:bg-slate-800/50">
                                                <td className="py-3 px-4">
                                                    <div className="flex items-center gap-3">
                                                        <div className="w-8 h-8 rounded-lg bg-violet-100 dark:bg-violet-500/10 flex items-center justify-center">
                                                            <Sparkles className="w-4 h-4 text-violet-600 dark:text-violet-400" />
                                                        </div>
                                                        <p className="font-medium text-slate-900 dark:text-slate-100">
                                                            {stockDisplayLabel({
                                                                symbol: row.symbol,
                                                                name: row.symbolName,
                                                                display_label: row.display_label,
                                                            })}
                                                        </p>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-4 text-sm text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {row.rangePreset} · {row.period} · {row.adjust}
                                                </td>
                                                <td className="py-3 px-4 text-sm text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                                    {new Date(row.at).toLocaleString('zh-CN', {
                                                        year: 'numeric',
                                                        month: '2-digit',
                                                        day: '2-digit',
                                                        hour: '2-digit',
                                                        minute: '2-digit',
                                                        hour12: false,
                                                    }).replace(/\//g, '-')}
                                                </td>
                                                <td className="py-3 px-4 text-sm text-slate-700 dark:text-slate-200">{biasLabel}</td>
                                                <td className="py-3 px-4">
                                                    <div className="flex items-center justify-end gap-2">
                                                        <Link
                                                            to={`/chart?insight=${encodeURIComponent(row.id)}`}
                                                            className="p-2 text-slate-400 hover:text-cyan-600 dark:hover:text-cyan-400 transition-colors"
                                                            title="在 K 线分析中打开"
                                                        >
                                                            <LineChart className="w-4 h-4" />
                                                        </Link>
                                                        <button
                                                            type="button"
                                                            className="p-2 text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors"
                                                            onClick={(e) => handleDeleteKlineInsight(e, row.id)}
                                                            title="从本机移除"
                                                        >
                                                            <Trash2 className="w-4 h-4" />
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        ) : reportListKind === 'full' ? (
                            <table className="w-full min-w-[1200px]">
                                <thead>
                                    <tr className="border-b border-slate-200 dark:border-slate-700">
                                        {[
                                            '股票',
                                            '分析日期',
                                            '沙盘综合研判结论',
                                            '置信度',
                                            '偏多峰值 / 偏空风控',
                                            '生成时间',
                                            '分析当日价',
                                            '兑现 T+1',
                                            '兑现 T+2',
                                            '兑现 T+3',
                                            '兑现 T+5',
                                            '今日实时价格',
                                            '操作',
                                        ].map((h) => (
                                            <th
                                                key={h}
                                                className={`py-3 px-2 text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap ${h === '操作' ? 'text-right' : 'text-left'}`}
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                                    {filteredReports.map((report) => {
                                        const kindMeta = reportTaskKindMeta(report)
                                        return (
                                            <tr
                                                key={report.id}
                                                className="transition-colors cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"
                                                onClick={() => handleSelectReport(report)}
                                            >
                                                <td className="py-3 px-2 align-top">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-8 h-8 shrink-0 rounded-lg bg-blue-100 dark:bg-blue-500/10 flex items-center justify-center">
                                                            <FileText className="w-4 h-4 text-blue-600 dark:text-blue-400" />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <p className="font-medium text-slate-900 dark:text-slate-100">
                                                                {stockDisplayLabel({
                                                                    symbol: report.symbol,
                                                                    name: report.name,
                                                                    display_label: report.display_label,
                                                                })}
                                                            </p>
                                                            <span className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${kindMeta.cls}`}>
                                                                <kindMeta.Icon className="h-3.5 w-3.5" />
                                                                {kindMeta.label}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-2 align-top text-sm text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {tradeDateOnly(report.trade_date)}
                                                </td>
                                                <td className="py-3 px-2 align-top">{renderSandboxConclusionCell(report)}</td>
                                                <td className="py-3 px-2 align-top">
                                                    {report.confidence != null ? (
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-14 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                                                <div
                                                                    className="h-full bg-blue-500 rounded-full"
                                                                    style={{ width: `${report.confidence}%` }}
                                                                />
                                                            </div>
                                                            <span className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">{report.confidence}%</span>
                                                        </div>
                                                    ) : (
                                                        <span className="text-slate-400">-</span>
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {report.target_price != null ? `¥${report.target_price}` : '-'} /{' '}
                                                    {report.stop_loss_price != null ? `¥${report.stop_loss_price}` : '-'}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                                    {report.created_at
                                                        ? new Date(report.created_at)
                                                              .toLocaleString('zh-CN', {
                                                                  year: 'numeric',
                                                                  month: '2-digit',
                                                                  day: '2-digit',
                                                                  hour: '2-digit',
                                                                  minute: '2-digit',
                                                                  hour12: false,
                                                              })
                                                              .replace(/\//g, '-')
                                                        : '-'}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {report.analysis_price != null ? (
                                                        `¥${report.analysis_price.toFixed(2)}${report.analysis_price_time ? ` (${new Date(report.analysis_price_time).toLocaleString('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit', hour12: false }).replace(/\//g, '-')})` : ''}`
                                                    ) : historicalPrices[report.id] !== undefined ? (
                                                        historicalPrices[report.id] !== null ? (
                                                            `¥${historicalPrices[report.id]?.toFixed(2)}`
                                                        ) : (
                                                            '-'
                                                        )
                                                    ) : (
                                                        <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't1')}</td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't2')}</td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't3')}</td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't5')}</td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {realtimeQuotes[report.symbol] !== undefined ? (
                                                        realtimeQuotes[report.symbol] !== null ? (
                                                            `¥${realtimeQuotes[report.symbol]?.toFixed(2)}`
                                                        ) : (
                                                            '-'
                                                        )
                                                    ) : (
                                                        <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top">
                                                    <div className="flex items-center justify-end gap-1">
                                                        <button
                                                            type="button"
                                                            className="p-2 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                                                            onClick={(e) => {
                                                                e.stopPropagation()
                                                                void handleSelectReport(report)
                                                            }}
                                                            title="查看详情"
                                                        >
                                                            <FileText className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className="p-2 text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors disabled:opacity-50"
                                                            onClick={(e) => handleDelete(e, report.id)}
                                                            disabled={deleting === report.id}
                                                            title="删除"
                                                        >
                                                            {deleting === report.id ? (
                                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                            ) : (
                                                                <Trash2 className="w-4 h-4" />
                                                            )}
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        ) : (
                            <table className="w-full min-w-[960px]">
                                <thead>
                                    <tr className="border-b border-slate-200 dark:border-slate-700">
                                        {[
                                            '股票',
                                            '分析日期',
                                            '结论',
                                            '置信度',
                                            '偏多峰值 / 偏空风控',
                                            '生成时间',
                                            '分析当日价',
                                            '兑现 T+0',
                                            '兑现 T+1',
                                            '今日实时价格',
                                            '操作',
                                        ].map((h) => (
                                            <th
                                                key={h}
                                                className={`py-3 px-2 text-xs font-medium text-slate-500 dark:text-slate-400 whitespace-nowrap ${h === '操作' ? 'text-right' : 'text-left'}`}
                                            >
                                                {h}
                                            </th>
                                        ))}
                                    </tr>
                                </thead>
                                <tbody className="divide-y divide-slate-200 dark:divide-slate-700">
                                    {filteredReports.map((report) => {
                                        const kindMeta = reportTaskKindMeta(report)
                                        return (
                                            <tr
                                                key={report.id}
                                                className="transition-colors cursor-pointer hover:bg-slate-50 dark:hover:bg-slate-800/50"
                                                onClick={() => handleSelectReport(report)}
                                            >
                                                <td className="py-3 px-2 align-top">
                                                    <div className="flex items-center gap-2">
                                                        <div className="w-8 h-8 shrink-0 rounded-lg bg-amber-100 dark:bg-amber-500/10 flex items-center justify-center">
                                                            <FileText className="w-4 h-4 text-amber-700 dark:text-amber-300" />
                                                        </div>
                                                        <div className="min-w-0">
                                                            <p className="font-medium text-slate-900 dark:text-slate-100">
                                                                {stockDisplayLabel({
                                                                    symbol: report.symbol,
                                                                    name: report.name,
                                                                    display_label: report.display_label,
                                                                })}
                                                            </p>
                                                            <span className={`mt-1 inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[11px] ${kindMeta.cls}`}>
                                                                <kindMeta.Icon className="h-3.5 w-3.5" />
                                                                {kindMeta.label}
                                                            </span>
                                                        </div>
                                                    </div>
                                                </td>
                                                <td className="py-3 px-2 align-top text-sm text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {tradeDateOnly(report.trade_date)}
                                                </td>
                                                <td className="py-3 px-2 align-top">{renderSandboxConclusionCell(report)}</td>
                                                <td className="py-3 px-2 align-top">
                                                    {report.confidence != null ? (
                                                        <div className="flex items-center gap-2">
                                                            <div className="w-14 h-1.5 bg-slate-200 dark:bg-slate-700 rounded-full overflow-hidden">
                                                                <div
                                                                    className="h-full bg-amber-500 rounded-full"
                                                                    style={{ width: `${report.confidence}%` }}
                                                                />
                                                            </div>
                                                            <span className="text-xs text-slate-600 dark:text-slate-400 tabular-nums">{report.confidence}%</span>
                                                        </div>
                                                    ) : (
                                                        <span className="text-slate-400">-</span>
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {report.target_price != null ? `¥${report.target_price}` : '-'} /{' '}
                                                    {report.stop_loss_price != null ? `¥${report.stop_loss_price}` : '-'}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-500 dark:text-slate-400 whitespace-nowrap">
                                                    {report.created_at
                                                        ? new Date(report.created_at)
                                                              .toLocaleString('zh-CN', {
                                                                  year: 'numeric',
                                                                  month: '2-digit',
                                                                  day: '2-digit',
                                                                  hour: '2-digit',
                                                                  minute: '2-digit',
                                                                  hour12: false,
                                                              })
                                                              .replace(/\//g, '-')
                                                        : '-'}
                                                </td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {report.analysis_price != null ? (
                                                        `¥${report.analysis_price.toFixed(2)}`
                                                    ) : historicalPrices[report.id] !== undefined ? (
                                                        historicalPrices[report.id] !== null ? (
                                                            `¥${historicalPrices[report.id]?.toFixed(2)}`
                                                        ) : (
                                                            '-'
                                                        )
                                                    ) : (
                                                        <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't0')}</td>
                                                <td className="py-3 px-2 align-top text-center">{renderHorizonOutcomeCell(report.outcome_summary, 't1')}</td>
                                                <td className="py-3 px-2 align-top text-xs text-slate-600 dark:text-slate-400 whitespace-nowrap">
                                                    {realtimeQuotes[report.symbol] !== undefined ? (
                                                        realtimeQuotes[report.symbol] !== null ? (
                                                            `¥${realtimeQuotes[report.symbol]?.toFixed(2)}`
                                                        ) : (
                                                            '-'
                                                        )
                                                    ) : (
                                                        <Loader2 className="w-3 h-3 animate-spin text-slate-400" />
                                                    )}
                                                </td>
                                                <td className="py-3 px-2 align-top">
                                                    <div className="flex items-center justify-end gap-1">
                                                        <button
                                                            type="button"
                                                            className="p-2 text-slate-400 hover:text-blue-600 dark:hover:text-blue-400 transition-colors"
                                                            onClick={(e) => {
                                                                e.stopPropagation()
                                                                void handleSelectReport(report)
                                                            }}
                                                            title="查看详情"
                                                        >
                                                            <FileText className="w-4 h-4" />
                                                        </button>
                                                        <button
                                                            type="button"
                                                            className="p-2 text-slate-400 hover:text-red-600 dark:hover:text-red-400 transition-colors disabled:opacity-50"
                                                            onClick={(e) => handleDelete(e, report.id)}
                                                            disabled={deleting === report.id}
                                                            title="删除"
                                                        >
                                                            {deleting === report.id ? (
                                                                <Loader2 className="w-4 h-4 animate-spin" />
                                                            ) : (
                                                                <Trash2 className="w-4 h-4" />
                                                            )}
                                                        </button>
                                                    </div>
                                                </td>
                                            </tr>
                                        )
                                    })}
                                </tbody>
                            </table>
                        )}
                    </div>

                    {reportListKind === 'kline' ? (
                        filteredKlineRows.length === 0 ? (
                            <div className="text-center py-12">
                                <Sparkles className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                                <p className="text-slate-500 dark:text-slate-400">
                                    {searchQuery ? '没有匹配的解读记录' : '暂无 K 线解读'}
                                </p>
                                <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                                    在{' '}
                                    <Link to="/chart" className="text-cyan-600 underline dark:text-cyan-400">
                                        K 线分析
                                    </Link>{' '}
                                    页使用 Ai助手 生成解读后会出现在此（本机最多 {CHART_INSIGHT_HISTORY_MAX} 条）
                                </p>
                            </div>
                        ) : null
                    ) : filteredReports.length === 0 ? (
                        <div className="text-center py-12">
                            <FileText className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                            <p className="text-slate-500 dark:text-slate-400">
                                {searchQuery ? '没有匹配的报告' : '暂无报告'}
                            </p>
                            <p className="text-sm text-slate-400 dark:text-slate-500 mt-1">
                                在分析页面生成新的报告
                            </p>
                        </div>
                    ) : null}

                    {reportListKind !== 'kline' && totalPages > 1 && (
                        <div className="flex items-center justify-between px-4 py-3 border-t border-slate-200 dark:border-slate-700">
                            <span className="text-sm text-slate-500 dark:text-slate-400">
                                第 {page + 1} / {totalPages} 页，共 {total} 条
                            </span>
                            <div className="flex items-center gap-2">
                                <button
                                    type="button"
                                    onClick={() => setPage(p => p - 1)}
                                    disabled={page === 0}
                                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                    title="上一页"
                                >
                                    <ChevronLeft className="w-4 h-4" />
                                </button>
                                <button
                                    type="button"
                                    onClick={() => setPage(p => p + 1)}
                                    disabled={page >= totalPages - 1}
                                    className="p-1.5 rounded-lg text-slate-400 hover:text-slate-600 dark:hover:text-slate-300 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
                                    title="下一页"
                                >
                                    <ChevronRight className="w-4 h-4" />
                                </button>
                            </div>
                        </div>
                    )}
                </div>
            )}
        </div>
        <OutcomeDashboardDialog
            open={outcomeDialogOpen}
            onClose={() => setOutcomeDialogOpen(false)}
            kind={reportListKind}
            onKindChange={(k) => setReportListKind(k)}
            klineRows={klineInsightRows}
        />
        </>
    )
}
