import type { ReactNode } from 'react'

export type AdminTableColumn<T> = {
    key: string
    header: string
    render: (row: T) => ReactNode
    className?: string
}

export default function AdminDataTable<T extends { id?: string }>({
    columns,
    rows,
    loading,
    error,
    emptyText,
    page,
    pageSize,
    total,
    onPageChange,
}: {
    columns: AdminTableColumn<T>[]
    rows: T[]
    loading?: boolean
    error?: string | null
    emptyText?: string
    page: number
    pageSize: number
    total: number
    onPageChange?: (p: number) => void
}) {
    if (error) {
        return <div className="text-sm text-rose-600 py-6">{error}</div>
    }
    if (loading && rows.length === 0) {
        return <div className="text-sm text-slate-500 py-10 text-center">加载中…</div>
    }
    if (!loading && rows.length === 0) {
        return <div className="text-sm text-slate-500 py-10 text-center">{emptyText ?? '暂无数据'}</div>
    }
    const totalPages = Math.max(1, Math.ceil(total / pageSize))
    return (
        <div className="space-y-3">
            <div className="overflow-x-auto rounded-xl border border-slate-200 dark:border-slate-800">
                <table className="min-w-full text-sm">
                    <thead className="bg-slate-50 dark:bg-slate-900/80">
                        <tr>
                            {columns.map((c) => (
                                <th key={c.key} className={`text-left font-medium px-3 py-2 ${c.className ?? ''}`}>
                                    {c.header}
                                </th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, i) => (
                            <tr
                                key={(row as { id?: string }).id ?? i}
                                className="border-t border-slate-100 dark:border-slate-800 odd:bg-white even:bg-slate-50/50 dark:odd:bg-slate-950/20 dark:even:bg-slate-900/30"
                            >
                                {columns.map((c) => (
                                    <td key={c.key} className={`px-3 py-2 align-top ${c.className ?? ''}`}>
                                        {c.render(row)}
                                    </td>
                                ))}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
            {onPageChange ? (
                <div className="flex items-center justify-between text-xs text-slate-500">
                    <span>
                        第 {page} / {totalPages} 页，共 {total} 条
                    </span>
                    <div className="flex gap-2">
                        <button
                            type="button"
                            disabled={page <= 1 || loading}
                            className="rounded border px-2 py-0.5 disabled:opacity-40"
                            onClick={() => onPageChange(page - 1)}
                        >
                            上一页
                        </button>
                        <button
                            type="button"
                            disabled={page >= totalPages || loading}
                            className="rounded border px-2 py-0.5 disabled:opacity-40"
                            onClick={() => onPageChange(page + 1)}
                        >
                            下一页
                        </button>
                    </div>
                </div>
            ) : null}
        </div>
    )
}
