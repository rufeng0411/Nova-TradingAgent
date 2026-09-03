import type { BusinessDay, UTCTimestamp } from 'lightweight-charts'

export function parseDateToBD(dateStr: string): BusinessDay | null {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(dateStr.slice(0, 10))
    if (!m) return null
    return { year: Number(m[1]), month: Number(m[2]), day: Number(m[3]) }
}

/** K 线十字光标 / 轴标签：只显示交易日日期（上海日历） */
export function formatKlineCrosshairTime(time: BusinessDay | UTCTimestamp): string {
    if (typeof time === 'object' && time !== null && 'year' in time) {
        const bd = time as BusinessDay
        return `${bd.year}-${String(bd.month).padStart(2, '0')}-${String(bd.day).padStart(2, '0')}`
    }
    if (typeof time === 'number') {
        return new Intl.DateTimeFormat('en-CA', {
            timeZone: 'Asia/Shanghai',
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
        }).format(new Date(time * 1000))
    }
    return String(time)
}

/** 分时图十字光标：上海时区的日期+时刻 */
export function formatIntradayCrosshairTime(time: BusinessDay | UTCTimestamp): string {
    if (typeof time === 'number') {
        return new Intl.DateTimeFormat('zh-CN', {
            timeZone: 'Asia/Shanghai',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false,
        }).format(new Date(time * 1000))
    }
    return String(time)
}
