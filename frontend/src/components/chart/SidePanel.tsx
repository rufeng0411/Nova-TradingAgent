import { X, Plus } from 'lucide-react'
import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { CHART_COMPARE_ENABLED, useChartStore, type KlineHistoryEntry } from '@/stores/chartStore'
import { normalizeCnAshareSymbol } from '@/lib/cnSymbol'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/services/api'
import type { WatchlistItem } from '@/types'
import { EXCHANGE_LISTED_SYMBOL_RE, stockDisplayLabel } from '@/utils/stockDisplay'

function historyRowSym(entry: KlineHistoryEntry): string {
    return normalizeCnAshareSymbol(entry.symbol.trim()) || entry.symbol.trim().toUpperCase()
}

/** 展示串中尚无中文简称时，尝试用 search 补全（仅沪深京 listed） */
function klineHistoryNeedsNameFetch(entry: KlineHistoryEntry): boolean {
    const sym = historyRowSym(entry)
    if (!EXCHANGE_LISTED_SYMBOL_RE.test(sym)) return false
    const label = stockDisplayLabel({
        symbol: entry.symbol,
        name: entry.name,
        display_label: entry.display_label,
    })
    return !/[\u4e00-\u9fff]/.test(label)
}

function CompareSection() {
    const { compareSymbols, addCompareSymbol, removeCompareSymbol } = useChartStore()
    const [add, setAdd] = useState('')

    return (
        <div>
            <p className="font-medium text-slate-600 dark:text-slate-300 mb-1">对比 (最多4)</p>
            <div className="flex gap-1">
                <input
                    value={add}
                    onChange={(e) => setAdd(e.target.value.toUpperCase())}
                    placeholder="600519 或 600519.SH"
                    className="flex-1 min-w-0 rounded border border-slate-200 dark:border-slate-600 bg-white dark:bg-slate-800 px-1 py-0.5 font-mono"
                />
                <button
                    type="button"
                    title="添加对比标的"
                    onClick={() => {
                        if (add) {
                            addCompareSymbol(add)
                            setAdd('')
                        }
                    }}
                    className="p-1 rounded bg-blue-500/20 text-blue-600"
                >
                    <Plus className="w-3 h-3" />
                </button>
            </div>
            <ul className="mt-1 space-y-0.5">
                {compareSymbols.map((s) => (
                    <li key={s} className="flex items-center justify-between gap-1 font-mono">
                        <span className="truncate">{s}</span>
                        <button type="button" title="移除" onClick={() => removeCompareSymbol(s)} className="text-slate-400 hover:text-red-500">
                            <X className="w-3 h-3" />
                        </button>
                    </li>
                ))}
            </ul>
        </div>
    )
}

function ShortcutChip({
    label,
    sub,
    active,
    onClick,
    variant,
}: {
    label: string
    sub?: string
    active: boolean
    onClick: () => void
    variant: 'scheduled' | 'history'
}) {
    const base =
        variant === 'scheduled'
            ? active
                ? 'border-emerald-500/70 bg-emerald-500/15 text-emerald-900 dark:text-emerald-100'
                : 'border-emerald-500/25 bg-emerald-500/[0.06] hover:bg-emerald-500/10 text-slate-800 dark:text-slate-100'
            : active
              ? 'border-sky-500/70 bg-sky-500/15 text-sky-950 dark:text-sky-50'
              : 'border-slate-300/80 bg-white/80 hover:bg-slate-50 dark:border-slate-600 dark:bg-slate-800/60 dark:hover:bg-slate-800'
    return (
        <button
            type="button"
            title={sub ? `${label} · ${sub}` : label}
            onClick={onClick}
            className={`w-full rounded-md border px-1.5 py-1 text-left text-[11px] leading-tight transition-colors ${base}`}
        >
            <span className="block truncate font-medium">{label}</span>
            {sub ? <span className="block truncate font-mono text-[10px] opacity-80">{sub}</span> : null}
        </button>
    )
}

