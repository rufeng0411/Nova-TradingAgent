import { useEffect, useRef, useCallback, useMemo, useState } from 'react'
import {
    CandlestickSeries,
    ColorType,
    LineSeries,
    HistogramSeries,
    createChart,
    createSeriesMarkers,
} from 'lightweight-charts'
import type {
    BusinessDay,
    CandlestickData,
    HistogramData,
    IChartApi,
    ISeriesApi,
    LineData,
    SeriesMarker,
} from 'lightweight-charts'
import { api } from '@/services/api'
import type {
    ChartInsightMarker,
    KlineAdjust,
    KlineCandle,
    KlinePeriod,
    SubChartType,
} from '@/types'
import {
    calcBoll,
    calcMacd,
    calcKdj,
    calcObv,
    calcRsi,
    calcSma,
    calcAtr,
    calcAmplitudePct,
    calcVolumeRatio,
    detectMacdState,
    detectKdjState,
    detectRsiState,
    detectMaState,
} from '@/lib/indicators'
import { formatKlineCrosshairTime, parseDateToBD } from '@/lib/chartTime'
import { normalizeCnAshareSymbol } from '@/lib/cnSymbol'
import { useThemeStore } from '@/stores/themeStore'
import { useChartSkinPalette } from '@/hooks/useChartSkinPalette'
import { useChartStore } from '@/stores/chartStore'
import { useQuoteStore } from '@/stores/quoteStore'
import { stockDisplayLabel } from '@/utils/stockDisplay'
import { RealtimeQuoteBadge } from '@/components/RealtimeQuoteBadge'
import AdvancedMarketPanel from '@/components/chart/AdvancedMarketPanel'
import { cnShanghaiDateText, isCnAshareRegularSession } from '@/lib/cnMarketHours'

function toCandleData(c: KlineCandle): CandlestickData<BusinessDay> | null {
    const time = parseDateToBD(c.date)
    if (!time) return null
    const o = Number(c.open)
    const h = Number(c.high)
    const l = Number(c.low)
    const cl = Number(c.close)
    if (![o, h, l, cl].every(Number.isFinite)) return null
    return { time, open: o, high: h, low: l, close: cl }
}

function closeArr(candles: KlineCandle[]): number[] {
    return candles.map((c) => Number(c.close)).filter(Number.isFinite)
}

function highArr(candles: KlineCandle[]): number[] {
    return candles.map((c) => Number(c.high)).filter(Number.isFinite)
}

function lowArr(candles: KlineCandle[]): number[] {
    return candles.map((c) => Number(c.low)).filter(Number.isFinite)
}

function volArr(candles: KlineCandle[]): number[] {
    return candles.map((c) => Number(c.volume ?? 0))
}

type SignalTone = 'bullish' | 'bearish' | 'neutral'

function SignalChip({ text, tone, title }: { text: string; tone: SignalTone; title?: string }) {
    const cls =
        tone === 'bullish'
            ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-500/40 dark:bg-red-900/25 dark:text-red-300'
            : tone === 'bearish'
              ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-500/40 dark:bg-emerald-900/25 dark:text-emerald-300'
              : 'border-slate-300 bg-slate-50 text-slate-600 dark:border-slate-600 dark:bg-slate-800/60 dark:text-slate-300'
    return (
        <span
            className={`inline-flex items-center gap-1 rounded-md border px-1.5 py-0.5 text-[10px] font-medium tabular-nums ${cls}`}
            title={title || text}
        >
            <span
                className={`inline-block h-1 w-1 rounded-full ${
                    tone === 'bullish' ? 'bg-red-500' : tone === 'bearish' ? 'bg-emerald-500' : 'bg-slate-400'
                }`}
            />
            {text}
        </span>
    )
}

