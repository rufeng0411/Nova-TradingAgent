import type { RealtimeQuote, TrackingBoardItem } from '@/types'

/**
 * 已知标的简称（与行情展示一致，可随后端 enrich 接口逐步下线为服务端权威数据）
 */
export const KNOWN_STOCK_NAMES: Record<string, string> = {
    '000001.SH': '上证指数',
    '000001.SZ': '平安银行',
    '399001.SZ': '深证成指',
    '399006.SZ': '创业板指',
    '000688.SH': '科创50',
    '899050.BJ': '北证50',
    '000300.SH': '沪深300',
    '000905.SH': '中证500',
    '000852.SH': '中证1000',
    '300750.SZ': '宁德时代',
    '600036.SH': '招商银行',
    '600120.SH': '浙江东方',
    '600330.SH': '天通股份',
    '600519.SH': '贵州茅台',
    '600406.SH': '国电南瑞',
    '600879.SH': '航天电子',
    '510300.SH': '沪深300ETF',
}

/** 可请求 K 线 / 行情的沪深京代码形态 */
export const EXCHANGE_LISTED_SYMBOL_RE = /^\d{6}\.(SH|SZ|BJ)$/i

function normalizeDisplaySymbol(symbol: string): string {
    const s = symbol.trim().toUpperCase()
    const m = s.match(/^(\d{6})(?:\.(SH|SZ|SS|BJ))?$/)
    if (!m) return s
    const code = m[1]
    const suffix = m[2]
    if (suffix === 'SS') return `${code}.SH`
    if (suffix === 'SH' || suffix === 'SZ' || suffix === 'BJ') return `${code}.${suffix}`
    if (code.startsWith('8') || code.startsWith('4')) return `${code}.BJ`
    return `${code}.${code.startsWith('5') || code.startsWith('6') || code.startsWith('9') ? 'SH' : 'SZ'}`
}

function reverseLookupKnownListedCode(displayOrName: string): string | null {
    const key = displayOrName.trim()
    if (!key) return null
    for (const [listed, cname] of Object.entries(KNOWN_STOCK_NAMES)) {
        if (key === cname) return listed
    }
    return null
}

/**
 * 将用户输入、展示名或裸代码尽量解析为 `XXXXXX.SH|SZ|BJ`；无法识别时返回 normalize 后的原串（可能仍为中文）。
 */
export function resolveExchangeListedSymbol(raw: string): string {
    const s = raw.trim()
    if (!s) return ''
    const normalized = normalizeDisplaySymbol(s)
    if (EXCHANGE_LISTED_SYMBOL_RE.test(normalized)) return normalized
    const fromKnown = reverseLookupKnownListedCode(s)
    if (fromKnown) return fromKnown
    return normalized
}

/**
 * 优先从 primary 解析交易所代码；若仍非 listed 形态，再尝试 fallback（如报告里的 `symbol`）。
 */
export function pickExchangeListedSymbol(primary: string, fallback?: string | null): string {
    const a = resolveExchangeListedSymbol(primary)
    if (EXCHANGE_LISTED_SYMBOL_RE.test(a)) return a
    if (fallback) {
        const b = resolveExchangeListedSymbol(fallback)
        if (EXCHANGE_LISTED_SYMBOL_RE.test(b)) return b
    }
    return a
}

/** 仅从本地映射解析名称，未知则返回 null */
export function lookupStockName(symbol: string): string | null {
    const s = resolveExchangeListedSymbol(symbol)
    return KNOWN_STOCK_NAMES[s] ?? null
}

/** 任意携带 symbol / name / display_label 的片段（列表项、报告行、API 响应等） */
export interface StockDisplayInput {
    symbol: string
    name?: string | null
    display_label?: string | null
}

const CN_LISTED_IN_LABEL_RE = /\d{6}\.(SH|SZ|BJ)/i

