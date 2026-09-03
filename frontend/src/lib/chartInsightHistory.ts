import type { ChartInsightResult, ChartRangePreset, KlineAdjust, KlinePeriod } from '@/types'
import { perUserLocalStorageKey } from '@/lib/perUserLocalKey'

const STORAGE_BASE = 'ta-kline-insight-history'
export const CHART_INSIGHT_HISTORY_MAX = 15

export type ChartInsightHistoryItem = {
    id: string
    at: string
    symbol: string
    symbolName?: string | null
    display_label?: string | null
    rangePreset: ChartRangePreset
    period: KlinePeriod
    adjust: KlineAdjust
    insight: ChartInsightResult
    fallback_only: boolean
}

function storageKey(): string {
    return perUserLocalStorageKey(STORAGE_BASE)
}

function readAll(): ChartInsightHistoryItem[] {
    if (typeof window === 'undefined') return []
    try {
        const raw = localStorage.getItem(storageKey())
        if (!raw) return []
        const j = JSON.parse(raw) as unknown
        if (!Array.isArray(j)) return []
        return j.filter((x) => x && typeof x === 'object' && typeof (x as ChartInsightHistoryItem).id === 'string') as ChartInsightHistoryItem[]
    } catch {
        return []
    }
}

export function loadChartInsightHistory(): ChartInsightHistoryItem[] {
    return readAll().slice(0, CHART_INSIGHT_HISTORY_MAX)
}

export function getChartInsightHistoryItem(id: string): ChartInsightHistoryItem | undefined {
    return readAll().find((x) => x.id === id)
}

export function pushChartInsightHistory(
    entry: Omit<ChartInsightHistoryItem, 'id' | 'at'> & { id?: string },
): ChartInsightHistoryItem {
    const id = entry.id ?? `${Date.now()}_${Math.random().toString(36).slice(2, 10)}`
    const at = new Date().toISOString()
    const full: ChartInsightHistoryItem = { ...entry, id, at }
    const prev = readAll()
    const next = [full, ...prev.filter((x) => x.id !== id)].slice(0, CHART_INSIGHT_HISTORY_MAX)
    localStorage.setItem(storageKey(), JSON.stringify(next))
    return full
}

export function removeChartInsightHistoryItem(id: string): void {
    const next = readAll().filter((x) => x.id !== id)
    localStorage.setItem(storageKey(), JSON.stringify(next))
}
