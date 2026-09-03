import { useEffect, useMemo, useState } from 'react'
import { Download, Zap } from 'lucide-react'

import DecisionCard from '@/components/DecisionCard'
import type { FastAnalysisDetail } from '@/types'
import { exportFastAnalysisMarkdown } from '@/utils/fastAnalysisExport'
import { sanitizeReportMarkdown, type InstrumentDisplayContext } from '@/utils/reportText'
import { lookupStockName, stockDisplayLabel, stockDisplayParts } from '@/utils/stockDisplay'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'

/** 与智能分析页「沙盘」用语对齐：看多 / 中性 / 看空 */
const CONSENSUS_ZH: Record<string, string> = {
    bullish: '看多',
    bearish: '看空',
    neutral: '中性',
}

const DIRECTION_LABEL: Record<string, string> = {
    bullish: '偏多',
    bearish: '偏空',
    neutral: '中性',
}

const HORIZON_LABEL: Record<string, string> = {
    next_2h: '未来约 2 小时',
    same_day: '当日剩余时段',
    next_session: '下一交易日',
}

const PHASE_LABEL: Record<string, string> = {
    morning_10_to_11_30: '上午 10:00–11:30',
    afternoon_13_to_14_30: '午后 13:00–14:30',
    closing_14_30_to_15_00: '尾盘 14:30–15:00',
}

const ACTION_LABEL: Record<string, string> = {
    buy_add: '加仓 / 介入',
    sell_reduce: '减仓',
    hold: '持有观望',
    wait_observe: '观望等待',
    close_all: '清仓',
}

const SCENARIO_LABEL: Record<string, string> = {
    new_entry: '新建仓',
    add: '加仓',
    add_to_existing: '加仓',
    reduce: '减仓',
    reduce_existing: '减仓',
    clear: '清仓',
    exit_existing: '清仓',
    hold: '持有',
    hold_existing: '持有',
    wait_observe: '等待企稳信号',
}

function isWaitObservePosition(position: Record<string, unknown>): boolean {
    const sc = String(position.scenario || '').toLowerCase()
    if (sc === 'wait_observe') return true
    // schema 兜底：LLM 没用 wait_observe 但价位全部为 0 + 目标仓位 0 时按等待处理
    const entry = Array.isArray(position.entry_zone) ? (position.entry_zone as unknown[]) : []
    const exit = Array.isArray(position.exit_zone) ? (position.exit_zone as unknown[]) : []
    const allZero = (arr: unknown[]) => arr.length > 0 && arr.every((x) => Number(x) === 0)
    const tpr = Array.isArray(position.take_profit_tiers) ? (position.take_profit_tiers as unknown[]) : []
    const tpZeroOrEmpty = tpr.length === 0
        || tpr.every((t) => {
            const r = t as Record<string, unknown>
            return Number(r?.price ?? 0) === 0 && Number(r?.size_pct ?? 0) === 0
        })
    const targetZero = Number(position.target_position_pct ?? 0) === 0
    const stopZero = Number(position.stop_loss ?? 0) === 0
    return targetZero && stopZero && allZero(entry) && allZero(exit) && tpZeroOrEmpty
}

function str(v: unknown): string {
    if (v === null || v === undefined) return ''
    if (typeof v === 'string') return v
    if (typeof v === 'number' || typeof v === 'boolean') return String(v)
    return ''
}

function num(v: unknown): string {
    if (typeof v === 'number' && !Number.isNaN(v)) return String(v)
    return '—'
}

function mapFastDirectionToDecision(dir: string): 'buy' | 'sell' | 'hold' | undefined {
    const d = dir.toLowerCase()
    if (d === 'bullish') return 'buy'
    if (d === 'bearish') return 'sell'
    if (d === 'neutral') return 'hold'
    return undefined
}

function fastConfidencePercent(v: unknown): number | undefined {
    if (typeof v !== 'number' || Number.isNaN(v)) return undefined
    return Math.min(100, Math.max(0, Math.round((v / 5) * 100)))
}

function firstPrice(arr: unknown): number | undefined {
    if (!Array.isArray(arr) || arr.length === 0) return undefined
    const n = Number(arr[0])
    return Number.isFinite(n) ? n : undefined
}