/**
 * 全站统一展示字符串：
 * - 优先使用服务端 `display_label`（todo 1–3：后端应返回「名称 代码」）。
 * - 当接口仍退回「仅代码」或与 symbol 等价（映射未加载、旧任务快照等）时，用 `name` + 本地映射补全。
 * - 旧报告 `symbol` / `display_label` 仅存中文时，在能解析到沪深京代码的前提下拼回「名称 代码」。
 *
 * 规范化后的 K 线/行情接口返回的 label 含 `XXXXXX.SH|SZZBJ`，不会误判为「纯中文」分支。
 */
export function stockDisplayLabel(stock: StockDisplayInput): string {
    const rawSym = (stock.symbol || '').trim()
    const sym = resolveExchangeListedSymbol(rawSym)
    const listed = EXCHANGE_LISTED_SYMBOL_RE.test(sym)
    const dl = stock.display_label?.trim()
    const name = stock.name?.trim()
    const effectiveName =
        name && name.toUpperCase() !== sym.toUpperCase() && name.toUpperCase() !== rawSym.toUpperCase()
            ? name
            : null

    if (dl && listed) {
        const symUp = sym.toUpperCase()
        const dlUp = dl.toUpperCase()
        if (dlUp === symUp || dlUp === rawSym.toUpperCase()) {
            return formatStockNameCode(effectiveName, sym)
        }
        if (!CN_LISTED_IN_LABEL_RE.test(dl)) {
            const nm = (effectiveName || dl).trim()
            return formatStockNameCode(nm || null, sym)
        }
    }

    if (dl) return dl
    return formatStockNameCode(stock.name, stock.symbol)
}

/** @deprecated 与 {@link stockDisplayLabel} 相同，保留别名以免外部引用断裂 */
export const stockDisplayLabelForReportRow = stockDisplayLabel

/**
 * 标题一行 / 副标题一行等场景：分解名称与代码（label 仍为统一字符串）。
 */
export function stockDisplayParts(stock: StockDisplayInput): { name: string; symbol: string; label: string } {
    const label = stockDisplayLabel(stock)
    const sym = resolveExchangeListedSymbol(stock.symbol || '')
    const rawName = stock.name?.trim()
    const known = lookupStockName(sym)
    const name = rawName || known || ''
    return { name, symbol: sym || stock.symbol.trim(), label }
}

