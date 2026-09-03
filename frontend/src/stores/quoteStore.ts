import { create } from 'zustand'

import { api } from '@/services/api'
import type { RealtimeQuote } from '@/types'
import { resolveExchangeListedSymbol } from '@/utils/stockDisplay'

const DEFAULT_TTL_MS = 10_000

type QuoteState = {
    quotes: Record<string, RealtimeQuote>
    fetchedAt: Record<string, number>
    /** 任意行情请求进行中（兼容旧订阅；角标请优先用 loadingBySymbol） */
    loading: boolean
    /** 正在拉取实时行情的标的（并发请求按 symbol 引用计数） */
    loadingBySymbol: Record<string, boolean>
    error: string | null
    fetchQuotes: (symbols: string[], options?: { force?: boolean }) => Promise<void>
    upsertQuotes: (quotes: Record<string, RealtimeQuote>, fetchedAt?: number) => void
}

const inFlight = new Map<string, Promise<void>>()
/** 并发 fetch 时每个 symbol 的 in-flight 计数 */
const symbolInflightCounts = new Map<string, number>()
let cacheTtlMs = DEFAULT_TTL_MS

function bumpSymbolInflight(symbols: string[], delta: 1 | -1): Record<string, boolean> {
    for (const sym of symbols) {
        const n = Math.max(0, (symbolInflightCounts.get(sym) ?? 0) + delta)
        if (n === 0) symbolInflightCounts.delete(sym)
        else symbolInflightCounts.set(sym, n)
    }
    const nextLoading: Record<string, boolean> = {}
    for (const [sym, c] of symbolInflightCounts) {
        if (c > 0) nextLoading[sym] = true
    }
    return nextLoading
}
function normalizeQuoteSymbols(symbols: string[]): string[] {
    const out: string[] = []
    const seen = new Set<string>()
    for (const raw of symbols) {
        const sym = resolveExchangeListedSymbol(raw || '').trim().toUpperCase()
        if (!sym || seen.has(sym)) continue
        seen.add(sym)
        out.push(sym)
    }
    return out
}

function requestKey(symbols: string[]): string {
    return [...symbols].sort().join('|')
}

export const useQuoteStore = create<QuoteState>((set, get) => ({
    quotes: {},
    fetchedAt: {},
    loading: false,
    loadingBySymbol: {},
    error: null,

    upsertQuotes(quotes, at) {
        const ts = at ?? Date.now()
        const symbols = Object.keys(quotes)
        if (!symbols.length) return
        set((state) => ({
            quotes: { ...state.quotes, ...quotes },
            fetchedAt: {
                ...state.fetchedAt,
                ...Object.fromEntries(symbols.map((sym) => [sym, ts])),
            },
        }))
    },

    async fetchQuotes(rawSymbols, options) {
        if (
            typeof document !== 'undefined' &&
            document.visibilityState === 'hidden' &&
            !options?.force
        ) {
            return
        }
        const symbols = normalizeQuoteSymbols(rawSymbols)
        if (!symbols.length) return

        const now = Date.now()
        const stale = options?.force
            ? symbols
            : symbols.filter((sym) => !get().quotes[sym] || now - (get().fetchedAt[sym] ?? 0) >= cacheTtlMs)
        if (!stale.length) return

        const key = requestKey(stale)
        const existing = inFlight.get(key)
        if (existing) return existing

        const promise = (async () => {
            const loadingBySymbol = bumpSymbolInflight(stale, 1)
            set(() => ({
                loading: true,
                loadingBySymbol,
                error: null,
            }))
            try {
                const resp = await api.getRealtimeQuotes(stale)
                const fetched = Date.now()
                cacheTtlMs = Math.max(1_000, (resp.cache_ttl_seconds || DEFAULT_TTL_MS / 1000) * 1000)
                const loadingBySymbolDone = bumpSymbolInflight(stale, -1)
                set((state) => ({
                    quotes: { ...state.quotes, ...resp.quotes },
                    fetchedAt: {
                        ...state.fetchedAt,
                        ...Object.fromEntries(stale.map((sym) => [sym, fetched])),
                    },
                    loading: Object.keys(loadingBySymbolDone).length > 0,
                    loadingBySymbol: loadingBySymbolDone,
                    error: null,
                }))
            } catch (error) {
                const loadingBySymbolDone = bumpSymbolInflight(stale, -1)
                set({
                    loading: Object.keys(loadingBySymbolDone).length > 0,
                    loadingBySymbol: loadingBySymbolDone,
                    error: error instanceof Error ? error.message : '实时行情加载失败',
                })
            } finally {
                inFlight.delete(key)
            }
        })()

        inFlight.set(key, promise)
        return promise
    },
}))
