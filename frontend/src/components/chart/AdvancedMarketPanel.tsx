import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { ChevronDown, ChevronRight, Loader2 } from 'lucide-react'
import { ColorType, LineSeries, createChart } from 'lightweight-charts'
import type { LineData, UTCTimestamp } from 'lightweight-charts'

import { api } from '@/services/api'
import { useAuthStore } from '@/stores/authStore'
import { cnShanghaiDateText } from '@/lib/cnMarketHours'
import { formatIntradayCrosshairTime } from '@/lib/chartTime'

type AdvTab = 'intraday' | 'orderbook' | 'trades' | 'profile'

const ADV_TABS: { id: AdvTab; label: string }[] = [
    { id: 'intraday', label: '分时' },
    { id: 'orderbook', label: '盘口' },
    { id: 'trades', label: '成交' },
    { id: 'profile', label: '企业' },
]

function asPayload(value: unknown): Record<string, unknown> {
    if (typeof value === 'string') {
        if (/<html|<!doctype/i.test(value.slice(0, 200))) {
            throw new Error('高级行情接口返回了前端页面，请检查 /v1 代理或后端服务。')
        }
        throw new Error('高级行情接口返回格式异常')
    }
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
        throw new Error('高级行情接口返回格式异常')
    }
    return value as Record<string, unknown>
}

function numText(v: unknown, digits = 2): string {
    const n = Number(v)
    if (!Number.isFinite(n)) return '--'
    return n.toFixed(digits).replace(/0+$/, '').replace(/\.$/, '')
}

function textValue(v: unknown): string {
    return typeof v === 'string' && v.trim() ? v.trim() : '--'
}

function rowsOf(payload: Record<string, unknown>, key: string): Record<string, unknown>[] {
    const raw = payload[key]
    return Array.isArray(raw) ? raw.filter((x): x is Record<string, unknown> => !!x && typeof x === 'object') : []
}

function friendlyDataError(payload: Record<string, unknown> | null, fallback: string | null): string | null {
    if (fallback) return fallback
    if (!payload || typeof payload.error !== 'string') return null
    if (typeof payload.detail === 'string' && payload.detail.trim()) return payload.detail.trim()
    return '数据源暂不可用，请稍后重试或切换其它标签。'
}

function intradayTimestamp(value: unknown): UTCTimestamp | null {
    const raw = textValue(value)
    if (raw === '--') return null

    // 完整日期时间（按东八区解析无时区信息的时间串）
    if (/^\d{4}-\d{2}-\d{2}/.test(raw)) {
        let normalized = raw.includes('T') ? raw : raw.replace(' ', 'T')
        if (!/[+-]\d{2}:?\d{2}$|Z$/i.test(normalized)) {
            normalized = `${normalized}+08:00`
        }
        const ms = Date.parse(normalized)
        if (Number.isFinite(ms)) return Math.floor(ms / 1000) as UTCTimestamp
    }

    // 仅时间（分时）——用上海交易日日期拼接，避免 UTC 日历错位
    if (/^\d{1,2}:\d{2}/.test(raw)) {
        const sessionDate = cnShanghaiDateText()
        let hhmmss = raw.trim()
        if (/^\d{1,2}:\d{2}$/.test(hhmmss)) hhmmss = `${hhmmss}:00`
        const ms = Date.parse(`${sessionDate}T${hhmmss}+08:00`)
        if (Number.isFinite(ms)) return Math.floor(ms / 1000) as UTCTimestamp
    }

    return null
}

function intradayPoints(rows: Record<string, unknown>[]): LineData<UTCTimestamp>[] {
    const points: LineData<UTCTimestamp>[] = []
    const seen = new Set<number>()
    for (const row of rows) {
        const time = intradayTimestamp(row.time)
        const value = Number(row.price)
        if (time == null || !Number.isFinite(value) || seen.has(time)) continue
        seen.add(time)
        points.push({ time, value })
    }
    return points.sort((a, b) => Number(a.time) - Number(b.time))
}

