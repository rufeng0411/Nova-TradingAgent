import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function CommerceApiCosts() {
    const [data, setData] = useState<Record<string, unknown> | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminCommerceApiCosts()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="API 成本管理" subtitle="占位：将基于 AI 调用日志聚合">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <pre className="text-xs bg-slate-100 dark:bg-slate-900 p-4 rounded-xl overflow-auto">
                {JSON.stringify(data, null, 2)}
            </pre>
        </AdminPage>
    )
}
