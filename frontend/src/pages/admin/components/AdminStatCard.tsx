export default function AdminStatCard({
    label,
    value,
    hint,
    onClick,
}: {
    label: string
    value: string | number
    hint?: string
    onClick?: () => void
}) {
    const Comp = onClick ? 'button' : 'div'
    return (
        <Comp
            type={onClick ? 'button' : undefined}
            onClick={onClick}
            className={`rounded-2xl border border-slate-200 dark:border-slate-800 bg-white dark:bg-slate-900/60 p-5 shadow-sm text-left w-full ${
                onClick ? 'hover:border-blue-400 cursor-pointer transition' : ''
            }`}
        >
            <div className="text-xs text-slate-500">{label}</div>
            <div className="mt-2 text-2xl font-bold font-mono">{value}</div>
            {hint ? <div className="mt-1 text-[11px] text-slate-400">{hint}</div> : null}
        </Comp>
    )
}
