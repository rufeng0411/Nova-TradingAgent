import { useCallback, useEffect, useMemo, useState } from 'react'
import { Loader2 } from 'lucide-react'
import {
    CartesianGrid,
    Legend,
    Line,
    LineChart,
    ResponsiveContainer,
    Tooltip,
    XAxis,
    YAxis,
} from 'recharts'
import { api } from '@/services/api'
import { useAdminEvents } from '@/hooks/useAdminEvents'
import { useAuthStore } from '@/stores/authStore'

function mergeByTs(items: { ts: string; key: string; value: number }[]) {
    const map = new Map<string, Record<string, string | number>>()
    for (const p of items) {
        const row = map.get(p.ts) || { ts: p.ts.slice(0, 10) }
        row[p.key] = p.value
        map.set(p.ts, row)
    }
    return Array.from(map.values()).sort((a, b) => String(a.ts).localeCompare(String(b.ts)))
}

function mergeOutcomeByMonth(items: { release_version: string; month: string; weighted_hit_rate: number }[]) {
    const rows = new Map<string, Record<string, string | number>>()
    for (const it of items) {
        const month = it.month || '--'
        const row = rows.get(month) || { month }
        row[it.release_version || 'dev'] = Number((it.weighted_hit_rate * 100).toFixed(2))
        rows.set(month, row)
    }
    return Array.from(rows.values()).sort((a, b) => String(a.month).localeCompare(String(b.month)))
}

export default function AdminDashboard() {
    const { user, token } = useAuthStore()
    const [d, setD] = useState<{
        total_users: number
        users_today: number
        credits_consumed_today: number
        active_subscriptions: number
    } | null>(null)
    const [series, setSeries] = useState<{ ts: string; key: string; value: number }[]>([])
    const [p95, setP95] = useState<{ ts: string; value: number }[]>([])
    const [outcomeTrend, setOutcomeTrend] = useState<{ release_version: string; month: string; weighted_hit_rate: number }[]>([])
    const [granularity, setGranularity] = useState<'day' | 'hour'>('day')
    const [err, setErr] = useState<string | null>(null)
    const [liveHint, setLiveHint] = useState<string | null>(null)

    const range = useMemo(() => {
        const to = new Date()
        const from = new Date(to)
        if (granularity === 'day') {
            from.setUTCDate(from.getUTCDate() - 29)
            from.setUTCHours(0, 0, 0, 0)
        } else {
            from.setUTCHours(from.getUTCHours() - 24, 0, 0, 0)
        }
        return { from: from.toISOString(), to: to.toISOString() }
    }, [granularity])

    const load = useCallback(async () => {
        setErr(null)
        try {
            const [dash, ov, tr, outcome] = await Promise.all([
                api.adminDashboard(),
                api.adminMetricsOverview({ from: range.from, to: range.to, granularity }),
                api.adminMetricsTraffic({ from: range.from, to: range.to, granularity }),
                api.adminReportsOutcomeTrend({ days: 90, group_by: 'release_version' }),
            ])
            setD(dash)
            setSeries(ov.items || [])
            setP95((tr.p95 || []).map((x) => ({ ts: x.ts.slice(0, 10), value: x.value })))
            setOutcomeTrend(outcome.items || [])
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        }
    }, [range.from, range.to, granularity])

    useEffect(() => {
        void load()
    }, [load])

    const onEvent = useCallback(() => {
        setLiveHint('指标已更新（最近事件）')
        window.setTimeout(() => setLiveHint(null), 4000)
        void load()
    }, [load])

    useAdminEvents(Boolean(user?.role === 'admin' && token), onEvent)

    const chartRows = useMemo(() => mergeByTs(series), [series])
    const outcomeRows = useMemo(() => mergeOutcomeByMonth(outcomeTrend), [outcomeTrend])
    const outcomeKeys = useMemo(() => {
        const keys = new Set<string>()
        for (const row of outcomeTrend) {
            keys.add(row.release_version || 'dev')
        }
        return Array.from(keys).sort()
    }, [outcomeTrend])

    if (err && !d) return <p className="text-rose-600">{err}</p>
    if (!d) {
        return (
            <div className="flex justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        )
    }

    const cards = [
        { label: '用户总数', value: d.total_users },
        { label: '今日新增', value: d.users_today },
        { label: '今日消耗点数', value: d.credits_consumed_today },
        { label: '有效订阅', value: d.active_subscriptions },
    ]

    return (
        <div className="space-y-6">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-xl font-bold">运营概览</h1>
                <div className="flex items-center gap-2">
                    <span className="text-xs text-slate-500">粒度</span>
                    <select
                        aria-label="时间粒度"
                        value={granularity}
                        onChange={(e) => setGranularity(e.target.value as 'day' | 'hour')}
                        className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm px-2 py-1"
                    >
                        <option value="day">按天</option>
                        <option value="hour">按小时（近窗）</option>
                    </select>
                </div>
            </div>
            {liveHint && <div className="text-sm text-emerald-600">{liveHint}</div>}
            {err && <div className="text-sm text-rose-600">{err}</div>}
            <div className="grid sm:grid-cols-2 lg:grid-cols-4 gap-4">
                {cards.map((c) => (
                    <div
                        key={c.label}
                        className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-5 shadow-sm"
                    >
                        <div className="text-xs text-slate-500">{c.label}</div>
                        <div className="mt-2 text-2xl font-bold font-mono">{c.value}</div>
                    </div>
                ))}
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-4 h-80">
                <div className="text-sm font-medium mb-2">趋势（用户 / 访问 / 点数 / 订阅）</div>
                <ResponsiveContainer width="100%" height="90%">
                    <LineChart data={chartRows}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                        <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Legend />
                        <Line type="monotone" dataKey="users.new_registrations" name="新用户" stroke="#2563eb" dot={false} />
                        <Line type="monotone" dataKey="access.requests" name="访问" stroke="#64748b" dot={false} />
                        <Line type="monotone" dataKey="credits.reserve_volume" name="点数 reserve" stroke="#f97316" dot={false} />
                        <Line type="monotone" dataKey="subscriptions.new" name="新订阅" stroke="#10b981" dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-4 h-64">
                <div className="text-sm font-medium mb-2">延迟 P95（ms）</div>
                <ResponsiveContainer width="100%" height="85%">
                    <LineChart data={p95}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                        <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} />
                        <Tooltip />
                        <Line type="monotone" dataKey="value" name="P95" stroke="#a855f7" dot={false} />
                    </LineChart>
                </ResponsiveContainer>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-4 h-72">
                <div className="text-sm font-medium mb-2">月度加权命中率（%）</div>
                <ResponsiveContainer width="100%" height="85%">
                    <LineChart data={outcomeRows}>
                        <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                        <XAxis dataKey="month" tick={{ fontSize: 10 }} />
                        <YAxis tick={{ fontSize: 10 }} domain={[0, 100]} />
                        <Tooltip />
                        <Legend />
                        {outcomeKeys.map((k, idx) => {
                            const palette = ['#2563eb', '#10b981', '#f97316', '#a855f7', '#ef4444', '#14b8a6']
                            return <Line key={k} type="monotone" dataKey={k} name={k} stroke={palette[idx % palette.length]} dot={false} />
                        })}
                    </LineChart>
                </ResponsiveContainer>
            </div>
        </div>
    )
}
