import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function AdminSignals() {
    const [items, setItems] = useState<
        { id: string; type: string; severity: string; user_id?: string | null; payload?: unknown; created_at?: string | null }[]
    >([])
    const [total, setTotal] = useState(0)
    const [severity, setSeverity] = useState('')
    const [err, setErr] = useState<string | null>(null)

    const load = async () => {
        setErr(null)
        try {
            const r = await api.adminSignals({
                page: 1,
                page_size: 100,
                severity: severity || undefined,
            })
            setItems(r.items)
            setTotal(r.total)
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        }
    }

    useEffect(() => {
        void load()
    }, [severity])

    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-center justify-between gap-3">
                <h1 className="text-xl font-bold">运营事件</h1>
                <select
                    value={severity}
                    onChange={(e) => setSeverity(e.target.value)}
                    className="rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 text-sm px-2 py-1"
                >
                    <option value="">全部严重度</option>
                    <option value="info">info</option>
                    <option value="warning">warning</option>
                    <option value="error">error</option>
                </select>
            </div>
            {err && <p className="text-rose-600 text-sm">{err}</p>}
            <p className="text-xs text-slate-500">共 {total} 条（当前页 {items.length}）</p>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 divide-y divide-slate-100 dark:divide-slate-800 bg-white dark:bg-slate-900/60">
                {items.length === 0 && (
                    <div className="p-8 flex justify-center text-slate-400">
                        <Loader2 className="w-6 h-6 animate-spin" />
                    </div>
                )}
                {items.map((s) => (
                    <div key={s.id} className="p-4 text-sm space-y-1">
                        <div className="flex flex-wrap gap-2 items-center">
                            <span className="font-mono text-xs text-slate-400">{s.created_at}</span>
                            <span className="rounded-md bg-slate-100 dark:bg-slate-800 px-2 py-0.5 text-xs">{s.severity}</span>
                            <span className="font-medium">{s.type}</span>
                        </div>
                        {s.user_id && (
                            <div>
                                用户{' '}
                                <Link className="text-blue-600 hover:underline font-mono text-xs" to={`/admin/users/${s.user_id}`}>
                                    {s.user_id}
                                </Link>
                            </div>
                        )}
                        {s.payload != null && (
                            <pre className="text-xs bg-slate-50 dark:bg-slate-950/80 p-2 rounded-lg overflow-x-auto max-h-40">
                                {JSON.stringify(s.payload, null, 2)}
                            </pre>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}
