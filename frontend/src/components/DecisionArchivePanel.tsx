import { useState } from 'react'
import type { DecisionArchiveEntry } from '@/types'

const RATING_COLORS: Record<string, string> = {
    Buy: 'bg-[#1e7d3a] text-white',
    Overweight: 'bg-[#69b97e] text-white',
    Hold: 'bg-[#8a8a8a] text-white',
    Underweight: 'bg-[#d97c75] text-white',
    Sell: 'bg-[#b53737] text-white',
}

type Props = {
    entries: DecisionArchiveEntry[]
}

export default function DecisionArchivePanel({ entries }: Props) {
    const [open, setOpen] = useState(false)
    if (!entries.length) {
        return (
            <div className="rounded-lg border border-slate-200 bg-slate-50 p-3 text-sm text-slate-500 dark:border-slate-700 dark:bg-slate-900/40">
                暂无历史决策档案
            </div>
        )
    }
    return (
        <div className="rounded-lg border border-slate-200 dark:border-slate-700">
            <button
                type="button"
                onClick={() => setOpen(v => !v)}
                className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium"
            >
                该 ticker 历史决策档案 ({entries.length})
                <span>{open ? '收起' : '展开'}</span>
            </button>
            {open && (
                <div className="space-y-2 border-t border-slate-200 p-3 dark:border-slate-700">
                    {entries.map((e, i) => (
                        <div key={i} className="rounded border border-slate-100 p-2 text-sm dark:border-slate-800">
                            <div className="flex flex-wrap items-center gap-2">
                                <span>{e.trade_date || '—'}</span>
                                {e.rating_5tier && (
                                    <span className={`rounded-full px-2 py-0.5 text-xs ${RATING_COLORS[e.rating_5tier] || RATING_COLORS.Hold}`}>
                                        {e.rating_5tier}
                                    </span>
                                )}
                                {e.outcome_raw_pct != null && <span>T+收益 {e.outcome_raw_pct}%</span>}
                                {e.outcome_alpha_pct != null && <span>Alpha {e.outcome_alpha_pct}%</span>}
                            </div>
                            {e.reflection_md && <p className="mt-1 text-slate-600 dark:text-slate-400">{e.reflection_md}</p>}
                        </div>
                    ))}
                </div>
            )}
        </div>
    )
}
