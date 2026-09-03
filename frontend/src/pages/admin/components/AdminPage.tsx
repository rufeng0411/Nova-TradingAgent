import type { ReactNode } from 'react'

export default function AdminPage({
    title,
    subtitle,
    actions,
    children,
}: {
    title: string
    subtitle?: string
    actions?: ReactNode
    children: ReactNode
}) {
    return (
        <div className="space-y-4">
            <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                    <h1 className="text-xl font-bold tracking-tight">{title}</h1>
                    {subtitle ? <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">{subtitle}</p> : null}
                </div>
                {actions ? <div className="flex flex-wrap items-center gap-2 shrink-0">{actions}</div> : null}
            </div>
            {children}
        </div>
    )
}
