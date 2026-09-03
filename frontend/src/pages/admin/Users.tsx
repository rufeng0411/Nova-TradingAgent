import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function AdminUsers() {
    const [q, setQ] = useState('')
    const [page, setPage] = useState(1)
    const [data, setData] = useState<{
        total: number
        items: { id: string; email: string; username?: string | null; role: string; status: string; credits: number }[]
    } | null>(null)
    const [err, setErr] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)

    const load = async (pageOverride?: number) => {
        setLoading(true)
        setErr(null)
        const p = pageOverride ?? page
        try {
            const r = await api.adminUsers({ q: q.trim() || undefined, page: p, page_size: 20 })
            setData(r)
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        void load()
        // eslint-disable-next-line react-hooks/exhaustive-deps -- 仅分页变化时重载
    }, [page])

    const search = (e: React.FormEvent) => {
        e.preventDefault()
        setPage(1)
        void load(1)
    }

    return (
        <div className="space-y-4">
            <form onSubmit={search} className="flex gap-2 flex-wrap">
                <input
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="邮箱 / 用户名"
                    className="rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm flex-1 min-w-[12rem] bg-white dark:bg-slate-950"
                />
                <button type="submit" className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm">
                    搜索
                </button>
            </form>
            {err && <p className="text-rose-600 text-sm">{err}</p>}
            {loading && !data ? (
                <Loader2 className="w-6 h-6 animate-spin text-slate-400" />
            ) : (
                <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900/60 shadow-sm">
                    <table className="min-w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900 text-left text-xs text-slate-500">
                            <tr>
                                <th className="px-4 py-2">邮箱</th>
                                <th className="px-4 py-2">用户名</th>
                                <th className="px-4 py-2">角色</th>
                                <th className="px-4 py-2">状态</th>
                                <th className="px-4 py-2">点数</th>
                                <th className="px-4 py-2" />
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                            {(data?.items || []).map((u) => (
                                <tr key={u.id}>
                                    <td className="px-4 py-2 break-all">{u.email}</td>
                                    <td className="px-4 py-2">{u.username || '—'}</td>
                                    <td className="px-4 py-2">{u.role}</td>
                                    <td className="px-4 py-2">{u.status}</td>
                                    <td className="px-4 py-2 font-mono">{u.credits}</td>
                                    <td className="px-4 py-2">
                                        <Link to={`/admin/users/${u.id}`} className="text-blue-600 hover:underline">
                                            详情
                                        </Link>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                    <div className="px-4 py-3 flex justify-between text-xs text-slate-500 border-t border-slate-100 dark:border-slate-800">
                        <span>共 {data?.total ?? 0} 条</span>
                        <div className="flex gap-2">
                            <button type="button" disabled={page <= 1} onClick={() => setPage((p) => p - 1)} className="disabled:opacity-40">
                                上一页
                            </button>
                            <button type="button" onClick={() => setPage((p) => p + 1)} className="disabled:opacity-40" disabled={!data || data.items.length < 20}>
                                下一页
                            </button>
                        </div>
                    </div>
                </div>
            )}
        </div>
    )
}