function stopLossNum(v: unknown): number | undefined {
    if (typeof v === 'number' && Number.isFinite(v)) return v
    if (typeof v === 'string' && v.trim()) {
        const n = Number(v)
        return Number.isFinite(n) ? n : undefined
    }
    return undefined
}

function FastConsensusSpectrum({ direction }: { direction: string }) {
    const d = direction.toLowerCase()
    const active = d === 'bullish' ? 2 : d === 'bearish' ? 0 : 1
    const labels: Array<{ text: string; activeCls: string; idleCls: string }> = [
        {
            text: '看空',
            activeCls:
                'border-green-400 bg-green-100 text-green-900 shadow-md ring-2 ring-green-400/40 dark:bg-green-900/35 dark:text-green-100 dark:border-green-500/60',
            idleCls: 'border-slate-200 bg-slate-50/80 text-slate-400 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-500',
        },
        {
            text: '中性',
            activeCls:
                'border-blue-400 bg-blue-100 text-blue-900 shadow-md ring-2 ring-blue-400/40 dark:bg-blue-900/35 dark:text-blue-100 dark:border-blue-500/60',
            idleCls: 'border-slate-200 bg-slate-50/80 text-slate-400 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-500',
        },
        {
            text: '看多',
            activeCls:
                'border-red-400 bg-red-100 text-red-900 shadow-md ring-2 ring-red-400/40 dark:bg-red-900/35 dark:text-red-100 dark:border-red-500/60',
            idleCls: 'border-slate-200 bg-slate-50/80 text-slate-400 dark:border-slate-700 dark:bg-slate-900/40 dark:text-slate-500',
        },
    ]
    return (
        <div className="rounded-xl border border-slate-200 bg-white/90 p-4 dark:border-slate-700 dark:bg-slate-900/50">
            <p className="mb-3 text-center text-xs font-medium tracking-wide text-slate-500 dark:text-slate-400">综合结论 · 沙盘倾向</p>
            <div className="grid grid-cols-3 gap-2">
                {labels.map((lb, i) => (
                    <div
                        key={lb.text}
                        className={`rounded-xl border px-2 py-3 text-center text-sm font-bold transition-all ${
                            active === i ? lb.activeCls : lb.idleCls
                        }`}
                    >
                        {lb.text}
                    </div>
                ))}
            </div>
            <div className="relative mx-auto mt-2 h-1.5 max-w-[200px] rounded-full bg-slate-200 dark:bg-slate-700">
                <div
                    className="absolute top-0 h-full w-1/3 rounded-full bg-gradient-to-r from-blue-500 to-cyan-400 transition-all duration-500"
                    style={{ left: `${active * 33.333}%` }}
                />
            </div>
        </div>
    )
}

function BulletList({ items }: { items: unknown[] }) {
    if (!items.length) return <p className="text-xs text-slate-400">无</p>
    return (
        <ul className="list-inside list-disc space-y-1 text-sm text-slate-700 dark:text-slate-200">
            {items.map((x, i) => (
                <li key={i}>{str(x)}</li>
            ))}
        </ul>
    )
}

type Candle = { date?: string; open?: number; high?: number; low?: number; close?: number }

