import { useCallback, useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { api } from '@/services/api'
import AdminDataTable, { type AdminTableColumn } from '@/pages/admin/components/AdminDataTable'
import AdminPage from '@/pages/admin/components/AdminPage'

type Row = { id: string; order_no?: string; user_id?: string; status?: string; amount_cents?: number; currency?: string }

export default function CommerceOrders() {
    const navigate = useNavigate()
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [rows, setRows] = useState<Row[]>([])
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminCommerceOrders({ page, page_size: 20 })
            setTotal(d.total)
            setRows((d.items || []) as Row[])
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        } finally {
            setLoading(false)
        }
    }, [page])

    useEffect(() => {
        void load()
    }, [load])

    const columns: AdminTableColumn<Row>[] = [
        { key: 'order_no', header: '订单号', render: (r) => r.order_no },
        { key: 'user', header: '用户', render: (r) => r.user_id },
        {
            key: 'amount',
            header: '金额(分)',
            render: (r) => <span className="font-mono">{r.amount_cents ?? 0}</span>,
        },
        { key: 'status', header: '状态', render: (r) => r.status },
        {
            key: 'act',
            header: '操作',
            render: (r) => (
                <button type="button" className="text-blue-600 text-xs" onClick={() => navigate(`/admin/commerce/orders/${r.id}`)}>
                    详情
                </button>
            ),
        },
    ]

    return (
        <AdminPage title="订单管理" subtitle="财务域：需 finance 权限；手动核销需 Idempotency-Key 与 X-Admin-Confirm">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <AdminDataTable<Row>
                columns={columns}
                rows={rows}
                loading={loading}
                error={err}
                emptyText="暂无订单数据"
                page={page}
                pageSize={20}
                total={total}
                onPageChange={setPage}
            />
        </AdminPage>
    )
}
