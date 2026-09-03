import { FormEvent, useState } from 'react'
import { Link } from 'react-router-dom'
import { Loader2 } from 'lucide-react'
import { api } from '@/services/api'

export default function ForgotPassword() {
    const [email, setEmail] = useState('')
    const [loading, setLoading] = useState(false)
    const [msg, setMsg] = useState<string | null>(null)
    const [error, setError] = useState<string | null>(null)
    const [devLink, setDevLink] = useState<string | null>(null)

    const submit = async (e: FormEvent) => {
        e.preventDefault()
        setLoading(true)
        setError(null)
        setMsg(null)
        setDevLink(null)
        try {
            const r = await api.forgotPassword({ email })
            setMsg((r.message as string) || '若邮箱已注册，将收到重置链接')
            const d = r.dev_reset_link as string | undefined
            if (d) setDevLink(d)
        } catch (err) {
            setError(err instanceof Error ? err.message : '发送失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="min-h-screen flex items-center justify-center bg-slate-50 dark:bg-slate-950 px-4">
            <div className="w-full max-w-md rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 p-8">
                <h1 className="text-xl font-bold">忘记密码</h1>
                <form onSubmit={submit} className="mt-6 space-y-4">
                    <input
                        type="email"
                        value={email}
                        onChange={(e) => setEmail(e.target.value)}
                        placeholder="注册邮箱"
                        className="w-full rounded-xl border border-slate-200 dark:border-slate-700 px-3 py-2 text-sm"
                        required
                    />
                    {error && <p className="text-sm text-rose-600">{error}</p>}
                    {msg && <p className="text-sm text-emerald-700">{msg}</p>}
                    {devLink && (
                        <p className="text-xs break-all text-slate-600">
                            开发环境链接：<a href={devLink}>{devLink}</a>
                        </p>
                    )}
                    <button type="submit" disabled={loading} className="w-full rounded-xl bg-blue-600 text-white py-2.5 text-sm flex justify-center gap-2">
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : null}
                        发送重置邮件
                    </button>
                </form>
                <Link to="/login" className="mt-4 block text-center text-sm text-blue-600">
                    返回登录
                </Link>
            </div>
        </div>
    )
}
