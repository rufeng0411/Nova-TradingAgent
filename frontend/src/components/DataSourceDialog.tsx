import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import {
    AlertTriangle,
    Boxes,
    ChevronRight,
    ChevronsDownUp,
    ChevronsUpDown,
    Database,
    ExternalLink,
    FileText,
    GitBranch,
    GripVertical,
    Maximize2,
    Minimize2,
    Tags,
    X,
} from 'lucide-react'
import type { DataSourceBundle, DataSourceItem } from '@/types'
import { DEFAULT_VENDOR_ICON, getItemVendorDisplay, getItemVendorIcon, getItemVendorSite } from '@/utils/dataSourceMeta'

type GroupMode = 'vendor' | 'category'

interface DataSourceDialogProps {
    open: boolean
    onClose: () => void
    dataSources?: DataSourceBundle
    derivedSignals?: Record<string, unknown>
    symbol?: string
    tradeDate?: string
}

const STATUS_LABEL: Record<string, string> = {
    hit: '命中',
    fallback: '降级命中',
    error: '失败',
    internal: '本地计算',
    skipped: '跳过',
    unsupported_channel: '未启用',
    hint: '接口成功但0行',
}

const STATUS_CLASS: Record<string, string> = {
    hit: 'text-emerald-600 dark:text-emerald-400',
    fallback: 'text-amber-600 dark:text-amber-400',
    error: 'text-rose-600 dark:text-rose-400',
    internal: 'text-slate-600 dark:text-slate-300',
    skipped: 'text-slate-500 dark:text-slate-400',
    unsupported_channel: 'text-violet-600 dark:text-violet-400',
    hint: 'text-sky-600 dark:text-sky-400',
}

const MIN_W = 420
const MIN_H = 340

function formatLatency(v: number | null | undefined): string {
    if (typeof v !== 'number' || Number.isNaN(v)) return '--'
    return `${v}ms`
}

function formatTs(v?: string): string {
    if (!v) return '--'
    const date = new Date(v)
    if (Number.isNaN(date.getTime())) return v
    return date.toLocaleString('zh-CN', { hour12: false })
}

function groupByVendor(items: DataSourceItem[]): Record<string, DataSourceItem[]> {
    const map: Record<string, DataSourceItem[]> = {}
    for (const item of items) {
        const key = item.vendor || 'unknown'
        if (!map[key]) map[key] = []
        map[key].push(item)
    }
    return map
}

function groupByCategory(items: DataSourceItem[]): Record<string, DataSourceItem[]> {
    const map: Record<string, DataSourceItem[]> = {}
    for (const item of items) {
        const key = item.category || 'unknown'
        if (!map[key]) map[key] = []
        map[key].push(item)
    }
    return map
}

const TRANSLATED_METHOD_LABEL: Record<string, string> = {
    orderbook_pressure_signal_v1: '盘口压力代理',
    active_buy_proxy_v1: '主动买入近似',
    moneyflow_structure_v1: '资金流结构化结论',
    financial_health_v1: '财务健康度',
    auction_intraday_strength_v1: '竞价时段强度',
}

function asRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) return null
    return value as Record<string, unknown>
}

function asNum(value: unknown): number | null {
    const n = Number(value)
    return Number.isFinite(n) ? n : null
}

function formatYiSigned(v: number | null | undefined): string {
    if (v === null || v === undefined || !Number.isFinite(v)) return '--'
    return `${(v / 1e8).toFixed(2)}`
}

