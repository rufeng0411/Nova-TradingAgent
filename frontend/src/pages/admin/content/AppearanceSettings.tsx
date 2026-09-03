import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function ContentAppearance() {
    const [data, setData] = useState<Record<string, unknown> | null>(null)
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminContentAppearance()
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="外观设置" subtitle="键值 JSON 配置（站点名、品牌色等）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <pre className="text-xs bg-slate-100 dark:bg-slate-900 p-4 rounded-xl overflow-auto">
                {JSON.stringify(data, null, 2)}
            </pre>
        </AdminPage>
    )
}
