/** 历史报告页 URL ?kind= 与列表 API task_kind 对齐：短名 full|fast|kline，并兼容 fast_analysis / full_analysis。 */
export type ReportListKind = 'full' | 'fast' | 'kline'

export function reportListKindFromSearchParams(searchParams: URLSearchParams): ReportListKind {
    const raw = (searchParams.get('kind') || 'full').toLowerCase().trim()
    if (raw === 'fast' || raw === 'fast_analysis') return 'fast'
    if (raw === 'kline') return 'kline'
    if (raw === 'full' || raw === 'full_analysis') return 'full'
    return 'full'
}
