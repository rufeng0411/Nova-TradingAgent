import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import ChartToolbar from '@/components/chart/ChartToolbar'
import InsightPanel from '@/components/chart/InsightPanel'
import ProChart from '@/components/chart/ProChart'
import SidePanel from '@/components/chart/SidePanel'
import {
    getChartInsightHistoryItem,
    loadChartInsightHistory,
    pushChartInsightHistory,
} from '@/lib/chartInsightHistory'
import { rangePresetToDates } from '@/lib/chartRange'
import { api } from '@/services/api'
import type { ChartInsightResult, ChartRangePreset, KlineAdjust, KlinePeriod } from '@/types'
import { CHART_COMPARE_ENABLED, EMPTY_COMPARE_SYMBOLS, useChartStore } from '@/stores/chartStore'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useAuthStore } from '@/stores/authStore'
import { normalizeChartSymbol } from '@/lib/cnSymbol'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { cnShanghaiDateText, isCnAshareRegularSession } from '@/lib/cnMarketHours'
import { stockDisplayLabel } from '@/utils/stockDisplay'

const TOUR_KEY = 'ta-chart-tour-dismissed'

export default function ChartPro() {
    const [searchParams, setSearchParams] = useSearchParams()
    const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'))
    const [insight, setInsight] = useState<ChartInsightResult | null>(null)
    /** 模型失败时使用本地规则摘要，篇幅会像「简版」——需提示用户 */
    const [insightFallbackOnly, setInsightFallbackOnly] = useState(false)
    const [insightLoading, setInsightLoading] = useState(false)
    const [insightErr, setInsightErr] = useState<string | null>(null)
    const [insightAwaitingStart, setInsightAwaitingStart] = useState(true)
    const [insightHistoryVersion, setInsightHistoryVersion] = useState(0)
    const [selectedInsightHistoryId, setSelectedInsightHistoryId] = useState<string | null>(null)
    const [showTour, setShowTour] = useState(false)
    const [tourDismissForever, setTourDismissForever] = useState(false)
    /** 交易时段内定时刷新日 K，使当日蜡烛随数据源更新（仍非交易所毫秒级实时） */
    const [liveRefreshKey, setLiveRefreshKey] = useState(0)

    const {
        symbol,
        symbolName,
        symbolDisplayLabel,
        setSymbol,
        rangePreset,
        setRangePreset,
        period,
        setPeriod,
        adjust,
        setAdjust,
        ma,
        showBoll,
        subChart,
        compareSymbols,
        liveDailyEnabled,
        insightOpen,
        setLiveDailyEnabled,
        setInsightOpen,
    } = useChartStore()

    const user = useAuthStore((s) => s.user)
    const canAdvancedMarketContext =
        user?.role === 'admin' || user?.entitlements?.advanced_market === true
    const hasRtEntitlement = user?.role === 'admin' || user?.entitlements?.tushare_rt === true
    const liveDailyActive = liveDailyEnabled && hasRtEntitlement && period === '1d'

    useEffect(() => {
        const obs = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'))
        })
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => obs.disconnect()
    }, [])

    const initUrl = useRef(false)
    const insightRestoreRef = useRef(false)
    const lastInsightUrlParam = useRef<string | null>(null)

    useEffect(() => {
        if (initUrl.current) return
        initUrl.current = true
        const sym = searchParams.get('symbol')
        const range = searchParams.get('range') as ChartRangePreset | null
        const per = searchParams.get('period') as KlinePeriod | null
        const adj = searchParams.get('adjust') as KlineAdjust | null
        if (sym?.trim()) {
            const norm = normalizeChartSymbol(sym)
            setSymbol(norm || sym.trim().toUpperCase())
        } else {
            const { currentSymbol, currentSymbolDisplayName } = useAnalysisStore.getState()
            const norm = normalizeChartSymbol(currentSymbol) || currentSymbol.trim().toUpperCase()
            const nm = currentSymbolDisplayName?.trim()
            setSymbol(norm, nm ? { name: nm } : undefined)
        }
        if (range && ['1M', '3M', '6M', 'YTD', '1Y', '3Y', '5Y', 'ALL'].includes(range)) setRangePreset(range)
        if (per && ['1d', '1w', '1mo'].includes(per)) setPeriod(per)
        if (adj && ['none', 'qfq', 'hfq'].includes(adj)) setAdjust(adj)
    }, [searchParams, setAdjust, setPeriod, setRangePreset, setSymbol])

    /** K 线当前标的 ↔ 智能分析 currentSymbol 对齐（双向之一：此处写入分析侧） */
    useEffect(() => {
        const norm = normalizeChartSymbol(symbol) || symbol.trim().toUpperCase()
        const aSym = useAnalysisStore.getState().currentSymbol
        const aNorm = normalizeChartSymbol(aSym) || aSym.trim().toUpperCase()
        if (norm === aNorm) return
        useAnalysisStore.getState().setCurrentSymbol(norm)
    }, [symbol])

    useEffect(() => {
        setSearchParams(
            (prev) => {
                const next = new URLSearchParams(prev)
                next.set('symbol', symbol)
                next.set('range', rangePreset)
                next.set('period', period)
                next.set('adjust', adjust)
                return next
            },
            { replace: true },
        )
    }, [symbol, rangePreset, period, adjust, setSearchParams])

    /** 无交易所后缀时补全为 XXXXXX.SH/SZ/BJ，同代码时保留已解析的名称 */
    useEffect(() => {
        const norm = normalizeChartSymbol(symbol)
        if (!norm || norm === symbol.trim().toUpperCase()) return
        const prev6 = symbol.match(/^(\d{6})/)?.[1] ?? ''
        const next6 = norm.match(/^(\d{6})/)?.[1] ?? ''
        const st = useChartStore.getState()
        const preserveName =
            prev6 && prev6 === next6 && st.symbolName != null && String(st.symbolName).trim() !== ''
        setSymbol(norm, preserveName ? { name: st.symbolName! } : undefined)
    }, [symbol, setSymbol])

    useEffect(() => {
        let cancelled = false
        const sym = normalizeChartSymbol(symbol) || symbol.trim().toUpperCase()
        void fetchAshareDisplayName(sym).then((name) => {
            if (cancelled) return
            const cur = useChartStore.getState().symbol
            const curNorm = normalizeChartSymbol(cur) || cur.trim().toUpperCase()
            if (curNorm !== sym) return
            if (name) {
                setSymbol(sym, { name })
            }
        }).catch(() => {})
        return () => {
            cancelled = true
        }
    }, [symbol, setSymbol])

    useEffect(() => {
        if (typeof window === 'undefined') return
        if (!localStorage.getItem(TOUR_KEY)) setShowTour(true)
    }, [])


    const dismissTour = (permanent: boolean) => {
        if (permanent) localStorage.setItem(TOUR_KEY, '1')
        setShowTour(false)
    }

    const insightHistoryList = useMemo(() => loadChartInsightHistory(), [insightHistoryVersion])
    const insightHistoryOptions = useMemo(
        () =>
            insightHistoryList.map((h) => ({
                id: h.id,
                label: `${new Date(h.at).toLocaleString('zh-CN', {
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    hour12: false,
                })} · ${stockDisplayLabel({
                    symbol: h.symbol,
                    name: h.symbolName,
                    display_label: h.display_label,
                })}`,
            })),
        [insightHistoryList],
    )

    const applyInsightHistoryItem = useCallback(
        (id: string) => {
            const item = getChartInsightHistoryItem(id)
            if (!item) return
            setSymbol(item.symbol, {
                name: item.symbolName ?? undefined,
                display_label: item.display_label ?? undefined,
            })
            setRangePreset(item.rangePreset)
            setPeriod(item.period)
            setAdjust(item.adjust)
            setInsight(item.insight)
            setInsightFallbackOnly(item.fallback_only)
            setInsightErr(null)
            setInsightAwaitingStart(false)
            setSelectedInsightHistoryId(item.id)
        },
        [setAdjust, setPeriod, setRangePreset, setSymbol],
    )

    /** 从「历史报告」等入口携带的 ?insight= 恢复本地解读快照 */
    useEffect(() => {
        const hid = searchParams.get('insight')
        if (!hid || lastInsightUrlParam.current === hid) return
        lastInsightUrlParam.current = hid
        const item = getChartInsightHistoryItem(hid)
        if (!item) {
            setSearchParams(
                (prev) => {
                    const next = new URLSearchParams(prev)
                    next.delete('insight')
                    return next
                },
                { replace: true },
            )
            return
        }
        insightRestoreRef.current = true
        applyInsightHistoryItem(item.id)
        setInsightOpen(true)
        setInsightHistoryVersion((v) => v + 1)
        setSearchParams(
            (prev) => {
                const next = new URLSearchParams(prev)
                next.delete('insight')
                next.set('symbol', item.symbol)
                next.set('range', item.rangePreset)
                next.set('period', item.period)
                next.set('adjust', item.adjust)
                return next
            },
            { replace: true },
        )
    }, [applyInsightHistoryItem, searchParams, setInsightOpen, setSearchParams])

    const runInsight = useCallback(
        async (bypassCache: boolean) => {
            setInsightLoading(true)
            setInsightErr(null)
            try {
                const { start, end } = rangePresetToDates(rangePreset)
                const res = await api.chartInsight({
                    symbol,
                    period,
                    adjust,
                    start_date: start,
                    end_date: end,
                    level: 'deep', // 专业模式（与 insight_prompt / ta_features 的 deep 一致）
                    language: 'zh',
                    bypass_cache: bypassCache,
                    selected_indicators: ['MA', 'BOLL', 'MACD', 'VOL', 'RSI', 'KDJ'],
                    context_level: canAdvancedMarketContext ? 'advanced' : 'basic',
                })
                setInsight(res.insight)
                setInsightFallbackOnly(res.fallback_only === true)
                const saved = pushChartInsightHistory({
                    symbol,
                    symbolName,
                    display_label: symbolDisplayLabel,
                    rangePreset,
                    period,
                    adjust,
                    insight: res.insight,
                    fallback_only: res.fallback_only === true,
                })
                setSelectedInsightHistoryId(saved.id)
                setInsightHistoryVersion((v) => v + 1)
            } catch (e) {
                setInsightErr(e instanceof Error ? e.message : '解读失败')
                setInsight(null)
                setInsightFallbackOnly(false)
            } finally {
                setInsightLoading(false)
            }
        },
        [adjust, canAdvancedMarketContext, period, rangePreset, symbol, symbolDisplayLabel, symbolName],
    )

    useEffect(() => {
        if (!insightOpen) return
        if (insightRestoreRef.current) {
            insightRestoreRef.current = false
            return
        }
        setInsightAwaitingStart(true)
        setInsight(null)
        setSelectedInsightHistoryId(null)
        setInsightErr(null)
        setInsightFallbackOnly(false)
    }, [insightOpen])

    const { start, end } = rangePresetToDates(rangePreset)

    useEffect(() => {
        if (liveDailyEnabled && !hasRtEntitlement) {
            setLiveDailyEnabled(false)
        }
    }, [hasRtEntitlement, liveDailyEnabled, setLiveDailyEnabled])

    useEffect(() => {
        const tick = () => {
            if (liveDailyActive) return
            if (document.visibilityState !== 'visible') return
            const today = cnShanghaiDateText()
            if (end < today) return
            if (!isCnAshareRegularSession()) return
            setLiveRefreshKey((k) => k + 1)
        }
        const id = window.setInterval(tick, 60_000)
        return () => clearInterval(id)
    }, [end, liveDailyActive])

    return (
        <div className="flex flex-col gap-3 h-[calc(100vh-6.5rem)] min-h-[560px] overflow-visible">
            <ChartToolbar
                onAiInsight={() => {
                    setInsightOpen(true)
                }}
                onTour={() => setShowTour(true)}
            />

            <div className="flex flex-1 min-h-0 gap-2">
                <SidePanel />
                <div className="flex-1 min-w-0 flex flex-col min-h-0 rounded-lg border border-slate-200 dark:border-slate-700 overflow-hidden p-1 bg-slate-50/50 dark:bg-slate-900/30">
                    <ProChart
                        symbol={symbol}
                        symbolName={symbolName}
                        symbolDisplayLabel={symbolDisplayLabel}
                        start={start}
                        end={end}
                        period={period}
                        adjust={adjust}
                        showMa={ma}
                        showBoll={showBoll}
                        subChart={subChart}
                        compareSymbols={CHART_COMPARE_ENABLED ? compareSymbols : EMPTY_COMPARE_SYMBOLS}
                        insightMarkers={insight?.markers}
                        insightLevels={insight?.levels}
                        isDark={isDark}
                        liveDailyEnabled={liveDailyEnabled}
                        hasRtEntitlement={hasRtEntitlement}
                        liveRefreshKey={liveRefreshKey}
                    />
                </div>
                <InsightPanel
                    insight={insight}
                    fallbackOnly={insightFallbackOnly}
                    loading={insightLoading}
                    error={insightErr}
                    awaitingStart={insightAwaitingStart}
                    onStart={() => {
                        setInsightAwaitingStart(false)
                        void runInsight(false)
                    }}
                    onRefresh={(b) => void runInsight(b)}
                    collapsed={!insightOpen}
                    onToggleCollapse={() => setInsightOpen(!insightOpen)}
                    creditsBalance={user?.credits ?? undefined}
                    includeAdvancedContext={canAdvancedMarketContext}
                    historyOptions={insightHistoryOptions}
                    selectedHistoryId={selectedInsightHistoryId}
                    onSelectHistory={applyInsightHistoryItem}
                />
            </div>

            {showTour && (
                <div className="fixed inset-0 z-[100] flex items-center justify-center bg-black/50 p-4">
                    <div className="max-w-md rounded-xl bg-white dark:bg-slate-800 p-4 shadow-xl text-sm">
                        <h3 className="font-semibold text-base mb-2">30 秒看懂 K 线分析</h3>
                        <ul className="list-disc pl-5 space-y-1 text-slate-600 dark:text-slate-300">
                            <li>红涨绿跌为中国 A 股常用配色。</li>
                            <li>蜡烛实体越长，当日多空博弈越激烈。</li>
                            <li>均线多头排列常被视为趋势向上（非投资建议）。</li>
                            <li>成交量配合价格上涨更值得关注。</li>
                            <li>点击「Ai助手」用白话文阅读技术面摘要。</li>
                        </ul>
                        <label className="flex items-center gap-2 mt-3 text-xs text-slate-500">
                            <input
                                type="checkbox"
                                checked={tourDismissForever}
                                onChange={(e) => setTourDismissForever(e.target.checked)}
                            />
                            不再显示
                        </label>
                        <div className="flex justify-end gap-2 mt-4">
                            <button
                                type="button"
                                className="px-3 py-1.5 rounded border border-slate-300 dark:border-slate-600"
                                onClick={() => dismissTour(false)}
                            >
                                关闭
                            </button>
                            <button
                                type="button"
                                className="px-3 py-1.5 rounded bg-blue-600 text-white"
                                onClick={() => dismissTour(tourDismissForever)}
                            >
                                知道了
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
