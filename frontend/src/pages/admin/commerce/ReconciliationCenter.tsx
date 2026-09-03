import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function CommerceReconciliation() {
    const [data, setData] = useState<{ items?: Record<string, unknown>[] } | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminCommerceReconciliationRuns()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="对账中心" subtitle="对账批次列表（差异明细后续扩展）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <ul className="text-sm space-y-2">
                {(data?.items || []).map((x) => (
                    <li key={String(x.id)} className="rounded border p-2">
                        {String(x.label)} — {String(x.status)}
                    </li>
                ))}
            </ul>
        </AdminPage>
    )
}