function CandlestickSparkline({ bars }: { bars: Candle[] }) {
    if (!bars.length) return null
    const W = 480
    const H = 140
    const padX = 8
    const padY = 10
    const highs = bars.map((b) => Number(b.high)).filter((x) => Number.isFinite(x))
    const lows = bars.map((b) => Number(b.low)).filter((x) => Number.isFinite(x))
    if (!highs.length || !lows.length) return null
    const hi = Math.max(...highs)
    const lo = Math.min(...lows)
    if (!(hi > lo)) return null
    const n = bars.length
    const slot = (W - padX * 2) / n
    const cw = Math.max(2, slot * 0.7)
    const y = (v: number) => padY + (1 - (v - lo) / (hi - lo)) * (H - padY * 2)
    const fmt = (v: number | undefined) => (typeof v === 'number' && Number.isFinite(v) ? v.toFixed(2) : '—')

    return (
        <div className="rounded-lg border border-slate-200 bg-white p-2 dark:border-slate-700 dark:bg-slate-900/40">
            <div className="mb-1 flex items-center justify-between text-[11px] text-slate-500">
                <span>近 {n} 根日 K</span>
                <span>
                    区间 {fmt(lo)} ~ {fmt(hi)}
                </span>
            </div>
            <svg viewBox={`0 0 ${W} ${H}`} className="h-32 w-full" role="img" aria-label="近期 K 线缩略图">
                {bars.map((b, i) => {
                    const o = Number(b.open)
                    const c = Number(b.close)
                    const h = Number(b.high)
                    const l = Number(b.low)
                    if (![o, c, h, l].every(Number.isFinite)) return null
                    const x = padX + slot * i + slot / 2
                    const up = c >= o
                    const color = up ? '#dc2626' : '#16a34a' // A 股配色：红涨绿跌
                    const yHigh = y(h)
                    const yLow = y(l)
                    const yOpen = y(o)
                    const yClose = y(c)
                    const top = Math.min(yOpen, yClose)
                    const bot = Math.max(yOpen, yClose)
                    const bodyH = Math.max(1, bot - top)
                    return (
                        <g key={i}>
                            <line x1={x} x2={x} y1={yHigh} y2={yLow} stroke={color} strokeWidth={1} />
                            <rect
                                x={x - cw / 2}
                                y={top}
                                width={cw}
                                height={bodyH}
                                fill={up ? color : color}
                                opacity={up ? 0.95 : 0.95}
                            />
                        </g>
                    )
                })}
            </svg>
            <div className="mt-1 flex justify-between text-[10px] text-slate-400">
                <span>{bars[0]?.date}</span>
                <span>{bars[bars.length - 1]?.date}</span>
            </div>
        </div>
    )
}

function KlineInsightCard({
    data,
    features,
    symbolLabel,
}: {
    data: Record<string, unknown>
    features: Record<string, unknown>
    symbolLabel: string
}) {
    const summary = str(data.summary)
    const bias = str(data.bias)
    const conf = data.confidence
    const sections = Array.isArray(data.sections) ? (data.sections as Record<string, unknown>[]) : []

    const recentBars = Array.isArray(features.recent_bars) ? (features.recent_bars as Candle[]) : []
    const bars = typeof features.bars === 'number' ? (features.bars as number) : 0
    const hasFeatureError = str(features.error) === 'insufficient_data' || bars === 0
    const hasInsightContent = !!summary || sections.length > 0

    // 兜底：当 LLM 返回的 kline_insight 为空或仅包含原始 features 时，从 features 自行拼一段说明
    const featureFallback = useMemo(() => {
        if (hasInsightContent) return null
        if (hasFeatureError) {
            return `${symbolLabel} K 线特征不足（bars=${bars}），可能是当日为非交易日或日 K 60 日窗口尚未拉到足够数据。`
        }
        const ret = typeof features.total_return_pct === 'number' ? `${features.total_return_pct}%` : '—'
        const align = str(features.ma_alignment) || 'neutral'
        const ph = features.period_high_20
        const pl = features.period_low_20
        const alignText = align === 'bullish_stack' ? '多头排列' : align === 'bearish_stack' ? '空头排列' : '均线纠结'
        const macd = features.macd_cross_up ? 'MACD 金叉' : features.macd_cross_down ? 'MACD 死叉' : 'MACD 无明显交叉'
        return `${symbolLabel} 近 ${bars} 根日 K：累计涨跌 ${ret}，${alignText}，${macd}；近 20 日高点 ${ph ?? '—'} / 低点 ${pl ?? '—'}。本地规则摘要，非投资建议。`
    }, [hasInsightContent, hasFeatureError, bars, features, symbolLabel])

    return (
        <div className="space-y-3 text-sm">
            <CandlestickSparkline bars={recentBars} />

            {summary ? (
                <p className="leading-relaxed text-slate-700 dark:text-slate-200">{summary}</p>
            ) : featureFallback ? (
                <p className="leading-relaxed text-slate-600 dark:text-slate-300">{featureFallback}</p>
            ) : null}

            {(bias || conf !== undefined) && (
                <div className="flex flex-wrap gap-2 text-xs">
                    {bias ? (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                            倾向：{DIRECTION_LABEL[bias] || bias}
                        </span>
                    ) : null}
                    {typeof conf === 'number' ? (
                        <span className="rounded-full bg-slate-100 px-2 py-0.5 text-slate-700 dark:bg-slate-800 dark:text-slate-200">
                            置信度：{conf.toFixed(2)}
                        </span>
                    ) : null}
                </div>
            )}

            {sections.length > 0 ? (
                <div className="grid gap-2 md:grid-cols-2">
                    {sections.map((sec, i) => (
                        <div key={i} className="rounded-lg border border-slate-200 p-2 dark:border-slate-700">
                            <h5 className="text-xs font-semibold text-slate-800 dark:text-slate-100">{str(sec.title)}</h5>
                            {Array.isArray(sec.points) ? (
                                <BulletList items={sec.points as unknown[]} />
                            ) : null}
                            {str(sec.novice_hint) ? (
                                <p className="mt-1 text-[11px] text-slate-500 dark:text-slate-400">{str(sec.novice_hint)}</p>
                            ) : null}
                        </div>
                    ))}
                </div>
            ) : null}

            <SupportResistancePanel features={features} data={data} />
        </div>
    )
}

