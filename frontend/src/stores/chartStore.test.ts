import { beforeEach, describe, expect, it } from 'vitest'

import { useChartStore } from '@/stores/chartStore'

describe('chartStore setSymbol', () => {
    beforeEach(() => {
        useChartStore.setState({
            symbol: '000001.SH',
            symbolName: null,
            symbolDisplayLabel: null,
        })
    })

    it('keeps symbolName when only exchange suffix is normalized (same 6-digit)', () => {
        useChartStore.getState().setSymbol('600519', { name: '贵州茅台' })
        useChartStore.getState().setSymbol('600519.SH')
        expect(useChartStore.getState().symbol).toBe('600519.SH')
        expect(useChartStore.getState().symbolName).toBe('贵州茅台')
    })

    it('clears symbolName when switching to a different six-digit code without name', () => {
        useChartStore.getState().setSymbol('600519.SH', { name: '贵州茅台' })
        useChartStore.getState().setSymbol('600036.SH')
        expect(useChartStore.getState().symbolName).toBeNull()
    })

    it('does not treat empty explicit name as overwrite (merge path preserves same-code name)', () => {
        useChartStore.getState().setSymbol('600519.SH', { name: '贵州茅台' })
        useChartStore.getState().setSymbol('600519.SH', { name: '' })
        useChartStore.getState().setSymbol('600519.SH', { name: null as unknown as string })
        expect(useChartStore.getState().symbolName).toBe('贵州茅台')
    })

    it('applies non-empty explicit name', () => {
        useChartStore.getState().setSymbol('600879.SH', { name: '航天电子' })
        expect(useChartStore.getState().symbolName).toBe('航天电子')
    })

    it('stores display_label and clears it when switching symbol without label', () => {
        useChartStore.getState().setSymbol('600519.SH', {
            name: '贵州茅台',
            display_label: '贵州茅台 600519.SH',
        })
        expect(useChartStore.getState().symbolDisplayLabel).toBe('贵州茅台 600519.SH')
        useChartStore.getState().setSymbol('600036.SH')
        expect(useChartStore.getState().symbolDisplayLabel).toBeNull()
    })
})