function IntradayLineChart({ rows }: { rows: Record<string, unknown>[] }) {
    const ref = useRef<HTMLDivElement>(null)
    const data = useMemo(() => intradayPoints(rows), [rows])

    useEffect(() => {
        if (!ref.current || data.length === 0) return
        const chart = createChart(ref.current, {
            width: ref.current.clientWidth || 520,
            height: 148,
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#64748b',
                attributionLogo: false,
            },
            grid: {
                vertLines: { color: 'rgba(148,163,184,0.14)' },
                horzLines: { color: 'rgba(148,163,184,0.14)' },
            },
            rightPriceScale: { borderColor: 'rgba(148,163,184,0.28)' },
            timeScale: {
                borderColor: 'rgba(148,163,184,0.28)',
                timeVisible: true,
                secondsVisible: false,
            },
            localization: {
                locale: 'zh-CN',
                timeFormatter: formatIntradayCrosshairTime,
            },
        })
        const line = chart.addSeries(LineSeries, {
            color: '#06b6d4',
            lineWidth: 2,
            priceLineVisible: true,
            lastValueVisible: true,
        })
        line.setData(data)
        chart.timeScale().fitContent()

        const onResize = () => {
            if (!ref.current) return
            chart.applyOptions({ width: ref.current.clientWidth || 520 })
        }
        window.addEventListener('resize', onResize)
        return () => {
            window.removeEventListener('resize', onResize)
            chart.remove()
        }
    }, [data])

    if (data.length === 0) {
        return (
            <div className="flex h-[148px] items-center justify-center rounded-md bg-slate-50 text-slate-400 dark:bg-slate-800/60">
                暂无可绘制分时点
            </div>
        )
    }

    return <div ref={ref} className="h-[148px] min-w-0 rounded-md bg-slate-50/70 dark:bg-slate-950/20" />
}

