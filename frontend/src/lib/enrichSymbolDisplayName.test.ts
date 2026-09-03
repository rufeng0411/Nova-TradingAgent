import { beforeEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/services/api'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'

vi.mock('@/services/api', () => ({
    api: {
        searchStocks: vi.fn(),
    },
}))

const searchStocksMock = vi.mocked(api.searchStocks)

describe('fetchAshareDisplayName', () => {
    beforeEach(() => {
        searchStocksMock.mockReset()
    })

    it('falls back to a bare six-digit search when suffixed search has no name', async () => {
        searchStocksMock
            .mockResolvedValueOnce({ results: [] })
            .mockResolvedValueOnce({ results: [{ symbol: '600519.SH', name: '贵州茅台' }] })

        await expect(fetchAshareDisplayName('600519.SH')).resolves.toBe('贵州茅台')
        expect(searchStocksMock).toHaveBeenNthCalledWith(1, '600519.SH', undefined)
        expect(searchStocksMock).toHaveBeenNthCalledWith(2, '600519', undefined)
    })

    it('normalizes bare codes before resolving display names', async () => {
        searchStocksMock.mockResolvedValueOnce({
            results: [{ symbol: '600036.SH', name: '招商银行' }],
        })

        await expect(fetchAshareDisplayName('600036')).resolves.toBe('招商银行')
        expect(searchStocksMock).toHaveBeenCalledWith('600036.SH', undefined)
    })
})
import { afterEach, describe, expect, it, vi } from 'vitest'

vi.mock('@/services/api', () => ({
    api: {
        searchStocks: vi.fn(),
    },
}))

import { api } from '@/services/api'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'

const searchStocks = vi.mocked(api.searchStocks)

describe('fetchAshareDisplayName', () => {
    afterEach(() => {
        searchStocks.mockReset()
    })

    it('returns null for non A-share symbol shape', async () => {
        expect(await fetchAshareDisplayName('AAPL')).toBeNull()
    })

    it('returns name from first successful search', async () => {
        searchStocks.mockResolvedValueOnce({
            results: [{ symbol: '600879.SH', name: '航天电子' }],
        })
        const n = await fetchAshareDisplayName('600879')
        expect(n).toBe('航天电子')
        expect(searchStocks).toHaveBeenCalled()
    })

    it('retries with six-digit query when full-code search returns no name', async () => {
        searchStocks
            .mockResolvedValueOnce({
                results: [{ symbol: '600879.SH', name: '' }],
            })
            .mockResolvedValueOnce({
                results: [{ symbol: '600879.SH', name: '航天电子' }],
            })
        const n = await fetchAshareDisplayName('600879.SH')
        expect(n).toBe('航天电子')
        expect(searchStocks).toHaveBeenCalledTimes(2)
        expect(searchStocks.mock.calls[1][0]).toBe('600879')
    })
})