function fmtLevels(arr: unknown): string {
    if (!Array.isArray(arr) || arr.length === 0) return '—'
    return (arr as unknown[])
        .map((x) => {
            const n = Number(x)
            return Number.isFinite(n) ? n.toFixed(2) : '—'
        })
        .join(' / ')
}

function pickLevels(
    features: Record<string, unknown>,
    data: Record<string, unknown>,
    keys: string[],
): unknown[] {
    for (const k of keys) {
        const v = (data as Record<string, unknown>)[k] ?? (features as Record<string, unknown>)[k]
        if (Array.isArray(v) && v.length > 0) return v as unknown[]
    }
    return []
}

function SupportResistancePanel({
    features,
    data,
}: {
    features: Record<string, unknown>
    data: Record<string, unknown>
}) {
    const supIntraday = pickLevels(features, data, ['supports_intraday', 'supports'])
    const resIntraday = pickLevels(features, data, ['resistances_intraday', 'resistances'])
    const sup60d = pickLevels(features, data, ['supports_60d'])
    const res60d = pickLevels(features, data, ['resistances_60d'])

    const hasIntraday = supIntraday.length > 0 || resIntraday.length > 0
    const has60d = sup60d.length > 0 || res60d.length > 0
    if (!hasIntraday && !has60d) return null

    return (
        <div className="grid gap-2 md:grid-cols-2">
            {hasIntraday ? (
                <div className="rounded-lg border border-emerald-200 bg-emerald-50/40 p-2 dark:border-emerald-700 dark:bg-emerald-900/20">
                    <h5 className="mb-1 text-xs font-semibold text-emerald-800 dark:text-emerald-200">短线 SR · 当日 + 近 5 日</h5>
                    <div className="space-y-0.5 text-xs text-slate-700 dark:text-slate-200">
                        <div>支撑：{fmtLevels(supIntraday)}</div>
                        <div>压力：{fmtLevels(resIntraday)}</div>
                    </div>
                </div>
            ) : null}
            {has60d ? (
                <div className="rounded-lg border border-slate-200 bg-slate-50/40 p-2 dark:border-slate-700 dark:bg-slate-900/40">
                    <h5 className="mb-1 text-xs font-semibold text-slate-700 dark:text-slate-200">中线 SR · 60 日历史密集区</h5>
                    <div className="space-y-0.5 text-xs text-slate-600 dark:text-slate-300">
                        <div>支撑：{fmtLevels(sup60d)}</div>
                        <div>压力：{fmtLevels(res60d)}</div>
                    </div>
                </div>
            ) : null}
        </div>
    )
}

interface Props {
    detail: FastAnalysisDetail
}

