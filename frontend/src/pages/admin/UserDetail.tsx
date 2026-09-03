import { FormEvent, useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

function canFinance(perms?: string[] | null) {
    if (!perms || perms.length === 0) return true
    return perms.includes('finance') || perms.includes('superadmin')
}

function canOps(perms?: string[] | null) {
    if (!perms || perms.length === 0) return true
    return perms.includes('ops') || perms.includes('superadmin')
}

export default function AdminUserDetail() {
    const { id } = useParams<{ id: string }>()
    const { user: me, refreshMe } = useAuthStore()
    const [u, setU] = useState<{
        id: string
        email: string
        username?: string | null
        display_name?: string | null
        role: string
        status: string
        credits: number
        plan_code?: string | null
        subscription_expires_at?: string | null
        admin_permissions?: string[] | null
    } | null>(null)
    const [tab, setTab] = useState<'form' | 'credits' | 'access' | 'audit'>('form')
    const [err, setErr] = useState<string | null>(null)
    const [msg, setMsg] = useState<string | null>(null)
    const [role, setRole] = useState('')
    const [status, setStatus] = useState('')
    const [perms, setPerms] = useState('')
    const [delta, setDelta] = useState('')
    const [reason, setReason] = useState('admin_adjust')
    const [newPw, setNewPw] = useState('')
    const [planCode, setPlanCode] = useState('')
    const [planDays, setPlanDays] = useState('30')
    const [busy, setBusy] = useState(false)
    const [creditsRows, setCreditsRows] = useState<
        { id: string; delta: number; type: string; reason?: string | null; created_at?: string | null }[]
    >([])
    const [accessRows, setAccessRows] = useState<
        { id: string; path?: string | null; status_code?: number | null; created_at?: string | null }[]
    >([])
    const [auditRows, setAuditRows] = useState<
        { id: string; action: string; payload?: Record<string, unknown> | null; created_at?: string | null }[]
    >([])

    const loadUser = async () => {
        if (!id) return
        setErr(null)
        try {
            const r = await api.adminGetUser(id)
            setU({
                ...r,
                admin_permissions: r.admin_permissions ?? null,
            })
            setRole(r.role)
            setStatus(r.status)
            setPlanCode(r.plan_code || '')
            const ap = r.admin_permissions
            setPerms(ap && ap.length ? ap.join(',') : '')
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        }
    }

    const loadDrill = async () => {
        if (!id) return
        try {
            const [ct, al, au] = await Promise.all([
                api.adminUserCreditTransactions(id, { page: 1, page_size: 30 }),
                api.adminAccessLogs({ user_id: id, page: 1, page_size: 30 }),
                api.adminAuditLogs(1, 30, id),
            ])
            setCreditsRows(ct.items)
            setAccessRows(al.items)
            setAuditRows(au.items)
        } catch {
            /* ignore */
        }
    }

    useEffect(() => {
        void loadUser()
    }, [id])

    useEffect(() => {
        if (tab !== 'form') void loadDrill()
    }, [tab, id])

    const askConfirmHeaders = async (): Promise<Record<string, string> | null> => {
        const pw = window.prompt('请输入您的管理员密码以确认敏感操作')
        if (!pw) return null
        try {
            const r = await api.adminConfirm(pw)
            return { 'X-Admin-Confirm': r.confirm_token }
        } catch (e) {
            setErr(e instanceof Error ? e.message : '确认失败')
            return null
        }
    }

    const saveMeta = async (e: FormEvent) => {
        e.preventDefault()
        if (!id) return
        setBusy(true)
        setMsg(null)
        try {
            const permArr = perms
                .split(',')
                .map((s) => s.trim())
                .filter(Boolean)
            await api.adminPatchUser(id, {
                role,
                status,
                admin_permissions: permArr.length ? permArr : [],
            })
            setMsg('已保存')
            await loadUser()
            if (me?.id === id) await refreshMe()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    const adjustCredits = async (e: FormEvent) => {
        e.preventDefault()
        if (!id) return
        const d = Number(delta)
        if (!Number.isFinite(d) || d === 0) {
            setErr('请输入非零整数')
            return
        }
        const h = await askConfirmHeaders()
        if (!h) return
        setBusy(true)
        setMsg(null)
        try {
            const idem = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())
            const r = await api.adminAdjustCredits(id, d, reason, {
                ...h,
                'Idempotency-Key': idem,
            })
            setMsg(`点数已调整，当前 ${r.balance}`)
            setDelta('')
            await loadUser()
            await loadDrill()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    const resetPw = async (e: FormEvent) => {
        e.preventDefault()
        if (!id || !newPw) return
        const h = await askConfirmHeaders()
        if (!h) return
        setBusy(true)
        setMsg(null)
        try {
            await api.adminResetPassword(id, newPw, h)
            setMsg('密码已重置')
            setNewPw('')
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    const setSub = async (e: FormEvent) => {
        e.preventDefault()
        if (!id || !planCode.trim()) return
        const h = await askConfirmHeaders()
        if (!h) return
        setBusy(true)
        setMsg(null)
        try {
            const idem = typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : String(Date.now())
            await api.adminSetSubscription(
                id,
                {
                    plan_code: planCode.trim(),
                    days: Number(planDays) || 30,
                    status: 'active',
                },
                { ...h, 'Idempotency-Key': idem },
            )
            setMsg('订阅已更新')
            await loadUser()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    if (!id) return <p className="text-slate-500">无效用户</p>
    if (err && !u) return <p className="text-rose-600">{err}</p>
    if (!u) {
        return (
            <div className="flex justify-center py-16">
                <Loader2 className="w-8 h-8 animate-spin" />
            </div>
        )
    }

    const myPerms = me?.admin_permissions
    const showFinance = canFinance(myPerms ?? null)
    const showOps = canOps(myPerms ?? null)

    return (
        <div className="max-w-5xl space-y-6">
            <Link to="/admin/users" className="text-sm text-blue-600 hover:underline">
                ← 返回列表
            </Link>
            <h2 className="text-xl font-bold">用户详情</h2>
            <div className="flex flex-wrap gap-2 text-sm">
                {(['form', 'credits', 'access', 'audit'] as const).map((t) => (
                    <button
                        key={t}
                        type="button"
                        onClick={() => setTab(t)}
                        className={`rounded-lg px-3 py-1 border ${
                            tab === t
                                ? 'bg-blue-600 text-white border-blue-600'
                                : 'border-slate-200 dark:border-slate-700 text-slate-600 dark:text-slate-300'
                        }`}
                    >
                        {t === 'form' ? '资料' : t === 'credits' ? '点数流水' : t === 'access' ? '访问日志' : '审计'}
                    </button>
                ))}
            </div>
            {msg && <p className="text-sm text-emerald-600">{msg}</p>}
            {err && <p className="text-sm text-rose-600">{err}</p>}

            {tab === 'form' && (
                <>
                    <div className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 text-sm space-y-1 bg-white dark:bg-slate-900/60">
                        <div>
                            <span className="text-slate-500">ID</span> <span className="font-mono break-all">{u.id}</span>
                        </div>
                        <div>
                            <span className="text-slate-500">邮箱</span> {u.email}
                        </div>
                        <div>
                            <span className="text-slate-500">用户名</span> {u.username || '—'}
                        </div>
                        <div>
                            <span className="text-slate-500">点数</span> <span className="font-mono">{u.credits}</span>
                        </div>
                        <div>
                            <span className="text-slate-500">套餐</span> {u.plan_code || '—'}
                        </div>
                    </div>

                    <form onSubmit={saveMeta} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-white dark:bg-slate-900/60">
                        <h3 className="font-medium">角色与权限</h3>
                        <div className="flex flex-wrap gap-3">
                            <select aria-label="角色" value={role} onChange={(e) => setRole(e.target.value)} className="rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950">
                                <option value="user">user</option>
                                <option value="admin">admin</option>
                            </select>
                            <select aria-label="状态" value={status} onChange={(e) => setStatus(e.target.value)} className="rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950">
                                <option value="active">active</option>
                                <option value="disabled">disabled</option>
                            </select>
                        </div>
                        <label className="block text-xs text-slate-500">
                            admin_permissions（逗号分隔，如 ops,finance；留空表示全权限）
                            <input
                                value={perms}
                                onChange={(e) => setPerms(e.target.value)}
                                className="mt-1 w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                        </label>
                        <button type="submit" disabled={busy} className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm">
                            保存
                        </button>
                    </form>

                    {showFinance && (
                        <form onSubmit={adjustCredits} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-white dark:bg-slate-900/60">
                            <h3 className="font-medium">调整点数</h3>
                            <input
                                type="number"
                                value={delta}
                                onChange={(e) => setDelta(e.target.value)}
                                placeholder="增量（可负）"
                                className="w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                            <input
                                aria-label="调账原因"
                                value={reason}
                                onChange={(e) => setReason(e.target.value)}
                                className="w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                            <button type="submit" disabled={busy} className="rounded-xl bg-slate-900 dark:bg-slate-100 text-white dark:text-slate-900 px-4 py-2 text-sm">
                                提交
                            </button>
                        </form>
                    )}

                    {showOps && (
                        <form onSubmit={resetPw} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-white dark:bg-slate-900/60">
                            <h3 className="font-medium">重置密码</h3>
                            <input
                                type="password"
                                value={newPw}
                                onChange={(e) => setNewPw(e.target.value)}
                                placeholder="新密码"
                                autoComplete="new-password"
                                className="w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                            <button type="submit" disabled={busy} className="rounded-xl bg-rose-600 text-white px-4 py-2 text-sm">
                                重置
                            </button>
                        </form>
                    )}

                    {showFinance && (
                        <form onSubmit={setSub} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 space-y-3 bg-white dark:bg-slate-900/60">
                            <h3 className="font-medium">设置订阅（管理员）</h3>
                            <input
                                value={planCode}
                                onChange={(e) => setPlanCode(e.target.value)}
                                placeholder="plan_code"
                                className="w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                            <input
                                value={planDays}
                                onChange={(e) => setPlanDays(e.target.value)}
                                placeholder="天数"
                                className="w-full rounded-xl border px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            />
                            <button type="submit" disabled={busy} className="rounded-xl bg-indigo-600 text-white px-4 py-2 text-sm">
                                应用订阅
                            </button>
                        </form>
                    )}
                </>
            )}

            {tab === 'credits' && (
                <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-x-auto bg-white dark:bg-slate-900/60 text-sm">
                    <table className="min-w-full">
                        <thead>
                            <tr className="text-left text-xs text-slate-500 border-b border-slate-100 dark:border-slate-800">
                                <th className="p-2">时间</th>
                                <th className="p-2">类型</th>
                                <th className="p-2">增量</th>
                                <th className="p-2">原因</th>
                            </tr>
                        </thead>
                        <tbody>
                            {creditsRows.map((r) => (
                                <tr key={r.id} className="border-b border-slate-50 dark:border-slate-800/80">
                                    <td className="p-2 font-mono text-xs whitespace-nowrap">{r.created_at}</td>
                                    <td className="p-2">{r.type}</td>
                                    <td className="p-2 font-mono">{r.delta}</td>
                                    <td className="p-2">{r.reason}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {tab === 'access' && (
                <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-x-auto bg-white dark:bg-slate-900/60 text-sm">
                    <table className="min-w-full">
                        <thead>
                            <tr className="text-left text-xs text-slate-500 border-b border-slate-100 dark:border-slate-800">
                                <th className="p-2">时间</th>
                                <th className="p-2">路径</th>
                                <th className="p-2">状态</th>
                            </tr>
                        </thead>
                        <tbody>
                            {accessRows.map((r) => (
                                <tr key={r.id} className="border-b border-slate-50 dark:border-slate-800/80">
                                    <td className="p-2 font-mono text-xs whitespace-nowrap">{r.created_at}</td>
                                    <td className="p-2 font-mono text-xs break-all">{r.path}</td>
                                    <td className="p-2">{r.status_code}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}

            {tab === 'audit' && (
                <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-x-auto bg-white dark:bg-slate-900/60 text-sm">
                    <table className="min-w-full">
                        <thead>
                            <tr className="text-left text-xs text-slate-500 border-b border-slate-100 dark:border-slate-800">
                                <th className="p-2">时间</th>
                                <th className="p-2">动作</th>
                                <th className="p-2">载荷</th>
                            </tr>
                        </thead>
                        <tbody>
                            {auditRows.map((r) => (
                                <tr key={r.id} className="border-b border-slate-50 dark:border-slate-800/80 align-top">
                                    <td className="p-2 font-mono text-xs whitespace-nowrap">{r.created_at}</td>
                                    <td className="p-2">{r.action}</td>
                                    <td className="p-2 text-xs">
                                        <pre className="whitespace-pre-wrap break-all max-w-md">{JSON.stringify(r.payload, null, 2)}</pre>
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    )
}
