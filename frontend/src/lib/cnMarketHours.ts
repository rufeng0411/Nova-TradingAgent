/**
 * 判断是否处于沪深京 A 股常规交易时段（上海时区周一至周五 9:30–11:30、13:00–15:00）。
 */
export function cnShanghaiDateText(now = new Date()): string {
    const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
    }).formatToParts(now)
    const y = parts.find((p) => p.type === 'year')?.value
    const m = parts.find((p) => p.type === 'month')?.value
    const d = parts.find((p) => p.type === 'day')?.value
    return y && m && d ? `${y}-${m}-${d}` : now.toISOString().slice(0, 10)
}

export function isCnAshareRegularSession(now = new Date()): boolean {
    const wd = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Shanghai',
        weekday: 'short',
    }).format(now)
    if (wd === 'Sat' || wd === 'Sun') return false

    const parts = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Shanghai',
        hour: 'numeric',
        minute: 'numeric',
        hour12: false,
    }).formatToParts(now)
    const hour = Number(parts.find((p) => p.type === 'hour')?.value ?? -1)
    const minute = Number(parts.find((p) => p.type === 'minute')?.value ?? -1)
    if (!Number.isFinite(hour) || !Number.isFinite(minute)) return false
    const mins = hour * 60 + minute
    const morning = mins >= 9 * 60 + 30 && mins <= 11 * 60 + 30
    const afternoon = mins >= 13 * 60 && mins <= 15 * 60
    return morning || afternoon
}
