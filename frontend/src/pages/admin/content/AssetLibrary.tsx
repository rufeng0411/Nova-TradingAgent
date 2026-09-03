import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function ContentAssets() {
    const [data, setData] = useState<{ items?: Record<string, unknown>[] } | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminContentAssets()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="素材库" subtitle="Logo / 二维码等外链素材登记">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <ul className="text-sm space-y-2">
                {(data?.items || []).map((a) => (
                    <li key={String(a.id)} className="rounded border p-2 break-all">
                        {String(a.name)} — {String(a.url)}
                    </li>
                ))}
            </ul>
        </AdminPage>
    )
}
