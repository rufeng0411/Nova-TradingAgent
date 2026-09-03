import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/services/api'
import { useQuoteStore } from '@/stores/quoteStore'

describe('quoteStore', () => {
    beforeEach(() => {
        vi.restoreAllMocks()
        useQuoteStore.setState({
            quotes: {},
            fetchedAt: {},
            loading: false,
            error: null,
        })
    })

    it('dedupes equivalent symbols and reuses in-flight requests', async () => {
        const spy = vi.spyOn(api, 'getRealtimeQuotes').mockResolvedValue({
            quotes: {
                '600519.SH': {
                    price: 1800,
                    change: 5,
                    change_pct: 0.2786,
                    quote_time: '2026-05-06 10:30:00',
                    source: 'test',
                },
            },
            missing: [],
            cache_ttl_seconds: 10,
        })

        const p1 = useQuoteStore.getState().fetchQuotes(['600519.SH'])
        const p2 = useQuoteStore.getState().fetchQuotes(['600519', '600519.SH'])
        await Promise.all([p1, p2])

        expect(spy).toHaveBeenCalledTimes(1)
        expect(spy).toHaveBeenCalledWith(['600519.SH'])
        expect(useQuoteStore.getState().quotes['600519.SH']?.price).toBe(1800)
    })

    it('uses cached quotes inside the ttl window', async () => {
        const spy = vi.spyOn(api, 'getRealtimeQuotes').mockResolvedValue({
            quotes: {
                '000001.SZ': {
                    price: 12.34,
                    change_pct: -0.2,
                    source: 'test',
                },
            },
            missing: [],
            cache_ttl_seconds: 10,
        })

        await useQuoteStore.getState().fetchQuotes(['000001'])
        await useQuoteStore.getState().fetchQuotes(['000001.SZ'])

        expect(spy).toHaveBeenCalledTimes(1)
        expect(useQuoteStore.getState().quotes['000001.SZ']?.change_pct).toBe(-0.2)
    })

    it('does not cache symbols that were missing from the quote response', async () => {
        const spy = vi.spyOn(api, 'getRealtimeQuotes')
            .mockResolvedValueOnce({
                quotes: {},
                missing: ['600057.SH'],
                cache_ttl_seconds: 10,
            })
            .mockResolvedValueOnce({
                quotes: {
                    '600057.SH': {
                        price: 7,
                        source: 'sina',
                    },
                },
                missing: [],
                cache_ttl_seconds: 10,
            })

        await useQuoteStore.getState().fetchQuotes(['600057.SH'])
        await useQuoteStore.getState().fetchQuotes(['600057.SH'])

        expect(spy).toHaveBeenCalledTimes(2)
        expect(useQuoteStore.getState().quotes['600057.SH']?.price).toBe(7)
    })

    it('force refresh bypasses the cached quote ttl', async () => {
        const spy = vi.spyOn(api, 'getRealtimeQuotes')
            .mockResolvedValueOnce({
                quotes: {
                    '600057.SH': { price: 7, source: 'sina' },
                },
                missing: [],
                cache_ttl_seconds: 10,
            })
            .mockResolvedValueOnce({
                quotes: {
                    '600057.SH': { price: 7.08, source: 'sina' },
                },
                missing: [],
                cache_ttl_seconds: 10,
            })

        await useQuoteStore.getState().fetchQuotes(['600057.SH'])
        await useQuoteStore.getState().fetchQuotes(['600057.SH'], { force: true })

        expect(spy).toHaveBeenCalledTimes(2)
        expect(useQuoteStore.getState().quotes['600057.SH']?.price).toBe(7.08)
    })
})