export default function SidePanel() {
    const { ma, setMa, showBoll, setShowBoll, symbol, setSymbol, klineQueryHistory, patchKlineQueryHistoryMeta } =
        useChartStore()
    const user = useAuthStore((s) => s.user)
    const [scheduledWatchlist, setScheduledWatchlist] = useState<WatchlistItem[]>([])
    const [wlErr, setWlErr] = useState<string | null>(null)

    const loadScheduled = useCallback(async () => {
        if (!user) {
            setScheduledWatchlist([])
            setWlErr(null)
            return
        }
        try {
            const overview = await api.getPortfolioOverview()
            const list = (overview.watchlist || []).filter((w) => w.has_scheduled)
            setScheduledWatchlist(list)
            setWlErr(null)
        } catch {
            setScheduledWatchlist([])
            setWlErr('自选列表加载失败')
        }
    }, [user])

    useEffect(() => {
        void loadScheduled()
    }, [loadScheduled])

    /** 最近查询：持久化里常只有代码，补拉中文名后统一为「名称 代码」 */
    useEffect(() => {
        let cancelled = false
        const todo = klineQueryHistory.filter(klineHistoryNeedsNameFetch)
        if (todo.length === 0) return

        const run = async () => {
            for (const e of todo) {
                if (cancelled) break
                const sym = historyRowSym(e)
                const n = await fetchAshareDisplayName(sym)
                if (cancelled || !n?.trim()) continue
                patchKlineQueryHistoryMeta(sym, { name: n.trim() })
            }
        }
        void run()
        return () => {
            cancelled = true
        }
    }, [klineQueryHistory, patchKlineQueryHistoryMeta])

    const chartActiveNorm = normalizeCnAshareSymbol(symbol.trim()) || symbol.trim().toUpperCase()

    return (
        <aside className="w-[11.5rem] shrink-0 space-y-3 p-2 rounded-lg border border-slate-200 dark:border-slate-700 bg-slate-50/80 dark:bg-slate-900/40 text-xs max-h-[min(100vh-8rem,720px)] overflow-y-auto">
            <div className="rounded-lg border border-emerald-200/80 bg-emerald-50/40 p-2 dark:border-emerald-500/25 dark:bg-emerald-950/20">
                <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-emerald-800 dark:text-emerald-300">
                        自选·定时
                    </span>
                    <span className="rounded bg-emerald-600/15 px-1 py-px text-[9px] font-medium text-emerald-700 dark:text-emerald-400">
                        定时任务
                    </span>
                </div>
                {!user ? (
                    <p className="text-[10px] leading-snug text-slate-500 dark:text-slate-400">
                        <Link className="text-emerald-700 underline dark:text-emerald-400" to="/login">
                            登录
                        </Link>
                        后显示已开启定时分析的自选标的。
                    </p>
                ) : wlErr ? (
                    <p className="text-[10px] text-amber-700 dark:text-amber-400">{wlErr}</p>
                ) : scheduledWatchlist.length === 0 ? (
                    <p className="text-[10px] leading-snug text-slate-500 dark:text-slate-400">
                        暂无定时自选。在{' '}
                        <Link className="text-emerald-700 underline dark:text-emerald-400" to="/portfolio">
                            自选
                        </Link>{' '}
                        中为标的开启「定时」。
                    </p>
                ) : (
                    <ul className="space-y-1">
                        {scheduledWatchlist.map((w) => {
                            const rowSym = normalizeCnAshareSymbol(w.symbol.trim()) || w.symbol.trim().toUpperCase()
                            const title = stockDisplayLabel({
                                symbol: w.symbol,
                                name: w.name,
                                display_label: w.display_label,
                            })
                            return (
                                <li key={w.id}>
                                    <ShortcutChip
                                        variant="scheduled"
                                        label={title}
                                        active={chartActiveNorm === rowSym}
                                        onClick={() =>
                                            setSymbol(w.symbol, {
                                                name: w.name?.trim() || undefined,
                                                display_label: w.display_label ?? undefined,
                                            })
                                        }
                                    />
                                </li>
                            )
                        })}
                    </ul>
                )}
            </div>

            <div className="rounded-lg border border-slate-200 bg-white/70 p-2 dark:border-slate-600 dark:bg-slate-900/50">
                <div className="flex items-center justify-between gap-1 mb-1.5">
                    <span className="text-[10px] font-semibold uppercase tracking-wide text-slate-600 dark:text-slate-300">
                        最近查询
                    </span>
                    <span className="rounded bg-slate-500/15 px-1 py-px text-[9px] font-medium text-slate-600 dark:text-slate-400">
                        最多10条
                    </span>
                </div>
                {klineQueryHistory.length === 0 ? (
                    <p className="text-[10px] leading-snug text-slate-500 dark:text-slate-400">在上方搜索或智能分析切换标的后会出现在此。</p>
                ) : (
                    <ul className="space-y-1">
                        {klineQueryHistory.map((entry) => {
                            const rowSym = historyRowSym(entry)
                            const title = stockDisplayLabel({
                                symbol: entry.symbol,
                                name: entry.name,
                                display_label: entry.display_label,
                            })
                            return (
                                <li key={rowSym}>
                                    <ShortcutChip
                                        variant="history"
                                        label={title}
                                        active={chartActiveNorm === rowSym}
                                        onClick={() =>
                                            setSymbol(entry.symbol, {
                                                name: entry.name?.trim() || undefined,
                                                display_label: entry.display_label ?? undefined,
                                            })
                                        }
                                    />
                                </li>
                            )
                        })}
                    </ul>
                )}
            </div>

            <div>
                <p className="font-medium text-slate-600 dark:text-slate-300 mb-1">均线</p>
                {(
                    [
                        ['ma5', 'MA5'],
                        ['ma10', 'MA10'],
                        ['ma20', 'MA20'],
                        ['ma60', 'MA60'],
                    ] as const
                ).map(([k, label]) => (
                    <label key={k} className="flex items-center gap-2 py-0.5 cursor-pointer">
                        <input type="checkbox" checked={ma[k]} onChange={() => setMa({ [k]: !ma[k] })} />
                        {label}
                    </label>
                ))}
                <label className="flex items-center gap-2 py-0.5 cursor-pointer mt-1">
                    <input type="checkbox" checked={showBoll} onChange={() => setShowBoll(!showBoll)} />
                    布林带
                </label>
            </div>
            {CHART_COMPARE_ENABLED ? <CompareSection /> : null}
        </aside>
    )
}
