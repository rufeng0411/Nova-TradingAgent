import { useCallback, useEffect, useMemo, useState } from 'react'
import { Menu, PanelLeftClose, PanelLeft, LogOut, Shield, Monitor } from 'lucide-react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { api } from '@/services/api'
import { ADMIN_NAV_GROUPS, filterAdminNavGroups } from '@/pages/admin/adminNav'
import { useMobile } from '@/hooks/useMobile'

function breadcrumbFor(pathname: string): string {
    if (pathname === '/admin' || pathname === '/admin/') return '概览'
    for (const g of ADMIN_NAV_GROUPS) {
        for (const it of g.items) {
            if (pathname === it.to || pathname.startsWith(it.to + '/')) {
                return `${g.label} / ${it.label}`
            }
        }
    }
    return '管理后台'
}

export default function AdminShell() {
    const navigate = useNavigate()
    const location = useLocation()
    const { user, logout } = useAuthStore()
    const [navCollapsed, setNavCollapsed] = useState(false)
    const [mobileOpen, setMobileOpen] = useState(false)
    const [bootstrap, setBootstrap] = useState<{
        enabled_modules?: Record<string, boolean>
        api_version?: string
    } | null>(null)

    const loadBootstrap = useCallback(() => {
        void api
            .adminBootstrap()
            .then((b) => setBootstrap(b))
            .catch(() => setBootstrap(null))
    }, [])

    useEffect(() => {
        loadBootstrap()
    }, [loadBootstrap])

    const perms = user?.admin_permissions ?? null
    const groups = useMemo(() => filterAdminNavGroups(ADMIN_NAV_GROUPS, perms), [perms])

    const initials = useMemo(() => {
        const s = (user?.username || user?.email || '').trim()
        return s ? s.slice(0, 2).toUpperCase() : 'AD'
    }, [user])

    const crumb = useMemo(() => breadcrumbFor(location.pathname), [location.pathname])

    const closeMobile = () => setMobileOpen(false)

    const isMobile = useMobile()

    if (isMobile) {
        return (
            <div className="flex-1 flex flex-col items-center justify-center p-8 text-center min-h-[100dvh] bg-slate-50 dark:bg-slate-950">
                <Monitor className="w-16 h-16 text-slate-300 dark:text-slate-700 mb-4" />
                <h2 className="text-xl font-bold mb-2 text-slate-900 dark:text-slate-100">电脑端专享功能</h2>
                <p className="text-slate-500 dark:text-slate-400 mb-8 text-sm max-w-xs mx-auto">
                    管理后台包含大量数据报表和复杂操作，为了保证您的体验，请在 PC 端浏览器中访问。
                </p>
                <button 
                    className="px-6 py-2.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-medium transition-colors" 
                    onClick={() => navigate('/m')}
                >
                    返回移动端控制台
                </button>
            </div>
        )
    }

    return (
        <div className="min-h-screen bg-slate-50 dark:bg-slate-950 text-slate-900 dark:text-slate-100 flex flex-col md:flex-row">
            {/* Mobile overlay */}
            {mobileOpen ? (
                <button
                    type="button"
                    aria-label="关闭菜单"
                    className="fixed inset-0 z-40 bg-black/40 md:hidden"
                    onClick={closeMobile}
                />
            ) : null}

            <aside
                className={`fixed z-50 inset-y-0 left-0 w-60 border-r border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 flex flex-col transition-transform duration-200 md:static md:translate-x-0 ${
                    mobileOpen ? 'translate-x-0' : '-translate-x-full md:translate-x-0'
                } ${navCollapsed ? 'md:w-16' : 'md:w-56'}`}
            >
                <div className="p-3 border-b border-slate-200 dark:border-slate-800 flex items-center gap-2">
                    <Shield className="w-6 h-6 text-blue-600 shrink-0" />
                    {!navCollapsed ? (
                        <div className="min-w-0 flex-1">
                            <div className="font-semibold truncate text-sm">管理后台</div>
                            <div className="text-[10px] text-slate-500 truncate">{bootstrap?.api_version ?? ''}</div>
                        </div>
                    ) : null}
                    <button
                        type="button"
                        className="hidden md:inline-flex p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800"
                        onClick={() => setNavCollapsed((v) => !v)}
                        aria-label={navCollapsed ? '展开侧栏' : '收起侧栏'}
                    >
                        {navCollapsed ? <PanelLeft className="w-4 h-4" /> : <PanelLeftClose className="w-4 h-4" />}
                    </button>
                </div>
                <nav className="flex-1 overflow-y-auto p-2 space-y-4">
                    {groups.map((g) => (
                        <div key={g.id}>
                            {!navCollapsed ? (
                                <div className="text-[10px] uppercase tracking-wider text-slate-400 px-2 mb-1">{g.label}</div>
                            ) : null}
                            <div className="space-y-0.5">
                                {g.items.map((it) => (
                                    <NavLink
                                        key={it.to}
                                        to={it.to}
                                        end={it.to === '/admin' || it.to === '/admin/reports/overview'}
                                        onClick={closeMobile}
                                        title={navCollapsed ? it.label : undefined}
                                        className={({ isActive }) =>
                                            `flex items-center gap-2 rounded-lg px-2 py-1.5 text-sm ${
                                                isActive
                                                    ? 'bg-blue-600 text-white'
                                                    : 'text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-800'
                                            } ${navCollapsed ? 'justify-center' : ''}`
                                        }
                                    >
                                        {it.status === 'building' && !navCollapsed ? (
                                            <span className="text-[10px] text-amber-600 shrink-0">建设中</span>
                                        ) : null}
                                        {!navCollapsed ? (
                                            <span className="truncate">{it.label}</span>
                                        ) : (
                                            <span className="text-[10px] font-medium w-8 text-center leading-tight">
                                                {it.label.slice(0, 2)}
                                            </span>
                                        )}
                                    </NavLink>
                                ))}
                            </div>
                        </div>
                    ))}
                </nav>
            </aside>

            <div className="flex-1 flex flex-col min-w-0 md:min-h-screen">
                <header className="sticky top-0 z-30 border-b border-slate-200 dark:border-slate-800 bg-white/90 dark:bg-slate-900/90 backdrop-blur flex items-center gap-3 px-3 py-2 md:px-4">
                    <button
                        type="button"
                        className="md:hidden p-2 rounded-lg border border-slate-200 dark:border-slate-700"
                        onClick={() => setMobileOpen(true)}
                        aria-label="打开菜单"
                    >
                        <Menu className="w-5 h-5" />
                    </button>
                    <div className="min-w-0 flex-1">
                        <div className="text-xs text-slate-500">当前位置</div>
                        <div className="font-medium truncate text-sm">{crumb}</div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0">
                        <div className="hidden sm:block text-right text-xs text-slate-500 max-w-[160px] truncate">
                            {user?.email}
                        </div>
                        <div className="w-8 h-8 rounded-full bg-blue-100 dark:bg-blue-900/40 text-blue-800 dark:text-blue-200 flex items-center justify-center text-xs font-bold">
                            {initials}
                        </div>
                        <button
                            type="button"
                            onClick={() => {
                                logout()
                                navigate('/login')
                            }}
                            className="inline-flex items-center gap-1 rounded-lg border border-slate-200 dark:border-slate-700 px-2 py-1 text-xs hover:bg-slate-100 dark:hover:bg-slate-800"
                        >
                            <LogOut className="w-3.5 h-3.5" />
                            退出
                        </button>
                    </div>
                </header>
                <main className="flex-1 p-4 md:p-6 w-full max-w-[1600px] mx-auto">
                    <Outlet context={{ bootstrap, reloadBootstrap: loadBootstrap }} />
                </main>
            </div>
        </div>
    )
}
