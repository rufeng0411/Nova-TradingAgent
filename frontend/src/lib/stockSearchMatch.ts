import { normalizeChartSymbol } from '@/lib/cnSymbol'
import type { StockSearchResult } from '@/types'

function rowHasDisplayName(r: { name?: string }): boolean {
    return r.name != null && String(r.name).trim() !== ''
}

/** 将 stock-search 结果与当前输入对齐（支持仅 6 位或带后缀代码） */
export function pickBestStockSearchResult(
    sym: string,
    results: StockSearchResult[],
): StockSearchResult | undefined {
    if (!results.length) return undefined
    const norm = normalizeChartSymbol(sym)
    const exact = results.find((r) => r.symbol.trim().toUpperCase() === norm && rowHasDisplayName(r))
    if (exact) return exact
    const exactNoName = results.find((r) => r.symbol.trim().toUpperCase() === norm)
    if (exactNoName) return exactNoName
    const digits = /^(\d{6})(?:\.[A-Z]{2})?$/i.exec(norm)
    const six = digits?.[1]
    if (six) {
        const withName = results.find((r) => {
            const head = r.symbol.split('.')[0]?.toUpperCase()
            return head === six && rowHasDisplayName(r)
        })
        if (withName) return withName
        const one = results.find((r) => {
            const head = r.symbol.split('.')[0]?.toUpperCase()
            return head === six
        })
        if (one) return one
    }
    const firstNamed = results.find(rowHasDisplayName)
    return firstNamed ?? results[0]
}
