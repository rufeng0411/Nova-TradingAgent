import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Monitor, Moon, Sun, CreditCard, ChevronLeft } from 'lucide-react'
import { useAuthStore } from '@/stores/authStore'

type ThemeMode = 'system' | 'light' | 'dark'

interface MobileHeaderProps {
    title?: string
    showBack?: boolean
    onBack?: () => void
}

export default function MobileHeader({ title = 'Nova-TradingAgent', showBack = false, onBack }: MobileHeaderProps) {
    const navigate = useNavigate()
    const { user } = useAuthStore()
    
    const [themeMode, setThemeMode] = useState<ThemeMode>(() => {
        const saved = (localStorage.getItem('ta-theme') || 'system') as ThemeMode
        return ['system', 'light', 'dark'].includes(saved) ? saved : 'system'
    })

    useEffect(() => {
        const onSync = () => {
            const saved = (localStorage.getItem('ta-theme') || 'system') as ThemeMode
            const mode: ThemeMode = ['system', 'light', 'dark'].includes(saved) ? saved : 'system'
            setThemeMode(mode)
        }
        window.addEventListener('ta-theme-sync', onSync)
        return () => window.removeEventListener('ta-theme-sync', onSync)
    }, [])

    const cycleTheme = () => {
        const next: ThemeMode =
            themeMode === 'system' ? 'light' : themeMode === 'light' ? 'dark' : 'system'
        localStorage.setItem('ta-theme', next)
        setThemeMode(next)
        window.dispatchEvent(new Event('ta-theme-sync'))
        
        // 应用主题
        const root = document.documentElement
        const systemDark = window.matchMedia('(prefers-color-scheme: dark)').matches
        const shouldBeDark = next === 'system' ? systemDark : next === 'dark'
        root.classList.toggle('dark', shouldBeDark)
    }

    const ThemeIcon = themeMode === 'system' ? Monitor : themeMode === 'light' ? Sun : Moon

    return (
        <header className="sticky top-0 z-40 h-14 bg-white/80 dark:bg-slate-950/80 backdrop-blur-xl border-b border-slate-200/80 dark:border-slate-800 flex items-center px-4 justify-between">
            <div className="flex-1 flex items-center justify-start">
                {showBack ? (
                    <button 
                        onClick={onBack || (() => navigate(-1))} 
                        className="p-2 -ml-2 text-slate-700 dark:text-slate-300 active:opacity-70"
                    >
                        <ChevronLeft className="w-6 h-6" />
                    </button>
                ) : (
                    <div className="flex items-center gap-2">
                        <div className="w-2.5 h-2.5 rounded-full bg-emerald-500 shadow-[0_0_12px_rgba(16,185,129,0.5)]" />
                    </div>
                )}
            </div>

            <div className="flex-1 flex justify-center">
                <span className="font-semibold text-slate-900 dark:text-slate-100 text-base truncate max-w-[150px]">
                    {title}
                </span>
            </div>

            <div className="flex-1 flex justify-end items-center gap-3">
                {user && (
                    <button 
                        onClick={() => navigate('/m/subscription')}
                        className="flex items-center gap-1 bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded-full active:scale-95"
                    >
                        <CreditCard className="w-3.5 h-3.5 text-slate-500 dark:text-slate-400" />
                        <span className="text-xs font-mono font-medium text-slate-700 dark:text-slate-300">{user.credits ?? 0}</span>
                    </button>
                )}
                <button onClick={cycleTheme} className="p-1.5 rounded-full bg-slate-100 dark:bg-slate-800 text-slate-600 dark:text-slate-400 active:scale-95">
                    <ThemeIcon className="w-4 h-4" />
                </button>
            </div>
        </header>
    )
}
