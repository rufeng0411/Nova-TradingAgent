import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function ContentSiteMessages() {
    const [data, setData] = useState<{ items?: Record<string, unknown>[] } | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminContentMessages()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="站内信" subtitle="草稿与发布（发布需二次确认）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <ul className="text-sm space-y-2">
                {(data?.items || []).map((m) => (
                    <li key={String(m.id)} className="rounded border p-2">
                        {String(m.title)} — {String(m.status)}
                    </li>
                ))}
            </ul>
        </AdminPage>
    )
}
