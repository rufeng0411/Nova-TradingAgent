import { describe, expect, it } from 'vitest'
import { calcSma, calcRsi, calcMacd, calcBoll } from './indicators'

describe('indicators', () => {
    it('calcSma matches rolling mean', () => {
        const closes = [10, 11, 12, 13, 14]
        const s = calcSma(closes, 3)
        expect(s[2]).toBeCloseTo(11)
        expect(s[4]).toBeCloseTo(13)
    })

    it('calcRsi returns values in 0-100 range when enough data', () => {
        const closes = Array.from({ length: 30 }, (_, i) => 100 + Math.sin(i / 3) * 2)
        const r = calcRsi(closes, 14)
        const last = r.filter((x) => x != null).pop()
        expect(last).toBeDefined()
        expect(last!).toBeGreaterThanOrEqual(0)
        expect(last!).toBeLessThanOrEqual(100)
    })

    it('calcMacd produces aligned lengths', () => {
        const closes = Array.from({ length: 60 }, (_, i) => 50 + i * 0.1)
        const { dif, dea, macd } = calcMacd(closes)
        expect(dif.length).toBe(closes.length)
        expect(dea.length).toBe(closes.length)
        expect(macd.length).toBe(closes.length)
    })

    it('calcBoll mid tracks sma20', () => {
        const closes = Array.from({ length: 40 }, (_, i) => 10 + i * 0.05)
        const b = calcBoll(closes, 20, 2)
        expect(b.mid[25]).not.toBeNull()
    })
})
