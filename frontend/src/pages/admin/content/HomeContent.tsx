import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function ContentHome() {
    const [data, setData] = useState<{ items?: Record<string, unknown>[] } | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminContentBlocks()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="首页管理" subtitle="内容块草稿/发布（content 权限）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <ul className="text-sm space-y-2">
                {(data?.items || []).map((b) => (
                    <li key={String(b.key)} className="rounded border p-3">
                        <div className="font-medium">{String(b.title)}</div>
                        <div className="text-xs text-slate-500">{String(b.key)} — {String(b.status)}</div>
                    </li>
                ))}
            </ul>
        </AdminPage>
    )
}
