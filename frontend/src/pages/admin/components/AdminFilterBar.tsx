import type { ReactNode } from 'react'

export type DateRangeValue = {
    startDate: string
    endDate: string
}

export default function AdminFilterBar({
    range,
    onRangeChange,
    onRefresh,
    onExportCsv,
    extra,
    grain,
    onGrainChange,
    loading,
}: {
    range: DateRangeValue
    onRangeChange: (r: DateRangeValue) => void
    onRefresh?: () => void
    onExportCsv?: () => void
    extra?: ReactNode
    grain?: 'day' | 'hour'
    onGrainChange?: (g: 'day' | 'hour') => void
    loading?: boolean
}) {
    return (
        <div className="flex flex-wrap items-end gap-3 rounded-xl border border-slate-200 dark:border-slate-800 bg-white/80 dark:bg-slate-900/50 p-3">
            <label className="text-xs text-slate-500 block">
                开始日期
                <input
                    type="date"
                    className="mt-1 block rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1 text-sm"
                    value={range.startDate}
                    onChange={(e) => onRangeChange({ ...range, startDate: e.target.value })}
                />
            </label>
            <label className="text-xs text-slate-500 block">
                结束日期
                <input
                    type="date"
                    className="mt-1 block rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1 text-sm"
                    value={range.endDate}
                    onChange={(e) => onRangeChange({ ...range, endDate: e.target.value })}
                />
            </label>
            <button
                type="button"
                className="text-xs rounded-lg border border-slate-200 dark:border-slate-700 px-2 py-1.5 hover:bg-slate-100 dark:hover:bg-slate-800"
                onClick={() => {
                    const to = new Date()
                    const from = new Date(to)
                    from.setUTCDate(from.getUTCDate() - 13)
                    onRangeChange({
                        startDate: from.toISOString().slice(0, 10),
                        endDate: to.toISOString().slice(0, 10),
                    })
                }}
            >
                近 14 天
            </button>
            {onGrainChange && grain !== undefined ? (
                <label className="text-xs text-slate-500 block">
                    粒度
                    <select
                        className="mt-1 block rounded-lg border border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-950 px-2 py-1 text-sm"
                        value={grain}
                        onChange={(e) => onGrainChange(e.target.value as 'day' | 'hour')}
                    >
                        <option value="day">按天</option>
                        <option value="hour">按小时</option>
                    </select>
                </label>
            ) : null}
            {extra}
            <div className="flex-1" />
            {onExportCsv ? (
                <button
                    type="button"
                    disabled={loading}
                    onClick={onExportCsv}
                    className="text-sm rounded-lg bg-slate-900 text-white dark:bg-slate-100 dark:text-slate-900 px-3 py-1.5 disabled:opacity-50"
                >
                    导出 CSV
                </button>
            ) : null}
            {onRefresh ? (
                <button
                    type="button"
                    disabled={loading}
                    onClick={onRefresh}
                    className="text-sm rounded-lg border border-slate-200 dark:border-slate-700 px-3 py-1.5 hover:bg-slate-50 dark:hover:bg-slate-800 disabled:opacity-50"
                >
                    {loading ? '刷新中…' : '刷新'}
                </button>
            ) : null}
        </div>
    )
}
