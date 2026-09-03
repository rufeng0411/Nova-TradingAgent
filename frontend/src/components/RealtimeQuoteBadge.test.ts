import { describe, expect, it } from 'vitest'

import { formatQuoteChange, getQuoteTone } from '@/components/RealtimeQuoteBadge'

describe('RealtimeQuoteBadge helpers', () => {
    it('formats positive and negative quote changes with signs', () => {
        expect(formatQuoteChange({ change: 1.23, change_pct: 2.5 })).toBe('+1.23 / +2.50%')
        expect(formatQuoteChange({ change: -0.4, change_pct: -1.1 })).toBe('-0.40 / -1.10%')
    })

    it('uses neutral tone when change is missing', () => {
        expect(getQuoteTone({})).toBe('neutral')
        expect(getQuoteTone({ change_pct: 0.1 })).toBe('up')
        expect(getQuoteTone({ change: -0.1 })).toBe('down')
    })
})
