import { FormEvent, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { Loader2, LockKeyhole, User } from 'lucide-react'
import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'

const FETCH_HINT =
    '无法连接后端。请按安装文档在仓库根启动 `uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000`，并用 http://127.0.0.1:8000 打开（需已构建 frontend/dist）。开发热重载才是 Vite 5173 + API 8001，不要与 8000 混用。'

export default function Login() {
    const navigate = useNavigate()
    const { setAuth } = useAuthStore()
    const [identifier, setIdentifier] = useState('')
    const [password, setPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const submit = async (e: FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setError(null)
        try {
            const res = await api.login({ identifier, password })
            setAuth(res.access_token, res.user)
            navigate('/analysis', { replace: true })
        } catch (err) {
            const msg = err instanceof Error ? err.message : '登录失败'
            if (msg === 'Failed to fetch') setError(FETCH_HINT)
            else setError(msg)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
            <div className="w-full max-w-md rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8 shadow-xl">
                <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">登录</h1>
                <p className="mt-1 text-sm text-slate-500">用户名或邮箱 + 密码</p>
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <div>
                        <label className="text-xs font-medium text-slate-500">用户名或邮箱</label>
                        <div className="mt-1 relative">
                            <User className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <input
                                value={identifier}
                                onChange={(e) => setIdentifier(e.target.value)}
                                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 pl-10 pr-3 py-2.5 text-sm"
                                autoComplete="username"
                                required
                            />
                        </div>
                    </div>
                    <div>
                        <label className="text-xs font-medium text-slate-500">密码</label>
                        <div className="mt-1 relative">
                            <LockKeyhole className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-slate-400" />
                            <input
                                type="password"
                                value={password}
                                onChange={(e) => setPassword(e.target.value)}
                                className="w-full rounded-xl border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 pl-10 pr-3 py-2.5 text-sm"
                                autoComplete="current-password"
                                required
                            />
                        </div>
                    </div>
                    {error && <p className="text-sm text-rose-600">{error}</p>}
                    <button
                        type="submit"
                        disabled={loading}
                        className="w-full flex items-center justify-center gap-2 rounded-xl bg-blue-600 hover:bg-blue-700 text-white py-2.5 text-sm font-medium disabled:opacity-50"
                    >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                        登录
                    </button>
                </form>
                <div className="mt-4 flex justify-between text-sm">
                    <Link to="/forgot-password" className="text-blue-600 hover:underline">
                        忘记密码
                    </Link>
                    <Link to="/register" className="text-blue-600 hover:underline">
                        注册账号
                    </Link>
                </div>
                <p className="mt-6 text-xs text-slate-400 text-center">首次使用邮箱 OTP 老账号？请使用「忘记密码」设置密码。</p>
            </div>
        </div>
    )
}
