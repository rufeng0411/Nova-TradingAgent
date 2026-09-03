import { api } from '@/services/api'
import { normalizeChartSymbol } from '@/lib/cnSymbol'
import { pickBestStockSearchResult } from '@/lib/stockSearchMatch'

/** A 股 XXXXXX.SH/SZ/BJ：拉取 stock-search 得到中文简称；失败或非标返回 null */
export async function fetchAshareDisplayName(symbol: string, signal?: AbortSignal): Promise<string | null> {
    const sym = normalizeChartSymbol(symbol) || symbol.trim().toUpperCase()
    if (!/^\d{6}\.(SH|SZ|BJ)$/i.test(sym)) return null

    const pickName = async (query: string): Promise<string | null> => {
        try {
            const { results } = await api.searchStocks(query, signal)
            const row = pickBestStockSearchResult(sym, results || [])
            const n = row?.name != null ? String(row.name).trim() : ''
            return n || null
        } catch {
            return null
        }
    }

    let n = await pickName(sym)
    if (!n) {
        const six = sym.split('.')[0]
        if (six && six.length === 6) {
            n = await pickName(six)
        }
    }
    return n
}