export default function FastAnalysisResult({ detail }: Props) {
    const verdict = (detail.verdict_json || {}) as Record<string, unknown>
    const timePhased = (detail.time_phased_json || {}) as Record<string, Record<string, unknown>>
    const position = (detail.position_advice_json || {}) as Record<string, unknown>
    const exec = (detail.executability_json || {}) as Record<string, unknown>
    const kline = (detail.kline_insight_json || {}) as Record<string, unknown>

    const direction = str(verdict.direction)
    const consensusZh = CONSENSUS_ZH[direction] || direction || '—'
    const horizon = str(verdict.horizon)
    const horizonLabel = HORIZON_LABEL[horizon] || horizon

    // 优先使用 request_context_json 内的名称；缺失时回退本地映射表，再异步从后端 stock-search 补齐
    const ctxName = str((detail.request_context_json as Record<string, unknown> | undefined)?.symbol_name)
    const ctxDisplayLabel = (detail.request_context_json as Record<string, unknown> | undefined)?.display_label as
        | string
        | undefined
    const [resolvedName, setResolvedName] = useState<string>(() => ctxName || lookupStockName(detail.symbol) || '')

    useEffect(() => {
        if (resolvedName) return
        let cancelled = false
        void fetchAshareDisplayName(detail.symbol).then((n) => {
            if (!cancelled && n) setResolvedName(n)
        })
        return () => {
            cancelled = true
        }
    }, [detail.symbol, resolvedName])

    const instrumentSanitize: InstrumentDisplayContext = useMemo(
        () => ({
            symbol: detail.symbol,
            name: resolvedName || ctxName || null,
            display_label: stockDisplayLabel({
                symbol: detail.symbol,
                name: resolvedName || ctxName || null,
                display_label: ctxDisplayLabel,
            }),
        }),
        [detail.symbol, ctxName, ctxDisplayLabel, resolvedName],
    )

    const parts = useMemo(
        () =>
            stockDisplayParts({
                symbol: detail.symbol,
                name: resolvedName || ctxName || null,
                display_label: ctxDisplayLabel,
            }),
        [detail.symbol, ctxName, ctxDisplayLabel, resolvedName],
    )

    const rawDump = useMemo(
        () =>
            JSON.stringify(
                {
                    verdict_json: detail.verdict_json,
                    time_phased_json: detail.time_phased_json,
                    position_advice_json: detail.position_advice_json,
                    executability_json: detail.executability_json,
                    kline_insight_json: detail.kline_insight_json,
                },
                null,
                2,
            ),
        [detail],
    )

    const takeProfit = Array.isArray(position.take_profit_tiers) ? (position.take_profit_tiers as Record<string, unknown>[]) : []
    const waitObserve = isWaitObservePosition(position)

    const reasoningMd = sanitizeReportMarkdown(str(verdict.reason), instrumentSanitize)

    return (
        <section className="card space-y-4">
            {/* 标题：股票名称 + 代码 作为最显眼的主标题 */}
            <header className="flex flex-wrap items-start justify-between gap-3 border-b border-slate-200 pb-3 dark:border-slate-700">
                <div className="min-w-0">
                    <div className="flex items-center gap-2">
                        <Zap className="h-5 w-5 shrink-0 text-amber-500" />
                        <h2 className="truncate text-xl font-bold tracking-tight text-slate-900 dark:text-slate-100">
                            {parts.name ? (
                                <>
                                    <span>{parts.name}</span>
                                    <span className="ml-2 font-mono text-base font-semibold text-slate-500 dark:text-slate-400">
                                        {parts.symbol}
                                    </span>
                                </>
                            ) : (
                                <span className="font-mono">{parts.symbol}</span>
                            )}
                        </h2>
                        <span className="ml-1 inline-flex items-center rounded-full bg-amber-50 px-2 py-0.5 text-xs font-medium text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                            快速分析
                        </span>
                    </div>
                    <p className="mt-1 text-xs text-slate-500 dark:text-slate-400">
                        交易日 {detail.trade_date}
                        {horizonLabel ? ` · 决策窗口：${horizonLabel}` : ''}
                        {detail.status ? ` · 状态：${detail.status}` : ''}
                    </p>
                </div>
                <button
                    type="button"
                    className="btn-secondary inline-flex items-center gap-2 px-3 py-1.5 text-sm"
                    onClick={() => exportFastAnalysisMarkdown(detail)}
                >
                    <Download className="h-4 w-4" />
                    导出 Markdown
                </button>
            </header>

            {/* 综合结论小标题，明确锚定到对应标的 */}
            <div>
                <h3 className="text-sm font-semibold text-slate-800 dark:text-slate-100">
                    综合结论 · {parts.label}
                </h3>
                <p className="mt-0.5 text-[11px] text-slate-500 dark:text-slate-400">
                    沙盘倾向（看多 / 中性 / 看空），仅供研究参考，不构成投资建议。
                </p>
            </div>

            <FastConsensusSpectrum direction={direction} />

            <DecisionCard
                symbol={detail.symbol}
                name={instrumentSanitize.name ?? undefined}
                display_label={instrumentSanitize.display_label ?? undefined}
                pillLabel={consensusZh}
                decision={mapFastDirectionToDecision(direction)}
                direction={consensusZh}
                confidence={fastConfidencePercent(verdict.confidence)}
                targetPrice={waitObserve ? undefined : firstPrice(position.entry_zone)}
                stopLoss={waitObserve ? undefined : stopLossNum(position.stop_loss)}
                reasoning={reasoningMd}
            />

            <div className="rounded-xl border border-slate-200 bg-slate-50/60 p-4 dark:border-slate-700 dark:bg-slate-900/40">
                <h3 className="mb-3 text-sm font-semibold text-slate-800 dark:text-slate-100">情景要点</h3>
                <div className="grid gap-4 md:grid-cols-2">
                    <div>
                        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-emerald-700 dark:text-emerald-400">主要驱动</h4>
                        <BulletList items={Array.isArray(verdict.key_drivers) ? (verdict.key_drivers as unknown[]) : []} />
                    </div>
                    <div>
                        <h4 className="mb-1 text-xs font-semibold uppercase tracking-wide text-rose-700 dark:text-rose-400">主要风险</h4>
                        <BulletList items={Array.isArray(verdict.risks) ? (verdict.risks as unknown[]) : []} />
                    </div>
                </div>
            </div>

            {/* 分时段 */}
            <div>
                <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">分时段策略</h3>
                <div className="grid gap-3 md:grid-cols-3">
                    {Object.entries(timePhased).map(([key, block]) => (
                        <div key={key} className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                            <h4 className="mb-2 text-xs font-semibold text-blue-700 dark:text-blue-300">
                                {PHASE_LABEL[key] || key}
                            </h4>
                            <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                                <div className="flex justify-between gap-2">
                                    <span className="text-slate-400">动作</span>
                                    <span className="text-right font-medium text-slate-800 dark:text-slate-100">
                                        {ACTION_LABEL[str(block.action)] || str(block.action) || '—'}
                                    </span>
                                </div>
                                <div className="flex justify-between gap-2">
                                    <span className="text-slate-400">参考仓位比例</span>
                                    <span>{num(block.size_pct)}</span>
                                </div>
                                {block.key_levels && typeof block.key_levels === 'object' ? (
                                    <div className="rounded bg-slate-50 px-2 py-1 dark:bg-slate-800/60">
                                        <span className="text-slate-400">关键位：</span>
                                        支撑 {num((block.key_levels as Record<string, unknown>).support)} · 压力{' '}
                                        {num((block.key_levels as Record<string, unknown>).resistance)}
                                    </div>
                                ) : null}
                                {str(block.trigger_condition) ? (
                                    <div className="pt-1 text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                                        <span className="font-medium text-slate-600 dark:text-slate-300">触发：</span>
                                        {str(block.trigger_condition)}
                                    </div>
                                ) : null}
                            </div>
                        </div>
                    ))}
                </div>
            </div>

            <div className="grid gap-3 md:grid-cols-2">
                {/* 仓位 */}
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">仓位建议</h3>
                    {isWaitObservePosition(position) ? (
                        <div className="space-y-2 text-xs text-slate-600 dark:text-slate-300">
                            <div className="flex justify-between">
                                <span className="text-slate-400">情景</span>
                                <span className="font-medium text-amber-700 dark:text-amber-300">
                                    {SCENARIO_LABEL.wait_observe}
                                </span>
                            </div>
                            <p className="rounded-md bg-amber-50/60 px-2 py-2 leading-relaxed text-slate-700 dark:bg-amber-900/20 dark:text-slate-200">
                                {str(position.sizing_rationale) || '本次不建议建仓或加仓，建议等待明确的企稳/止跌或破位信号再行动。'}
                            </p>
                        </div>
                    ) : (
                        <>
                            <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                                <div className="flex justify-between">
                                    <span className="text-slate-400">情景</span>
                                    <span className="font-medium text-slate-800 dark:text-slate-100">
                                        {SCENARIO_LABEL[str(position.scenario)] || str(position.scenario) || '—'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">目标仓位占比</span>
                                    <span>{num(position.target_position_pct)}</span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">参考介入区间</span>
                                    <span className="text-right">
                                        {Array.isArray(position.entry_zone) ? (position.entry_zone as unknown[]).map(num).join(' ~ ') : '—'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">参考退出 / 压力区</span>
                                    <span className="text-right">
                                        {Array.isArray(position.exit_zone) ? (position.exit_zone as unknown[]).map(num).join(' ~ ') : '—'}
                                    </span>
                                </div>
                                <div className="flex justify-between">
                                    <span className="text-slate-400">止损参考价</span>
                                    <span>{num(position.stop_loss)}</span>
                                </div>
                            </div>
                            {takeProfit.length > 0 ? (
                                <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
                                    <p className="mb-1 text-[11px] font-medium text-slate-500">分批止盈</p>
                                    <ul className="space-y-0.5 text-xs">
                                        {takeProfit.map((t, i) => (
                                            <li key={i}>
                                                价 {num(t.price)} · 比例 {num(t.size_pct)}
                                            </li>
                                        ))}
                                    </ul>
                                </div>
                            ) : null}
                            {str(position.sizing_rationale) ? (
                                <p className="mt-2 text-xs leading-relaxed text-slate-600 dark:text-slate-400">{str(position.sizing_rationale)}</p>
                            ) : null}
                        </>
                    )}
                </div>

                {/* 可执行性 */}
                <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                    <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">可执行性</h3>
                    <div className="space-y-1.5 text-xs text-slate-600 dark:text-slate-300">
                        <div className="flex justify-between">
                            <span className="text-slate-400">流动性评分</span>
                            <span>{num(exec.liquidity_score)} / 5</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-400">预估滑点</span>
                            <span>{num(exec.estimated_slippage_pct)}%</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-400">执行窗口</span>
                            <span>{num(exec.execution_window_minutes)} 分钟</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-400">建议拆单</span>
                            <span>{exec.split_orders_recommended === true ? '是' : exec.split_orders_recommended === false ? '否' : '—'}</span>
                        </div>
                        <div className="flex justify-between">
                            <span className="text-slate-400">建议上限仓位占比</span>
                            <span>{num(exec.max_advisable_position_pct)}</span>
                        </div>
                    </div>
                    {Array.isArray(exec.warnings) && (exec.warnings as unknown[]).length > 0 ? (
                        <div className="mt-2">
                            <p className="mb-1 text-[11px] font-medium text-amber-700 dark:text-amber-400">提示</p>
                            <BulletList items={exec.warnings as unknown[]} />
                        </div>
                    ) : null}
                </div>
            </div>

            {/* K 线解读 */}
            <div className="rounded-lg border border-slate-200 p-3 dark:border-slate-700">
                <h3 className="mb-2 text-sm font-semibold text-slate-800 dark:text-slate-100">K 线即时摘要 · {parts.label}</h3>
                <KlineInsightCard
                    data={kline}
                    features={(detail.kline_features_json || {}) as Record<string, unknown>}
                    symbolLabel={parts.label}
                />
            </div>

            <details className="rounded-lg border border-dashed border-slate-300 dark:border-slate-600">
                <summary className="cursor-pointer px-3 py-2 text-xs font-medium text-slate-500 dark:text-slate-400">
                    原始 JSON（调试用）
                </summary>
                <pre className="max-h-96 overflow-auto border-t border-slate-200 p-3 font-mono text-[11px] text-slate-600 dark:border-slate-700 dark:text-slate-400">
                    {rawDump}
                </pre>
            </details>
        </section>
    )
}
