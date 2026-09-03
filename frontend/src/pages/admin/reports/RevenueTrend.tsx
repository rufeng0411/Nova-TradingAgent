import { useCallback, useEffect, useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api, type AdminDateRangeParams } from '@/services/api'
import AdminFilterBar, { type DateRangeValue } from '@/pages/admin/components/AdminFilterBar'
import AdminPage from '@/pages/admin/components/AdminPage'

function defaultRange(): DateRangeValue {
    const to = new Date()
    const from = new Date(to)
    from.setUTCDate(from.getUTCDate() - 13)
    return { startDate: from.toISOString().slice(0, 10), endDate: to.toISOString().slice(0, 10) }
}

function toApiRange(r: DateRangeValue, grain: 'day' | 'hour'): AdminDateRangeParams {
    return { start_date: r.startDate, end_date: r.endDate, grain }
}

export default function RevenueTrendReport() {
    const [range, setRange] = useState<DateRangeValue>(() => defaultRange())
    const [grain, setGrain] = useState<'day' | 'hour'>('day')
    const [rows, setRows] = useState<Record<string, unknown>[]>([])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminReportsRevenueTrend(toApiRange(range, grain))
            setRows((d.items || []) as Record<string, unknown>[])
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        } finally {
            setLoading(false)
        }
    }, [range, grain])

    useEffect(() => {
        void load()
    }, [load])

    const chartData = useMemo(
        () =>
            rows.map((x) => ({
                ts: String(x.ts || '').slice(0, 10),
                revenue_yuan: Number(x.revenue_cents_operational || 0) / 100,
            })),
        [rows],
    )

    return (
        <AdminPage
            title="收入趋势"
            subtitle="运营口径：新建订阅对应套餐标价之和（分→元），非实收"
        >
            <AdminFilterBar
                range={range}
                onRangeChange={setRange}
                onRefresh={() => void load()}
                onExportCsv={async () => {
                    const blob = await api.adminReportsExportCsvBlob('revenue-trend', toApiRange(range, grain))
                    const u = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = u
                    a.download = 'revenue-trend.csv'
                    a.click()
                    URL.revokeObjectURL(u)
                }}
                grain={grain}
                onGrainChange={setGrain}
                loading={loading}
            />
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-4 h-96">
                {!loading && chartData.length === 0 ? (
                    <div className="text-sm text-slate-500 py-12 text-center">当前日期范围无数据</div>
                ) : (
                    <ResponsiveContainer width="100%" height="100%">
                        <LineChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                            <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} />
                            <Tooltip formatter={(v: number) => [`${v.toFixed(2)} 元`, '运营收入']} />
                            <Legend />
                            <Line type="monotone" dataKey="revenue_yuan" name="运营收入(元)" stroke="#f59e0b" dot={false} />
                        </LineChart>
                    </ResponsiveContainer>
                )}
            </div>
        </AdminPage>
    )
}
