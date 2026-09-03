import { useCallback, useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminFilterBar, { type DateRangeValue } from '@/pages/admin/components/AdminFilterBar'
import AdminPage from '@/pages/admin/components/AdminPage'
import AdminStatCard from '@/pages/admin/components/AdminStatCard'

function defaultRange(): DateRangeValue {
    const to = new Date()
    const from = new Date(to)
    from.setUTCDate(from.getUTCDate() - 13)
    return { startDate: from.toISOString().slice(0, 10), endDate: to.toISOString().slice(0, 10) }
}

export default function OpsStatsReport() {
    const [range, setRange] = useState<DateRangeValue>(() => defaultRange())
    const [data, setData] = useState<Record<string, unknown> | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminReportsOpsStats({ start_date: range.startDate, end_date: range.endDate })
            setData(d)
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        } finally {
            setLoading(false)
        }
    }, [range])

    useEffect(() => {
        void load()
    }, [load])

    const top = (data?.top_credit_users as { user_id?: string; credits_used?: number }[] | undefined) || []

    return (
        <AdminPage title="运营统计" subtitle="周期内报告成功/失败、ARPU（运营口径）与高点数用户">
            <AdminFilterBar
                range={range}
                onRangeChange={setRange}
                onRefresh={() => void load()}
                onExportCsv={async () => {
                    const blob = await api.adminReportsExportCsvBlob('ops-stats', {
                        start_date: range.startDate,
                        end_date: range.endDate,
                        grain: 'day',
                    })
                    const u = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = u
                    a.download = 'ops-stats.csv'
                    a.click()
                    URL.revokeObjectURL(u)
                }}
                loading={loading}
            />
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            {data ? (
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    <AdminStatCard label="用户总数" value={Number(data.total_users || 0)} />
                    <AdminStatCard label="有效订阅用户(近似)" value={Number(data.active_subscription_users || 0)} />
                    <AdminStatCard label="报告成功" value={Number(data.reports_completed || 0)} />
                    <AdminStatCard label="报告失败" value={Number(data.reports_failed || 0)} />
                    <AdminStatCard
                        label="ARPU（分/运营口径）"
                        value={Number(data.arpu_cents_operational || 0)}
                        hint="周期收入分 / 付费用户数"
                    />
                </div>
            ) : null}
            <div className="mt-6">
                <h2 className="text-sm font-semibold mb-2">Top 点数消耗用户</h2>
                {top.length === 0 ? (
                    <div className="text-sm text-slate-500">无数据</div>
                ) : (
                    <ul className="text-sm space-y-1 font-mono">
                        {top.map((t) => (
                            <li key={t.user_id}>
                                {t.user_id} — {t.credits_used}
                            </li>
                        ))}
                    </ul>
                )}
            </div>
        </AdminPage>
    )
}
