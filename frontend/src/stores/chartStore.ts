import { create } from 'zustand'
import { createJSONStorage, persist } from 'zustand/middleware'
import type { ChartRangePreset, KlineAdjust, KlinePeriod, SubChartType } from '@/types'
import { normalizeCnAshareSymbol } from '@/lib/cnSymbol'
import { perUserLocalStorageKey } from '@/lib/perUserLocalKey'

export interface MaFlags {
    ma5: boolean
    ma10: boolean
    ma20: boolean
    ma60: boolean
}

/** 对比走势暂时下线，恢复时改为 true */
export const CHART_COMPARE_ENABLED = false

/** 传给 ProChart.compareSymbols 的稳定空数组。勿使用 inline `[]`，否则引用每帧变化会触发 K 线拉取 effect 反复执行（闪烁）。 */
export const EMPTY_COMPARE_SYMBOLS: string[] = []

/** K 线页「最近查询」一条记录（与全站 {@link stockDisplayLabel} 对齐） */
export interface KlineHistoryEntry {
    symbol: string
    name?: string | null
    display_label?: string | null
}

function normalizeHistorySymbol(raw: string): string {
    return normalizeCnAshareSymbol(raw.trim()) || raw.trim().toUpperCase()
}

interface ChartStoreState {
    symbol: string
    /** 展示在代码后的中文简称；未知时为 null */
    symbolName: string | null
    /** 后端权威「名称 代码」展示串；有值时 Toolbar / ProChart 优先使用 */
    symbolDisplayLabel: string | null
    rangePreset: ChartRangePreset
    period: KlinePeriod
    adjust: KlineAdjust
    ma: MaFlags
    showBoll: boolean
    subChart: SubChartType
    compareSymbols: string[]
    liveDailyEnabled: boolean
    insightOpen: boolean
    setSymbol: (s: string, opts?: { name?: string | null; display_label?: string | null }) => void
    setRangePreset: (r: ChartRangePreset) => void
    setPeriod: (p: KlinePeriod) => void
    setAdjust: (a: KlineAdjust) => void
    setMa: (m: Partial<MaFlags>) => void
    setShowBoll: (v: boolean) => void
    setSubChart: (s: SubChartType) => void
    setCompareSymbols: (symbols: string[]) => void
    addCompareSymbol: (symbol: string) => void
    removeCompareSymbol: (symbol: string) => void
    setLiveDailyEnabled: (v: boolean) => void
    setInsightOpen: (v: boolean) => void
    /** K 线页最近查询（时间序，新在前，最多 10 条） */
    klineQueryHistory: KlineHistoryEntry[]
    pushKlineQueryHistory: (
        raw: string,
        opts?: { name?: string | null; display_label?: string | null },
    ) => void
    /** 为「最近查询」已存在条目补写名称/展示串（不调整顺序） */
    patchKlineQueryHistoryMeta: (
        raw: string,
        opts: { name?: string | null; display_label?: string | null },
    ) => void
}

export const defaultMa: MaFlags = {
    ma5: true,
    ma10: true,
    ma20: true,
    ma60: true,
}

const chartPersistStorage = createJSONStorage(() => ({
    getItem: (name: string) => localStorage.getItem(perUserLocalStorageKey(name)),
    setItem: (name: string, value: string) => localStorage.setItem(perUserLocalStorageKey(name), value),
    removeItem: (name: string) => localStorage.removeItem(perUserLocalStorageKey(name)),
}))

