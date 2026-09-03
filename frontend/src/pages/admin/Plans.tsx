import { FormEvent, useEffect, useState } from 'react'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

type PlanRow = {
    id: string
    code: string
    name: string
    price_cents: number
    currency: string
    period_days: number
    monthly_credits: number
    is_active?: boolean
    sort_order?: number
}

export default function AdminPlans() {
    const [rows, setRows] = useState<PlanRow[]>([])
    const [err, setErr] = useState<string | null>(null)
    const [msg, setMsg] = useState<string | null>(null)
    const [busy, setBusy] = useState(false)
    const [code, setCode] = useState('')
    const [name, setName] = useState('')
    const [price, setPrice] = useState('0')
    const [days, setDays] = useState('30')
    const [mc, setMc] = useState('0')

    const load = async () => {
        setErr(null)
        try {
            const r = await api.adminPlans()
            setRows(r as PlanRow[])
        } catch (e) {
            setErr(e instanceof Error ? e.message : '加载失败')
        }
    }

    useEffect(() => {
        void load()
    }, [])

    const create = async (e: FormEvent) => {
        e.preventDefault()
        setBusy(true)
        setMsg(null)
        try {
            await api.adminCreatePlan({
                code: code.trim(),
                name: name.trim(),
                price_cents: Math.round(Number(price) * 100),
                period_days: Number(days) || 30,
                monthly_credits: Number(mc) || 0,
            })
            setCode('')
            setName('')
            setMsg('已创建')
            await load()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    const toggle = async (p: PlanRow) => {
        setBusy(true)
        try {
            await api.adminPatchPlan(p.id, { is_active: !p.is_active })
            await load()
        } catch (ex) {
            setErr(ex instanceof Error ? ex.message : '失败')
        } finally {
            setBusy(false)
        }
    }

    return (
        <div className="space-y-6">
            {msg && <p className="text-sm text-emerald-600">{msg}</p>}
            {err && <p className="text-sm text-rose-600">{err}</p>}

            <form onSubmit={create} className="rounded-2xl border border-slate-200 dark:border-slate-800 p-4 grid sm:grid-cols-2 lg:grid-cols-6 gap-3 items-end bg-white dark:bg-slate-900/60">
                <div>
                    <label className="text-xs text-slate-500">code</label>
                    <input value={code} onChange={(e) => setCode(e.target.value)} className="mt-1 w-full rounded-xl border px-2 py-1.5 text-sm bg-white dark:bg-slate-950" required />
                </div>
                <div>
                    <label className="text-xs text-slate-500">名称</label>
                    <input value={name} onChange={(e) => setName(e.target.value)} className="mt-1 w-full rounded-xl border px-2 py-1.5 text-sm bg-white dark:bg-slate-950" required />
                </div>
                <div>
                    <label className="text-xs text-slate-500">价格(元)</label>
                    <input value={price} onChange={(e) => setPrice(e.target.value)} type="number" step="0.01" className="mt-1 w-full rounded-xl border px-2 py-1.5 text-sm bg-white dark:bg-slate-950" />
                </div>
                <div>
                    <label className="text-xs text-slate-500">周期天</label>
                    <input value={days} onChange={(e) => setDays(e.target.value)} type="number" className="mt-1 w-full rounded-xl border px-2 py-1.5 text-sm bg-white dark:bg-slate-950" />
                </div>
                <div>
                    <label className="text-xs text-slate-500">月点数</label>
                    <input value={mc} onChange={(e) => setMc(e.target.value)} type="number" className="mt-1 w-full rounded-xl border px-2 py-1.5 text-sm bg-white dark:bg-slate-950" />
                </div>
                <button type="submit" disabled={busy} className="rounded-xl bg-blue-600 text-white py-2 text-sm h-9">
                    {busy ? <Loader2 className="w-4 h-4 animate-spin inline" /> : '新建'}
                </button>
            </form>

            <div className="rounded-2xl border border-slate-200 dark:border-slate-800 overflow-hidden bg-white dark:bg-slate-900/60 shadow-sm">
                <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-900 text-left text-xs text-slate-500">
                        <tr>
                            <th className="px-4 py-2">code</th>
                            <th className="px-4 py-2">名称</th>
                            <th className="px-4 py-2">价格</th>
                            <th className="px-4 py-2">天</th>
                            <th className="px-4 py-2">月点数</th>
                            <th className="px-4 py-2">启用</th>
                        </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 dark:divide-slate-800">
                        {rows.map((p) => (
                            <tr key={p.id}>
                                <td className="px-4 py-2 font-mono">{p.code}</td>
                                <td className="px-4 py-2">{p.name}</td>
                                <td className="px-4 py-2">{(p.price_cents / 100).toFixed(2)} {p.currency}</td>
                                <td className="px-4 py-2">{p.period_days}</td>
                                <td className="px-4 py-2">{p.monthly_credits}</td>
                                <td className="px-4 py-2">
                                    <button type="button" onClick={() => void toggle(p)} className="text-blue-600 text-xs">
                                        {p.is_active === false ? '已停⇒启用' : '停用'}
                                    </button>
                                </td>
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    )
}