function formatTranslatedSummary(method: string, payload: Record<string, unknown>): string | null {
    const err = String(payload.error || '')
    if (err && err !== 'none' && err !== 'null') return null
    if (method === 'orderbook_pressure_signal_v1') {
        const ask = asNum(payload.ask_total)
        const bid = asNum(payload.bid_total)
        const ratio = asNum(payload.ask_bid_ratio)
        const pressure = String(payload.pressure || '').trim()
        if (ask === null && bid === null && ratio === null && !pressure) return null
        return `卖买比 ${ratio?.toFixed(2) ?? '--'}，卖挂单 ${formatYiSigned(ask)} 亿，买挂单 ${formatYiSigned(bid)} 亿，结论：${pressure || '待观察'}。`
    }
    if (method === 'active_buy_proxy_v1') {
        const net = asNum(payload.net_main)
        const pct = asNum(payload.net_inflow_pct)
        const ratio = asNum(payload.active_buy_proxy_ratio)
        if (net === null && pct === null && ratio === null) return null
        return `大单净流入 ${formatYiSigned(net)} 亿，净流入占比 ${pct !== null ? `${(pct * 100).toFixed(2)}%` : '--'}，近似主动买入占比 ${ratio !== null ? `${(ratio * 100).toFixed(1)}%` : '--'}（近似指标，非真 L2 逐笔）。`
    }
    if (method === 'moneyflow_structure_v1') {
        const net5d = asNum(payload.main_net_inflow_5d)
        const rank = asNum(payload.industry_rank_pct)
        const inst = asNum(payload.inst_net_buy_7d)
        if (net5d === null && rank === null && inst === null) return null
        return `近5日主力净流入 ${formatYiSigned(net5d)} 亿，行业梯队分位 ${rank !== null ? `${(rank * 100).toFixed(1)}%` : '--'}，机构净买 ${formatYiSigned(inst)} 亿。`
    }
    if (method === 'financial_health_v1') {
        const score = asNum(payload.health_score)
        const roe = asNum(payload.roe)
        const debt = asNum(payload.debt_ratio)
        const cq = asNum(payload.cash_quality)
        if (score === null && roe === null && debt === null && cq === null) return null
        return `健康分 ${score !== null ? score.toFixed(1) : '--'}/100，ROE ${roe !== null ? `${roe.toFixed(2)}%` : '--'}，资产负债率 ${debt !== null ? `${debt.toFixed(2)}%` : '--'}，现金流质量 ${cq !== null ? cq.toFixed(2) : '--'}。`
    }
    if (method === 'auction_intraday_strength_v1') {
        const vg = asNum(payload.vol_growth_pct)
        const pm = asNum(payload.price_move_pct)
        const ag = asNum(payload.amount_growth_pct)
        const tone = String(payload.tone || '').trim()
        if (vg === null && pm === null && ag === null && !tone) return null
        return `竞价量变化 ${vg !== null ? `${(vg * 100).toFixed(1)}%` : '--'}，价格变化 ${pm !== null ? `${(pm * 100).toFixed(2)}%` : '--'}，委托金额变化 ${ag !== null ? `${(ag * 100).toFixed(1)}%` : '--'}，结论：${tone || '待观察'}。`
    }
    return null
}

function resolveRelatedMethods(item: DataSourceItem): string[] {
    const methods = new Set<string>()
    const raw = `${item.key} ${item.method || ''} ${item.category || ''} ${item.display_name || ''}`.toLowerCase()
    if (item.method && TRANSLATED_METHOD_LABEL[item.method]) methods.add(item.method)
    if (raw.includes('auction') || raw.includes('竞价')) methods.add('auction_intraday_strength_v1')
    if (raw.includes('rt_k') || raw.includes('orderbook') || raw.includes('盘口') || raw.includes('l2')) {
        methods.add('orderbook_pressure_signal_v1')
    }
    if (raw.includes('moneyflow') || raw.includes('fund_flow') || raw.includes('top_list') || raw.includes('龙虎榜') || raw.includes('资金')) {
        methods.add('active_buy_proxy_v1')
        methods.add('moneyflow_structure_v1')
    }
    if (
        raw.includes('fina') ||
        raw.includes('fundamentals') ||
        raw.includes('balance') ||
        raw.includes('cashflow') ||
        raw.includes('income') ||
        raw.includes('daily_basic') ||
        raw.includes('财务') ||
        raw.includes('估值')
    ) {
        methods.add('financial_health_v1')
    }
    return Array.from(methods)
}

function buildTranslatedTextMap(items: DataSourceItem[]): Record<string, string> {
    const out: Record<string, string> = {}
    for (const item of items) {
        const method = String(item.method || '').trim()
        const preview = String(item.detail_preview || '').trim()
        if (!preview) continue
        if (method && TRANSLATED_METHOD_LABEL[method]) {
            out[method] = preview
            continue
        }
        if (item.key === 'orderbook_pressure_signal') out.orderbook_pressure_signal_v1 = preview
        if (item.key === 'active_buy_proxy') out.active_buy_proxy_v1 = preview
        if (item.key === 'moneyflow_structure') out.moneyflow_structure_v1 = preview
        if (item.key === 'financial_health') out.financial_health_v1 = preview
        if (item.key === 'auction_intraday_strength') out.auction_intraday_strength_v1 = preview
    }
    return out
}

