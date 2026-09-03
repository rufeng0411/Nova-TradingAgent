import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function AdminAccessLogs() {
    const [page, setPage] = useState(1)
    const [failuresOnly, setFailuresOnly] = useState(false)
    const [data, setData] = useState<{
        total: number
        items: { id: string; user_id?: string | null; method?: string | null; path?: string | null; status_code?: number | null; latency_ms?: number | null; created_at?: string | null }[]
    } | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        void api
            .adminAccessLogs({ page, page_size: 50, failures_only: failuresOnly })
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [page, failuresOnly])

    if (err) return <p className="text-rose-600">{err}</p>
    if (!data) {
        return (
            <div className="flex justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        )
    }

    return (
        <div className="space-y-3">
            <div className="flex items-center gap-3 text-sm">
                <label className="inline-flex items-center gap-2 cursor-pointer">
                    <input type="checkbox" checked={failuresOnly} onChange={(e) => setFailuresOnly(e.target.checked)} />
                    仅失败 / 风险（HTTP ≥400）
                </label>
            </div>
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900/60 shadow-sm">
            <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500">
                        <tr>
                            <th className="px-3 py-2">时间</th>
                            <th className="px-3 py-2">用户</th>
                            <th className="px-3 py-2">方法</th>
                            <th className="px-3 py-2">路径</th>
                            <th className="px-3 py-2">状态</th>
                            <th className="px-3 py-2">ms</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {data.items.map((r) => (
                            <tr key={r.id}>
                                <td className="px-3 py-2 whitespace-nowrap">{r.created_at || '—'}</td>
                                <td className="px-3 py-2 font-mono max-w-[8rem] truncate" title={r.user_id || ''}>
                                    {r.user_id || '—'}
                                </td>
                                <td className="px-3 py-2">{r.method}</td>
                                <td className="px-3 py-2 max-w-md truncate" title={r.path || ''}>
                                    {r.path}
                                </td>
                                <td className="px-3 py-2">{r.status_code}</td>
                                <td className="px-3 py-2">{r.latency_ms}</td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            <div className="px-4 py-3 flex justify-between text-xs text-slate-500 border-t border-slate-100 dark:border-slate-800">
                <span>共 {data.total} 条</span>
                <div className="flex gap-2">
                    <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-40">
                        上一页
                    </button>
                    <button type="button" onClick={() => setPage((p) => p + 1)} disabled={data.items.length < 50}>
                        下一页
                    </button>
                </div>
            </div>
        </div>
        </div>
    )
}
