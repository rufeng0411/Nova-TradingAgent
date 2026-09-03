import { useEffect, useState } from 'react'
import { api } from '@/services/api'
import AdminPage from '@/pages/admin/components/AdminPage'

export default function CommerceCreditPackages() {
    const [items, setItems] = useState<Record<string, unknown>[]>([])
    const [err, setErr] = useState<string | null>(null)
    useEffect(() => {
        void api
            .adminCommerceCreditPackages()
            .then(setItems)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [])
    return (
        <AdminPage title="礼包管理" subtitle="点数包配置（财务域）">
            {err ? <p className="text-rose-600 text-sm">{err}</p> : null}
            <ul className="text-sm space-y-2">
                {items.map((x) => (
                    <li key={String(x.id)} className="rounded border border-slate-200 dark:border-slate-800 p-3 font-mono">
                        {String(x.code)} · {String(x.name)} · {String(x.credits)} 点 · {(Number(x.price_cents) / 100).toFixed(2)} 元
                    </li>
                ))}
            </ul>
        </AdminPage>
    )
}