const FILENAME_BAD = /[/\\?%*:|"<>]/g

/** 导出报告、下载文件名用（剔除路径非法字符，空格压成下划线） */
export function stockSafeFilename(stock: StockDisplayInput, fallback = 'report'): string {
    const base = stockDisplayLabel(stock).replace(FILENAME_BAD, '_').replace(/\s+/g, '_').replace(/_+/g, '_').trim()
    const trimmed = base.replace(/^_|_$/g, '').slice(0, 120)
    if (trimmed) return trimmed
    const sym = resolveExchangeListedSymbol(stock.symbol || '').replace(/\./g, '_')
    return sym || fallback
}

/**
 * 展示用：「名称 代码」，例如：贵州茅台 600519.SH
 * - 有权威名称时优先使用（如 instrument_context.security_name）
 * - 否则尝试本地映射
 * - 皆无时仅返回规范化代码
 * - 名称与代码相同时不重复拼接
 */
export function formatStockNameCode(name: string | null | undefined, symbol: string): string {
    const sym = resolveExchangeListedSymbol(symbol)
    const n = name?.trim()
    if (n) {
        if (n.toUpperCase() === sym.toUpperCase()) return sym || symbol.trim()
        return `${n} ${sym}`.trim()
    }
    const known = lookupStockName(sym)
    if (known) return `${known} ${sym}`.trim()
    return sym || symbol.trim()
}

/** 跟踪看板聚合接口字段 → 通用实时报价展示（不发起额外 /quotes 请求） */
export function trackingItemToRealtimeQuote(item: TrackingBoardItem): RealtimeQuote {
    return {
        price: item.live_price ?? undefined,
        open: item.day_open ?? undefined,
        high: item.day_high ?? undefined,
        low: item.day_low ?? undefined,
        previous_close: item.previous_close ?? undefined,
        change: item.price_change ?? undefined,
        change_pct: item.price_change_pct ?? undefined,
        volume: item.volume ?? undefined,
        amount: item.amount ?? undefined,
        quote_time: item.quote_time ?? undefined,
        source: item.quote_source ?? undefined,
    }
}

function pickFiniteNumber(primary: number | null | undefined, fallback: number | null | undefined): number | null | undefined {
    return primary != null && Number.isFinite(primary) ? primary : fallback
}

function roundMoney(value: number): number {
    return Math.round(value * 100) / 100
}

function parseQuoteTime(value: string | null | undefined): number | null {
    if (!value) return null
    const parsed = Date.parse(value.includes('T') ? value : value.replace(' ', 'T'))
    return Number.isFinite(parsed) ? parsed : null
}

function shouldUseQuoteFallback(item: TrackingBoardItem, quote: RealtimeQuote): boolean {
    const itemHasQuote = item.live_price != null || Boolean(item.quote_time) || Boolean(item.quote_source)
    if (!itemHasQuote) return true

    const quoteTime = parseQuoteTime(quote.quote_time)
    const itemTime = parseQuoteTime(item.quote_time)
    if (quoteTime != null && itemTime != null) return quoteTime >= itemTime
    if (quoteTime != null && itemTime == null) return true
    return false
}

/**
 * 跟踪看板接口会在行情源偶发超时/降级时返回持仓静态值；
 * 这里用全局实时报价缓存补齐展示层动态数据。
 */
export function mergeTrackingBoardQuotes(
    items: TrackingBoardItem[],
    quotes: Record<string, RealtimeQuote>,
): TrackingBoardItem[] {
    return items.map((item) => {
        const symbol = resolveExchangeListedSymbol(item.symbol).trim().toUpperCase()
        const quote = quotes[symbol] ?? quotes[item.symbol]
        if (!quote) return item
        if (!shouldUseQuoteFallback(item, quote)) return item

        const livePrice = pickFiniteNumber(quote.price, item.live_price)
        const currentPosition = item.current_position
        const averageCost = item.average_cost
        const liveMarketValue =
            livePrice != null && currentPosition != null && Number.isFinite(livePrice) && Number.isFinite(currentPosition)
                ? roundMoney(livePrice * currentPosition)
                : item.live_market_value
        const floatingPnl =
            livePrice != null &&
            currentPosition != null &&
            averageCost != null &&
            Number.isFinite(livePrice) &&
            Number.isFinite(currentPosition) &&
            Number.isFinite(averageCost)
                ? roundMoney((livePrice - averageCost) * currentPosition)
                : item.floating_pnl
        const floatingPnlPct =
            livePrice != null && averageCost != null && averageCost !== 0 && Number.isFinite(livePrice) && Number.isFinite(averageCost)
                ? roundMoney(((livePrice - averageCost) / averageCost) * 100)
                : item.floating_pnl_pct

        return {
            ...item,
            live_price: livePrice,
            day_open: pickFiniteNumber(quote.open, item.day_open),
            price_change: pickFiniteNumber(quote.change, item.price_change),
            price_change_pct: pickFiniteNumber(quote.change_pct, item.price_change_pct),
            day_high: pickFiniteNumber(quote.high, item.day_high),
            day_low: pickFiniteNumber(quote.low, item.day_low),
            previous_close: pickFiniteNumber(quote.previous_close, item.previous_close),
            volume: pickFiniteNumber(quote.volume, item.volume),
            amount: pickFiniteNumber(quote.amount, item.amount),
            quote_time: quote.quote_time ?? item.quote_time,
            quote_source: quote.source ?? item.quote_source,
            live_market_value: liveMarketValue,
            floating_pnl: floatingPnl,
            floating_pnl_pct: floatingPnlPct,
        }
    })
}
