import { useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

type Plan = {
    id: string
    code: string
    name: string
    price_cents: number
    currency: string
    period_days: number
    monthly_credits: number
}

type Tx = {
    id: string
    delta: number
    type: string
    reason?: string | null
    ref_type?: string | null
    ref_id?: string | null
    balance_after: number
    created_at?: string | null
}

export default function Subscription() {
    const { refreshMe } = useAuthStore()
    const [plans, setPlans] = useState<Plan[]>([])
    const [balance, setBalance] = useState<{ credits: number; plan_code?: string | null; subscription_status?: string | null; subscription_expires_at?: string | null } | null>(null)
    const [sub, setSub] = useState<{
        id: string
        plan_code?: string | null
        status: string
        expires_at?: string | null
    } | null>(null)
    const [tx, setTx] = useState<Tx[]>([])
    const [total, setTotal] = useState(0)
    const [loading, setLoading] = useState(true)
    const [busy, setBusy] = useState<string | null>(null)
    const [msg, setMsg] = useState<string | null>(null)
    const [err, setErr] = useState<string | null>(null)

    const load = async () => {
        setLoading(true)
        setErr(null)
        try {
            const [p, b, s, tr] = await Promise.all([
                api.getBillingPlans(),
                api.getBillingBalance(),
                api.getBillingSubscription(),
                api.getBillingTransactions(0, 50),
            ])
            setPlans(p as Plan[])
            setBalance(b)
            setSub(s)
            setTx(tr.items as Tx[])
            setTotal(tr.total)
            void refreshMe()
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        } finally {
            setLoading(false)
        }
    }

    useEffect(() => {
        void load()
    }, [])

    const subscribe = async (code: string) => {
        setBusy(code)
        setMsg(null)
        setErr(null)
        try {
            const r = await api.subscribePlan(code)
            setMsg(r.message || '已提交')
            await load()
        } catch (e) {
            setErr(e instanceof Error ? e.message : '申请失败')
        } finally {
            setBusy(null)
        }
    }

    if (loading) {
        return (
            <div className="flex justify-center py-20 text-slate-500">
                <Loader2 className="w-8 h-8 animate-spin" />
            </div>
        )
    }

    return (
        <div className="max-w-5xl space-y-8">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">订阅与流水</h1>
                <p className="text-sm text-slate-500 mt-1">套餐申请需管理员审核（MVP）</p>
            </div>
            {msg && <p className="text-sm text-emerald-600">{msg}</p>}
            {err && <p className="text-sm text-rose-600">{err}</p>}

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-6 shadow-sm">
                <h2 className="font-semibold">当前余额</h2>
                <div className="mt-3 flex flex-wrap gap-6 text-sm">
                    <div>
                        <div className="text-slate-500">点数</div>
                        <div className="text-2xl font-mono font-bold">{balance?.credits ?? '—'}</div>
                    </div>
                    <div>
                        <div className="text-slate-500">套餐代码</div>
                        <div>{balance?.plan_code || '—'}</div>
                    </div>
                    <div>
                        <div className="text-slate-500">订阅状态</div>
                        <div>{balance?.subscription_status || '—'}</div>
                    </div>
                    <div>
                        <div className="text-slate-500">到期</div>
                        <div className="break-all">{balance?.subscription_expires_at || '—'}</div>
                    </div>
                </div>
                {sub && (
                    <p className="mt-3 text-xs text-slate-500">
                        当前订阅记录：{sub.plan_code} / {sub.status}
                        {sub.expires_at ? ` · 到期 ${sub.expires_at}` : ''}
                    </p>
                )}
            </section>

            <section>
                <h2 className="font-semibold mb-4">套餐</h2>
                <div className="grid sm:grid-cols-2 lg:grid-cols-3 gap-4">
                    {plans.map((p) => (
                        <div
                            key={p.id}
                            className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-5 flex flex-col shadow-sm"
                        >
                            <div className="font-semibold text-lg">{p.name}</div>
                            <div className="text-xs text-slate-500 mt-1 font-mono">{p.code}</div>
                            <div className="mt-3 text-sm text-slate-600 dark:text-slate-300">
                                {(p.price_cents / 100).toFixed(2)} {p.currency} / {p.period_days} 天
                            </div>
                            <div className="text-sm mt-1">每月点数：{p.monthly_credits}</div>
                            <button
                                type="button"
                                disabled={!!busy}
                                onClick={() => void subscribe(p.code)}
                                className="mt-4 rounded-xl bg-blue-600 text-white py-2 text-sm disabled:opacity-50"
                            >
                                {busy === p.code ? <Loader2 className="w-4 h-4 animate-spin inline" /> : null}
                                申请订阅
                            </button>
                        </div>
                    ))}
                    {plans.length === 0 && <p className="text-slate-500 text-sm">暂无可用套餐</p>}
                </div>
            </section>

            <section className="rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 overflow-hidden shadow-sm">
                <div className="px-6 py-4 border-b border-slate-100 dark:border-slate-800 flex justify-between items-center">
                    <h2 className="font-semibold">点数流水</h2>
                    <span className="text-xs text-slate-500">共 {total} 条</span>
                </div>
                <div className="overflow-x-auto">
                    <table className="min-w-full text-sm">
                        <thead className="bg-slate-50 dark:bg-slate-900 text-left text-xs text-slate-500">
                            <tr>
                                <th className="px-4 py-2">时间</th>
                                <th className="px-4 py-2">变动</th>
                                <th className="px-4 py-2">类型</th>
                                <th className="px-4 py-2">原因</th>
                                <th className="px-4 py-2">余额</th>
                            </tr>
                        </thead>
                        <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                            {tx.map((r) => (
                                <tr key={r.id}>
                                    <td className="px-4 py-2 whitespace-nowrap text-xs">{r.created_at || '—'}</td>
                                    <td className={`px-4 py-2 font-mono ${r.delta >= 0 ? 'text-emerald-600' : 'text-rose-600'}`}>{r.delta > 0 ? `+${r.delta}` : r.delta}</td>
                                    <td className="px-4 py-2">{r.type}</td>
                                    <td className="px-4 py-2 max-w-xs truncate" title={r.reason || ''}>
                                        {r.reason || '—'}
                                    </td>
                                    <td className="px-4 py-2 font-mono">{r.balance_after}</td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            </section>
        </div>
    )
}
