import { useState, useRef, useCallback, type KeyboardEvent } from 'react'
import { Search, BarChart3, Sparkles, HelpCircle, Info, Loader2 } from 'lucide-react'
import { api } from '@/services/api'
import { normalizeCnAshareSymbol } from '@/lib/cnSymbol'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { pickBestStockSearchResult } from '@/lib/stockSearchMatch'
import type { ChartRangePreset, KlineAdjust, KlinePeriod, SubChartType } from '@/types'
import { CHART_COMPARE_ENABLED, useChartStore } from '@/stores/chartStore'
import { useAuthStore } from '@/stores/authStore'
import { stockDisplayLabel } from '@/utils/stockDisplay'

const RANGE_PRESETS: { id: ChartRangePreset; label: string }[] = [
    { id: '1M', label: '1M' },
    { id: '3M', label: '3M' },
    { id: '6M', label: '6M' },
    { id: 'YTD', label: 'YTD' },
    { id: '1Y', label: '1Y' },
    { id: '3Y', label: '3Y' },
    { id: '5Y', label: '5Y' },
    { id: 'ALL', label: 'ALL' },
]

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

const CODE_RE = /^(\d{6})\.(SH|SZ|BJ)$/i

export default function ChartToolbar({
    onAiInsight,
    onTour,
}: {
    onAiInsight: () => void
    onTour?: () => void
}) {
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
        subChart,
        setSubChart,
        liveDailyEnabled,
        setLiveDailyEnabled,
        setInsightOpen,
    } = useChartStore()
    const user = useAuthStore((s) => s.user)
    const [q, setQ] = useState('')
    const [searching, setSearching] = useState(false)
    const [searchErr, setSearchErr] = useState<string | null>(null)
    const searchAbortRef = useRef<AbortController | null>(null)
    const submitSeqRef = useRef(0)

    const pickSymbol = useCallback(
        (sym: string, displayName?: string | null, displayLabel?: string | null) => {
            const s = sym.trim().toUpperCase()
            setSymbol(s, { name: displayName ?? undefined, display_label: displayLabel ?? undefined })
            setQ('')
            setSearchErr(null)
        },
        [setSymbol],
    )

    /** 无下拉联想：仅点击「加载」或回车时解析标的；6 位代码本地规范化，名称走 `/stock-search` */
    const applySymbolFromInput = useCallback(async () => {
        const trimmed = q.trim()
        if (!trimmed) return

        setSearchErr(null)
        searchAbortRef.current?.abort()
        const ac = new AbortController()
        searchAbortRef.current = ac
        const seq = ++submitSeqRef.current

        const norm = normalizeCnAshareSymbol(trimmed)
        if (norm && CODE_RE.test(norm)) {
            setSearching(true)
            try {
                const [searchResp, fetchedName] = await Promise.all([
                    api.searchStocks(norm, ac.signal).catch(() => ({ results: [] })),
                    fetchAshareDisplayName(norm, ac.signal),
                ])
                if (seq !== submitSeqRef.current) return
                const row = pickBestStockSearchResult(norm, searchResp.results || [])
                const name = row?.name?.trim() || fetchedName
                const dl = row?.display_label?.trim() || null
                if (name) {
                    pickSymbol((row?.symbol || norm).trim().toUpperCase(), name, dl)
                } else {
                    pickSymbol(norm, undefined, dl ?? undefined)
                }
            } catch (e) {
                if (e instanceof Error && e.name === 'AbortError') return
                if (seq !== submitSeqRef.current) return
                pickSymbol(norm)
            } finally {
                if (seq === submitSeqRef.current) setSearching(false)
            }
            return
        }

        setSearching(true)
        try {
            const { results: r } = await api.searchStocks(trimmed, ac.signal)
            if (seq !== submitSeqRef.current) return
            const list = r || []
            if (list.length === 1) {
                pickSymbol(list[0].symbol, list[0].name, list[0].display_label ?? null)
                return
            }
            if (list.length > 1) {
                setSearchErr('匹配到多只股票，请输入更完整的名称或 6 位代码')
                return
            }
            const norm2 = normalizeCnAshareSymbol(trimmed)
            if (norm2 && CODE_RE.test(norm2)) {
                pickSymbol(norm2)
                return
            }
            setSearchErr('未找到该股票，请检查代码或名称')
        } catch (e) {
            if (e instanceof Error && e.name === 'AbortError') return
            if (seq !== submitSeqRef.current) return
            setSearchErr(e instanceof Error ? e.message : '搜索失败')
        } finally {
            if (seq === submitSeqRef.current) setSearching(false)
        }
    }, [pickSymbol, q])

    const toolbarSymbolTitle = stockDisplayLabel({
        symbol,
        name: symbolName,
        display_label: symbolDisplayLabel,
    })
    const hasRtEntitlement = user?.role === 'admin' || user?.entitlements?.tushare_rt === true
    const canToggleRt = period === '1d' && hasRtEntitlement
    const rtChipTitle = !hasRtEntitlement
        ? '需开通 Tushare A股日线RT 权益后可启用'
        : period !== '1d'
            ? '仅日K支持实时日线'
            : liveDailyEnabled
                ? 'Tushare A股日线RT 已开启（约12秒刷新）'
                : '开启后按约12秒刷新当日蜡烛与量柱'

    const onSearchKeyDown = (e: KeyboardEvent<HTMLInputElement>) => {
        if (e.key === 'Enter') {
            e.preventDefault()
            void applySymbolFromInput()
        }
    }

    return (
        <div className="flex flex-wrap items-center gap-2 p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/60 overflow-visible">
            <div className="flex flex-col gap-0.5 min-w-[240px] max-w-[min(100vw-2rem,360px)]">
                <div className="flex items-center gap-1">
                    <Search className="w-4 h-4 shrink-0 text-slate-400" />
                    <input
                        value={q}
                        onChange={(e) => {
                            setQ(e.target.value)
                            setSearchErr(null)
                        }}
                        onKeyDown={onSearchKeyDown}
                        placeholder="6 位代码或名称，回车加载"
                        className="flex-1 min-w-0 bg-transparent text-sm outline-none text-slate-900 dark:text-slate-100"
                        aria-label="股票代码或名称"
                        autoComplete="off"
                    />
                    <button
                        type="button"
                        onMouseDown={(e) => e.preventDefault()}
                        onClick={() => void applySymbolFromInput()}
                        disabled={searching || !q.trim()}
                        className="shrink-0 text-xs px-2 py-1 rounded border border-slate-200 dark:border-slate-600 bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700 disabled:opacity-50"
                    >
                        {searching ? <Loader2 className="w-3.5 h-3.5 animate-spin" /> : '加载'}
                    </button>
                </div>
                {searchErr && (
                    <p className="text-xs text-red-500 dark:text-red-400 px-1" role="alert">
                        {searchErr}
                    </p>
                )}
            </div>
            <span
                className="text-xs px-1 max-w-[min(100vw-2rem,360px)] truncate text-slate-800 dark:text-slate-100 font-medium tabular-nums"
                title={toolbarSymbolTitle}
            >
                {toolbarSymbolTitle}
            </span>
            <span
                className="inline-flex items-center text-slate-400 dark:text-slate-500"
                title="日 K 由行情源提供，盘中最后一根会随数据源更新；A 股交易时段约每 60 秒自动拉新。非交易所行情终端的逐笔/毫秒级实时数据。"
                aria-label="数据说明"
            >
                <Info className="h-3.5 w-3.5" />
            </span>

            <div className="flex items-center gap-0.5 border-l border-slate-200 dark:border-slate-600 pl-2">
                {RANGE_PRESETS.map((p) => (
                    <button
                        key={p.id}
                        type="button"
                        onClick={() => setRangePreset(p.id)}
                        className={`text-xs px-1.5 py-0.5 rounded ${
                            rangePreset === p.id
                                ? 'bg-blue-500/20 text-blue-600 dark:text-blue-400'
                                : 'text-slate-500 hover:text-slate-800 dark:hover:text-slate-200'
                        }`}
                    >
                        {p.label}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-0.5 border-l border-slate-200 dark:border-slate-600 pl-2">
                {PERIODS.map((p) => (
                    <button
                        key={p.id}
                        type="button"
                        onClick={() => setPeriod(p.id)}
                        className={`text-xs px-1.5 py-0.5 rounded ${
                            period === p.id
                                ? 'bg-violet-500/20 text-violet-600 dark:text-violet-400'
                                : 'text-slate-500'
                        }`}
                    >
                        {p.label}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-0.5 border-l border-slate-200 dark:border-slate-600 pl-2">
                {ADJUST.map((a) => (
                    <button
                        key={a.id}
                        type="button"
                        onClick={() => setAdjust(a.id)}
                        className={`text-xs px-1.5 py-0.5 rounded ${
                            adjust === a.id
                                ? 'bg-amber-500/20 text-amber-700 dark:text-amber-400'
                                : 'text-slate-500'
                        }`}
                    >
                        {a.label}
                    </button>
                ))}
            </div>

            <div className="flex items-center gap-1 border-l border-slate-200 dark:border-slate-600 pl-2">
                <BarChart3 className="w-3.5 h-3.5 text-slate-400" />
                <select
                    value={subChart}
                    onChange={(e) => setSubChart(e.target.value as SubChartType)}
                    className="chart-native-select text-xs rounded border px-1.5 py-0.5 min-w-[5rem]"
                    aria-label="副图指标"
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
                type="button"
                title={rtChipTitle}
                disabled={!canToggleRt}
                onClick={() => setLiveDailyEnabled(!liveDailyEnabled)}
                className={`inline-flex items-center gap-1 text-xs px-2 py-1 rounded border ${
                    !canToggleRt
                        ? 'border-slate-300/70 text-slate-400 dark:border-slate-700 dark:text-slate-500 cursor-not-allowed'
                        : liveDailyEnabled
                            ? 'border-cyan-500/35 bg-gradient-to-r from-cyan-600/20 to-blue-600/20 text-cyan-700 dark:text-cyan-300'
                            : 'border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300 hover:bg-slate-50 dark:hover:bg-slate-800'
                }`}
                aria-label="切换日K实时模式"
            >
                <span className={`inline-block h-1.5 w-1.5 rounded-full ${liveDailyEnabled && canToggleRt ? 'bg-emerald-500 animate-pulse' : 'bg-slate-400/70'}`} />
                实时
            </button>

            <button
                type="button"
                onClick={() => {
                    setInsightOpen(true)
                    onAiInsight()
                }}
                className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded bg-gradient-to-r from-cyan-600/20 to-blue-600/20 text-cyan-700 dark:text-cyan-300 border border-cyan-500/30"
            >
                <Sparkles className="w-3.5 h-3.5" />
                Ai助手
            </button>

            {onTour && (
                <button
                    type="button"
                    onClick={onTour}
                    className="inline-flex items-center gap-1 text-xs px-2 py-1 rounded border border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300"
                >
                    <HelpCircle className="w-3.5 h-3.5" />
                    新手引导
                </button>
            )}

            {CHART_COMPARE_ENABLED ? (
                <span className="text-[10px] text-slate-400 flex items-center gap-1 ml-auto">对比在左侧添加</span>
            ) : null}
        </div>
    )
}
