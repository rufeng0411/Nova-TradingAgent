import { FormEvent, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function ResetPassword() {
    const [params] = useSearchParams()
    const navigate = useNavigate()
    const token = useMemo(() => params.get('token') || '', [params])
    const [password, setPassword] = useState('')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const submit = async (e: FormEvent) => {
        e.preventDefault()
        if (!token) {
            setError('链接无效')
            return
        }
        setLoading(true)
        setError(null)
        try {
            await api.resetPassword(token, password)
            navigate('/login', { replace: true })
        } catch (err) {
            setError(err instanceof Error ? err.message : '重置失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
            <div className="w-full max-w-md rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8">
                <h1 className="text-xl font-bold">设置新密码</h1>
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <input
                        type="password"
                        value={password}
                        onChange={(e) => setPassword(e.target.value)}
                        placeholder="新密码（≥8 位，含字母与数字）"
                        className="w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
                        required
                    />
                    {error && <p className="text-sm text-rose-600">{error}</p>}
                    <button type="submit" disabled={loading} className="w-full rounded-xl bg-blue-600 text-white py-2.5 text-sm flex justify-center gap-2">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                        确认
                    </button>
                </form>
                <Link to="/login" className="mt-4 block text-center text-sm text-blue-600">
                    返回登录
                </Link>
            </div>
        </div>
    )
}
