import { useEffect, useLayoutEffect, useMemo, useRef, useState, useCallback } from 'react'
import { Bell, BellOff, ChevronDown, CreditCard, LogOut, Monitor, Moon, Settings, Shield, Sun, UserCircle } from 'lucide-react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/stores/authStore'
import { useThemeStore } from '@/stores/themeStore'

type ThemeMode = 'system' | 'light' | 'dark'

function getInitials(user?: { username?: string | null; email?: string | null } | null): string {
    const s = (user?.username || user?.email || '').trim()
    if (!s) return 'NT'
    return s.slice(0, 2).toUpperCase()
}

export default function Header() {
    const navigate = useNavigate()
    const { user, logout } = useAuthStore()
    const skin = useThemeStore((s) => s.skin)
    const setSkin = useThemeStore((s) => s.setSkin)
    const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
        const saved = (localStorage.getItem('ta-theme') || 'system') as ThemeMode
        return ['system', 'light', 'dark'].includes(saved) ? saved : 'system'
    })
    const [notifPermission, setNotifPermission] = useState<NotificationPermission>(() =>
        typeof window !== 'undefined' && 'Notification' in window ? Notification.permission : 'default',
    )
    const [menuOpen, setMenuOpen] = useState(false)
    const menuRef = useRef<HTMLDivElement | null>(null)

    const applyTheme = useCallback((mode: ThemeMode) => {
        const root = document.documentElement
        const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
        const shouldBeDark = mode === 'system' ? systemDark : mode === 'dark'
        root.classList.toggle('dark', shouldBeDark)
    }, [])

    useLayoutEffect(() => {
        applyTheme(themeMode)
    }, [applyTheme, themeMode])

    useEffect(() => {
        const onSync = () => {
            const saved = (localStorage.getItem('ta-theme') || 'system') as ThemeMode
            const mode: ThemeMode = ['system', 'light', 'dark'].includes(saved) ? saved : 'system'
            setThemeMode(mode)
        }
        window.addEventListener('ta-theme-sync', onSync)
        return () => window.removeEventListener('ta-theme-sync', onSync)
    }, [])

    useEffect(() => {
        const onClick = (event: MouseEvent) => {
            if (menuRef.current && !menuRef.current.contains(event.target as Node)) {
                setMenuOpen(false)
            }
        }
        document.addEventListener('mousedown', onClick)
        return () => document.removeEventListener('mousedown', onClick)
    }, [])

    const cycleTheme = () => {
        const next: ThemeMode =
            themeMode === 'system' ? 'light' : themeMode === 'light' ? 'dark' : 'system'
        localStorage.setItem('ta-theme', next)
        setThemeMode(next)
        window.dispatchEvent(new Event('ta-theme-sync'))
    }

    const toggleNotifications = async () => {
        if (!('Notification' in window)) return
        if (Notification.permission === 'denied') {
            alert('通知权限已被浏览器拒绝，请在浏览器设置中手动开启')
            return
        }
        const perm = await Notification.requestPermission()
        setNotifPermission(perm)
    }

    const themeLabel = themeMode === 'system' ? '跟随系统' : themeMode === 'light' ? '浅色' : '深色'
    const ThemeIcon = themeMode === 'system' ? Monitor : themeMode === 'light' ? Sun : Moon
    const accountTone = useMemo(() => getInitials(user), [user])

    return (
        <header className="h-16 sticky top-0 z-40 border-b border-slate-200/80 dark:border-slate-800 bg-white/88 dark:bg-slate-950/78 backdrop-blur-xl">
            <div className="h-full px-6 flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <div className="hidden md:flex items-center gap-4">
                        <div className="flex items-center gap-2.5">
                            <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_16px_rgba(16,185,129,0.4)]" />
                            <div className="text-sm font-semibold tracking-[0.04em] text-slate-900 dark:text-slate-100">Nova-TradingAgent</div>
                        </div>
                        <div className="h-4 w-px bg-slate-200 dark:bg-slate-800" />
                        <div className="text-xs tracking-[0.18em] text-slate-400 dark:text-slate-500">工作台在线</div>
                    </div>
                </div>

                <div className="flex items-center gap-2">
                    {user && (
                        <>
                            <button
                                type="button"
                                onClick={() => navigate('/subscription')}
                                className="hidden sm:flex items-center gap-1.5 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-3 py-1.5 text-xs font-medium text-slate-700 dark:text-slate-200 hover:border-blue-300"
                                title="订阅与流水"
                            >
                                <CreditCard className="w-3.5 h-3.5" />
                                <span className="font-mono text-blue-600 dark:text-blue-400">{user.credits ?? 0}</span>
                                <span className="text-slate-400">点</span>
                                {user.plan_code && <span className="text-slate-500 truncate max-w-[5rem]">{user.plan_code}</span>}
                            </button>
                            {user.role === 'admin' && (
                                <button
                                    type="button"
                                    onClick={() => {
                                        const w = window.open('/admin', 'taAdmin', 'noopener,noreferrer,width=1440,height=900')
                                        if (!w) navigate('/admin')
                                    }}
                                    className="hidden sm:inline-flex items-center gap-1 rounded-2xl border border-amber-200 dark:border-amber-800 bg-amber-50 dark:bg-amber-950/50 px-2.5 py-1.5 text-xs font-medium text-amber-900 dark:text-amber-100"
                                >
                                    <Shield className="w-3.5 h-3.5" />
                                    管理
                                </button>
                            )}
                        </>
                    )}
                    {user && (
                        <div className="relative" ref={menuRef}>
                            <button
                                onClick={() => setMenuOpen(v => !v)}
                                className="group flex items-center gap-2 rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900 px-2 py-1.5 hover:border-slate-300 dark:hover:border-slate-700 hover:bg-slate-50 dark:hover:bg-slate-900/90 transition-all"
                            >
                                <div className="w-8 h-8 rounded-xl bg-gradient-to-br from-cyan-500 via-blue-500 to-indigo-600 text-white flex items-center justify-center text-[11px] font-bold shadow-[0_10px_20px_rgba(37,99,235,0.2)]">
                                    {accountTone}
                                </div>
                                <ChevronDown className={`w-3.5 h-3.5 text-slate-400 transition-transform ${menuOpen ? 'rotate-180' : ''}`} />
                            </button>

                            {menuOpen && (
                                <div className="absolute right-0 top-[calc(100%+0.75rem)] w-64 rounded-3xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-950 shadow-[0_24px_80px_rgba(15,23,42,0.18)] overflow-hidden">
                                    <div className="px-4 py-3.5 border-b border-slate-100 dark:border-slate-900">
                                        <div className="text-[11px] tracking-[0.18em] text-slate-400 dark:text-slate-500">已登录</div>
                                        <div className="mt-1 text-sm font-medium text-slate-950 dark:text-slate-50">
                                            {user.username || user.email}
                                        </div>
                                        <div className="mt-0.5 text-xs text-slate-500 break-all">{user.email}</div>
                                        <div className="mt-2 flex flex-wrap gap-2 text-[11px]">
                                            <span className="rounded-lg bg-slate-100 dark:bg-slate-900 px-2 py-0.5 font-mono">点数 {user.credits ?? 0}</span>
                                            {user.plan_code && (
                                                <span className="rounded-lg bg-blue-50 dark:bg-blue-950/40 px-2 py-0.5">{user.plan_code}</span>
                                            )}
                                        </div>
                                    </div>
                                    <div className="p-2">
                                        <button
                                            onClick={() => {
                                                setMenuOpen(false)
                                                navigate('/account')
                                            }}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
                                                <UserCircle className="w-4 h-4" />
                                            </div>
                                            账户中心
                                        </button>
                                        <button
                                            onClick={() => {
                                                setMenuOpen(false)
                                                navigate('/subscription')
                                            }}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
                                                <CreditCard className="w-4 h-4" />
                                            </div>
                                            订阅与流水
                                        </button>
                                        {user.role === 'admin' && (
                                            <button
                                                onClick={() => {
                                                    setMenuOpen(false)
                                                    const w = window.open('/admin', 'taAdmin', 'noopener,noreferrer,width=1440,height=900')
                                                    if (!w) navigate('/admin')
                                                }}
                                                className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-amber-800 dark:text-amber-200 hover:bg-amber-50 dark:hover:bg-amber-950/40 transition-colors"
                                            >
                                                <div className="w-8 h-8 rounded-xl bg-amber-100 dark:bg-amber-900/40 flex items-center justify-center">
                                                    <Shield className="w-4 h-4" />
                                                </div>
                                                管理后台
                                            </button>
                                        )}
                                        <button
                                            onClick={() => {
                                                setSkin('default')
                                                setMenuOpen(false)
                                            }}
                                            className={`w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors ${
                                                skin === 'default'
                                                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                                                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900'
                                            }`}
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center text-[10px] font-bold">
                                                默
                                            </div>
                                            <div className="flex-1 text-left">
                                                <div>默认皮肤</div>
                                                <div className="text-xs text-slate-400 dark:text-slate-500">当前线上风格</div>
                                            </div>
                                        </button>
                                        <button
                                            onClick={() => {
                                                setSkin('linear')
                                                setMenuOpen(false)
                                            }}
                                            className={`w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors ${
                                                skin === 'linear'
                                                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                                                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900'
                                            }`}
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-indigo-500/15 flex items-center justify-center text-[10px] font-bold text-indigo-600 dark:text-indigo-300">
                                                L
                                            </div>
                                            <div className="flex-1 text-left">
                                                <div>Linear</div>
                                                <div className="text-xs text-slate-400 dark:text-slate-500">极简灰 + 紫蓝强调</div>
                                            </div>
                                        </button>
                                        <button
                                            onClick={() => {
                                                setSkin('graphite')
                                                setMenuOpen(false)
                                            }}
                                            className={`w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm transition-colors ${
                                                skin === 'graphite'
                                                    ? 'bg-slate-100 dark:bg-slate-800 text-slate-900 dark:text-slate-100'
                                                    : 'text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900'
                                            }`}
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-800 flex items-center justify-center text-[10px] font-bold text-slate-100">
                                                G
                                            </div>
                                            <div className="flex-1 text-left">
                                                <div>石墨</div>
                                                <div className="text-xs text-slate-400 dark:text-slate-500">投研中性灰 + 哑光靛</div>
                                            </div>
                                        </button>
                                        <button
                                            onClick={cycleTheme}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
                                                <ThemeIcon className="w-4 h-4" />
                                            </div>
                                            <div className="flex-1 text-left">
                                                <div>主题模式</div>
                                                <div className="text-xs text-slate-400 dark:text-slate-500">{themeLabel}</div>
                                            </div>
                                        </button>
                                        <button
                                            onClick={toggleNotifications}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center relative">
                                                {notifPermission === 'denied' ? <BellOff className="w-4 h-4" /> : <Bell className="w-4 h-4" />}
                                                <span className={`absolute top-1.5 right-1.5 w-1.5 h-1.5 rounded-full ${
                                                    notifPermission === 'granted' ? 'bg-emerald-500' : notifPermission === 'denied' ? 'bg-rose-500' : 'bg-slate-400'
                                                }`} />
                                            </div>
                                            <div className="flex-1 text-left">
                                                <div>通知提醒</div>
                                                <div className="text-xs text-slate-400 dark:text-slate-500">
                                                    {notifPermission === 'granted' ? '已启用' : notifPermission === 'denied' ? '已拒绝' : '未设置'}
                                                </div>
                                            </div>
                                        </button>
                                        <button
                                            onClick={() => {
                                                setMenuOpen(false)
                                                navigate('/reports')
                                            }}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
                                                <Monitor className="w-4 h-4" />
                                            </div>
                                            我的报告
                                        </button>
                                        <button
                                            onClick={() => {
                                                setMenuOpen(false)
                                                navigate('/settings')
                                            }}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-slate-700 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-900 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-slate-100 dark:bg-slate-900 flex items-center justify-center">
                                                <Settings className="w-4 h-4" />
                                            </div>
                                            模型设置
                                        </button>
                                    </div>
                                    <div className="p-2 border-t border-slate-100 dark:border-slate-900">
                                        <button
                                            onClick={() => {
                                                setMenuOpen(false)
                                                logout()
                                            }}
                                            className="w-full flex items-center gap-3 rounded-2xl px-3 py-2.5 text-sm text-rose-600 dark:text-rose-400 hover:bg-rose-50 dark:hover:bg-rose-500/10 transition-colors"
                                        >
                                            <div className="w-8 h-8 rounded-xl bg-rose-50 dark:bg-rose-500/10 flex items-center justify-center">
                                                <LogOut className="w-4 h-4" />
                                            </div>
                                            退出登录
                                        </button>
                                    </div>
                                </div>
                            )}
                        </div>
                    )}
                </div>
            </div>
        </header>
    )
}
