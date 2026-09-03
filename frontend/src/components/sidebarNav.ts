import type { LucideIcon } from 'lucide-react'
import {
    Activity,
    Briefcase,
    CandlestickChart,
    CreditCard,
    FileText,
    LayoutDashboard,
    ListTodo,
    MessageSquare,
    Settings,
    UserCircle,
    Wallet,
    Zap,
} from 'lucide-react'

export interface SidebarNavItem {
    path: string
    icon: LucideIcon
    label: string
}

export const navItems: SidebarNavItem[] = [
    { path: '/', icon: LayoutDashboard, label: '控制台' },
    { path: '/analysis', icon: Activity, label: '智能分析' },
    { path: '/analysis/fast', icon: Zap, label: '快速分析' },
    { path: '/chart', icon: CandlestickChart, label: 'K线分析' },
    { path: '/tasks', icon: ListTodo, label: '任务中心' },
    { path: '/reports', icon: FileText, label: '历史报告' },
    { path: '/portfolio', icon: Briefcase, label: '自选 & 定时' },
    { path: '/tracking-board', icon: Wallet, label: '跟踪看板' },
    { path: '/realtime-board', icon: Activity, label: '实时盘' },
    { path: '/account', icon: UserCircle, label: '账户' },
    { path: '/subscription', icon: CreditCard, label: '订阅' },
    { path: '/feedback', icon: MessageSquare, label: '反馈留言' },
    { path: '/settings', icon: Settings, label: '设置' },
]
