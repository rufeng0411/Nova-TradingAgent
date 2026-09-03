import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function CommercePricing() {
    const [rows, setRows] = useState<Record<string, unknown>[]>([])
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminCommercePricingTable()
            .then(setRows)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="计费表格" subtitle="当前套餐公开字段（运营对照）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <div className="overflow-x-auto rounded-xl border">
                <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-900">
                        <tr>
                            <th className="text-left p-2">套餐</th>
                            <th className="text-left p-2">价格(分)</th>
                            <th className="text-left p-2">周期天</th>
                            <th className="text-left p-2">月点数</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((r) => (
                            <tr key={String(r.id)} className="border-t">
                                <td className="p-2">{String(r.name)}</td>
                                <td className="p-2 font-mono">{String(r.price_cents)}</td>
                                <td className="p-2">{String(r.period_days)}</td>
                                <td className="p-2">{String(r.monthly_credits)}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </AdminPage>
    )
}
