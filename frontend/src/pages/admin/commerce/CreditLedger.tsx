import { useCallback, useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminDataTable, { type AdminTableColumn } from '@/pages/admin/components/AdminDataTable'
import AdminPage from '@/pages/admin/components/AdminPage'

type Row = Record<string, unknown> & { id?: string }

export default function CommerceCreditLedger() {
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [rows, setRows] = useState<Row[]>([])
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminCommerceCreditLedger({ page, page_size: 30 })
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
        { key: 'u', header: '用户', render: (r) => String(r.user_id || '') },
        { key: 'd', header: '变动', render: (r) => <span className="font-mono">{String(r.delta)}</span> },
        { key: 't', header: '类型', render: (r) => String(r.type || '') },
        { key: 'r', header: '原因', render: (r) => String(r.reason || '') },
        { key: 'c', header: '时间', render: (r) => String(r.created_at || '') },
    ]

    return (
        <AdminPage title="点数账本" subtitle="全局 credit_transactions 视图（财务域）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <AdminDataTable<Row>
                columns={columns}
                rows={rows}
                loading={loading}
                error={err}
                page={page}
                pageSize={30}
                total={total}
                onPageChange={setPage}
            />
        </AdminPage>
    )
}