function fmtNum(v: number | null | undefined, digits = 2): string {
    if (v == null || !Number.isFinite(v)) return '--'
    return Number(v).toLocaleString('zh-CN', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

function fmtCompact(v: number | null | undefined): string {
    if (v == null || !Number.isFinite(v)) return '--'
    const n = Math.abs(v)
    if (n >= 1e8) return `${(v / 1e8).toFixed(2)}亿`
    if (n >= 1e4) return `${(v / 1e4).toFixed(2)}万`
    return Number(v).toLocaleString('zh-CN', { maximumFractionDigits: 0 })
}

function asNumber(v: unknown): number | null {
    const n = Number(v)
    return Number.isFinite(n) ? n : null
}

/** K 线实例就绪前 refs 可能仍为 null（Strict Mode / 主题切换重建图表）；短暂等待避免永远不请求数据 */
async function waitForChartRefs(
    refsReady: () => boolean,
    cancelled: () => boolean,
    maxMs = 12000,
): Promise<boolean> {
    const t0 = typeof performance !== 'undefined' ? performance.now() : Date.now()
    while (!cancelled()) {
        if (refsReady()) return true
        if ((typeof performance !== 'undefined' ? performance.now() : Date.now()) - t0 > maxMs) break
        await new Promise((r) => setTimeout(r, 24))
    }
    return refsReady()
}

export interface ProChartProps {
    symbol: string
    /** 中文简称，与 symbol 组成「名称（代码）」展示在图区上方 */
    symbolName: string | null
    /** 后端权威展示标签，优先于 symbolName + symbol 的本地拼接 */
    symbolDisplayLabel: string | null
    start: string
    end: string
    period: KlinePeriod
    adjust: KlineAdjust
    showMa: { ma5: boolean; ma10: boolean; ma20: boolean; ma60: boolean }
    showBoll: boolean
    subChart: SubChartType
    compareSymbols: string[]
    insightMarkers?: ChartInsightMarker[]
    insightLevels?: { supports: number[]; resistances: number[] }
    isDark: boolean
    liveDailyEnabled?: boolean
    hasRtEntitlement?: boolean
    /** 交易时段内父组件递增以触发重新拉取日 K（当日数据更新） */
    liveRefreshKey?: number
}

const MA_COLORS = {
    ma5: '#f59e0b',
    ma10: '#a855f7',
    ma20: '#3b82f6',
    ma60: '#64748b',
} as const

export default function ProChart({
    symbol,
    symbolName,
    symbolDisplayLabel,
    start,
    end,
    period,
    adjust,
    showMa,
    showBoll,
    subChart,
    compareSymbols,
    insightMarkers,
    insightLevels,
    isDark,
    liveDailyEnabled = false,
    hasRtEntitlement = false,
    liveRefreshKey = 0,
}: ProChartProps) {
    const skin = useThemeStore((s) => s.skin)
    const chartPalette = useChartSkinPalette(isDark)
    const chartSymbolTitle = stockDisplayLabel({ symbol, name: symbolName, display_label: symbolDisplayLabel })
    const [loadErr, setLoadErr] = useState<string | null>(null)
    const [liveStatusText, setLiveStatusText] = useState<string | null>(null)
    const [liveStatusError, setLiveStatusError] = useState<string | null>(null)
    const [chartCandles, setChartCandles] = useState<KlineCandle[]>([])
    const [isSymbolLoading, setIsSymbolLoading] = useState(false)
    const [liveDecisionSnapshot, setLiveDecisionSnapshot] = useState<{
        pre_close?: number
        open?: number
        high?: number
        low?: number
        close?: number
        vol?: number
        amount?: number
        num?: number
        change?: number
        change_pct?: number
        trade_time?: string | null
    } | null>(null)
    const [auctionSnapshot, setAuctionSnapshot] = useState<Record<string, unknown> | null>(null)
    const [cyqSummary, setCyqSummary] = useState<Record<string, unknown> | null>(null)
    const [cyqDistribution, setCyqDistribution] = useState<Array<{ price: number; ratio: number }>>([])
    const [moneyflowItems, setMoneyflowItems] = useState<Array<Record<string, unknown>>>([])
    const [factorSnapshot, setFactorSnapshot] = useState<Record<string, unknown> | null>(null)
    const [dailyBasicSnapshot, setDailyBasicSnapshot] = useState<Record<string, unknown> | null>(null)
    const [eventMarkers, setEventMarkers] = useState<Array<Record<string, unknown>>>([])
    const [hsgtItems, setHsgtItems] = useState<Array<Record<string, unknown>>>([])
    const [hsgtMarketItems, setHsgtMarketItems] = useState<Array<Record<string, unknown>>>([])
    const [corpEventMarkers, setCorpEventMarkers] = useState<Array<Record<string, unknown>>>([])
    const mainRef = useRef<HTMLDivElement>(null)
    const volRef = useRef<HTMLDivElement>(null)
    const subRef = useRef<HTMLDivElement>(null)

    const chartMain = useRef<IChartApi | null>(null)
    const chartVol = useRef<IChartApi | null>(null)
    const chartSub = useRef<IChartApi | null>(null)

    const candleSeries = useRef<ISeriesApi<'Candlestick'> | null>(null)
    const volSeries = useRef<ISeriesApi<'Histogram'> | null>(null)
    const maSeries = useRef<Partial<Record<'ma5' | 'ma10' | 'ma20' | 'ma60', ISeriesApi<'Line'>>>>({})
    const bollSeries = useRef<{
        upper?: ISeriesApi<'Line'>
        mid?: ISeriesApi<'Line'>
        lower?: ISeriesApi<'Line'>
    }>({})
    const compareLines = useRef<ISeriesApi<'Line'>[]>([])
    const subSeries = useRef<ISeriesApi<'Line' | 'Histogram'>[]>([])
    const subPriceLines = useRef<{ series: ISeriesApi<'Line' | 'Histogram'>; line: ReturnType<ISeriesApi<'Line'>['createPriceLine']> }[]>([])
    const subMarkersPlugin = useRef<{ setMarkers: (m: SeriesMarker<BusinessDay>[]) => void } | null>(null)
    const priceLines = useRef<ReturnType<ISeriesApi<'Candlestick'>['createPriceLine']>[]>([])
    const markersPlugin = useRef<{ setMarkers: (m: SeriesMarker<BusinessDay>[]) => void } | null>(null)
    const syncing = useRef(false)
    const lastDataKey = useRef<string | null>(null)
    const liveFailCount = useRef(0)
    const upsertQuotes = useQuoteStore((s) => s.upsertQuotes)

    const gridColor = chartPalette.gridColor
    const textColor = chartPalette.textColor
    const borderColor = chartPalette.borderColor

    /** 派生：信号徽章（MA 排列 / MACD / KDJ / RSI），仅 1d 周期会展示。
     *  各指标按自身最小样本数判定；样本不足时给出"待 ≥N 根（当前 X）"具体提示。 */
    const decisionSignals = useMemo(() => {
        const closes = closeArr(chartCandles)
        const highs = highArr(chartCandles)
        const lows = lowArr(chartCandles)
        const n = closes.length
        const ma5 = calcSma(closes, 5)
        const ma10 = calcSma(closes, 10)
        const ma20 = calcSma(closes, 20)
        const macd = calcMacd(closes)
        const kdj = calcKdj(highs, lows, closes)
        const rsi14 = calcRsi(closes, 14)
        return {
            ma: detectMaState(ma5, ma10, ma20, n),
            macd: detectMacdState(macd.dif, macd.dea, macd.macd, n),
            kdj: detectKdjState(kdj.k, kdj.d, n),
            rsi: detectRsiState(rsi14, n),
        }
    }, [chartCandles])

    /** 派生：当日决策需要的明细（OHLC、振幅、量比、换手率、涨跌、成交额等） */
    const decisionSnapshot = useMemo(() => {
        const live = liveDecisionSnapshot
        const last = chartCandles.length ? chartCandles[chartCandles.length - 1] : null
        const prev = chartCandles.length > 1 ? chartCandles[chartCandles.length - 2] : null
        const open = live?.open ?? Number(last?.open)
        const high = live?.high ?? Number(last?.high)
        const low = live?.low ?? Number(last?.low)
        const close = live?.close ?? Number(last?.close)
        const preClose = live?.pre_close ?? (prev ? Number(prev.close) : undefined)
        const vol = live?.vol ?? Number(last?.volume ?? 0)
        const amount = live?.amount
        const num = live?.num
        let chg: number | undefined
        let chgPct: number | undefined
        if (Number.isFinite(close) && Number.isFinite(preClose as number) && (preClose as number) !== 0) {
            chg = (close as number) - (preClose as number)
            chgPct = (chg / (preClose as number)) * 100
        } else if (Number.isFinite(close) && Number.isFinite(open) && open !== 0) {
            chg = (close as number) - open
            chgPct = (chg / open) * 100
        }
        const amp = calcAmplitudePct(high, low, preClose)
        const vols = volArr(chartCandles)
        const vr = calcVolumeRatio(vols, 5)
        const turnover = asNumber(dailyBasicSnapshot?.turnover_rate) ?? last?.turnover_rate
        return {
            open: Number.isFinite(open) ? open : undefined,
            high: Number.isFinite(high) ? high : undefined,
            low: Number.isFinite(low) ? low : undefined,
            close: Number.isFinite(close) ? close : undefined,
            pre_close: Number.isFinite(preClose as number) ? (preClose as number) : undefined,
            vol: Number.isFinite(vol) ? vol : undefined,
            amount: typeof amount === 'number' && Number.isFinite(amount) ? amount : undefined,
            num: typeof num === 'number' && Number.isFinite(num) ? num : undefined,
            change: typeof chg === 'number' ? chg : undefined,
            change_pct: typeof chgPct === 'number' ? chgPct : undefined,
            amplitude_pct: amp ?? undefined,
            volume_ratio: vr ?? undefined,
            turnover_rate: typeof turnover === 'number' ? turnover : undefined,
            trade_time: live?.trade_time ?? last?.date?.slice(0, 19) ?? null,
        }
    }, [chartCandles, dailyBasicSnapshot, liveDecisionSnapshot])

    const commonLayout = useCallback(() => ({
        layout: {
            background: { type: ColorType.Solid, color: 'transparent' },
            textColor,
            attributionLogo: false,
        },
        grid: {
            vertLines: { color: gridColor },
            horzLines: { color: gridColor },
        },
        crosshair: {
            vertLine: { color: chartPalette.crosshairVert },
            horzLine: { color: chartPalette.crosshairHorz },
        },
        localization: {
            locale: 'zh-CN',
            dateFormat: 'yyyy-MM-dd',
            timeFormatter: formatKlineCrosshairTime,
        },
        rightPriceScale: { borderColor },
        timeScale: { borderColor, timeVisible: false, rightOffset: 6 },
    }), [borderColor, chartPalette.crosshairHorz, chartPalette.crosshairVert, gridColor, textColor])

    const chartOptions = useCallback(
        (height: number, master: boolean) => ({
            ...commonLayout(),
            width: mainRef.current?.clientWidth ?? 800,
            height,
            handleScroll: master,
            handleScale: master,
            timeScale: {
                ...commonLayout().timeScale,
                visible: master,
            },
        }),
        [commonLayout],
    )

    useEffect(() => {
        if (!mainRef.current || !volRef.current || !subRef.current) return

        const w = mainRef.current.clientWidth
        const hMain = Math.max(280, Math.floor(mainRef.current.clientHeight || 360))
        const hVol = Math.max(72, Math.floor(volRef.current.clientHeight || 100))
        const hSub = Math.max(100, Math.floor(subRef.current.clientHeight || 140))

        const m = createChart(mainRef.current, {
            ...chartOptions(hMain, true),
            width: w,
        })
        const v = createChart(volRef.current, {
            ...chartOptions(hVol, false),
            width: w,
            timeScale: { visible: false, borderColor },
        })
        const sChart = createChart(subRef.current, {
            ...chartOptions(hSub, false),
            width: w,
            timeScale: { visible: true, borderColor },
        })

        chartMain.current = m
        chartVol.current = v
        chartSub.current = sChart

        const candle = m.addSeries(CandlestickSeries, {
            upColor: '#ef4444',
            downColor: '#22c55e',
            wickUpColor: '#ef4444',
            wickDownColor: '#22c55e',
            borderVisible: false,
        })
        candleSeries.current = candle
        markersPlugin.current = createSeriesMarkers(candle, [])

        maSeries.current.ma5 = m.addSeries(LineSeries, { color: MA_COLORS.ma5, lineWidth: 1, title: 'MA5' })
        maSeries.current.ma10 = m.addSeries(LineSeries, { color: MA_COLORS.ma10, lineWidth: 1, title: 'MA10' })
        maSeries.current.ma20 = m.addSeries(LineSeries, { color: MA_COLORS.ma20, lineWidth: 1, title: 'MA20' })
        maSeries.current.ma60 = m.addSeries(LineSeries, { color: MA_COLORS.ma60, lineWidth: 1, title: 'MA60' })

        bollSeries.current.upper = m.addSeries(LineSeries, {
            color: 'rgba(148, 163, 184, 0.7)',
            lineWidth: 1,
            lineStyle: 2,
            title: 'BOLL上',
        })
        bollSeries.current.mid = m.addSeries(LineSeries, {
            color: 'rgba(148, 163, 184, 0.9)',
            lineWidth: 1,
            title: 'BOLL中',
        })
        bollSeries.current.lower = m.addSeries(LineSeries, {
            color: 'rgba(148, 163, 184, 0.7)',
            lineWidth: 1,
            lineStyle: 2,
            title: 'BOLL下',
        })

        const vol = v.addSeries(HistogramSeries, {
            color: '#64748b',
            priceFormat: { type: 'volume' },
            priceScaleId: 'right',
        })
        volSeries.current = vol

        const onMasterRange = () => {
            if (syncing.current) return
            const range = m.timeScale().getVisibleLogicalRange()
            if (!range) return
            syncing.current = true
            v.timeScale().setVisibleLogicalRange(range)
            sChart.timeScale().setVisibleLogicalRange(range)
            syncing.current = false
        }
        m.timeScale().subscribeVisibleLogicalRangeChange(onMasterRange)

        const onResize = () => {
            const width = mainRef.current?.clientWidth ?? w
            m.applyOptions({ width, height: mainRef.current?.clientHeight ?? hMain })
            v.applyOptions({ width, height: volRef.current?.clientHeight ?? hVol })
            sChart.applyOptions({ width, height: subRef.current?.clientHeight ?? hSub })
        }
        window.addEventListener('resize', onResize)

        return () => {
            window.removeEventListener('resize', onResize)
            m.timeScale().unsubscribeVisibleLogicalRangeChange(onMasterRange)
            m.remove()
            v.remove()
            sChart.remove()
            chartMain.current = null
            chartVol.current = null
            chartSub.current = null
            candleSeries.current = null
            volSeries.current = null
            maSeries.current = {}
            bollSeries.current = {}
            markersPlugin.current = null
        }
    }, [borderColor, chartOptions, commonLayout, gridColor, isDark, skin, textColor])

    useEffect(() => {
        const enabled = liveDailyEnabled && hasRtEntitlement && period === '1d'
        if (!enabled) {
            setLiveStatusError(null)
            setLiveStatusText(null)
            liveFailCount.current = 0
            return
        }
        let stopped = false
        let timer: number | null = null

        const tick = async () => {
            if (stopped) return
            if (typeof document !== 'undefined' && document.visibilityState !== 'visible') {
                setLiveStatusText(null)
                return
            }
            if (!isCnAshareRegularSession()) {
                setLiveStatusText(`收盘 ${cnShanghaiDateText()}`)
                return
            }
            const sym = (normalizeCnAshareSymbol(symbol) || symbol).trim().toUpperCase()
            try {
                const resp = await api.getRtDaily([sym])
                if (stopped) return
                const quote = resp.quotes[sym]
                if (!quote) {
                    liveFailCount.current += 1
                    setLiveStatusError("实时快照缺失")
                    if (liveFailCount.current >= 3) {
                        useChartStore.getState().setLiveDailyEnabled(false)
                    }
                    return
                }
                const time = parseDateToBD(cnShanghaiDateText())
                const open = Number(quote.open)
                const high = Number(quote.high)
                const low = Number(quote.low)
                const close = Number(quote.close)
                if (time && [open, high, low, close].every(Number.isFinite)) {
                    candleSeries.current?.update({ time, open, high, low, close })
                }
                const vol = Number(quote.vol)
                if (time && Number.isFinite(vol)) {
                    const up = Number.isFinite(close) && Number.isFinite(open) ? close >= open : true
                    volSeries.current?.update({
                        time,
                        value: vol,
                        color: up ? 'rgba(239,68,68,0.65)' : 'rgba(34,197,94,0.65)',
                    })
                }
                upsertQuotes(
                    {
                        [sym]: {
                            price: Number.isFinite(close) ? close : undefined,
                            open: Number.isFinite(open) ? open : undefined,
                            high: Number.isFinite(high) ? high : undefined,
                            low: Number.isFinite(low) ? low : undefined,
                            previous_close: Number.isFinite(Number(quote.pre_close)) ? Number(quote.pre_close) : undefined,
                            change: Number.isFinite(Number(quote.change)) ? Number(quote.change) : undefined,
                            change_pct: Number.isFinite(Number(quote.change_pct)) ? Number(quote.change_pct) : undefined,
                            volume: Number.isFinite(vol) ? vol : undefined,
                            amount: Number.isFinite(Number(quote.amount)) ? Number(quote.amount) : undefined,
                            quote_time: quote.trade_time ?? undefined,
                            source: "tushare_rt",
                        },
                    },
                    Date.now(),
                )
                setLiveDecisionSnapshot({
                    pre_close: Number.isFinite(Number(quote.pre_close)) ? Number(quote.pre_close) : undefined,
                    open: Number.isFinite(open) ? open : undefined,
                    high: Number.isFinite(high) ? high : undefined,
                    low: Number.isFinite(low) ? low : undefined,
                    close: Number.isFinite(close) ? close : undefined,
                    vol: Number.isFinite(vol) ? vol : undefined,
                    amount: Number.isFinite(Number(quote.amount)) ? Number(quote.amount) : undefined,
                    num: Number.isFinite(Number(quote.num)) ? Number(quote.num) : undefined,
                    change: Number.isFinite(Number(quote.change)) ? Number(quote.change) : undefined,
                    change_pct: Number.isFinite(Number(quote.change_pct)) ? Number(quote.change_pct) : undefined,
                    trade_time: quote.trade_time ?? null,
                })
                setChartCandles((prev) => {
                    if (!prev.length) return prev
                    const day = cnShanghaiDateText()
                    const next = [...prev]
                    const idx = next.findIndex((x) => (x.date || '').slice(0, 10) === day)
                    const merged: KlineCandle = {
                        date: `${day} 00:00:00`,
                        open: Number.isFinite(open) ? open : (next[idx]?.open ?? next[next.length - 1].open),
                        high: Number.isFinite(high) ? high : (next[idx]?.high ?? next[next.length - 1].high),
                        low: Number.isFinite(low) ? low : (next[idx]?.low ?? next[next.length - 1].low),
                        close: Number.isFinite(close) ? close : (next[idx]?.close ?? next[next.length - 1].close),
                        volume: Number.isFinite(vol) ? vol : (next[idx]?.volume ?? next[next.length - 1].volume),
                        change: Number.isFinite(Number(quote.change)) ? Number(quote.change) : next[idx]?.change,
                        change_percent: Number.isFinite(Number(quote.change_pct)) ? Number(quote.change_pct) : next[idx]?.change_percent,
                    }
                    if (idx >= 0) next[idx] = { ...next[idx], ...merged }
                    else next.push(merged)
                    return next
                })
                liveFailCount.current = 0
                setLiveStatusError(null)
                setLiveStatusText(quote.trade_time ? `LIVE ${quote.trade_time}` : "LIVE")
            } catch (e) {
                if (stopped) return
                liveFailCount.current += 1
                const msg = e instanceof Error ? e.message : "实时刷新失败"
                setLiveStatusError(msg)
                if (liveFailCount.current >= 3) {
                    useChartStore.getState().setLiveDailyEnabled(false)
                }
            }
        }

        void tick()
        timer = window.setInterval(() => {
            void tick()
        }, 12_000)
        const onVis = () => {
            if (document.visibilityState === 'visible') void tick()
        }
        document.addEventListener('visibilitychange', onVis)
        return () => {
            stopped = true
            document.removeEventListener('visibilitychange', onVis)
            if (timer != null) window.clearInterval(timer)
        }
    }, [hasRtEntitlement, liveDailyEnabled, period, symbol, upsertQuotes])

    useEffect(() => {
        let stopped = false
        const sym = (normalizeCnAshareSymbol(symbol) || symbol).trim().toUpperCase()
        if (!sym) return
        const run = async () => {
            try {
                const [auction, cyq, moneyflow, factor, dailyBasic, events, hsgt, corpEvents] = await Promise.all([
                    api.getChartAuction(sym).catch(() => ({ enabled: false, symbol: sym, snapshot: null })),
                    api.getChartCyq(sym, 90).catch(() => ({ enabled: false, symbol: sym, summary: null, distribution: [] as Array<{ price: number; ratio: number }> })),
                    api.getChartMoneyflow(sym, 120).catch(() => ({ enabled: false, symbol: sym, items: [] as Array<Record<string, unknown>> })),
                    api.getChartFactorPro(sym, 180).catch(() => ({ enabled: false, symbol: sym, snapshot: null })),
                    api.getChartDailyBasic(sym, 180).catch(() => ({ enabled: false, symbol: sym, snapshot: null })),
                    api.getChartEvents(sym, start, end).catch(() => ({ enabled: false, symbol: sym, items: [] as Array<Record<string, unknown>> })),
                    api.getChartHsgt(sym, 120).catch(() => ({ enabled: false, symbol: sym, items: [] as Array<Record<string, unknown>>, market: [] as Array<Record<string, unknown>> })),
                    api.getChartCorpEvents(sym, start, end).catch(() => ({ enabled: false, symbol: sym, items: [] as Array<Record<string, unknown>> })),
                ])
                if (stopped) return
                setAuctionSnapshot((auction.snapshot as Record<string, unknown> | null) ?? null)
                setCyqSummary((cyq.summary as Record<string, unknown> | null) ?? null)
                setCyqDistribution(Array.isArray(cyq.distribution) ? cyq.distribution : [])
                setMoneyflowItems(Array.isArray(moneyflow.items) ? moneyflow.items : [])
                setFactorSnapshot((factor.snapshot as Record<string, unknown> | null) ?? null)
                setDailyBasicSnapshot((dailyBasic.snapshot as Record<string, unknown> | null) ?? null)
                setEventMarkers(Array.isArray(events.items) ? events.items : [])
                setHsgtItems(Array.isArray(hsgt.items) ? hsgt.items : [])
                setHsgtMarketItems(Array.isArray(hsgt.market) ? hsgt.market : [])
                setCorpEventMarkers(Array.isArray(corpEvents.items) ? corpEvents.items : [])
            } catch {
                if (stopped) return
            }
        }
        void run()
        return () => {
            stopped = true
        }
    }, [end, start, symbol])

    useEffect(() => {
        let cancelled = false
        const ac = new AbortController()

        const lineFrom = (values: (number | null)[], datesArr: string[]): LineData<BusinessDay>[] => {
            const out: LineData<BusinessDay>[] = []
            for (let i = 0; i < values.length; i++) {
                const val = values[i]
                const t = parseDateToBD(datesArr[i])
                if (val == null || !t || !Number.isFinite(val)) continue
                out.push({ time: t, value: val })
            }
            return out
        }

        const run = async () => {
            const symParam = (normalizeCnAshareSymbol(symbol) || symbol).trim()
            if (!symParam) {
                setLoadErr('标的代码为空，无法加载 K 线')
                return
            }
            try {
                setIsSymbolLoading(true)
                const resp = await api.getKline(symParam, start, end, { period, adjust, signal: ac.signal })
                if (cancelled) return
                const refsOk = () =>
                    !!(candleSeries.current && volSeries.current && chartMain.current)
                const ok = await waitForChartRefs(refsOk, () => cancelled)
                if (!ok || cancelled) {
                    if (!cancelled) setLoadErr('图表初始化超时，K 线数据已获取，请刷新页面重试')
                    return
                }
                setLoadErr(null)
                const candle = candleSeries.current!
                const vol = volSeries.current!
                const mainChart = chartMain.current!
                const symDataKey = `${symParam}|${start}|${end}|${period}|${adjust}`
                const isLiveRefresh = liveRefreshKey > 0 && lastDataKey.current === symDataKey
                const visibleRange = isLiveRefresh ? mainChart.timeScale().getVisibleLogicalRange() : null
                const symUp = symParam.trim().toUpperCase()
                const dl = resp.display_label ?? null
                const st = useChartStore.getState()
                if (st.symbol.trim().toUpperCase() !== symUp || st.symbolDisplayLabel !== dl) {
                    useChartStore.getState().setSymbol(symUp, { display_label: dl })
                }
                const candles = resp.candles
                setChartCandles(candles)
                setLiveDecisionSnapshot(null)
                const candleData: CandlestickData<BusinessDay>[] = []
                for (const c of candles) {
                    const cd = toCandleData(c)
                    if (cd) candleData.push(cd)
                }
                candle.setData(candleData)
                if (visibleRange) {
                    mainChart.timeScale().setVisibleLogicalRange(visibleRange)
                } else {
                    mainChart.timeScale().fitContent()
                }
                lastDataKey.current = symDataKey

                const dates = candles.map((c) => c.date.slice(0, 10))
                const closes = closeArr(candles)
                const highs = highArr(candles)
                const lows = lowArr(candles)
                const vols = volArr(candles)

                const s5 = calcSma(closes, 5)
                const s10 = calcSma(closes, 10)
                const s20 = calcSma(closes, 20)
                const s60 = calcSma(closes, 60)

                maSeries.current.ma5?.setData(showMa.ma5 ? lineFrom(s5, dates) : [])
                maSeries.current.ma10?.setData(showMa.ma10 ? lineFrom(s10, dates) : [])
                maSeries.current.ma20?.setData(showMa.ma20 ? lineFrom(s20, dates) : [])
                maSeries.current.ma60?.setData(showMa.ma60 ? lineFrom(s60, dates) : [])

                const boll = calcBoll(closes, 20, 2)
                if (showBoll) {
                    bollSeries.current.upper?.setData(lineFrom(boll.upper, dates))
                    bollSeries.current.mid?.setData(lineFrom(boll.mid, dates))
                    bollSeries.current.lower?.setData(lineFrom(boll.lower, dates))
                } else {
                    bollSeries.current.upper?.setData([])
                    bollSeries.current.mid?.setData([])
                    bollSeries.current.lower?.setData([])
                }

                const histData: HistogramData<BusinessDay>[] = []
                for (let i = 0; i < candles.length; i++) {
                    const c = candles[i]
                    const t = parseDateToBD(c.date)
                    if (!t) continue
                    const volume = Number(c.volume ?? 0)
                    const up = Number(c.close) >= Number(c.open)
                    histData.push({
                        time: t,
                        value: volume,
                        color: up ? 'rgba(239,68,68,0.65)' : 'rgba(34,197,94,0.65)',
                    })
                }
                vol.setData(histData)

                const cs = chartSub.current
                if (cs) {
                    // 清理上一次副图的价格参考线
                    for (const ref of subPriceLines.current) {
                        try {
                            ref.series.removePriceLine(ref.line)
                        } catch {
                            /* noop */
                        }
                    }
                    subPriceLines.current = []
                    // 清理副图 markers
                    if (subMarkersPlugin.current) {
                        try {
                            subMarkersPlugin.current.setMarkers([])
                        } catch {
                            /* noop */
                        }
                    }
                    subMarkersPlugin.current = null
                    for (const ser of subSeries.current) {
                        try {
                            cs.removeSeries(ser)
                        } catch {
                            /* noop */
                        }
                    }
                }
                subSeries.current = []

                if (subChart !== 'none' && cs) {
                    if (subChart === 'macd') {
                        const { dif, dea, macd } = calcMacd(closes)
                        const ldif = lineFrom(dif, dates)
                        const ldea = lineFrom(dea, dates)
                        const lmacd: HistogramData<BusinessDay>[] = []
                        for (let i = 0; i < macd.length; i++) {
                            const mv = macd[i]
                            const t = parseDateToBD(dates[i])
                            if (mv == null || !t) continue
                            lmacd.push({
                                time: t,
                                value: mv,
                                color: mv >= 0 ? 'rgba(239,68,68,0.75)' : 'rgba(34,197,94,0.75)',
                            })
                        }
                        const h = cs.addSeries(HistogramSeries, { priceScaleId: 'right' })
                        h.setData(lmacd)
                        subSeries.current.push(h)
                        const d1 = cs.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'DIF' })
                        const d2 = cs.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'DEA' })
                        d1.setData(ldif)
                        d2.setData(ldea)
                        subSeries.current.push(d1, d2)
                        // 0 轴参考线
                        try {
                            subPriceLines.current.push({
                                series: h,
                                line: h.createPriceLine({
                                    price: 0,
                                    color: 'rgba(148,163,184,0.55)',
                                    lineWidth: 1,
                                    lineStyle: 0,
                                    axisLabelVisible: false,
                                    title: '0',
                                }),
                            })
                        } catch {
                            /* noop */
                        }
                        // 全周期金/死叉箭头
                        const macdMarkers: SeriesMarker<BusinessDay>[] = []
                        for (let i = 1; i < dif.length; i++) {
                            const f1 = dif[i - 1]
                            const s1 = dea[i - 1]
                            const f2 = dif[i]
                            const s2 = dea[i]
                            if (f1 == null || s1 == null || f2 == null || s2 == null) continue
                            const t = parseDateToBD(dates[i])
                            if (!t) continue
                            if (f1 <= s1 && f2 > s2) {
                                macdMarkers.push({ time: t, position: 'belowBar', shape: 'arrowUp', color: '#ef4444', text: '金叉' })
                            } else if (f1 >= s1 && f2 < s2) {
                                macdMarkers.push({ time: t, position: 'aboveBar', shape: 'arrowDown', color: '#22c55e', text: '死叉' })
                            }
                        }
                        try {
                            subMarkersPlugin.current = createSeriesMarkers(d1, macdMarkers)
                        } catch {
                            /* noop */
                        }
                    } else if (subChart === 'kdj') {
                        const { k, d, j } = calcKdj(highs, lows, closes)
                        const lk = cs.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'K' })
                        const ld = cs.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'D' })
                        const lj = cs.addSeries(LineSeries, { color: '#a855f7', lineWidth: 1, title: 'J' })
                        lk.setData(lineFrom(k, dates))
                        ld.setData(lineFrom(d, dates))
                        lj.setData(lineFrom(j, dates))
                        subSeries.current.push(lk, ld, lj)
                        // 80/20 阈值参考线（K 系列）
                        try {
                            subPriceLines.current.push({
                                series: lk,
                                line: lk.createPriceLine({
                                    price: 80,
                                    color: 'rgba(239,68,68,0.6)',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '超买80',
                                }),
                            })
                            subPriceLines.current.push({
                                series: lk,
                                line: lk.createPriceLine({
                                    price: 20,
                                    color: 'rgba(34,197,94,0.6)',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '超卖20',
                                }),
                            })
                        } catch {
                            /* noop */
                        }
                        // 金/死叉箭头（K vs D）
                        const kdjMarkers: SeriesMarker<BusinessDay>[] = []
                        for (let i = 1; i < k.length; i++) {
                            const f1 = k[i - 1]
                            const s1 = d[i - 1]
                            const f2 = k[i]
                            const s2 = d[i]
                            if (f1 == null || s1 == null || f2 == null || s2 == null) continue
                            const t = parseDateToBD(dates[i])
                            if (!t) continue
                            if (f1 <= s1 && f2 > s2) {
                                kdjMarkers.push({ time: t, position: 'belowBar', shape: 'arrowUp', color: '#ef4444', text: '金叉' })
                            } else if (f1 >= s1 && f2 < s2) {
                                kdjMarkers.push({ time: t, position: 'aboveBar', shape: 'arrowDown', color: '#22c55e', text: '死叉' })
                            }
                        }
                        try {
                            subMarkersPlugin.current = createSeriesMarkers(lk, kdjMarkers)
                        } catch {
                            /* noop */
                        }
                    } else if (subChart === 'rsi') {
                        const rsi6 = calcRsi(closes, 6)
                        const rsi12 = calcRsi(closes, 12)
                        const r1 = cs.addSeries(LineSeries, { color: '#f59e0b', lineWidth: 1, title: 'RSI6' })
                        const r2 = cs.addSeries(LineSeries, { color: '#3b82f6', lineWidth: 1, title: 'RSI12' })
                        r1.setData(lineFrom(rsi6, dates))
                        r2.setData(lineFrom(rsi12, dates))
                        subSeries.current.push(r1, r2)
                        try {
                            subPriceLines.current.push({
                                series: r1,
                                line: r1.createPriceLine({
                                    price: 70,
                                    color: 'rgba(239,68,68,0.6)',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '超买70',
                                }),
                            })
                            subPriceLines.current.push({
                                series: r1,
                                line: r1.createPriceLine({
                                    price: 30,
                                    color: 'rgba(34,197,94,0.6)',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '超卖30',
                                }),
                            })
                        } catch {
                            /* noop */
                        }
                    } else if (subChart === 'atr') {
                        const atr = calcAtr(highs, lows, closes, 14)
                        const a = cs.addSeries(LineSeries, { color: '#94a3b8', lineWidth: 1, title: 'ATR14' })
                        a.setData(lineFrom(atr, dates))
                        subSeries.current.push(a)
                    } else if (subChart === 'moneyflow') {
                        const xl = cs.addSeries(HistogramSeries, { color: 'rgba(239,68,68,0.75)', title: '超大单' })
                        const l = cs.addSeries(HistogramSeries, { color: 'rgba(251,146,60,0.75)', title: '大单' })
                        const m = cs.addSeries(HistogramSeries, { color: 'rgba(59,130,246,0.75)', title: '中单' })
                        const s = cs.addSeries(HistogramSeries, { color: 'rgba(34,197,94,0.75)', title: '小单' })
                        const pXl: HistogramData<BusinessDay>[] = []
                        const pL: HistogramData<BusinessDay>[] = []
                        const pM: HistogramData<BusinessDay>[] = []
                        const pS: HistogramData<BusinessDay>[] = []
                        for (const row of moneyflowItems) {
                            const t = parseDateToBD(String(row.date || ''))
                            if (!t) continue
                            const vXl = asNumber(row.xl)
                            const vL = asNumber(row.l)
                            const vM = asNumber(row.m)
                            const vS = asNumber(row.s)
                            if (vXl != null) pXl.push({ time: t, value: vXl, color: 'rgba(239,68,68,0.75)' })
                            if (vL != null) pL.push({ time: t, value: vL, color: 'rgba(251,146,60,0.75)' })
                            if (vM != null) pM.push({ time: t, value: vM, color: 'rgba(59,130,246,0.75)' })
                            if (vS != null) pS.push({ time: t, value: vS, color: 'rgba(34,197,94,0.75)' })
                        }
                        xl.setData(pXl)
                        l.setData(pL)
                        m.setData(pM)
                        s.setData(pS)
                        subSeries.current.push(xl, l, m, s)
                    } else if (subChart === 'hsgt_flow') {
                        const net = cs.addSeries(HistogramSeries, { color: 'rgba(14,165,233,0.75)', title: '个股北向' })
                        const mk = cs.addSeries(LineSeries, { color: '#a855f7', lineWidth: 1, title: '市场北向' })
                        const pNet: HistogramData<BusinessDay>[] = []
                        const pMk: LineData<BusinessDay>[] = []
                        for (const row of hsgtItems) {
                            const t = parseDateToBD(String(row.date || ''))
                            const n = asNumber(row.stock_net)
                            if (t && n != null) pNet.push({ time: t, value: n, color: 'rgba(14,165,233,0.75)' })
                        }
                        for (const row of hsgtMarketItems) {
                            const t = parseDateToBD(String(row.date || ''))
                            const n = asNumber(row.north_net)
                            if (t && n != null) pMk.push({ time: t, value: n })
                        }
                        net.setData(pNet)
                        mk.setData(pMk)
                        subSeries.current.push(net, mk)
                    } else if (subChart === 'chip_distribution') {
                        const chip = cs.addSeries(HistogramSeries, { color: 'rgba(168,85,247,0.75)', title: '筹码密度' })
                        const points: HistogramData<BusinessDay>[] = []
                        const sorted = [...cyqDistribution].sort((a, b) => a.price - b.price)
                        const len = sorted.length
                        for (let i = 0; i < len; i++) {
                            const t = parseDateToBD(dates[Math.max(0, dates.length - len + i)] || dates[dates.length - 1] || '')
                            if (!t) continue
                            points.push({
                                time: t,
                                value: Number(sorted[i].ratio) || 0,
                                color: 'rgba(168,85,247,0.75)',
                            })
                        }
                        chip.setData(points)
                        subSeries.current.push(chip)
                    } else if (subChart === 'obv') {
                        const obv = calcObv(closes, vols)
                        const o = cs.addSeries(LineSeries, { color: '#22d3ee', lineWidth: 1, title: 'OBV' })
                        o.setData(lineFrom(obv, dates))
                        subSeries.current.push(o)
                    }
                    if (!isLiveRefresh) cs.timeScale().fitContent()
                }

                if (!isLiveRefresh) {
                    for (const line of compareLines.current) {
                        try {
                            chartMain.current?.removeSeries(line)
                        } catch {
                            /* noop */
                        }
                    }
                    compareLines.current = []
                    if (dates.length > 0 && compareSymbols.length > 0 && chartMain.current) {
                        chartMain.current.applyOptions({
                            leftPriceScale: {
                                visible: true,
                                borderVisible: true,
                                entireTextOnly: false,
                            },
                        })
                        const palette = ['#22d3ee', '#eab308', '#f472b6', '#34d399']
                        const targets = compareSymbols
                            .map((cmpRaw) => normalizeCnAshareSymbol(cmpRaw))
                            .filter((cmp): cmp is string => !!cmp && cmp !== normalizeCnAshareSymbol(symbol))
                        const results = await Promise.all(
                            targets.map(async (cmp) => {
                                try {
                                    const r2 = await api.getKline(cmp, start, end, { period, adjust, signal: ac.signal })
                                    return { cmp, candles: r2.candles }
                                } catch {
                                    return null
                                }
                            }),
                        )
                        let pi = 0
                        for (const item of results) {
                            if (!item) continue
                            const closeMap = new Map<string, number>()
                            for (const x of item.candles) {
                                closeMap.set(x.date.slice(0, 10), Number(x.close))
                            }
                            const pts: LineData<BusinessDay>[] = []
                            let first: number | null = null
                            for (const d of dates) {
                                const cl = closeMap.get(d)
                                if (cl == null || !Number.isFinite(cl)) continue
                                if (first == null) first = cl
                                const t = parseDateToBD(d)
                                if (!t || first === null) continue
                                pts.push({ time: t, value: (cl / first - 1) * 100 })
                            }
                            const ln = chartMain.current.addSeries(LineSeries, {
                                color: palette[pi % palette.length],
                                lineWidth: 2,
                                title: `${item.cmp}%`,
                                priceScaleId: 'left',
                            })
                            ln.setData(pts)
                            compareLines.current.push(ln)
                            pi++
                        }
                    } else if (chartMain.current) {
                        chartMain.current.applyOptions({
                            leftPriceScale: { visible: false, borderVisible: false },
                        })
                    }

                    for (const pl of priceLines.current) {
                        try {
                            candleSeries.current?.removePriceLine(pl)
                        } catch {
                            /* noop */
                        }
                    }
                    priceLines.current = []
                    if (insightLevels && candleSeries.current) {
                        for (const p of insightLevels.supports) {
                            if (!Number.isFinite(p)) continue
                            priceLines.current.push(
                                candleSeries.current.createPriceLine({
                                    price: p,
                                    color: '#22c55e',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '支撑',
                                }),
                            )
                        }
                        for (const p of insightLevels.resistances) {
                            if (!Number.isFinite(p)) continue
                            priceLines.current.push(
                                candleSeries.current.createPriceLine({
                                    price: p,
                                    color: '#ef4444',
                                    lineWidth: 1,
                                    lineStyle: 2,
                                    axisLabelVisible: true,
                                    title: '压力',
                                }),
                            )
                        }
                    }

                    const mergedEvents = [...eventMarkers, ...corpEventMarkers]
                    if (markersPlugin.current && (insightMarkers?.length || mergedEvents.length)) {
                        const insightMk: SeriesMarker<BusinessDay>[] = (insightMarkers || []).flatMap((im) => {
                            const t = parseDateToBD(im.time)
                            if (!t) return []
                            const shape =
                                im.type === 'golden_cross'
                                    ? 'arrowUp'
                                    : im.type === 'death_cross'
                                      ? 'arrowDown'
                                      : 'circle'
                            const color =
                                im.type === 'golden_cross'
                                    ? '#22c55e'
                                    : im.type === 'death_cross'
                                      ? '#ef4444'
                                      : '#94a3b8'
                            return [
                                {
                                    time: t,
                                    position: 'aboveBar',
                                    shape,
                                    color,
                                    text: im.label.slice(0, 12),
                                } as SeriesMarker<BusinessDay>,
                            ]
                        })
                        const eventMk: SeriesMarker<BusinessDay>[] = mergedEvents.flatMap((ev) => {
                            const date = String(ev.date || '').slice(0, 10)
                            const t = parseDateToBD(date)
                            if (!t) return []
                            const tp = String(ev.type || '')
                            const isUp = tp === 'limit_up'
                            const isDown = tp === 'limit_down'
                            const isTop = tp === 'top_list'
                            const isBlock = tp === 'block_trade'
                            const isFinPos = tp === 'forecast'
                            const isFinNeg = tp === 'express'
                            const shape: SeriesMarker<BusinessDay>['shape'] = isUp || isFinPos ? 'arrowUp' : isDown || isFinNeg ? 'arrowDown' : isTop ? 'circle' : 'square'
                            const color = isUp ? '#ef4444' : isDown ? '#22c55e' : isTop ? '#f59e0b' : isBlock ? '#fb923c' : '#a855f7'
                            return [
                                {
                                    time: t,
                                    position: isDown ? 'aboveBar' : 'belowBar',
                                    shape,
                                    color,
                                    text: String(ev.label || tp || '事件').slice(0, 12),
                                } as SeriesMarker<BusinessDay>,
                            ]
                        })
                        markersPlugin.current.setMarkers([...insightMk, ...eventMk])
                    } else if (markersPlugin.current) {
                        markersPlugin.current.setMarkers([])
                    }
                }
            } catch (e) {
                if (cancelled) return
                if (e instanceof DOMException && e.name === 'AbortError') return
                const msg = e instanceof Error ? e.message : '加载 K 线失败'
                setLoadErr(msg)
                candleSeries.current?.setData([])
                volSeries.current?.setData([])
            } finally {
                if (!cancelled) setIsSymbolLoading(false)
            }
        }

        void run()
        return () => {
            cancelled = true
            ac.abort()
        }
    }, [
        symbol,
        start,
        end,
        period,
        adjust,
        showMa,
        showBoll,
        subChart,
        compareSymbols,
        insightMarkers,
        insightLevels,
        isDark,
        liveRefreshKey,
        moneyflowItems,
        hsgtItems,
        hsgtMarketItems,
        cyqDistribution,
        eventMarkers,
        corpEventMarkers,
    ])

    return (
        <div className="flex flex-col gap-1 w-full min-h-0 flex-1">
            <div
                className="shrink-0 flex flex-wrap items-center gap-2 px-1 pt-0.5 text-xs text-slate-800 dark:text-slate-100 font-medium tabular-nums"
                title={chartSymbolTitle}
            >
                <span className="truncate">{chartSymbolTitle}</span>
                <RealtimeQuoteBadge symbol={symbol} autoFetch={!(liveDailyEnabled && hasRtEntitlement)} />
                {liveDailyEnabled && hasRtEntitlement ? (
                    <span
                        className={`inline-flex items-center gap-1 rounded-full border px-2 py-0.5 text-[10px] font-medium ${
                            liveStatusError
                                ? 'border-red-300 bg-red-50 text-red-700 dark:border-red-600/40 dark:bg-red-900/20 dark:text-red-300'
                                : liveStatusText?.startsWith('LIVE')
                                    ? 'border-emerald-300 bg-emerald-50 text-emerald-700 dark:border-emerald-600/40 dark:bg-emerald-900/20 dark:text-emerald-300'
                                    : 'border-slate-300 bg-slate-100 text-slate-600 dark:border-slate-700 dark:bg-slate-800 dark:text-slate-300'
                        }`}
                        title={liveStatusError || liveStatusText || '实时状态'}
                    >
                        <span className={`inline-block h-1.5 w-1.5 rounded-full ${liveStatusText?.startsWith('LIVE') && !liveStatusError ? 'bg-emerald-500 animate-pulse' : liveStatusError ? 'bg-red-500' : 'bg-slate-400'}`} />
                        {liveStatusError ? `异常 ${liveStatusError}` : liveStatusText || '实时待机'}
                    </span>
                ) : null}
            </div>
            {period === '1d' ? (
                <div
                    className="mx-1 shrink-0 rounded-md border border-slate-200 bg-white/70 px-2 py-1 text-[11px] tabular-nums shadow-sm dark:border-slate-700 dark:bg-slate-900/45"
                    role="region"
                    aria-label="日K决策头条带"
                >
                    <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
                        {/* 价格组：现价 + 涨跌 + 涨跌% */}
                        <span
                            className={`text-sm font-semibold ${
                                (decisionSnapshot?.change_pct ?? 0) > 0
                                    ? 'text-red-600 dark:text-red-400'
                                    : (decisionSnapshot?.change_pct ?? 0) < 0
                                      ? 'text-emerald-600 dark:text-emerald-400'
                                      : 'text-slate-700 dark:text-slate-200'
                            }`}
                        >
                            {fmtNum(decisionSnapshot?.close, 2)}
                        </span>
                        <span
                            className={`text-[11px] ${
                                (decisionSnapshot?.change ?? 0) > 0
                                    ? 'text-red-600 dark:text-red-400'
                                    : (decisionSnapshot?.change ?? 0) < 0
                                      ? 'text-emerald-600 dark:text-emerald-400'
                                      : 'text-slate-500'
                            }`}
                        >
                            {decisionSnapshot?.change != null ? (decisionSnapshot.change >= 0 ? '+' : '') + fmtNum(decisionSnapshot.change, 2) : '--'}
                            {' / '}
                            {decisionSnapshot?.change_pct != null
                                ? `${decisionSnapshot.change_pct >= 0 ? '+' : ''}${decisionSnapshot.change_pct.toFixed(2)}%`
                                : '--'}
                        </span>
                        <span className="hidden sm:inline-block h-3 w-px bg-slate-200 dark:bg-slate-700" />
                        {/* OHLC 组 */}
                        <span className="text-slate-600 dark:text-slate-300">
                            <span className="text-slate-400">开</span>{' '}
                            {fmtNum(decisionSnapshot?.open, 2)}
                            {'  '}
                            <span className="text-slate-400">高</span>{' '}
                            {fmtNum(decisionSnapshot?.high, 2)}
                            {'  '}
                            <span className="text-slate-400">低</span>{' '}
                            {fmtNum(decisionSnapshot?.low, 2)}
                            {'  '}
                            <span className="text-slate-400">昨</span>{' '}
                            {fmtNum(decisionSnapshot?.pre_close, 2)}
                        </span>
                        <span className="hidden sm:inline-block h-3 w-px bg-slate-200 dark:bg-slate-700" />
                        {/* 量价组 */}
                        <span className="text-slate-600 dark:text-slate-300">
                            <span className="text-slate-400">量</span>{' '}
                            {fmtCompact(decisionSnapshot?.vol)}
                            {'  '}
                            <span className="text-slate-400">额</span>{' '}
                            {fmtCompact(decisionSnapshot?.amount)}
                            {decisionSnapshot?.turnover_rate != null && (
                                <>
                                    {'  '}
                                    <span className="text-slate-400">换手</span>{' '}
                                    {decisionSnapshot.turnover_rate.toFixed(2)}%
                                </>
                            )}
                            {asNumber(dailyBasicSnapshot?.pe) != null && (
                                <>
                                    {'  '}
                                    <span className="text-slate-400">PE</span>{' '}
                                    {fmtNum(asNumber(dailyBasicSnapshot?.pe), 1)}
                                </>
                            )}
                            {asNumber(dailyBasicSnapshot?.pb) != null && (
                                <>
                                    {'  '}
                                    <span className="text-slate-400">PB</span>{' '}
                                    {fmtNum(asNumber(dailyBasicSnapshot?.pb), 2)}
                                </>
                            )}
                        </span>
                        <span className="hidden sm:inline-block h-3 w-px bg-slate-200 dark:bg-slate-700" />
                        {/* 派生组：振幅 + 量比 */}
                        <span className="text-slate-600 dark:text-slate-300">
                            <span
                                className="text-slate-400"
                                title="今日 (高-低) / 昨收"
                            >
                                振幅
                            </span>{' '}
                            {decisionSnapshot?.amplitude_pct != null
                                ? `${decisionSnapshot.amplitude_pct.toFixed(2)}%`
                                : '--'}
                            {'  '}
                            <span
                                className="text-slate-400"
                                title="今日成交量 / 过去 5 日平均成交量"
                            >
                                量比
                            </span>{' '}
                            {decisionSnapshot?.volume_ratio != null
                                ? decisionSnapshot.volume_ratio.toFixed(2)
                                : '--'}
                            {decisionSnapshot?.num != null && (
                                <>
                                    {'  '}
                                    <span className="text-slate-400">笔数</span>{' '}
                                    {fmtCompact(decisionSnapshot.num)}
                                </>
                            )}
                        </span>
                    </div>
                    {/* 信号徽章行：MA / MACD / KDJ / RSI */}
                    <div className="mt-1 flex flex-wrap items-center gap-1.5">
                        {asNumber(auctionSnapshot?.gap_pct) != null && (
                            <SignalChip
                                text={`竞价缺口 ${asNumber(auctionSnapshot?.gap_pct)! >= 0 ? '+' : ''}${asNumber(auctionSnapshot?.gap_pct)!.toFixed(2)}%`}
                                tone={asNumber(auctionSnapshot?.gap_pct)! >= 0 ? 'bullish' : 'bearish'}
                            />
                        )}
                        {asNumber(auctionSnapshot?.bull_bear_ratio) != null && (
                            <SignalChip
                                text={`竞价多空比 ${asNumber(auctionSnapshot?.bull_bear_ratio)!.toFixed(2)}`}
                                tone={asNumber(auctionSnapshot?.bull_bear_ratio)! >= 1 ? 'bullish' : 'neutral'}
                            />
                        )}
                        {asNumber(cyqSummary?.locked_ratio) != null && (
                            <SignalChip
                                text={`套牢盘 ${asNumber(cyqSummary?.locked_ratio)!.toFixed(1)}%`}
                                tone={asNumber(cyqSummary?.locked_ratio)! > 70 ? 'bearish' : 'neutral'}
                            />
                        )}
                        {asNumber(cyqSummary?.win_rate) != null && (
                            <SignalChip
                                text={`胜率 ${asNumber(cyqSummary?.win_rate)!.toFixed(1)}%`}
                                tone={asNumber(cyqSummary?.win_rate)! >= 50 ? 'bullish' : 'bearish'}
                            />
                        )}
                        {asNumber(factorSnapshot?.main_net_inflow_rate) != null && (
                            <SignalChip
                                text={`主力净流入率 ${asNumber(factorSnapshot?.main_net_inflow_rate)!.toFixed(2)}%`}
                                tone={asNumber(factorSnapshot?.main_net_inflow_rate)! >= 0 ? 'bullish' : 'bearish'}
                            />
                        )}
                        {asNumber(factorSnapshot?.momentum_pctile_60d) != null && (
                            <SignalChip
                                text={`动量分位 ${fmtNum(asNumber(factorSnapshot?.momentum_pctile_60d), 2)}`}
                                tone="neutral"
                            />
                        )}
                        <SignalChip text={decisionSignals.ma.text} tone={decisionSignals.ma.tone} />
                        <SignalChip text={decisionSignals.macd.text} tone={decisionSignals.macd.tone} />
                        <SignalChip text={decisionSignals.kdj.text} tone={decisionSignals.kdj.tone} />
                        <SignalChip text={decisionSignals.rsi.text} tone={decisionSignals.rsi.tone} />
                        {!!corpEventMarkers.length && (
                            <span className="rounded border border-violet-300 bg-violet-50 px-1.5 py-0.5 text-[10px] text-violet-700 dark:border-violet-600/40 dark:bg-violet-900/20 dark:text-violet-300">
                                近30天事件 {corpEventMarkers.length}
                            </span>
                        )}
                        <span className="ml-auto text-[10px] text-slate-400 dark:text-slate-500">
                            {decisionSnapshot?.trade_time ? `更新 ${decisionSnapshot.trade_time}` : '等待交易日数据'}
                        </span>
                    </div>
                </div>
            ) : null}
            {cyqDistribution.length > 0 && (
                <div className="mx-1 shrink-0 rounded-md border border-slate-200/80 bg-white/60 px-2 py-1 dark:border-slate-700 dark:bg-slate-900/40">
                    <div className="mb-1 flex items-center justify-between text-[10px] text-slate-500 dark:text-slate-400">
                        <span>筹码峰图（右侧价位密度）</span>
                        <span>{cyqDistribution.length} 档</span>
                    </div>
                    <div className="flex h-10 items-end gap-[2px]">
                        {cyqDistribution.slice(-40).map((d, idx) => {
                            const ratio = Number(d.ratio) || 0
                            const barClass =
                                ratio > 0.08
                                    ? 'h-full opacity-95'
                                    : ratio > 0.05
                                      ? 'h-4/5 opacity-80'
                                      : ratio > 0.02
                                        ? 'h-3/5 opacity-70'
                                        : 'h-2/5 opacity-55'
                            return (
                                <span
                                    key={`${d.price}-${idx}`}
                                    className={`w-1 flex-1 rounded-sm bg-violet-400 ${barClass}`}
                                    title={`${d.price.toFixed(2)} / ${(ratio * 100).toFixed(2)}%`}
                                />
                            )
                        })}
                    </div>
                </div>
            )}
            <AdvancedMarketPanel symbol={symbol} defaultCollapsed />
            {isSymbolLoading && (
                <div className="mx-1 shrink-0 rounded-md border border-slate-200/80 bg-slate-50 px-2 py-1 text-xs text-slate-500 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-300">
                    切换标的中，正在加载 K 线...
                </div>
            )}
            {loadErr && (
                <div
                    className="shrink-0 rounded border border-amber-500/40 bg-amber-500/10 px-2 py-1.5 text-xs text-amber-800 dark:text-amber-200"
                    role="alert"
                >
                    {loadErr}
                </div>
            )}
            <div ref={mainRef} className="w-full min-h-[280px] flex-[3]" />
            <div ref={volRef} className="w-full h-[90px] shrink-0" />
            <div ref={subRef} className="w-full h-[130px] shrink-0" />
        </div>
    )
}
