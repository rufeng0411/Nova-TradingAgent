import { describe, expect, it } from 'vitest'

import { cnShanghaiDateText, isCnAshareRegularSession } from '@/lib/cnMarketHours'

describe('cnMarketHours', () => {
    it('formats trading day using Shanghai timezone', () => {
        expect(cnShanghaiDateText(new Date('2026-05-05T16:30:00.000Z'))).toBe('2026-05-06')
    })

    it('detects regular A-share session in Shanghai timezone', () => {
        expect(isCnAshareRegularSession(new Date('2026-05-06T02:00:00.000Z'))).toBe(true)
        expect(isCnAshareRegularSession(new Date('2026-05-06T04:00:00.000Z'))).toBe(false)
    })
})
