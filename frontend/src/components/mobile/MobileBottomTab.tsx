import { useNavigate, useLocation } from 'react-router-dom'
import { Home, LineChart, FileText, UserCircle, Activity } from 'lucide-react'

export default function MobileBottomTab() {
    const navigate = useNavigate()
    const location = useLocation()
    const pathname = location.pathname

    const tabs = [
        { path: '/m', icon: Home, label: '控制台', match: /^\/m(\/)?$/ },
        { path: '/m/analysis', icon: Activity, label: '分析', match: /^\/m\/analysis/ },
        { path: '/m/chart', icon: LineChart, label: '看盘', match: /^\/m\/chart/ },
        { path: '/m/reports', icon: FileText, label: '报告', match: /^\/m\/reports/ },
        { path: '/m/account', icon: UserCircle, label: '我的', match: /^\/m\/(account|settings|subscription|portfolio|tasks)/ }
    ]

    return (
        <div className="fixed bottom-0 left-0 right-0 z-50 bg-white/80 dark:bg-slate-900/80 backdrop-blur-xl border-t border-slate-200 dark:border-slate-800 pb-[env(safe-area-inset-bottom)]">
            <div className="flex h-14 items-center justify-around px-2">
                {tabs.map(tab => {
                    const isActive = tab.match.test(pathname)
                    const Icon = tab.icon
                    return (
                        <button
                            key={tab.path}
                            onClick={() => navigate(tab.path)}
                            className="flex flex-1 flex-col items-center justify-center gap-1 h-full relative active:scale-95 transition-transform"
                        >
                            {isActive && (
                                <div className="absolute top-1 w-1 h-1 rounded-full bg-blue-500" />
                            )}
                            <Icon 
                                className={`w-5 h-5 transition-colors ${
                                    isActive ? 'text-blue-600 dark:text-blue-400' : 'text-slate-400 dark:text-slate-500'
                                }`} 
                            />
                            <span 
                                className={`text-[10px] transition-colors ${
                                    isActive ? 'font-semibold text-blue-600 dark:text-blue-400' : 'text-slate-500'
                                }`}
                            >
                                {tab.label}
                            </span>
                        </button>
                    )
                })}
            </div>
        </div>
    )
}
