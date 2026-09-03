import { useEffect, useState } from 'react'
import { useParams } from 'react-router-dom'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function CommerceOrderDetail() {
    const { id } = useParams()
    const [row, setRow] = useState<Record<string, unknown> | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        if (!id) return
        void api
            .adminCommerceOrder(id)
            .then((d) => setRow(d))
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [id])

    return (
        <AdminPage title="订单详情" subtitle={String(row?.order_no || id || '')}>
            {err ? <p className="text-rose-600">{err}</p> : null}
            {row ? (
                <pre className="text-xs bg-slate-100 dark:bg-slate-900 p-4 rounded-xl overflow-auto">
                    {JSON.stringify(row, null, 2)}
                </pre>
            ) : null}
            <p className="text-xs text-slate-500 mt-4">写操作请在 API 文档或后续表单中携带确认令牌与幂等键。</p>
        </AdminPage>
    )
}
