import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function AdminAuditLogs() {
    const [page, setPage] = useState(1)
    const [data, setData] = useState<{
        total: number
        items: { id: string; admin_id: string; action: string; target_user_id?: string | null; payload?: Record<string, unknown> | null; created_at?: string | null }[]
    } | null>(null)
    const [err, setErr] = useState<string | null>(null)

    useEffect(() => {
        void api
            .adminAuditLogs(page, 50)
            .then(setData)
            .catch((e) => setErr(e instanceof Error ? e.message : '加载失败'))
    }, [page])

    if (err) return <p className="text-rose-600">{err}</p>
    if (!data) {
        return (
            <div className="flex justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin text-slate-400" />
            </div>
        )
    }

    return (
        <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900/60 shadow-sm">
            <div className="overflow-x-auto">
                <table className="min-w-full text-xs">
                    <thead className="bg-slate-50 dark:bg-slate-900 text-left text-slate-500">
                        <tr>
                            <th className="px-3 py-2">时间</th>
                            <th className="px-3 py-2">管理员</th>
                            <th className="px-3 py-2">动作</th>
                            <th className="px-3 py-2">目标用户</th>
                            <th className="px-3 py-2">载荷</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {data.items.map((r) => (
                            <tr key={r.id}>
                                <td className="px-3 py-2 whitespace-nowrap align-top">{r.created_at || '—'}</td>
                                <td className="px-3 py-2 font-mono align-top max-w-[6rem] truncate">{r.admin_id}</td>
                                <td className="px-3 py-2 align-top">{r.action}</td>
                                <td className="px-3 py-2 font-mono align-top max-w-[6rem] truncate">{r.target_user_id || '—'}</td>
                                <td className="px-3 py-2 align-top max-w-lg">
                                    <pre className="whitespace-pre-wrap break-all text-[10px] text-slate-600 dark:text-slate-400">
                                        {r.payload ? JSON.stringify(r.payload, null, 0) : '—'}
                                    </pre>
                                </td>
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
    )
}
