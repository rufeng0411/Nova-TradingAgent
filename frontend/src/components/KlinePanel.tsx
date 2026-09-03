import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import {
    BusinessDay,
    CandlestickData,
    CandlestickSeries,
    ColorType,
    HistogramSeries,
    IChartApi,
    ISeriesApi,
    LineSeries,
    MouseEventParams,
    HistogramData,
    LineData,
    createChart,
} from 'lightweight-charts'
import { Activity, CandlestickChart, Maximize2 } from 'lucide-react'
import { subMonths } from 'date-fns'
import { api } from '@/services/api'
import type { ChartRangePreset, KlineCandle } from '@/types'
import { useAnalysisStore } from '@/stores/analysisStore'
import { formatKlineCrosshairTime } from '@/lib/chartTime'
import { calcSma } from '@/lib/indicators'
import { useThemeStore } from '@/stores/themeStore'
import { useChartSkinPalette } from '@/hooks/useChartSkinPalette'
import { normalizeChartSymbol } from '@/lib/cnSymbol'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { EXCHANGE_LISTED_SYMBOL_RE, pickExchangeListedSymbol, stockDisplayLabel } from '@/utils/stockDisplay'
import { RealtimeQuoteBadge } from '@/components/RealtimeQuoteBadge'

interface KlinePanelProps {
    symbol: string
    onSymbolChange?: (symbol: string) => void
    onExpand?: (payload: { symbol: string; range: ChartRangePreset }) => void
}

function toDateText(date: Date): string {
    const y = date.getFullYear()
    const m = String(date.getMonth() + 1).padStart(2, '0')
    const d = String(date.getDate()).padStart(2, '0')
    return `${y}-${m}-${d}`
}

function toBusinessDay(value: string): BusinessDay | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value)
    if (!m) return null
    const year = Number(m[1])
    const month = Number(m[2])
    const day = Number(m[3])
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) return null
    return { year, month, day }
}

function formatNumber(value?: number | null, digits = 2): string {
    if (value == null || !Number.isFinite(value)) return '--'
    return new Intl.NumberFormat('zh-CN', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    }).format(value)
}

function formatVolume(value?: number | null): string {
    if (value == null || !Number.isFinite(value)) return '--'
    if (Math.abs(value) >= 1e8) return `${formatNumber(value / 1e8, 2)}亿`
    if (Math.abs(value) >= 1e4) return `${formatNumber(value / 1e4, 2)}万`
    return formatNumber(value, 0)
}