export default function AdvancedMarketPanel({
    symbol,
    defaultCollapsed = false,
}: {
    symbol: string
    /** 默认是否折叠（KLine 页传入 true，避免抢主图空间） */
    defaultCollapsed?: boolean
}) {
    const user = useAuthStore((s) => s.user)
    const canAdv =
        user?.role === 'admin' || user?.entitlements?.advanced_market === true

    const [collapsed, setCollapsed] = useState<boolean>(defaultCollapsed)
    const [tab, setTab] = useState<AdvTab>('intraday')
    const [loading, setLoading] = useState(false)
    const [err, setErr] = useState<string | null>(null)
    const [payload, setPayload] = useState<Record<string, unknown> | null>(null)

    const loadTab = useCallback(
        async (t: AdvTab) => {
            if (!canAdv) return
            setLoading(true)
            setErr(null)
            try {
                let res: unknown
                if (t === 'intraday') res = await api.getMarketIntraday(symbol)
                else if (t === 'orderbook') res = await api.getMarketOrderbook(symbol)
                else if (t === 'trades') res = await api.getMarketTrades(symbol)
                else res = await api.getMarketCompanyProfile(symbol)
                setPayload(asPayload(res))
            } catch (e) {
                setErr(e instanceof Error ? e.message : '加载失败')
                setPayload(null)
            } finally {
                setLoading(false)
            }
        },
        [canAdv, symbol],
    )

    /** 折叠时不发请求；首次展开或切换 symbol/tab 才请求 */
    useEffect(() => {
        if (!canAdv || collapsed) return
        void loadTab(tab)
    }, [canAdv, collapsed, symbol, tab, loadTab])

    const pickTab = (t: AdvTab) => {
        setTab(t)
        setPayload(null)
    }

    const intradayRows = useMemo(() => rowsOf(payload ?? {}, 'bars').slice(-8), [payload])
    const orderRows = useMemo(() => rowsOf(payload ?? {}, 'levels').slice(0, 16), [payload])
    const tradeRows = useMemo(() => rowsOf(payload ?? {}, 'trades').slice(-12), [payload])
    const summary = (payload?.summary && typeof payload.summary === 'object' ? payload.summary : {}) as Record<
        string,
        unknown
    >
    const backendError = friendlyDataError(payload, null)

    if (!canAdv) {
        return (
            <div className="mx-1 shrink-0 rounded-lg border border-dashed border-slate-300 bg-slate-50/80 px-3 py-2 text-xs text-slate-600 dark:border-slate-600 dark:bg-slate-900/40 dark:text-slate-400">
                <span className="font-medium text-slate-700 dark:text-slate-300">高级行情</span>
                ：分时、五档、成交摘要与企业资料为{' '}
                <Link className="text-cyan-600 hover:underline dark:text-cyan-400" to="/subscription">
                    高级 VIP
                </Link>{' '}
                权益；管理员默认开放。
            </div>
        )
    }

    return (
        <div className="mx-1 shrink-0 rounded-lg border border-slate-200 bg-white/70 shadow-sm dark:border-slate-700 dark:bg-slate-900/45">
            <div className="flex flex-wrap items-center gap-1 border-b border-slate-200/80 px-2 py-1 dark:border-slate-700/80">
                <button
                    type="button"
                    aria-label={collapsed ? '展开高级行情' : '折叠高级行情'}
                    onClick={() => setCollapsed((c) => !c)}
                    className="mr-1 inline-flex items-center gap-1 rounded px-1 py-0.5 text-[11px] font-semibold text-slate-700 hover:bg-slate-100 dark:text-slate-300 dark:hover:bg-slate-800"
                >
                    {collapsed ? <ChevronRight className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
                    高级行情
                </button>
                {!collapsed &&
                    ADV_TABS.map((t) => (
                        <button
                            key={t.id}
                            type="button"
                            onClick={() => pickTab(t.id)}
                            className={`rounded px-2 py-0.5 text-[11px] font-medium ${
                                tab === t.id
                                    ? 'bg-cyan-600 text-white'
                                    : 'text-slate-600 hover:bg-slate-100 dark:text-slate-400 dark:hover:bg-slate-800'
                            }`}
                        >
                            {t.label}
                        </button>
                    ))}
                {!collapsed && loading && <Loader2 className="h-3.5 w-3.5 animate-spin text-slate-400" />}
                {collapsed && (
                    <span className="text-[10px] text-slate-500 dark:text-slate-400">
                        分时 / 盘口 / 成交 / 企业 — 点击展开
                    </span>
                )}
            </div>
            {collapsed ? null : (
            <div className="max-h-56 overflow-auto px-2 py-2 text-[11px] text-slate-700 dark:text-slate-300">
                {(err || backendError) && (
                    <p className="text-amber-700 dark:text-amber-400">{err || `数据源暂不可用：${backendError}`}</p>
                )}
                {!err && !backendError && tab === 'intraday' && payload && (
                    <div className="grid gap-2 md:grid-cols-[1.6fr_1fr]">
                        <IntradayLineChart rows={rowsOf(payload, 'bars')} />
                        <div className="grid grid-cols-2 gap-1 rounded-md bg-slate-50 p-2 dark:bg-slate-800/60">
                            <span className="text-slate-400">最新</span>
                            <span className="text-right font-medium">{numText(summary.last)}</span>
                            <span className="text-slate-400">高 / 低</span>
                            <span className="text-right font-medium">
                                {numText(summary.high)} / {numText(summary.low)}
                            </span>
                            <span className="text-slate-400">点数</span>
                            <span className="text-right font-medium">{numText(summary.points, 0)}</span>
                        </div>
                        <div className="grid grid-cols-4 gap-x-2 gap-y-1 tabular-nums md:col-span-2">
                            {intradayRows.map((r, i) => (
                                <div key={`${r.time}-${i}`} className="contents">
                                    <span className="text-slate-400">{textValue(r.time)}</span>
                                    <span className="text-right">{numText(r.price)}</span>
                                    <span className="text-right text-slate-500">{numText(r.volume, 0)}</span>
                                    <span className="truncate text-slate-400">{textValue(r.note)}</span>
                                </div>
                            ))}
                        </div>
                    </div>
                )}
                {!err && !backendError && tab === 'orderbook' && payload && (
                    <div className="grid grid-cols-2 gap-x-4 gap-y-1 tabular-nums sm:grid-cols-4">
                        {orderRows.map((r, i) => (
                            <div key={`${r.item}-${i}`} className="flex justify-between gap-2 rounded bg-slate-50 px-2 py-1 dark:bg-slate-800/60">
                                <span className="text-slate-400">{textValue(r.item)}</span>
                                <span className="font-medium">{numText(r.value)}</span>
                            </div>
                        ))}
                    </div>
                )}
                {!err && !backendError && tab === 'trades' && payload && (
                    <div className="grid grid-cols-4 gap-x-2 gap-y-1 tabular-nums">
                        {tradeRows.map((r, i) => (
                            <div key={`${r.time}-${i}`} className="contents">
                                <span className="text-slate-400">{textValue(r.time)}</span>
                                <span className="text-right font-medium">{numText(r.price)}</span>
                                <span className="text-right text-slate-500">{numText(r.volume, 0)}</span>
                                <span className="truncate text-slate-400">{textValue(r.note)}</span>
                            </div>
                        ))}
                    </div>
                )}
                {!err && !backendError && tab === 'profile' && payload && (
                    <div className="space-y-1">
                        {typeof payload.markdown_excerpt === 'string' && (
                            <p className="whitespace-pre-wrap text-[11px] leading-snug text-slate-600 dark:text-slate-300">
                                {(payload.markdown_excerpt as string).slice(0, 1200)}
                            </p>
                        )}
                        {!payload.markdown_excerpt && (
                            <p className="text-slate-500">暂无企业简介</p>
                        )}
                    </div>
                )}
                {!loading && !err && !payload && <p className="text-slate-500">暂无数据</p>}
            </div>
            )}
        </div>
    )
}
