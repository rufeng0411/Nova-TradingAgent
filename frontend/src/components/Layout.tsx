import { ReactNode, useEffect, useRef } from 'react'
import { useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header from './Header'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/services/api'

interface LayoutProps {
    children: ReactNode
}

export default function Layout({ children }: LayoutProps) {
    const maintenance = useAuthStore((s) => s.publicFeatures?.maintenance)
    const userId = useAuthStore((s) => s.user?.id)
    const location = useLocation()
    const navigate = useNavigate()
    const cancelledRef = useRef(false)
    const checkedForUserRef = useRef<string | null>(null)

    useEffect(() => {
        cancelledRef.current = false
        const path = location.pathname
        if (!userId) return
        if (path === '/analysis' || path.startsWith('/admin')) return
        // 同一用户只在本次会话首次进入非分析页时尝试一次：避免在其它页面频繁拉任务中心。
        if (checkedForUserRef.current === userId) return
        checkedForUserRef.current = userId

        void (async () => {
            try {
                const tasks = await api.listMyTasks()
                if (cancelledRef.current) return
                const runItem = tasks.running[0]
                if (!runItem?.job_id) return
                const st = await api.getJobStatus(runItem.job_id)
                if (cancelledRef.current) return
                if (st.status !== 'pending' && st.status !== 'running') return
                const q = new URLSearchParams({ job_id: runItem.job_id })
                const sy = (runItem.symbol || st.symbol || '').trim()
                if (sy) q.set('symbol', sy)
                navigate(`/analysis?${q}`, { replace: true })
            } catch {}
        })()

        return () => {
            cancelledRef.current = true
        }
    }, [userId, location.pathname, navigate])

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100">
            {maintenance && (
                <div className="bg-amber-500 text-amber-950 text-center text-sm py-2 px-4 font-medium">
                    系统维护中：部分功能可能暂时不可用。管理员仍可通过独立窗口访问管理后台。
                </div>
            )}
            <Sidebar />
            <div className="ml-16 min-h-screen flex flex-col">
                <Header />
                <main className="flex-1 p-6 bg-slate-50 dark:bg-gradient-to-br dark:from-slate-900 dark:via-slate-900/95 dark:to-slate-800">
                    {children}
                </main>
            </div>
        </div>
    )
}
