import { useCallback, useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminDataTable, { type AdminTableColumn } from '@/pages/admin/components/AdminDataTable'
import AdminPage from '@/pages/admin/components/AdminPage'

type Row = Record<string, unknown> & { id?: string }

export default function OpsUsageRecords() {
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [rows, setRows] = useState<Row[]>([])
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminOpsUsage({ page, page_size: 25 })
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
        { key: 'task', header: '任务', render: (r) => String(r.task_id || '—') },
        { key: 'cr', header: '预扣', render: (r) => String(r.credits_reserved ?? '') },
        { key: 'cc', header: '消耗', render: (r) => String(r.credits_consumed ?? '') },
        { key: 't', header: '时间', render: (r) => String(r.created_at || '') },
    ]

    return (
        <AdminPage title="用量记录" subtitle="分析链路点数与 Token 占位字段">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <AdminDataTable<Row>
                columns={columns}
                rows={rows}
                loading={loading}
                error={err}
                page={page}
                pageSize={25}
                total={total}
                onPageChange={setPage}
            />
        </AdminPage>
    )
}
