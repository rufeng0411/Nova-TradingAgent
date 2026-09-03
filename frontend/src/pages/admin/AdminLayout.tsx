import { NavLink, Outlet } from 'react-router-dom'

const links: { to: string; label: string; end?: boolean }[] = [
    { to: '/admin', label: '仪表盘', end: true },
    { to: '/admin/users', label: '用户' },
    { to: '/admin/access-logs', label: '访问日志' },
    { to: '/admin/plans', label: '套餐' },
    { to: '/admin/audit-logs', label: '审计' },
]

export default function AdminLayout() {
    return (
        <div className="space-y-6">
            <div>
                <h1 className="text-2xl font-bold text-slate-900 dark:text-slate-50">管理后台</h1>
                <nav className="mt-4 flex flex-wrap gap-2">
                    {links.map((l) => (
                        <NavLink
                            key={l.to}
                            to={l.to}
                            end={l.end}
                            className={({ isActive }) =>
                                `rounded-xl px-4 py-2 text-sm font-medium transition-colors ${
                                    isActive
                                        ? 'bg-blue-600 text-white'
                                        : 'bg-slate-100 dark:bg-slate-800 text-slate-700 dark:text-slate-200 hover:bg-slate-200 dark:hover:bg-slate-700'
                                }`
                            }
                        >
                            {l.label}
                        </NavLink>
                    ))}
                </nav>
            </div>
            <Outlet />
        </div>
    )
}
