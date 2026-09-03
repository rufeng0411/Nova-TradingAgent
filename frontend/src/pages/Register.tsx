import { FormEvent, useEffect, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

export default function Register() {
    const navigate = useNavigate()
    const { setAuth } = useAuthStore()
    const [username, setUsername] = useState('')
    const [email, setEmail] = useState('')
    const [phone, setPhone] = useState('')
    const [password, setPassword] = useState('')
    const [avail, setAvail] = useState<boolean | null>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        const t = username.trim().toLowerCase()
        if (t.length < 3) {
            setAvail(null)
            return
        }
        const h = setTimeout(() => {
            void api
                .checkUsername(t)
                .then((r) => setAvail(r.available))
                .catch(() => setAvail(null))
        }, 500)
        return () => clearTimeout(h)
    }, [username])

    const submit = async (e: FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setError(null)
        try {
            const res = await api.register({
                username,
                email,
                password,
                phone: phone || undefined,
            })
            setAuth(res.access_token, res.user)
            navigate('/analysis', { replace: true })
        } catch (err) {
            setError(err instanceof Error ? err.message : '注册失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4 py-10">
            <div className="w-full max-w-md rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-xl">
                <h1 className="text-xl font-bold">注册</h1>
                <form onSubmit={submit} className="mt-6 space-y-3">
                    <div>
                        <label className="text-xs text-slate-500">用户名（小写字母数字下划线）</label>
                        <input
                            value={username}
                            onChange={(e) => setUsername(e.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
                            required
                            minLength={3}
                        />
                        {avail === false && <p className="text-xs text-rose-600 mt-1">用户名已被占用</p>}
                        {avail === true && <p className="text-xs text-emerald-600 mt-1">可用</p>}
                    </div>
                    <div>
                        <label className="text-xs text-slate-500">邮箱</label>
                        <input
                            type="email"
                            value={email}
                            onChange={(e) => setEmail(e.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
                            required
                        />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500">手机（可选，找回辅助）</label>
                        <input value={phone} onChange={(e) => setPhone(e.target.value)} className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm" />
                    </div>
                    <div>
                        <label className="text-xs text-slate-500">密码（≥8 位，含字母与数字）</label>
                        <input
                            type="password"
                            value={password}
                            onChange={(e) => setPassword(e.target.value)}
                            className="mt-1 w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
                            required
                        />
                    </div>
                    {error && <p className="text-sm text-rose-600">{error}</p>}
                    <button
                        type="submit"
                        disabled={loading || avail === false}
                        className="w-full rounded-xl bg-blue-600 text-white py-2.5 text-sm font-medium disabled:opacity-50 flex justify-center gap-2"
                    >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                        注册并登录
                    </button>
                </form>
                <Link to="/login" className="mt-4 block text-center text-sm text-blue-600">
                    已有账号？登录
                </Link>
            </div>
        </div>
    )
}
