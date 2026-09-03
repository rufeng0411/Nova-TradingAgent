import { format, startOfYear, subMonths, subYears } from 'date-fns'
import type { ChartRangePreset } from '@/types'

export function rangePresetToDates(preset: ChartRangePreset, end: Date = new Date()): { start: string; end: string } {
    const endStr = format(end, 'yyyy-MM-dd')
    let start: Date
    switch (preset) {
        case '1M':
            start = subMonths(end, 1)
            break
        case '3M':
            start = subMonths(end, 3)
            break
        case '6M':
            start = subMonths(end, 6)
            break
        case 'YTD':
            start = startOfYear(end)
            break
        case '1Y':
            start = subYears(end, 1)
            break
        case '3Y':
            start = subYears(end, 3)
            break
        case '5Y':
            start = subYears(end, 5)
            break
        case 'ALL':
            start = new Date(1990, 0, 1)
            break
        default:
            start = subMonths(end, 6)
    }
    return { start: format(start, 'yyyy-MM-dd'), end: endStr }
}
