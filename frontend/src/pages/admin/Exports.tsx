import { useState } from 'react'
import { getBaseUrl } from '@/services/api'
import { api } from '@/services/api'

export default function AdminExports() {
    const [jobs, setJobs] = useState<{ id: string; status: string; download_ready?: boolean; download_token?: string | null }[]>([])
    const [busy, setBusy] = useState(false)
    const [err, setErr] = useState<string | null>(null)

    const poll = async (id: string) => {
        for (let i = 0; i < 60; i++) {
            const st = await api.adminExportStatus(id)
            setJobs((prev) => {
                const rest = prev.filter((j) => j.id !== id)
                return [{ id: st.id, status: st.status, download_ready: st.download_ready, download_token: st.download_token }, ...rest]
            })
            if (st.status === 'completed' || st.status === 'failed') break
            await new Promise((r) => setTimeout(r, 1000))
        }
    }

    const start = async (t: 'users' | 'access_logs' | 'credits') => {
        setBusy(true)
        setErr(null)
        try {
            const r = await api.adminExportCreate(t)
            setJobs((prev) => [{ id: r.id, status: r.status }, ...prev])
            void poll(r.id)
        } catch (e) {
            setErr(e instanceof Error ? e.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    const download = async (id: string, token: string) => {
        const base = getBaseUrl()
        const auth = localStorage.getItem('ta-access-token')
        const res = await fetch(`${base}/v1/admin/export/${id}/download?token=${encodeURIComponent(token)}`, {
            headers: auth ? { Authorization: `Bearer ${auth}` } : {},
        })
        if (!res.ok) {
            setErr(await res.text())
            return
        }
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `export-${id}.csv`
        a.click()
        URL.revokeObjectURL(url)
    }

    return (
        <div className="space-y-6 max-w-2xl">
            <h1 className="text-xl font-bold">导出中心</h1>
            {err && <p className="text-rose-600 text-sm">{err}</p>}
            <div className="flex flex-wrap gap-2">
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => void start('users')}
                    className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
                >
                    导出用户
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => void start('access_logs')}
                    className="rounded-xl bg-slate-800 text-white px-4 py-2 text-sm disabled:opacity-50"
                >
                    导出访问日志
                </button>
                <button
                    type="button"
                    disabled={busy}
                    onClick={() => void start('credits')}
                    className="rounded-xl bg-emerald-700 text-white px-4 py-2 text-sm disabled:opacity-50"
                >
                    导出点数流水
                </button>
            </div>
            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 divide-y divide-slate-100 dark:divide-slate-800">
                {jobs.length === 0 && <div className="p-6 text-sm text-slate-500">暂无导出任务</div>}
                {jobs.map((j) => (
                    <div key={j.id} className="p-4 flex flex-wrap items-center justify-between gap-2 text-sm">
                        <div>
                            <div className="font-mono text-xs text-slate-500">{j.id}</div>
                            <div className="mt-1">
                                状态：<span className="font-medium">{j.status}</span>
                            </div>
                        </div>
                        {j.download_ready && j.download_token && (
                            <button
                                type="button"
                                onClick={() => void download(j.id, j.download_token!)}
                                className="rounded-lg border border-blue-200 text-blue-700 dark:text-blue-300 px-3 py-1 text-xs"
                            >
                                下载 CSV
                            </button>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}
