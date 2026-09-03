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

export default function FeatureTokenReport() {
    const [range, setRange] = useState<DateRangeValue>(() => defaultRange())
    const [data, setData] = useState<Record<string, unknown> | null>(null)
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminReportsFeatureToken({ start_date: range.startDate, end_date: range.endDate })
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

    return (
        <AdminPage title="功能与 Token" subtitle={String(data?.note || 'API Token 使用概况')}>
            <AdminFilterBar
                range={range}
                onRangeChange={setRange}
                onRefresh={() => void load()}
                onExportCsv={async () => {
                    const blob = await api.adminReportsExportCsvBlob('feature-token', {
                        start_date: range.startDate,
                        end_date: range.endDate,
                    })
                    const u = URL.createObjectURL(blob)
                    const a = document.createElement('a')
                    a.href = u
                    a.download = 'feature-token.csv'
                    a.click()
                    URL.revokeObjectURL(u)
                }}
                loading={loading}
            />
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            {data ? (
                <div className="grid sm:grid-cols-2 gap-4">
                    <AdminStatCard label="活跃 API Token 数" value={Number(data.api_tokens_active || 0)} />
                    <AdminStatCard label="周期内有使用记录的 Token" value={Number(data.api_tokens_used_in_period || 0)} />
                </div>
            ) : null}
        </AdminPage>
    )
}