export const useChartStore = create<ChartStoreState>()(
    persist(
        (set, get) => ({
    symbol: '000001.SH',
    symbolName: null,
    symbolDisplayLabel: null,
    rangePreset: '6M',
    period: '1d',
    adjust: 'none',
    ma: { ...defaultMa },
    showBoll: true,
    subChart: 'macd',
    compareSymbols: [],
    liveDailyEnabled: false,
    insightOpen: false,
    klineQueryHistory: [],
    pushKlineQueryHistory: (raw, opts) => {
        const norm = normalizeHistorySymbol(raw)
        if (!norm) return
        set((state) => ({
            klineQueryHistory: [
                {
                    symbol: norm,
                    name: opts?.name ?? null,
                    display_label: opts?.display_label ?? null,
                },
                ...state.klineQueryHistory.filter((x) => normalizeHistorySymbol(x.symbol) !== norm),
            ].slice(0, 10),
        }))
    },
    patchKlineQueryHistoryMeta: (raw, opts) => {
        const norm = normalizeHistorySymbol(raw)
        if (!norm) return
        set((state) => ({
            klineQueryHistory: state.klineQueryHistory.map((x) => {
                if (normalizeHistorySymbol(x.symbol) !== norm) return x
                const nextName =
                    opts.name !== undefined
                        ? String(opts.name ?? '').trim() || x.name
                        : x.name
                const nextDl =
                    opts.display_label !== undefined
                        ? String(opts.display_label ?? '').trim() || x.display_label
                        : x.display_label
                return {
                    ...x,
                    name: nextName ?? null,
                    display_label: nextDl ?? null,
                }
            }),
        }))
    },
    setSymbol: (symbol, opts) => {
        const s = symbol.trim().toUpperCase()
        const prev = get().symbol.trim().toUpperCase()
        const prevName = get().symbolName
        const prevDl = get().symbolDisplayLabel

        /** 仅非空简称才视为「显式设置」；null/空/空白走保留逻辑，避免接口空 name 抹掉已有中文名 */
        let explicitName: string | undefined
        if (opts != null && opts.name !== undefined) {
            const t = opts.name == null ? '' : String(opts.name).trim()
            if (t) explicitName = t
        }

        let explicitDl: string | null | undefined
        if (opts != null && opts.display_label !== undefined) {
            const d = opts.display_label == null ? '' : String(opts.display_label).trim()
            explicitDl = d ? d : null
        }

        let symbolName: string | null

        if (explicitName !== undefined) {
            symbolName = explicitName
        } else if (prev === s) {
            symbolName = prevName
        } else {
            const p6 = prev.match(/^(\d{6})/)?.[1]
            const n6 = s.match(/^(\d{6})/)?.[1]
            if (
                p6 &&
                n6 &&
                p6 === n6 &&
                prevName != null &&
                String(prevName).trim() !== ''
            ) {
                // 仅规范化交易所后缀（如 600519 → 600519.SH）时保留已有中文名
                symbolName = prevName
            } else {
                symbolName = null
            }
        }

        let symbolDisplayLabel: string | null = prevDl
        if (explicitDl !== undefined) {
            symbolDisplayLabel = explicitDl
        } else if (s !== prev) {
            symbolDisplayLabel = null
        }

        set((state) => {
            const histKey = normalizeHistorySymbol(s) || s
            const nextHist =
                s !== prev
                    ? [
                          {
                              symbol: histKey,
                              name: symbolName,
                              display_label: symbolDisplayLabel,
                          },
                          ...state.klineQueryHistory.filter((x) => normalizeHistorySymbol(x.symbol) !== histKey),
                      ].slice(0, 10)
                    : state.klineQueryHistory
            return { symbol: s, symbolName, symbolDisplayLabel, klineQueryHistory: nextHist }
        })
    },
    setRangePreset: (rangePreset) => set({ rangePreset }),
    setPeriod: (period) => set({ period }),
    setAdjust: (adjust) => set({ adjust }),
    setMa: (partial) => set({ ma: { ...get().ma, ...partial } }),
    setShowBoll: (showBoll) => set({ showBoll }),
    setSubChart: (subChart) => set({ subChart }),
    setCompareSymbols: (compareSymbols) =>
        set({
            compareSymbols: [
                ...new Set(
                    compareSymbols.map((s) => normalizeCnAshareSymbol(s)).filter(Boolean),
                ),
            ].slice(0, 4),
        }),
    addCompareSymbol: (symbol) => {
        const norm = normalizeCnAshareSymbol(symbol)
        if (!norm) return
        const cur = get().compareSymbols
        if (cur.includes(norm) || cur.length >= 4) return
        set({ compareSymbols: [...cur, norm] })
    },
    removeCompareSymbol: (symbol) =>
        set({ compareSymbols: get().compareSymbols.filter((x) => x !== symbol) }),
    setLiveDailyEnabled: (liveDailyEnabled) => set({ liveDailyEnabled }),
    setInsightOpen: (insightOpen) => set({ insightOpen }),
        }),
        {
            name: 'tradingagents-chart',
            version: 3,
            storage: chartPersistStorage,
            partialize: (state) => ({
                klineQueryHistory: state.klineQueryHistory,
                liveDailyEnabled: state.liveDailyEnabled,
            }),
            migrate: (persistedState, oldVersion) => {
                const p = persistedState as { klineQueryHistory?: unknown; liveDailyEnabled?: unknown }
                if (oldVersion < 2 && Array.isArray(p?.klineQueryHistory)) {
                    p.klineQueryHistory = p.klineQueryHistory.map((item) =>
                        typeof item === 'string' ? { symbol: item } : item,
                    )
                }
                if (oldVersion < 3 && typeof p.liveDailyEnabled !== 'boolean') {
                    p.liveDailyEnabled = false
                }
                return persistedState as typeof persistedState
            },
        },
    ),
)
