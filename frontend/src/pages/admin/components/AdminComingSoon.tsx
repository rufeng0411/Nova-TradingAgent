/** 未完全接入数据时的占位：说明将展示的数据域，避免误调未实现接口 */

export default function AdminComingSoon({
    title,
    description,
    bullets,
}: {
    title: string
    description: string
    bullets?: string[]
}) {
    return (
        <div className="rounded-2xl border border-dashed border-amber-300/80 bg-amber-50/80 dark:bg-amber-950/30 dark:border-amber-700/60 p-6 space-y-3">
            <div className="text-sm font-semibold text-amber-900 dark:text-amber-100">{title} · 建设中</div>
            <p className="text-sm text-slate-700 dark:text-slate-300">{description}</p>
            {bullets && bullets.length > 0 && (
                <ul className="list-disc pl-5 text-sm text-slate-600 dark:text-slate-400 space-y-1">
                    {bullets.map((b) => (
                        <li key={b}>{b}</li>
                    ))}
                </ul>
            )}
        </div>
    )
}
