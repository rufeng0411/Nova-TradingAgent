import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { Settings, Sparkles } from 'lucide-react'
import ProChart from '@/components/chart/ProChart'
import InsightPanel from '@/components/chart/InsightPanel'
import BottomSheetDrawer from '@/components/mobile/BottomSheetDrawer'
import { EMPTY_COMPARE_SYMBOLS, useChartStore } from '@/stores/chartStore'
import { useAuthStore } from '@/stores/authStore'
import { rangePresetToDates } from '@/lib/chartRange'
import { normalizeChartSymbol } from '@/lib/cnSymbol'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { cnShanghaiDateText, isCnAshareRegularSession } from '@/lib/cnMarketHours'
import { api } from '@/services/api'
import { useQuoteStore } from '@/stores/quoteStore'
import type { ChartInsightResult, KlineAdjust, KlinePeriod, SubChartType } from '@/types'
import { resolveExchangeListedSymbol, stockDisplayLabel } from '@/utils/stockDisplay'
import {
    getChartInsightHistoryItem,
    loadChartInsightHistory,
    pushChartInsightHistory,
} from '@/lib/chartInsightHistory'

const PERIODS: { id: KlinePeriod; label: string }[] = [
    { id: '1d', label: '日K' },
    { id: '1w', label: '周K' },
    { id: '1mo', label: '月K' },
]

const ADJUST: { id: KlineAdjust; label: string }[] = [
    { id: 'none', label: '不复权' },
    { id: 'qfq', label: '前复权' },
    { id: 'hfq', label: '后复权' },
]

