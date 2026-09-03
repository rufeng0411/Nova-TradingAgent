import { useCallback, useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminDataTable, { type AdminTableColumn } from '@/pages/admin/components/AdminDataTable'
import AdminPage from '@/pages/admin/components/AdminPage'

type Row = Record<string, unknown> & { id?: string }

export default function OpsAiCallLogs() {
    const [page, setPage] = useState(1)
    const [total, setTotal] = useState(0)
    const [rows, setRows] = useState<Row[]>([])
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)

    const load = useCallback(async () => {
        setLoading(true)
        setErr(null)
        try {
            const d = await api.adminOpsAiCalls({ page, page_size: 25 })
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
        { key: 'm', header: '模型', render: (r) => `${String(r.provider || '')}/${String(r.model || '')}` },
        { key: 'tok', header: 'Token', render: (r) => `${r.prompt_tokens ?? 0}+${r.completion_tokens ?? 0}` },
        { key: 'st', header: '状态', render: (r) => String(r.status || '') },
        { key: 'pv', header: '摘要', render: (r) => String(r.prompt_preview || '—').slice(0, 48) },
        { key: 't', header: '时间', render: (r) => String(r.created_at || '') },
    ]

    return (
        <AdminPage title="AI 调用日志" subtitle="仅存 preview，需 ops 权限；无数据表示尚未埋点">
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