function clampPanel(x: number, y: number, w: number, h: number) {
    const margin = 8
    const vw = typeof window !== 'undefined' ? window.innerWidth : 1200
    const vh = typeof window !== 'undefined' ? window.innerHeight : 800
    const cw = Math.min(Math.max(w, MIN_W), vw - margin * 2)
    const ch = Math.min(Math.max(h, MIN_H), vh - margin * 2)
    const cx = Math.min(Math.max(x, margin), vw - cw - margin)
    const cy = Math.min(Math.max(y, margin), vh - ch - margin)
    return { x: cx, y: cy, w: cw, h: ch }
}

export default function DataSourceDialog({ open, onClose, dataSources, derivedSignals, symbol, tradeDate }: DataSourceDialogProps) {
    const [mode, setMode] = useState<GroupMode>('vendor')
    const [fullscreen, setFullscreen] = useState(false)
    const [bounds, setBounds] = useState({ x: 0, y: 0, w: 960, h: 680 })

    const listRef = useRef<HTMLDivElement>(null)
    const dragRef = useRef<{
        active: boolean
        kind: 'move' | 'resize'
        sx: number
        sy: number
        ox: number
        oy: number
        ow: number
        oh: number
    } | null>(null)

    const items = dataSources?.items || []
    const translatedTextMap = useMemo(() => buildTranslatedTextMap(items), [items])
    const derivedSignalCount = useMemo(() => Object.keys(derivedSignals || {}).length, [derivedSignals])
    const translatedTextCount = useMemo(() => Object.keys(translatedTextMap).length, [translatedTextMap])

    const grouped = useMemo(() => {
        if (mode === 'vendor') return groupByVendor(items)
        return groupByCategory(items)
    }, [items, mode])

    useLayoutEffect(() => {
        if (!open) return
        const vw = window.innerWidth
        const vh = window.innerHeight
        const w = Math.min(1024, vw - 48)
        const h = Math.min(Math.floor(vh * 0.82), 760)
        const x = Math.floor((vw - w) / 2)
        const y = Math.floor((vh - h) / 2)
        setBounds(clampPanel(x, y, w, h))
        setFullscreen(false)
    }, [open])

    useEffect(() => {
        if (!open) return
        const onKey = (e: KeyboardEvent) => {
            if (e.key === 'Escape') onClose()
        }
        window.addEventListener('keydown', onKey)
        return () => window.removeEventListener('keydown', onKey)
    }, [open, onClose])

    useEffect(() => {
        const onMove = (e: MouseEvent) => {
            const d = dragRef.current
            if (!d?.active) return
            const dx = e.clientX - d.sx
            const dy = e.clientY - d.sy
            if (d.kind === 'move') {
                setBounds((prev) => clampPanel(d.ox + dx, d.oy + dy, prev.w, prev.h))
            } else {
                setBounds((prev) => clampPanel(prev.x, prev.y, d.ow + dx, d.oh + dy))
            }
        }
        const onUp = () => {
            if (dragRef.current) dragRef.current.active = false
        }
        window.addEventListener('mousemove', onMove)
        window.addEventListener('mouseup', onUp)
        return () => {
            window.removeEventListener('mousemove', onMove)
            window.removeEventListener('mouseup', onUp)
        }
    }, [])

    const startDragMove = useCallback(
        (e: React.MouseEvent) => {
            if (fullscreen) return
            if ((e.target as HTMLElement).closest('button,a')) return
            e.preventDefault()
            dragRef.current = {
                active: true,
                kind: 'move',
                sx: e.clientX,
                sy: e.clientY,
                ox: bounds.x,
                oy: bounds.y,
                ow: bounds.w,
                oh: bounds.h,
            }
        },
        [fullscreen, bounds.x, bounds.y, bounds.w, bounds.h],
    )

    const startResize = useCallback(
        (e: React.MouseEvent) => {
            if (fullscreen) return
            e.preventDefault()
            e.stopPropagation()
            dragRef.current = {
                active: true,
                kind: 'resize',
                sx: e.clientX,
                sy: e.clientY,
                ox: bounds.x,
                oy: bounds.y,
                ow: bounds.w,
                oh: bounds.h,
            }
        },
        [fullscreen, bounds.x, bounds.y, bounds.w, bounds.h],
    )

    const setAllDetailsOpen = useCallback((openAll: boolean) => {
        listRef.current?.querySelectorAll('details.ta-ds-detail').forEach((el) => {
            ;(el as HTMLDetailsElement).open = openAll
        })
    }, [])

    if (!open) return null

    const panelClass = fullscreen
        ? 'fixed inset-3 z-[121] flex flex-col overflow-hidden rounded-xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900 sm:inset-6'
        : 'fixed z-[121] flex flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-2xl dark:border-slate-700 dark:bg-slate-900'

    const panelStyle = fullscreen
        ? undefined
        : ({
              left: bounds.x,
              top: bounds.y,
              width: bounds.w,
              height: bounds.h,
          } as React.CSSProperties)

    return (
        <div
            className="fixed inset-0 z-[120] bg-slate-900/45"
            role="presentation"
            onMouseDown={(e) => {
                if (e.target === e.currentTarget) onClose()
            }}
        >
            <div
                className={panelClass}
                style={panelStyle}
                role="dialog"
                aria-modal="true"
                aria-labelledby="ta-ds-title"
                onMouseDown={(e) => e.stopPropagation()}
            >
                {/* 标题 + 分组 / 批量展开（整块可拖拽，按钮不触发拖拽） */}
                <div
                    className={`shrink-0 select-none border-b border-slate-200/90 px-3 pb-2 pt-2.5 dark:border-slate-700/80 ${fullscreen ? 'cursor-default' : 'cursor-move'}`}
                    onMouseDown={startDragMove}
                >
                    <div className="flex items-start justify-between gap-2">
                        <div className="flex min-w-0 flex-1 items-start gap-2">
                            <GripVertical className={`mt-0.5 h-4 w-4 shrink-0 text-slate-400 ${fullscreen ? 'opacity-40' : ''}`} aria-hidden />
                            <Database className="mt-0.5 h-4 w-4 shrink-0 text-blue-500" />
                            <div className="min-w-0">
                                <h3 id="ta-ds-title" className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
                                    数据源明细
                                </h3>
                                <p className="mt-0.5 truncate text-[11px] leading-snug text-slate-500 dark:text-slate-400">
                                    {symbol || '—'} · {tradeDate || '—'} · {formatTs(dataSources?.generated_at)} · {formatLatency(dataSources?.total_latency_ms)} · {items.length} 条
                                </p>
                            </div>
                        </div>
                        <div className="flex shrink-0 items-center gap-0.5">
                            <button
                                type="button"
                                title="展开全部详情"
                                aria-label="展开全部详情"
                                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setAllDetailsOpen(true)
                                }}
                            >
                                <ChevronsUpDown className="h-4 w-4" />
                            </button>
                            <button
                                type="button"
                                title="折叠全部详情"
                                aria-label="折叠全部详情"
                                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setAllDetailsOpen(false)
                                }}
                            >
                                <ChevronsDownUp className="h-4 w-4" />
                            </button>
                            <button
                                type="button"
                                title={fullscreen ? '退出全屏' : '全屏'}
                                aria-label={fullscreen ? '退出全屏' : '全屏'}
                                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setFullscreen((v) => !v)
                                }}
                            >
                                {fullscreen ? <Minimize2 className="h-4 w-4" /> : <Maximize2 className="h-4 w-4" />}
                            </button>
                            <button
                                type="button"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    onClose()
                                }}
                                aria-label="关闭"
                                title="关闭"
                                className="rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-800 dark:hover:bg-slate-800 dark:hover:text-slate-100"
                            >
                                <X className="h-4 w-4" />
                            </button>
                        </div>
                    </div>
                    <div className="mt-2 flex items-center justify-between gap-2 pl-7">
                        <div className="inline-flex rounded-md bg-slate-100/90 p-0.5 dark:bg-slate-800/80">
                            <button
                                type="button"
                                title="按数据源（vendor）分组"
                                aria-label="按 vendor 分组"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setMode('vendor')
                                }}
                                className={`rounded p-1.5 ${mode === 'vendor' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}`}
                            >
                                <Boxes className="h-3.5 w-3.5" />
                            </button>
                            <button
                                type="button"
                                title="按信息类目分组"
                                aria-label="按类目分组"
                                onClick={(e) => {
                                    e.stopPropagation()
                                    setMode('category')
                                }}
                                className={`rounded p-1.5 ${mode === 'category' ? 'bg-white text-slate-900 shadow-sm dark:bg-slate-600 dark:text-slate-100' : 'text-slate-500 dark:text-slate-400'}`}
                            >
                                <Tags className="h-3.5 w-3.5" />
                            </button>
                        </div>
                    </div>
                </div>

                <div ref={listRef} className="min-h-0 flex-1 overflow-y-auto px-3 py-2">
                    {!items.length ? (
                        <div className="rounded-xl border border-dashed border-slate-300 p-8 text-center text-sm text-slate-500 dark:border-slate-600 dark:text-slate-400">
                            该报告未记录数据源
                        </div>
                    ) : (
                        <div className="space-y-3">
                            {Object.entries(grouped).map(([groupKey, groupItems]) => {
                                const first = groupItems[0]
                                const title = mode === 'vendor' ? getItemVendorDisplay(first) : groupKey
                                const site = mode === 'vendor' ? getItemVendorSite(first) : ''
                                return (
                                    <div key={groupKey} className="rounded-lg bg-slate-50/70 p-2 dark:bg-slate-800/35">
                                        <div className="mb-1.5 flex items-center justify-between gap-2 px-0.5">
                                            <div className="flex min-w-0 items-center gap-1.5">
                                                <img
                                                    src={mode === 'vendor' ? getItemVendorIcon(first) : DEFAULT_VENDOR_ICON}
                                                    alt=""
                                                    className="h-5 w-5 shrink-0 rounded bg-white object-contain p-0.5"
                                                    onError={(e) => {
                                                        if (e.currentTarget.src.endsWith(DEFAULT_VENDOR_ICON)) return
                                                        e.currentTarget.src = DEFAULT_VENDOR_ICON
                                                    }}
                                                />
                                                <span className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">{title}</span>
                                                {site ? (
                                                    <a
                                                        href={site}
                                                        target="_blank"
                                                        rel="noreferrer"
                                                        title="官网"
                                                        className="shrink-0 rounded p-0.5 text-slate-400 hover:bg-slate-200/80 hover:text-blue-600 dark:hover:bg-slate-700 dark:hover:text-blue-400"
                                                    >
                                                        <ExternalLink className="h-3.5 w-3.5" />
                                                    </a>
                                                ) : null}
                                            </div>
                                            <span className="shrink-0 text-[11px] text-slate-400">{groupItems.length}</span>
                                        </div>

                                        <div className="space-y-1.5">
                                            {groupItems.map((item) => {
                                                const translatedBlocks = resolveRelatedMethods(item)
                                                    .map((method) => {
                                                        const payload = asRecord(derivedSignals?.[method])
                                                        let text = payload ? formatTranslatedSummary(method, payload) : null
                                                        if (!text) text = translatedTextMap[method] || null
                                                        if (!text) return null
                                                        return {
                                                            method,
                                                            label: TRANSLATED_METHOD_LABEL[method] || method,
                                                            text,
                                                        }
                                                    })
                                                    .filter((v): v is { method: string; label: string; text: string } => Boolean(v))
                                                return (
                                                    <div
                                                        key={`${item.key}-${item.fetched_at}-${item.vendor || 'none'}`}
                                                        className="rounded-md bg-white/95 px-2.5 py-1.5 dark:bg-slate-900/55"
                                                    >
                                                        <div className="flex items-start justify-between gap-2">
                                                            <div className="min-w-0 flex-1">
                                                                <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-0">
                                                                    <span className="text-sm font-medium text-slate-900 dark:text-slate-100">{item.display_name}</span>
                                                                    <span className="text-[11px] text-slate-400">{item.key}</span>
                                                                </div>
                                                                <p className="mt-0.5 truncate text-[11px] text-slate-500 dark:text-slate-400">
                                                                    {formatTs(item.fetched_at)} · {getItemVendorDisplay(item)}
                                                                </p>
                                                                {item.status === 'fallback' && item.fallback_chain?.length ? (
                                                                    <span
                                                                        className="mt-0.5 inline-flex items-center gap-0.5 text-amber-600 dark:text-amber-400"
                                                                        title={item.fallback_chain.join(' → ')}
                                                                    >
                                                                        <GitBranch className="h-3 w-3 shrink-0" aria-hidden />
                                                                    </span>
                                                                ) : null}
                                                                {item.status === 'error' && item.error ? (
                                                                    <p className="mt-0.5 line-clamp-2 text-[11px] text-rose-600 dark:text-rose-400">
                                                                        <AlertTriangle className="mr-0.5 inline h-3 w-3 align-text-bottom" />
                                                                        {item.error}
                                                                    </p>
                                                                ) : null}
                                                                {item.status === 'unsupported_channel' ? (
                                                                    <p className="mt-0.5 line-clamp-2 text-[11px] text-violet-600 dark:text-violet-400">
                                                                        该数据产品未在当前权限内启用
                                                                    </p>
                                                                ) : null}
                                                            </div>
                                                            <div className="shrink-0 text-right">
                                                                <p className={`text-[11px] font-medium ${STATUS_CLASS[item.status] || STATUS_CLASS.hit}`}>
                                                                    {STATUS_LABEL[item.status] || item.status}
                                                                </p>
                                                                <p className="text-[10px] text-slate-400">{formatLatency(item.latency_ms)}</p>
                                                            </div>
                                                        </div>

                                                        <details className="ta-ds-detail group mt-1">
                                                            <summary className="flex cursor-pointer list-none items-center gap-1 rounded px-1 py-0.5 text-slate-500 hover:bg-slate-100/80 dark:text-slate-400 dark:hover:bg-slate-800/60 [&::-webkit-details-marker]:hidden">
                                                                <ChevronRight className="h-3.5 w-3.5 shrink-0 transition-transform group-open:rotate-90" aria-hidden />
                                                                <FileText className="h-3.5 w-3.5 shrink-0 opacity-80" aria-hidden />
                                                                <span className="sr-only">数据源详情</span>
                                                            </summary>
                                                            <div className="mt-1 space-y-1.5 pl-5">
                                                                {item.method ? (
                                                                    <p className="font-mono text-[10px] leading-snug text-slate-400 dark:text-slate-500">{item.method}</p>
                                                                ) : null}
                                                                {item.fallback_chain?.length ? (
                                                                    <p className="font-mono text-[10px] leading-snug text-slate-500 dark:text-slate-400" title={item.fallback_chain.join(' → ')}>
                                                                        {item.fallback_chain.join(' → ')}
                                                                    </p>
                                                                ) : null}
                                                                <div className="space-y-1 rounded border border-emerald-700/80 bg-emerald-900 px-2 py-1.5 text-emerald-50 dark:border-emerald-700 dark:bg-emerald-950">
                                                                        <p className="text-[10px] font-semibold tracking-wide">翻译结论（供 LLM）</p>
                                                                        {translatedBlocks.length ? (
                                                                            translatedBlocks.map((block) => (
                                                                                <p key={`${item.key}-${block.method}`} className="text-[10px] leading-relaxed">
                                                                                    <span className="font-semibold">{block.label}：</span>
                                                                                    {block.text}
                                                                                </p>
                                                                            ))
                                                                        ) : (
                                                                            <p className="text-[10px] leading-relaxed text-emerald-100/95">
                                                                                当前条目暂无翻译信号。全局 derived_signals={derivedSignalCount}，翻译条目={translatedTextCount}。
                                                                            </p>
                                                                        )}
                                                                </div>
                                                                {item.detail_preview?.trim() ? (
                                                                    <pre className="max-h-[min(48vh,380px)] overflow-auto whitespace-pre-wrap break-words rounded bg-slate-100/90 p-2 font-mono text-[10px] leading-relaxed text-slate-800 dark:bg-slate-950/80 dark:text-slate-200">
                                                                        {item.detail_preview}
                                                                    </pre>
                                                                ) : (
                                                                    <p className="text-[10px] text-slate-400">无预览 · 重新生成分析可更新</p>
                                                                )}
                                                            </div>
                                                        </details>
                                                    </div>
                                                )
                                            })}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>
                    )}
                </div>

                {!fullscreen ? (
                    <div
                        role="presentation"
                        className="absolute bottom-1 right-1 h-5 w-5 cursor-nwse-resize rounded-sm bg-transparent hover:bg-slate-200/60 dark:hover:bg-slate-700/60"
                        title="拖拽调整窗口大小"
                        onMouseDown={startResize}
                    />
                ) : null}

                <div className="shrink-0 px-3 py-1.5 text-center text-[10px] text-slate-400 dark:text-slate-500">当次采集 · 非实时</div>
            </div>
        </div>
    )
}
