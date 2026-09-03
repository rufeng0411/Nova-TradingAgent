import { describe, expect, it } from 'vitest'

import {
    formatStockNameCode,
    lookupStockName,
    mergeTrackingBoardQuotes,
    pickExchangeListedSymbol,
    resolveExchangeListedSymbol,
    stockDisplayLabel,
    stockDisplayLabelForReportRow,
    stockSafeFilename,
} from '@/utils/stockDisplay'

describe('stock display labels', () => {
    it('normalizes bare A-share codes before local name lookup', () => {
        expect(lookupStockName('600519')).toBe('贵州茅台')
        expect(formatStockNameCode(null, '600519')).toBe('贵州茅台 600519.SH')
    })

    it('keeps the unified name-code format when an API name is present', () => {
        expect(formatStockNameCode('招商银行', '600036')).toBe('招商银行 600036.SH')
    })

    it('resolves Chinese short name from local map to listed symbol', () => {
        expect(resolveExchangeListedSymbol('贵州茅台')).toBe('600519.SH')
        expect(formatStockNameCode('贵州茅台', '贵州茅台')).toBe('贵州茅台 600519.SH')
    })

    it('pick prefers primary when listed, else report.symbol', () => {
        expect(pickExchangeListedSymbol('贵州茅台', '000001.SH')).toBe('600519.SH')
        expect(pickExchangeListedSymbol('未知', '600519.SH')).toBe('600519.SH')
    })

    it('stockDisplayLabel prefers API display_label', () => {
        expect(
            stockDisplayLabel({
                symbol: '600519.SH',
                name: '贵州茅台',
                display_label: '贵州茅台 600519.SH',
            }),
        ).toBe('贵州茅台 600519.SH')
    })

    it('stockDisplayLabel keeps canonical K 线样式「名称 代码」不被改写', () => {
        expect(
            stockDisplayLabel({
                symbol: '300750.SZ',
                name: '宁德时代',
                display_label: '宁德时代 300750.SZ',
            }),
        ).toBe('宁德时代 300750.SZ')
    })

    it('stockDisplayLabel enriches code-only display_label using local known names', () => {
        expect(
            stockDisplayLabel({
                symbol: '300750.SZ',
                name: '',
                display_label: '300750.SZ',
            }),
        ).toBe('宁德时代 300750.SZ')
    })

    it('stockDisplayLabel ignores API name when name is also only the symbol', () => {
        expect(
            stockDisplayLabel({
                symbol: '300750.SZ',
                name: '300750.SZ',
                display_label: '300750.SZ',
            }),
        ).toBe('宁德时代 300750.SZ')
    })

    it('stockDisplayLabel covers recent report codes even when backend map is unavailable', () => {
        expect(
            stockDisplayLabel({
                symbol: '600330.SH',
                name: '600330.SH',
                display_label: '600330.SH',
            }),
        ).toBe('天通股份 600330.SH')
    })

    it('stockDisplayLabel merges Chinese-only display_label with listed symbol（旧报告等）', () => {
        expect(
            stockDisplayLabel({
                symbol: '300750.SZ',
                name: '',
                display_label: '宁德时代',
            }),
        ).toBe('宁德时代 300750.SZ')
    })

    it('stockDisplayLabelForReportRow 别名与 stockDisplayLabel 一致', () => {
        const stock = { symbol: '600519.SH', name: '', display_label: '600519.SH' as string | null }
        expect(stockDisplayLabelForReportRow(stock)).toBe(stockDisplayLabel(stock))
    })

    it('stockSafeFilename strips unsafe characters', () => {
        expect(
            stockSafeFilename({
                symbol: '600519.SH',
                name: '测试/星',
                display_label: '测试/星 600519.SH',
            }),
        ).toMatch(/^测试_星_600519/)
    })

    it('does not duplicate when name equals listed symbol', () => {
        expect(formatStockNameCode('600519.SH', '600519.SH')).toBe('600519.SH')
    })

    it('merges refreshed quotes into tracking board items with stale aggregate data', () => {
        const [item] = mergeTrackingBoardQuotes(
            [{
                symbol: '600057.SH',
                name: '厦门象屿',
                current_position: 200,
                average_cost: 8.15,
                market_value: 1408,
                live_market_value: 1408,
                live_price: null,
                quote_source: null,
            }],
            {
                '600057.SH': {
                    price: 7,
                    open: 7.16,
                    high: 7.17,
                    low: 6.99,
                    previous_close: 7.23,
                    change: -0.23,
                    change_pct: -3.1812,
                    volume: 30716269,
                    amount: 216034145,
                    quote_time: '2026-05-06 11:30:00',
                    source: 'sina',
                },
            },
        )

        expect(item.live_price).toBe(7)
        expect(item.live_market_value).toBe(1400)
        expect(item.floating_pnl).toBe(-230)
        expect(item.floating_pnl_pct).toBe(-14.11)
        expect(item.quote_source).toBe('sina')
        expect(item.quote_time).toBe('2026-05-06 11:30:00')
    })

    it('keeps newer tracking board quotes over older global quote cache', () => {
        const [item] = mergeTrackingBoardQuotes(
            [{
                symbol: '600057.SH',
                name: '厦门象屿',
                current_position: 200,
                average_cost: 8.15,
                live_market_value: 1420,
                floating_pnl: -210,
                floating_pnl_pct: -12.88,
                live_price: 7.1,
                quote_time: '2026-05-06 11:31:00',
                quote_source: 'tracking-board',
            }],
            {
                '600057.SH': {
                    price: 7,
                    quote_time: '2026-05-06 11:30:00',
                    source: 'sina',
                },
            },
        )

        expect(item.live_price).toBe(7.1)
        expect(item.live_market_value).toBe(1420)
        expect(item.floating_pnl).toBe(-210)
        expect(item.floating_pnl_pct).toBe(-12.88)
        expect(item.quote_source).toBe('tracking-board')
        expect(item.quote_time).toBe('2026-05-06 11:31:00')
    })
})
