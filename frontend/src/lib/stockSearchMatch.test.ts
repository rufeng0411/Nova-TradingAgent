import { describe, expect, it } from 'vitest'

import { pickBestStockSearchResult } from '@/lib/stockSearchMatch'

describe('pickBestStockSearchResult', () => {
    it('prefers exact symbol match with a non-empty name', () => {
        const rows = [
            { symbol: '600879.SZ', name: '错配' },
            { symbol: '600879.SH', name: '航天电子' },
        ]
        const r = pickBestStockSearchResult('600879.SH', rows)
        expect(r?.symbol.toUpperCase()).toBe('600879.SH')
        expect(r?.name).toBe('航天电子')
    })

    it('falls back to six-digit head match with name when exact has empty name', () => {
        const rows = [
            { symbol: '600879.SH', name: '' },
            { symbol: '600879.SH', name: '   ' },
            { symbol: '600879.SH', name: '航天电子' },
        ]
        const r = pickBestStockSearchResult('600879.SH', rows)
        expect(r?.name.trim()).toBe('航天电子')
    })

    it('matches six digits against results without suffix', () => {
        const rows = [{ symbol: '600519', name: '贵州茅台' }]
        const r = pickBestStockSearchResult('600519.SH', rows)
        expect(r?.name).toBe('贵州茅台')
    })

    it('returns first row with display name before unnamed first row', () => {
        const rows = [
            { symbol: '600000.SH', name: '' },
            { symbol: '600001.SH', name: '有名称' },
        ]
        const r = pickBestStockSearchResult('600999.SH', rows)
        expect(r?.name).toBe('有名称')
    })

    it('returns undefined for empty results', () => {
        expect(pickBestStockSearchResult('000001.SH', [])).toBeUndefined()
    })
})
