import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'

import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'
import type { RtBoardResponse } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'

const PRESETS = [
    { label: '上交所主板', pattern: '6*.SH' },
    { label: '创业板', pattern: '3*.SZ' },
    { label: '科创板', pattern: '688*.SH' },
    { label: '北交所', pattern: '9*.BJ' },
] as const

type SortKey = 'change_pct' | 'change' | 'amount' | 'vol'

function formatNum(v: unknown, digits = 2): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '--'
    return n.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '')
}

export default function RealtimeBoard() {
    const user = useAuthStore((s) => s.user)
    const hasRtEntitlement = user?.role === 'admin' || user?.entitlements?.tushare_rt === true
    const [pattern, setPattern] = useState<string>(PRESETS[0].pattern)
    const [sort, setSort] = useState<SortKey>('change_pct')
    const [limit, setLimit] = useState(50)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [data, setData] = useState<RtBoardResponse | null>(null)

    useEffect(() => {
        if (!hasRtEntitlement) return
        let stopped = false
        const run = async () => {
            setLoading(true)
            setError(null)
            try {
                const res = await api.getRtBoard(pattern, sort, limit)
                if (stopped) return
                setData(res)
            } catch (e) {
                if (stopped) return
                setError(e instanceof Error ? e.message : '实时盘加载失败')
            } finally {
                if (!stopped) setLoading(false)
            }
        }
        void run()
        const id = window.setInterval(() => {
            if (document.visibilityState !== 'visible') return
            void run()
        }, 12_000)
        const onVis = () => {
            if (document.visibilityState === 'visible') void run()
        }
        document.addEventListener('visibilitychange', onVis)
        return () => {
            stopped = true
            document.removeEventListener('visibilitychange', onVis)
            clearInterval(id)
        }
    }, [hasRtEntitlement, limit, pattern, sort])

    const rows = useMemo(() => data?.items ?? [], [data])

    if (!hasRtEntitlement) {
        return (
            <div className="rounded-lg border border-dashed border-slate-300 bg-white/80 dark:border-slate-700 dark:bg-slate-900/40 p-5 text-sm text-slate-600 dark:text-slate-300">
                实时盘需要开通 Tushare A股日线RT 权益。
                <Link to="/subscription" className="ml-2 text-cyan-600 dark:text-cyan-400 underline">
                    前往订阅
                </Link>
            </div>
        )
    }

    return (
        <div className="space-y-3">
            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/40 p-3">
                <div className="flex flex-wrap items-center gap-2">
                    {PRESETS.map((p) => (
                        <button
                            key={p.pattern}
                            type="button"
                            onClick={() => setPattern(p.pattern)}
                            className={`px-2 py-1 text-xs rounded border ${
                                pattern === p.pattern
                                    ? 'border-cyan-500/40 bg-cyan-500/15 text-cyan-700 dark:text-cyan-300'
                                    : 'border-slate-300 dark:border-slate-600 text-slate-600 dark:text-slate-300'
                            }`}
                        >
                            {p.label}
                        </button>
                    ))}
                    <select
                        value={sort}
                        onChange={(e) => setSort(e.target.value as SortKey)}
                        className="text-xs rounded border border-slate-300 dark:border-slate-600 bg-transparent px-2 py-1"
                        aria-label="实时盘排序"
                    >
                        <option value="change_pct">按涨跌幅</option>
                        <option value="change">按涨跌额</option>
                        <option value="amount">按成交额</option>
                        <option value="vol">按成交量</option>
                    </select>
                    <select
                        value={limit}
                        onChange={(e) => setLimit(Number(e.target.value))}
                        className="text-xs rounded border border-slate-300 dark:border-slate-600 bg-transparent px-2 py-1"
                        aria-label="实时盘条数"
                    >
                        <option value={20}>20</option>
                        <option value={50}>50</option>
                        <option value={100}>100</option>
                    </select>
                    <span className="text-[11px] text-slate-500 dark:text-slate-400 ml-auto">
                        {loading ? '刷新中…' : '约 12 秒刷新'}
                    </span>
                </div>
            </div>

            <div className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white/80 dark:bg-slate-900/40 overflow-auto">
                {error ? <p className="p-3 text-sm text-red-500">{error}</p> : null}
                <table className="min-w-full text-xs">
                    <thead className="sticky top-0 bg-slate-100/95 dark:bg-slate-800/95 text-slate-600 dark:text-slate-300">
                        <tr>
                            <th className="px-2 py-2 text-left">标的</th>
                            <th className="px-2 py-2 text-right">最新</th>
                            <th className="px-2 py-2 text-right">涨跌额</th>
                            <th className="px-2 py-2 text-right">涨跌幅%</th>
                            <th className="px-2 py-2 text-right">成交量</th>
                            <th className="px-2 py-2 text-right">成交额</th>
                            <th className="px-2 py-2 text-right">笔数</th>
                            <th className="px-2 py-2 text-right">买一/卖一</th>
                            <th className="px-2 py-2 text-right">时间</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((raw, idx) => {
                            const row = raw as Record<string, unknown>
                            const symbol = String(row.symbol ?? '')
                            const name = (row.name as string | undefined) ?? undefined
                            return (
                                <tr key={`${symbol}-${idx}`} className="border-t border-slate-100 dark:border-slate-800">
                                    <td className="px-2 py-1.5">{stockDisplayLabel({ symbol, name })}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.close)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.change)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.change_pct)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.vol, 0)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.amount, 0)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{formatNum(row.num, 0)}</td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">
                                        {formatNum(row.bid_price1)} / {formatNum(row.ask_price1)}
                                    </td>
                                    <td className="px-2 py-1.5 text-right tabular-nums">{String(row.trade_time ?? '--')}</td>
                                </tr>
                            )
                        })}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