export default function MobileChartPro() {
    const [searchParams, setSearchParams] = useSearchParams()
    const [isDark, setIsDark] = useState(() => document.documentElement.classList.contains('dark'))
    const [liveRefreshKey, setLiveRefreshKey] = useState(0)

    const [settingsDrawer, setSettingsDrawer] = useState(false)
    const [insightDrawer, setInsightDrawer] = useState(false)

    const [insight, setInsight] = useState<ChartInsightResult | null>(null)
    const [insightLoading, setInsightLoading] = useState(false)
    const [insightErr, setInsightErr] = useState<string | null>(null)
    const [insightFallbackOnly, setInsightFallbackOnly] = useState(false)
    const [insightAwaitingStart, setInsightAwaitingStart] = useState(true)
    const [insightHistoryVersion, setInsightHistoryVersion] = useState(0)
    const [selectedInsightHistoryId, setSelectedInsightHistoryId] = useState<string | null>(null)
    const lastInsightUrlParam = useRef<string | null>(null)

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
        setMa,
        showBoll,
        setShowBoll,
        subChart,
        setSubChart,
        liveDailyEnabled,
        setLiveDailyEnabled,
    } = useChartStore()

    const user = useAuthStore((s) => s.user)
    const canAdvancedMarketContext = user?.role === 'admin' || user?.entitlements?.advanced_market === true
    const hasRtEntitlement = user?.role === 'admin' || user?.entitlements?.tushare_rt === true
    const liveDailyActive = liveDailyEnabled && hasRtEntitlement && period === '1d'
    const normalizedSymbol = resolveExchangeListedSymbol(symbol || '').trim().toUpperCase()
    const liveQuote = useQuoteStore((s) => (normalizedSymbol ? s.quotes[normalizedSymbol] : undefined))

    useEffect(() => {
        const obs = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'))
        })
        obs.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => obs.disconnect()
    }, [])

    useEffect(() => {
        const sym = searchParams.get('symbol')
        if (sym?.trim()) {
            const norm = normalizeChartSymbol(sym)
            setSymbol(norm || sym.trim().toUpperCase())
        }
    }, [searchParams, setSymbol])

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
        applyInsightHistoryItem(item.id)
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
    }, [applyInsightHistoryItem, searchParams, setSearchParams])

    useEffect(() => {
        let cancelled = false
        const sym = normalizeChartSymbol(symbol) || symbol.trim().toUpperCase()
        void fetchAshareDisplayName(sym).then((name) => {
            if (cancelled || !name) return
            const cur = useChartStore.getState().symbol
            if ((normalizeChartSymbol(cur) || cur.trim().toUpperCase()) === sym) {
                setSymbol(sym, { name })
            }
        })
        return () => { cancelled = true }
    }, [symbol, setSymbol])

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

    const runInsight = async (bypassCache: boolean) => {
        setInsightLoading(true)
        setInsightErr(null)
        try {
            const res = await api.chartInsight({
                symbol,
                period,
                adjust,
                start_date: start,
                end_date: end,
                level: 'deep',
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
    }

    const handleOpenInsight = () => {
        setInsightDrawer(true)
        if (insightAwaitingStart) {
            setInsightAwaitingStart(false)
            runInsight(false)
        }
    }

    return (
        <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-950">
            {/* Header info inside layout */}
            <div className="px-4 py-2 border-b border-slate-200 dark:border-slate-800 flex justify-between items-center bg-white dark:bg-slate-900">
                <div className="font-bold text-lg text-slate-900 dark:text-slate-100 truncate">
                    {stockDisplayLabel({ symbol, name: symbolName, display_label: symbolDisplayLabel })}
                </div>
                <div className="flex gap-2">
                    <button
                        type="button"
                        onClick={() => setLiveDailyEnabled(!liveDailyEnabled)}
                        disabled={!hasRtEntitlement || period !== '1d'}
                        title={
                            !hasRtEntitlement
                                ? '需开通 Tushare A股日线RT 权益'
                                : period !== '1d'
                                    ? '仅日K支持实时模式'
                                    : liveDailyEnabled
                                        ? '实时模式已开启'
                                        : '开启实时模式'
                        }
                        className={`flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-full border active:scale-95 ${
                            !hasRtEntitlement || period !== '1d'
                                ? 'border-slate-300 text-slate-400 dark:border-slate-700 dark:text-slate-500'
                                : liveDailyEnabled
                                    ? 'bg-gradient-to-r from-cyan-500/10 to-blue-500/10 text-cyan-700 dark:text-cyan-400 border-cyan-500/20'
                                    : 'border-slate-300 text-slate-600 dark:border-slate-600 dark:text-slate-300'
                        }`}
                    >
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${liveDailyEnabled ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400/70'}`} />
                        实时
                    </button>
                    <button 
                        onClick={handleOpenInsight}
                        className="flex items-center gap-1 text-xs px-2.5 py-1.5 rounded-full bg-gradient-to-r from-cyan-500/10 to-blue-500/10 text-cyan-700 dark:text-cyan-400 border border-cyan-500/20 active:scale-95"
                    >
                        <Sparkles className="w-3.5 h-3.5" />
                        Ai 洞察
                    </button>
                </div>
            </div>
            {liveDailyEnabled && hasRtEntitlement ? (
                <div className="px-4 py-1 text-[11px] text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900">
                    {liveQuote?.source === 'tushare_rt'
                        ? `● LIVE ${liveQuote.quote_time || ''}`.trim()
                        : '实时待机'}
                </div>
            ) : null}

            {/* Chart Area */}
            <div className="flex-1 min-h-[50vh] relative -mx-2 px-2 pb-14 overflow-hidden">
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
                    compareSymbols={EMPTY_COMPARE_SYMBOLS}
                    insightMarkers={insight?.markers}
                    insightLevels={insight?.levels}
                    isDark={isDark}
                    liveDailyEnabled={liveDailyEnabled}
                    hasRtEntitlement={hasRtEntitlement}
                    liveRefreshKey={liveRefreshKey}
                />
                
                {/* Floating Toolbar inside chart area at the bottom */}
                <div className="absolute bottom-2 left-2 right-2 bg-white/90 dark:bg-slate-900/90 backdrop-blur-md border border-slate-200 dark:border-slate-700 rounded-xl p-1.5 flex items-center justify-between shadow-lg">
                    <div className="flex overflow-x-auto hide-scrollbar gap-1 px-1 flex-1">
                        {PERIODS.map(p => (
                            <button
                                key={p.id}
                                onClick={() => setPeriod(p.id)}
                                className={`whitespace-nowrap px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
                                    period === p.id 
                                        ? 'bg-blue-100 dark:bg-blue-900/40 text-blue-700 dark:text-blue-400' 
                                        : 'text-slate-600 dark:text-slate-400'
                                }`}
                            >
                                {p.label}
                            </button>
                        ))}
                        <div className="w-px h-4 bg-slate-300 dark:bg-slate-700 my-auto mx-1 shrink-0" />
                        <select 
                            value={subChart} 
                            onChange={e => setSubChart(e.target.value as SubChartType)}
                            aria-label="副图指标"
                            className="bg-transparent text-xs font-medium text-slate-600 dark:text-slate-400 outline-none px-2"
                        >
                            <option value="macd">MACD</option>
                            <option value="kdj">KDJ</option>
                            <option value="rsi">RSI</option>
                            <option value="atr">ATR</option>
                            <option value="obv">OBV</option>
                            <option value="moneyflow">资金流</option>
                            <option value="hsgt_flow">北向资金</option>
                            <option value="chip_distribution">筹码分布</option>
                            <option value="none">无副图</option>
                        </select>
                    </div>
                    
                    <button 
                        onClick={() => setSettingsDrawer(true)}
                        aria-label="打开图表设置"
                        className="p-1.5 ml-1 shrink-0 text-slate-500 rounded-full hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                        <Settings className="w-4 h-4" />
                    </button>
                </div>
            </div>

            {/* Settings Drawer */}
            <BottomSheetDrawer 
                isOpen={settingsDrawer} 
                onClose={() => setSettingsDrawer(false)}
                title="图表设置"
                heightClass="h-[60vh]"
            >
                <div className="space-y-6">
                    <div>
                        <h4 className="text-sm font-semibold mb-3 text-slate-900 dark:text-slate-100">复权类型</h4>
                        <div className="flex gap-2">
                            {ADJUST.map(a => (
                                <button
                                    key={a.id}
                                    onClick={() => setAdjust(a.id)}
                                    className={`flex-1 py-2 rounded-xl text-sm border transition-colors ${
                                        adjust === a.id 
                                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400' 
                                            : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400'
                                    }`}
                                >
                                    {a.label}
                                </button>
                            ))}
                        </div>
                    </div>

                    <div>
                        <h4 className="text-sm font-semibold mb-3 text-slate-900 dark:text-slate-100">主图指标 (多选)</h4>
                        <div className="grid grid-cols-3 gap-2">
                            {(['ma5', 'ma10', 'ma20', 'ma60'] as const).map(k => (
                                <button
                                    key={k}
                                    onClick={() => setMa({ [k]: !ma[k] })}
                                    className={`py-2 rounded-xl text-sm border transition-colors ${
                                        ma[k] 
                                            ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400' 
                                            : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400'
                                    }`}
                                >
                                    {k.toUpperCase()}
                                </button>
                            ))}
                            <button
                                onClick={() => setShowBoll(!showBoll)}
                                className={`py-2 rounded-xl text-sm border transition-colors ${
                                    showBoll 
                                        ? 'border-blue-500 bg-blue-50 dark:bg-blue-900/20 text-blue-700 dark:text-blue-400' 
                                        : 'border-slate-200 dark:border-slate-800 text-slate-600 dark:text-slate-400'
                                }`}
                            >
                                BOLL
                            </button>
                        </div>
                    </div>
                </div>
            </BottomSheetDrawer>

            {/* Insight Drawer */}
            <BottomSheetDrawer 
                isOpen={insightDrawer} 
                onClose={() => setInsightDrawer(false)}
                title="Ai 盘面解读"
                heightClass="h-[85vh]"
            >
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
                    collapsed={false}
                    onToggleCollapse={() => {}}
                    creditsBalance={user?.credits ?? undefined}
                    includeAdvancedContext={canAdvancedMarketContext}
                    mobileMode={true}
                    historyOptions={insightHistoryOptions}
                    selectedHistoryId={selectedInsightHistoryId}
                    onSelectHistory={applyInsightHistoryItem}
                />
            </BottomSheetDrawer>
        </div>
    )
}
