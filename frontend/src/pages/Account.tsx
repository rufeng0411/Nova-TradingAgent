import { FormEvent, useEffect, useState } from 'react'
import { Copy, Loader2, Trash2 } from 'lucide-react'
import { api } from '@/services/api'
import type { UserToken } from '@/types'
import { useAuthStore } from '@/stores/authStore'

export default function Account() {
    const { user, refreshMe } = useAuthStore()
    const [displayName, setDisplayName] = useState(user?.display_name || '')
    const [email, setEmail] = useState(user?.email || '')
    const [phone, setPhone] = useState('')
    const [credits, setCredits] = useState<number | null>(user?.credits ?? null)
    const [planCode, setPlanCode] = useState<string | null>(user?.plan_code ?? null)
    const [subExp, setSubExp] = useState<string | null>(user?.subscription_expires_at ?? null)
    const [oldPw, setOldPw] = useState('')
    const [newPw, setNewPw] = useState('')
    const [tokens, setTokens] = useState<UserToken[]>([])
    const [newTokenName, setNewTokenName] = useState('')
    const [createdPlain, setCreatedPlain] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)
    const [msg, setMsg] = useState<string | null>(null)
    const [err, setErr] = useState<string | null>(null)

    const reload = async () => {
        const u = await refreshMe()
        if (u) {
            setDisplayName(u.display_name || '')
            setEmail(u.email || '')
            setCredits(u.credits ?? null)
            setPlanCode(u.plan_code ?? null)
            setSubExp(u.subscription_expires_at ?? null)
        }
        try {
            const bal = await api.getBillingBalance()
            setCredits(bal.credits)
            setPlanCode(bal.plan_code ?? null)
            setSubExp(bal.subscription_expires_at ?? null)
        } catch {
            /* ignore */
        }
        try {
            const t = await api.getTokens()
            setTokens(t)
        } catch {
            setTokens([])
        }
    }

    useEffect(() => {
        void reload()
    }, [])

    const saveProfile = async (e: FormEvent) => {
        e.preventDefault()
        setErr(null)
        setMsg(null)
        setLoading(true)
        try {
            await api.patchMe({
                email: email.trim(),
                display_name: displayName.trim() || undefined,
                phone: phone.trim() || undefined,
            })
            await reload()
            setMsg('资料已保存')
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '保存失败')
        } finally {
            setLoading(false)
        }
    }

    const savePassword = async (e: FormEvent) => {
        e.preventDefault()
        setErr(null)
        setMsg(null)
        setLoading(true)
        try {
            await api.changePassword(oldPw, newPw)
            setOldPw('')
            setNewPw('')
            setMsg('密码已更新')
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '改密失败')
        } finally {
            setLoading(false)
        }
    }

    const createTok = async (e: FormEvent) => {
        e.preventDefault()
        setErr(null)
        setCreatedPlain(null)
        setLoading(true)
        try {
            const t = await api.createToken({ name: newTokenName.trim() || 'default' })
            setNewTokenName('')
            if (t.token) setCreatedPlain(t.token)
            await reload()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '创建失败')
        } finally {
            setLoading(false)
        }
    }

    const delTok = async (id: string) => {
        if (!confirm('确定删除该 Token？')) return
        setLoading(true)
        try {
            await api.deleteToken(id)
            await reload()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '删除失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="max-w-3xl space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">账户</h1>
                <p className="text-sm text-slate-500 mt-1">资料、安全与 API Token</p>
            </div>

            {msg && <p className="text-sm text-emerald-600">{msg}</p>}
            {err && <p className="text-sm text-rose-600">{err}</p>}

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-6 shadow-sm">
                <h2 className="font-semibold text-slate-800 dark:text-slate-100">点数与套餐</h2>
                <dl className="mt-3 grid grid-cols-1 sm:grid-cols-3 gap-3 text-sm">
                    <div>
                        <dt className="text-slate-500">当前点数</dt>
                        <dd className="font-mono text-lg">{credits ?? '—'}</dd>
                    </div>
                    <div>
                        <dt className="text-slate-500">套餐</dt>
                        <dd>{planCode || '—'}</dd>
                    </div>
                    <div>
                        <dt className="text-slate-500">订阅到期</dt>
                        <dd className="break-all">{subExp || '—'}</dd>
                    </div>
                </dl>
                <p className="text-xs text-slate-400 mt-2">详细流水与订阅申请见「订阅与流水」页。</p>
            </section>

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-6 shadow-sm">
                <h2 className="font-semibold text-slate-800 dark:text-slate-100">基本资料</h2>
                <form onSubmit={saveProfile} className="mt-4 space-y-3 max-w-md">
                    <div>
                        <label className="text-xs text-slate-500">显示名</label>
                        <input
                            value={displayName}
                            onChange={(e) => setDisplayName(e.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                        />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500">邮箱</label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                            required
                        />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500">手机（可选，加密存储）</label>
                        <input
                            value={phone}
                            onChange={(e) => setPhone(e.target.value)}
                            placeholder="更新时填写；留空不修改"
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                        />
                    </div>
                    <button
                        type="submit"
                        disabled={loading}
                        className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm disabled:opacity-50"
                    >
                        保存资料
                    </button>
                </form>
                {user?.phone_masked && <p className="mt-2 text-xs text-slate-500">已绑定手机（脱敏）：{user.phone_masked}</p>}
            </section>

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-6 shadow-sm">
                <h2 className="font-semibold text-slate-800 dark:text-slate-100">修改密码</h2>
                <form onSubmit={savePassword} className="mt-4 space-y-3 max-w-md">
                    <input
                        type="password"
                        value={oldPw}
                        onChange={(e) => setOldPw(e.target.value)}
                        placeholder="当前密码"
                        aria-label="当前密码"
                        className="w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                        required
                    />
                    <input
                        type="password"
                        value={newPw}
                        onChange={(e) => setNewPw(e.target.value)}
                        placeholder="新密码（≥8 位，含字母与数字）"
                        aria-label="新密码"
                        className="w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                        required
                    />
                    <button type="submit" disabled={loading} className="rounded-xl bg-slate-900 dark:bg-slate-100 dark:text-slate-900 text-white px-4 py-2 text-sm">
                        更新密码
                    </button>
                </form>
            </section>

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-6 shadow-sm">
                <h2 className="font-semibold text-slate-800 dark:text-slate-100">API Token</h2>
                <p className="text-xs text-slate-500 mt-1">用于外部调用；创建后仅显示一次，请妥善保存。</p>
                {createdPlain && (
                    <div className="mt-3 flex items-center gap-2 rounded-xl bg-amber-50 dark:bg-amber-950/40 border border-amber-200 dark:border-amber-800 px-3 py-2 text-sm font-mono break-all">
                        {createdPlain}
                        <button
                            type="button"
                            className="shrink-0 p-1 rounded-lg hover:bg-amber-100 dark:hover:bg-amber-900"
                            title="复制"
                            onClick={() => void navigator.clipboard.writeText(createdPlain)}
                        >
                            <Copy className="w-4 h-4" />
                        </button>
                    </div>
                )}
                <form onSubmit={createTok} className="mt-4 flex flex-wrap gap-2 items-end">
                    <input
                        value={newTokenName}
                        onChange={(e) => setNewTokenName(e.target.value)}
                        placeholder="Token 名称"
                        className="flex-1 min-w-[12rem] rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm bg-white dark:bg-slate-950"
                    />
                    <button type="submit" disabled={loading} className="rounded-xl bg-blue-600 text-white px-4 py-2 text-sm inline-flex items-center gap-2">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                        新建
                    </button>
                </form>
                <ul className="mt-4 divide-y divide-slate-100 dark:divide-slate-800">
                    {tokens.map((t) => (
                        <li key={t.id} className="py-3 flex justify-between gap-2 text-sm">
                            <div>
                                <div className="font-medium">{t.name}</div>
                                <div className="text-xs text-slate-500 font-mono">{t.token_hint || '****'}</div>
                            </div>
                            <button type="button" onClick={() => void delTok(t.id)} className="text-rose-600 p-2" title="删除">
                                <Trash2 className="w-4 h-4" />
                            </button>
                        </li>
                    ))}
                    {tokens.length === 0 && <li className="py-4 text-slate-500 text-sm">暂无 Token</li>}
                </ul>
            </section>
        </div>
    )
}
