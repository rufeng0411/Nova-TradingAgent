import { useCallback, useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminDataTable, { type AdminTableColumn } from '@/pages/admin/components/AdminDataTable'
import AdminPage from '@/pages/admin/components/AdminPage'

type Row = Record<string, unknown> & { id?: string }

export default function OpsTasks() {
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [rows, setRows] = useState<Row[]>([])
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminOpsTasks({ page, page_size: 25 })
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
        { key: 'id', header: 'ID', render: (r) => <span className="font-mono text-xs">{String(r.id)}</span> },
        { key: 'sym', header: '标的', render: (r) => String(r.symbol || '') },
        { key: 'st', header: '状态', render: (r) => String(r.status || '') },
        { key: 'uid', header: '用户', render: (r) => String(r.user_id || '—') },
        { key: 'err', header: '错误摘要', render: (r) => String(r.error || '—').slice(0, 80) },
    ]

    return (
        <AdminPage title="任务管理" subtitle="当前以分析报告为任务视图（需 ops 权限）">
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
