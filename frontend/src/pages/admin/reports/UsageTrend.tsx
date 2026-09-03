import { useCallback, useEffect, useMemo, useState } from 'react'
import { Bar, BarChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
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

export default function UsageTrendReport() {
    const [range, setRange] = useState<DateRangeValue>(() => defaultRange())
    const [grain, setGrain] = useState<'day' | 'hour'>('day')
    const [rows, setRows] = useState<Record<string, unknown>[]>([])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminReportsUsageTrend(toApiRange(range, grain))
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
                reserve: Number(x.reserve || 0),
                commit: Number(x.commit || 0),
                refund: Number(x.refund || 0),
                other: Number(x.other || 0),
            })),
        [rows],
    )

    return (
        <AdminPage title="用量趋势" subtitle="点数流水按类型汇总（绝对值）">
            <AdminFilterBar
                range={range}
                onRangeChange={setRange}
                onRefresh={() => void load()}
                onExportCsv={async () => {
                    const blob = await api.adminReportsExportCsvBlob('usage-trend', toApiRange(range, grain))
                    const u = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = u
                    a.download = 'usage-trend.csv'
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
                        <BarChart data={chartData}>
                            <CartesianGrid strokeDasharray="3 3" opacity={0.3} />
                            <XAxis dataKey="ts" tick={{ fontSize: 10 }} />
                            <YAxis tick={{ fontSize: 10 }} />
                            <Tooltip />
                            <Legend />
                            <Bar dataKey="reserve" stackId="a" name="预扣" fill="#f97316" />
                            <Bar dataKey="commit" stackId="a" name="确认" fill="#22c55e" />
                            <Bar dataKey="refund" stackId="a" name="退款" fill="#94a3b8" />
                            <Bar dataKey="other" stackId="a" name="其他" fill="#a855f7" />
                        </BarChart>
                    </ResponsiveContainer>
                )}
            </div>
        </AdminPage>
    )
}
