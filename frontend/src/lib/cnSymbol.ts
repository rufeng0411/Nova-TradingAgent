import { formatStockNameCode } from '@/utils/stockDisplay'

/**
 * 将 A 股常见输入规范为 XXXXXX.SH / XXXXXX.SZ / XXXXXX.BJ，与后端 `_normalize_symbol` 对齐。
 */
export function normalizeCnAshareSymbol(raw: string): string {
    const s = raw.trim().toUpperCase()
    if (!s) return ''
    const m = s.match(/^(\d{6})(?:\.(SH|SZ|SS|BJ))?$/)
    if (m) {
        const code = m[1]
        const suf = m[2]
        if (suf === 'SS') return `${code}.SH`
        if (suf === 'SH' || suf === 'SZ' || suf === 'BJ') return `${code}.${suf}`
        // 与 api.main._normalize_symbol 一致：5/6/9 → SH，否则北京所 8/4 常见口径单独处理
        if (code.startsWith('8') || code.startsWith('4')) return `${code}.BJ`
        const market = code.startsWith('5') || code.startsWith('6') || code.startsWith('9') ? 'SH' : 'SZ'
        return `${code}.${market}`
    }
    return s
}

/** 专业 K 线页统一用的规范代码（含交易所后缀），用于 URL / store / 与后端 stock-search 对齐 */
export function normalizeChartSymbol(raw: string): string {
    const s = raw.trim()
    if (!s) return ''
    const n = normalizeCnAshareSymbol(s)
    return (n || s).trim().toUpperCase()
}

/** 展示用：「名称 代码」，与全站 formatStockNameCode 一致 */
export function formatCnSymbolLabel(symbol: string, name: string | null | undefined): string {
    return formatStockNameCode(name, symbol)
}