/** 图表 series 在 Strict Mode / 主题切换重建后可能晚于数据 effect；短暂等待避免永远不请求 */
async function waitForKlineSeriesRefs(
    refsReady: () => boolean,
    cancelled: () => boolean,
    maxMs = 12000,
): Promise<boolean> {
    const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now()
    while (!cancelled()) {
        if (refsReady()) return true
        if ((typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0 > maxMs) break
        await new Promise((r) => setTimeout(r, 32))
    }
    return refsReady()
}

const INDEX_PRESETS = [
    { symbol: '000001.SH', label: '上证指数' },
    { symbol: '399001.SZ', label: '深证成指' },
    { symbol: '399006.SZ', label: '创业板指' },
    { symbol: '000688.SH', label: '科创50' },
    { symbol: '899050.BJ', label: '北证50' },
] as const

const RANGE_TABS: { id: ChartRangePreset; label: string; months: number }[] = [
    { id: '1M', label: '1M', months: 1 },
    { id: '3M', label: '3M', months: 3 },
    { id: '6M', label: '6M', months: 6 },
]

export default function KlinePanel({ symbol, onSymbolChange, onExpand }: KlinePanelProps) {
    const navigate = useNavigate()
    const currentAnalysisSymbol = useAnalysisStore((state) => state.currentSymbol)
    const currentSymbolDisplayName = useAnalysisStore((state) => state.currentSymbolDisplayName)
    const report = useAnalysisStore((state) => state.report)
    const [panelSymbolName, setPanelSymbolName] = useState<string | null>(null)
    const [klineDisplayLabel, setKlineDisplayLabel] = useState<string | null>(null)
    const mainRef = useRef<HTMLDivElement | null>(null)
    const volRef = useRef<HTMLDivElement | null>(null)
    const chartMain = useRef<IChartApi | null>(null)
    const chartVol = useRef<IChartApi | null>(null)
    const seriesRef = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const ma5Ref = useRef<ISeriesApi<'Line'> | null>(null)
    const ma20Ref = useRef<ISeriesApi<'Line'> | null>(null)
    const volSeriesRef = useRef<ISeriesApi<'Histogram'> | null>(null)
    const syncing = useRef(false)

    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [isDark, setIsDark] = useState(document.documentElement.classList.contains('dark'))
    const skin = useThemeStore((s) => s.skin)
    const chartPalette = useChartSkinPalette(isDark)
    const [candles, setCandles] = useState<KlineCandle[]>([])
    const [activeCandle, setActiveCandle] = useState<KlineCandle | null>(null)
    const candlesRef = useRef<KlineCandle[]>([])
    const [rangeTab, setRangeTab] = useState<ChartRangePreset>('6M')
    const [showMa5, setShowMa5] = useState(true)
    const [showMa20, setShowMa20] = useState(true)

    const apiSymbol = useMemo(
        () => pickExchangeListedSymbol(symbol, report?.symbol ?? null),
        [symbol, report?.symbol],
    )

    useEffect(() => {
        const raw = symbol.trim()
        const resolved = pickExchangeListedSymbol(raw, report?.symbol ?? null)
        if (!EXCHANGE_LISTED_SYMBOL_RE.test(resolved)) return
        if (resolved.toUpperCase() === raw.toUpperCase()) return
        onSymbolChange?.(resolved)
    }, [symbol, report?.symbol, onSymbolChange])

    const range = useMemo(() => {
        const end = new Date()
        const tab = RANGE_TABS.find((t) => t.id === rangeTab)
        const months = tab?.months ?? 6
        const start = subMonths(end, months)
        return {
            start: toDateText(start),
            end: toDateText(end),
        }
    }, [rangeTab])

    useEffect(() => {
        const observer = new MutationObserver(() => {
            setIsDark(document.documentElement.classList.contains('dark'))
        })
        observer.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] })
        return () => observer.disconnect()
    }, [])

    useEffect(() => {
        let cancelled = false
        const sym = normalizeChartSymbol(apiSymbol) || apiSymbol.trim().toUpperCase()
        void fetchAshareDisplayName(sym)
            .then((name) => {
                if (!cancelled) setPanelSymbolName(name)
            })
            .catch(() => {
                if (!cancelled) setPanelSymbolName(null)
            })
        return () => {
            cancelled = true
        }
    }, [apiSymbol])

    useEffect(() => {
        if (!mainRef.current || !volRef.current) return

        const textColor = chartPalette.textColor
        const gridColor = chartPalette.gridColor
        const borderColor = chartPalette.borderColor
        const w = mainRef.current.clientWidth
        const hMain = Math.max(160, mainRef.current.clientHeight || 220)
        const hVol = Math.max(48, volRef.current.clientHeight || 56)

        const layout = {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor,
                attributionLogo: false,
            },
            localization: {
                locale: 'zh-CN',
                dateFormat: 'yyyy-MM-dd',
                timeFormatter: formatKlineCrosshairTime,
            },
            grid: {
                vertLines: { color: gridColor },
                horzLines: { color: gridColor },
            },
            crosshair: {
                vertLine: { color: chartPalette.crosshairVert },
                horzLine: { color: chartPalette.crosshairHorz },
            },
        }

        const main = createChart(mainRef.current, {
            ...layout,
            width: w,
            height: hMain,
            handleScroll: true,
            handleScale: true,
            rightPriceScale: { borderColor },
            timeScale: {
                borderColor,
                timeVisible: false,
                rightOffset: 6,
                visible: false,
                tickMarkFormatter: (time: BusinessDay | string) => {
                    if (typeof time !== 'object') return String(time)
                    const y = String(time.year)
                    const mo = String(time.month).padStart(2, '0')
                    const d = String(time.day).padStart(2, '0')
                    return `${y}/${mo}/${d}`
                },
            },
        })

        const volChart = createChart(volRef.current, {
            ...layout,
            width: w,
            height: hVol,
            handleScroll: false,
            handleScale: false,
            rightPriceScale: { borderColor },
            timeScale: { borderColor, visible: true, timeVisible: false, rightOffset: 6 },
        })

        chartMain.current = main
        chartVol.current = volChart

        const series = main.addSeries(CandlestickSeries, {
            upColor: '#ef4444',
            downColor: '#22c55e',
            wickUpColor: '#ef4444',
            wickDownColor: '#22c55e',
            borderVisible: false,
        })
        seriesRef.current = series

        ma5Ref.current = main.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'MA5' })
        ma20Ref.current = main.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'MA20' })

        const volS = volChart.addSeries(HistogramSeries, {
            priceFormat: { type: 'volume' },
            priceScaleId: 'right',
        })
        volSeriesRef.current = volS

        const onMainRange = () => {
            if (syncing.current) return
            const r = main.timeScale().getVisibleLogicalRange()
            if (!r) return
            syncing.current = true
            volChart.timeScale().setVisibleLogicalRange(r)
            syncing.current = false
        }
        main.timeScale().subscribeVisibleLogicalRangeChange(onMainRange)

        const handleCrosshairMove = (param: MouseEventParams) => {
            if (!param.time || !seriesRef.current) {
                setActiveCandle(candlesRef.current.length ? candlesRef.current[candlesRef.current.length - 1] : null)
                return
            }
            const pointData = param.seriesData.get(seriesRef.current) as CandlestickData | undefined
            if (!pointData) return
            const timestr =
                typeof pointData.time === 'object'
                    ? `${pointData.time.year}-${String(pointData.time.month).padStart(2, '0')}-${String(pointData.time.day).padStart(2, '0')}`
                    : String(pointData.time)
            const matched = candlesRef.current.find((c) => c.date.startsWith(timestr))
            if (matched) setActiveCandle(matched)
        }
        main.subscribeCrosshairMove(handleCrosshairMove)

        const handleDblClick = () => {
            chartMain.current?.timeScale().fitContent()
            chartVol.current?.timeScale().fitContent()
        }
        mainRef.current.addEventListener('dblclick', handleDblClick)

        const onResize = () => {
            if (!mainRef.current || !volRef.current) return
            const width = mainRef.current.clientWidth
            main.applyOptions({ width, height: mainRef.current.clientHeight })
            volChart.applyOptions({ width, height: volRef.current.clientHeight })
        }
        window.addEventListener('resize', onResize)

        if (candlesRef.current.length) {
            /* populated by data effect */
        }

        return () => {
            window.removeEventListener('resize', onResize)
            mainRef.current?.removeEventListener('dblclick', handleDblClick)
            main.timeScale().unsubscribeVisibleLogicalRangeChange(onMainRange)
            main.unsubscribeCrosshairMove(handleCrosshairMove)
            main.remove()
            volChart.remove()
            chartMain.current = null
            chartVol.current = null
            seriesRef.current = null
            ma5Ref.current = null
            ma20Ref.current = null
            volSeriesRef.current = null
        }
    }, [chartPalette, isDark, skin])

    useEffect(() => {
        let cancelled = false
        const ac = new AbortController()

        const load = async () => {
            setLoading(true)
            setError(null)
            setKlineDisplayLabel(null)
            if (!EXCHANGE_LISTED_SYMBOL_RE.test(apiSymbol)) {
                setCandles([])
                candlesRef.current = []
                setActiveCandle(null)
                seriesRef.current?.setData([])
                volSeriesRef.current?.setData([])
                ma5Ref.current?.setData([])
                ma20Ref.current?.setData([])
                setError('无法识别交易所代码，暂无K线数据')
                setLoading(false)
                return
            }
            try {
                const resp = await api.getKline(apiSymbol, range.start, range.end, { signal: ac.signal })
                if (cancelled) return
                const refsOk = () =>
                    !!(seriesRef.current && volSeriesRef.current && ma5Ref.current && ma20Ref.current)
                const ok = await waitForKlineSeriesRefs(refsOk, () => cancelled)
                if (!ok || cancelled) {
                    if (!cancelled) {
                        setError('图表初始化超时，K 线数据已获取，请刷新页面重试')
                    }
                    return
                }
                setKlineDisplayLabel(resp.display_label?.trim() || null)
                const data: CandlestickData[] = resp.candles.flatMap((c) => {
                    const time = toBusinessDay((c.date || '').slice(0, 10))
                    const open = Number(c.open)
                    const high = Number(c.high)
                    const low = Number(c.low)
                    const close = Number(c.close)
                    if (!time) return []
                    if (![open, high, low, close].every(Number.isFinite)) return []
                    return [{ time, open, high, low, close }]
                })

                setCandles(resp.candles)
                candlesRef.current = resp.candles
                setActiveCandle(resp.candles.length ? resp.candles[resp.candles.length - 1] : null)
                seriesRef.current?.setData(data)

                const dates = resp.candles.map((c) => c.date.slice(0, 10))
                const closes = resp.candles.map((c) => Number(c.close)).filter(Number.isFinite)
                const s5 = calcSma(closes, 5)
                const s20 = calcSma(closes, 20)
                const lineFrom = (values: (number | null)[]): LineData<BusinessDay>[] => {
                    const out: LineData<BusinessDay>[] = []
                    for (let i = 0; i < values.length; i++) {
                        const val = values[i]
                        const t = toBusinessDay(dates[i])
                        if (val == null || !t || !Number.isFinite(val)) continue
                        out.push({ time: t, value: val })
                    }
                    return out
                }
                ma5Ref.current?.setData(showMa5 ? lineFrom(s5) : [])
                ma20Ref.current?.setData(showMa20 ? lineFrom(s20) : [])

                const hist: HistogramData<BusinessDay>[] = []
                for (const c of resp.candles) {
                    const t = toBusinessDay(c.date.slice(0, 10))
                    if (!t) continue
                    const vol = Number(c.volume ?? 0)
                    const up = Number(c.close) >= Number(c.open)
                    hist.push({
                        time: t,
                        value: vol,
                        color: up ? 'rgba(239,68,68,0.55)' : 'rgba(34,197,94,0.55)',
                    })
                }
                volSeriesRef.current?.setData(hist)

                chartMain.current?.timeScale().fitContent()
                chartVol.current?.timeScale().fitContent()
                if (!data.length) {
                    setError('暂无可用K线数据')
                }
            } catch (e) {
                if (cancelled) return
                if (e instanceof DOMException && e.name === 'AbortError') return
                setKlineDisplayLabel(null)
                setError(e instanceof Error ? e.message : '加载K线失败')
                setCandles([])
                candlesRef.current = []
                setActiveCandle(null)
                seriesRef.current?.setData([])
                volSeriesRef.current?.setData([])
                ma5Ref.current?.setData([])
                ma20Ref.current?.setData([])
            } finally {
                setLoading(false)
            }
        }

        load()
        return () => {
            cancelled = true
            ac.abort()
            setLoading(false)
        }
    }, [range.end, range.start, apiSymbol, showMa20, showMa5])

    useEffect(() => {
        if (!ma5Ref.current || !ma20Ref.current || !candles.length) return
        const dates = candles.map((c) => c.date.slice(0, 10))
        const closes = candles.map((c) => Number(c.close)).filter(Number.isFinite)
        const s5 = calcSma(closes, 5)
        const s20 = calcSma(closes, 20)
        const lineFrom = (values: (number | null)[]): LineData<BusinessDay>[] => {
            const out: LineData<BusinessDay>[] = []
            for (let i = 0; i < values.length; i++) {
                const val = values[i]
                const t = toBusinessDay(dates[i])
                if (val == null || !t || !Number.isFinite(val)) continue
                out.push({ time: t, value: val })
            }
            return out
        }
        ma5Ref.current.setData(showMa5 ? lineFrom(s5) : [])
        ma20Ref.current.setData(showMa20 ? lineFrom(s20) : [])
    }, [showMa5, showMa20, candles])

    const panelCandle = activeCandle ?? (candles.length ? candles[candles.length - 1] : null)
    const panelChange = panelCandle?.change ?? (panelCandle ? panelCandle.close - panelCandle.open : null)
    const panelChangePercent =
        panelCandle?.change_percent ??
        (panelCandle && panelCandle.open !== 0 ? ((panelChange ?? 0) / panelCandle.open) * 100 : null)
    const isUp = (panelChange ?? 0) >= 0
    const compactChangePercent =
        panelChangePercent == null ? '--' : `${panelChangePercent >= 0 ? '+' : ''}${formatNumber(panelChangePercent)}%`
    const showCurrentSymbolButton = !!currentAnalysisSymbol && currentAnalysisSymbol !== apiSymbol
    const symbolUpper = apiSymbol.trim().toUpperCase()
    const analysisSymUpper = pickExchangeListedSymbol(
        currentAnalysisSymbol?.trim() ?? '',
        report?.symbol ?? null,
    ).toUpperCase()
    const analysisAlignedName =
        analysisSymUpper === symbolUpper
            ? (currentSymbolDisplayName ?? report?.instrument_context?.security_name ?? null)
            : null
    const titleName = panelSymbolName ?? analysisAlignedName
    const klineTitle = stockDisplayLabel({
        symbol: apiSymbol,
        name: titleName ?? undefined,
        display_label: klineDisplayLabel,
    })
    const currentSymbolLabel = currentAnalysisSymbol
        ? stockDisplayLabel({
              symbol: pickExchangeListedSymbol(currentAnalysisSymbol, report?.symbol ?? null),
              name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
              display_label: report?.instrument_context?.display_label,
          })
        : '当前标的'

    const goPro = () => {
        const payload = { symbol: apiSymbol.toUpperCase(), range: rangeTab }
        if (onExpand) onExpand(payload)
        else {
            const q = new URLSearchParams({
                symbol: payload.symbol,
                range: payload.range,
                period: '1d',
                adjust: 'none',
            })
            navigate(`/chart?${q.toString()}`)
        }
    }

    return (
        <section className="card h-full flex flex-col overflow-hidden" data-tone="kline">
            <div className="flex flex-col gap-2 mb-2 shrink-0">
                <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex items-center gap-2">
                        <CandlestickChart className="w-6 h-6 text-cyan-500 shrink-0" />
                        <div className="min-w-0">
                            <div className="flex min-w-0 flex-wrap items-center gap-1.5">
                                <h2
                                    className="truncate text-base font-semibold text-slate-900 dark:text-slate-100 leading-tight"
                                    title={klineTitle}
                                >
                                    {klineTitle}
                                </h2>
                                <RealtimeQuoteBadge symbol={apiSymbol} compact />
                            </div>
                            <div className="flex flex-wrap items-baseline gap-x-3 gap-y-0.5 mt-0.5">
                                <span className={`text-lg font-bold ${isUp ? 'text-red-500' : 'text-emerald-500'}`}>
                                    {formatNumber(panelCandle?.close)}
                                </span>
                                <span className={`text-sm font-medium ${isUp ? 'text-red-400' : 'text-emerald-400'}`}>
                                    {compactChangePercent}
                                </span>
                                <span className="text-[11px] text-slate-500 dark:text-slate-400">
                                    {panelCandle?.date?.slice(0, 10) || '--'}
                                </span>
                            </div>
                        </div>
                    </div>
                    <button
                        type="button"
                        onClick={goPro}
                        title="K线分析"
                        className="shrink-0 p-2 rounded-lg border border-cyan-500/40 text-cyan-600 dark:text-cyan-400 hover:bg-cyan-500/10"
                    >
                        <Maximize2 className="w-5 h-5" />
                    </button>
                </div>

                <div className="flex flex-wrap items-center gap-2 justify-between">
                    <div className="flex items-center gap-1 flex-wrap">
                        {RANGE_TABS.map((t) => (
                            <button
                                type="button"
                                key={t.id}
                                onClick={() => setRangeTab(t.id)}
                                className={`text-xs px-2 py-0.5 rounded border ${
                                    rangeTab === t.id
                                        ? 'border-blue-500 text-blue-600 bg-blue-50 dark:bg-blue-500/15 dark:text-blue-400'
                                        : 'border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400'
                                }`}
                            >
                                {t.label}
                            </button>
                        ))}
                        <label className="flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-400 ml-1">
                            <input type="checkbox" checked={showMa5} onChange={() => setShowMa5(!showMa5)} />
                            MA5
                        </label>
                        <label className="flex items-center gap-1 text-[11px] text-slate-600 dark:text-slate-400">
                            <input type="checkbox" checked={showMa20} onChange={() => setShowMa20(!showMa20)} />
                            MA20
                        </label>
                    </div>
                    <div className="flex flex-shrink-0 items-center gap-1 overflow-x-auto">
                        {showCurrentSymbolButton && (
                            <button
                                type="button"
                                onClick={() =>
                                    onSymbolChange?.(
                                        pickExchangeListedSymbol(
                                            currentAnalysisSymbol ?? '',
                                            report?.symbol ?? null,
                                        ),
                                    )
                                }
                                className="shrink-0 whitespace-nowrap text-xs px-2 py-1 rounded border border-emerald-500 text-emerald-600 dark:text-emerald-400 bg-emerald-50 dark:bg-emerald-500/10"
                            >
                                {currentSymbolLabel}
                            </button>
                        )}
                        {INDEX_PRESETS.map((item) => (
                            <button
                                type="button"
                                key={item.symbol}
                                onClick={() => onSymbolChange?.(item.symbol)}
                                className={`shrink-0 whitespace-nowrap text-xs px-2 py-1 rounded border transition-colors ${
                                    item.symbol === apiSymbol
                                        ? 'border-blue-500 text-blue-500 bg-blue-50 dark:bg-blue-500/10'
                                        : 'border-slate-200 dark:border-slate-600 text-slate-600 dark:text-slate-400'
                                }`}
                            >
                                {item.label}
                            </button>
                        ))}
                    </div>
                </div>

                <div className="text-[11px] text-slate-500 dark:text-slate-400 bg-slate-100/80 dark:bg-slate-800/50 rounded px-2 py-1">
                    O {formatNumber(panelCandle?.open)} · H {formatNumber(panelCandle?.high)} · L{' '}
                    {formatNumber(panelCandle?.low)} · 量 {formatVolume(panelCandle?.volume)} · 换手{' '}
                    {panelCandle?.turnover_rate == null ? '--' : `${formatNumber(panelCandle.turnover_rate)}%`}
                </div>
            </div>

            <div className="relative flex-1 min-h-0 flex flex-col rounded-md border border-slate-200 dark:border-slate-700 bg-slate-50 dark:bg-slate-900/50 overflow-hidden">
                <div ref={mainRef} className="flex-1 min-h-[160px] relative" />
                <div ref={volRef} className="h-14 shrink-0 border-t border-slate-200 dark:border-slate-700 relative" />
                {loading && (
                    <div className="absolute right-3 top-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-slate-600 dark:text-slate-400 flex items-center gap-1 z-10">
                        <Activity className="w-3 h-3 animate-pulse" />
                        加载中
                    </div>
                )}
                {error && (
                    <div className="absolute left-3 top-3 text-xs px-2 py-1 rounded bg-white/90 dark:bg-slate-800/90 text-orange-500 z-10">
                        {error}
                    </div>
                )}
            </div>
        </section>
    )
}
