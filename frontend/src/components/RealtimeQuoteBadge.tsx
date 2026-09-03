import { useEffect, useMemo } from 'react'

import { useQuoteStore } from '@/stores/quoteStore'
import type { RealtimeQuote } from '@/types'
import { resolveExchangeListedSymbol } from '@/utils/stockDisplay'

type QuoteTone = 'up' | 'down' | 'neutral'

export function getQuoteTone(quote?: Pick<RealtimeQuote, 'change' | 'change_pct'> | null): QuoteTone {
    const raw = quote?.change_pct ?? quote?.change
    if (raw == null || !Number.isFinite(Number(raw))) return 'neutral'
    const value = Number(raw)
    if (value > 0) return 'up'
    if (value < 0) return 'down'
    return 'neutral'
}

function formatSigned(value?: number | null, suffix = ''): string {
    if (value == null || !Number.isFinite(value)) return '--'
    const sign = value > 0 ? '+' : ''
    return `${sign}${value.toFixed(2)}${suffix}`
}

export function formatQuoteChange(quote?: Pick<RealtimeQuote, 'change' | 'change_pct'> | null): string {
    return `${formatSigned(quote?.change)} / ${formatSigned(quote?.change_pct, '%')}`
}

function formatPrice(value?: number | null): string {
    if (value == null || !Number.isFinite(value)) return '--'
    return value.toFixed(value >= 100 ? 2 : 3).replace(/0+$/, '').replace(/\.$/, '')
}

export function RealtimeQuoteBadge({
    symbol,
    quote,
    autoFetch = true,
    compact = false,
}: {
    symbol: string
    quote?: RealtimeQuote | null
    autoFetch?: boolean
    compact?: boolean
}) {
    const normalizedSymbol = useMemo(() => resolveExchangeListedSymbol(symbol || '').trim().toUpperCase(), [symbol])
    const storeQuote = useQuoteStore((state) => (normalizedSymbol ? state.quotes[normalizedSymbol] : undefined))
    const loading = useQuoteStore((state) => state.loading)
    const fetchQuotes = useQuoteStore((state) => state.fetchQuotes)
    const effectiveQuote = quote ?? storeQuote ?? null
    const tone = getQuoteTone(effectiveQuote)

    useEffect(() => {
        if (!autoFetch || !normalizedSymbol) return
        void fetchQuotes([normalizedSymbol])
    }, [autoFetch, fetchQuotes, normalizedSymbol])

    const toneClass =
        tone === 'up'
            ? 'text-red-600 bg-red-50 border-red-100 dark:text-red-300 dark:bg-red-500/10 dark:border-red-500/20'
            : tone === 'down'
                ? 'text-emerald-600 bg-emerald-50 border-emerald-100 dark:text-emerald-300 dark:bg-emerald-500/10 dark:border-emerald-500/20'
                : 'text-slate-500 bg-slate-50 border-slate-200 dark:text-slate-300 dark:bg-slate-800/60 dark:border-slate-700'

    return (
        <span
            className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium ${toneClass}`}
            title={effectiveQuote?.quote_time ? `行情时间：${effectiveQuote.quote_time}` : '实时行情'}
        >
            <span>{loading && !effectiveQuote ? '行情加载中' : `现价 ${formatPrice(effectiveQuote?.price)}`}</span>
            {!compact && <span>{formatQuoteChange(effectiveQuote)}</span>}
        </span>
    )
}
