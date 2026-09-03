import { useState } from 'react'
import { ChevronLeft, ChevronRight, Loader2, RefreshCw, Sparkles } from 'lucide-react'
import { Link } from 'react-router-dom'
import type { ChartInsightResult } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'
import { useChartStore } from '@/stores/chartStore'

function SectionCard({
    title,
    section,
}: {
    title: string
    section: { title: string; points: string[]; novice_hint?: string }
}) {
    const [open, setOpen] = useState(true)
    return (
        <div className="border border-slate-200 dark:border-slate-600 rounded-md overflow-hidden">
            <button
                type="button"
                onClick={() => setOpen(!open)}
                className="w-full flex items-center justify-between px-2 py-1.5 text-left text-xs font-medium bg-slate-100 dark:bg-slate-800"
            >
                {title}
                <span className="text-slate-400">{open ? '−' : '+'}</span>
            </button>
            {open && (
                <div className="px-2 py-2 space-y-1 text-[11px] text-slate-600 dark:text-slate-300">
                    <p className="text-slate-500 dark:text-slate-400">{section.title}</p>
                    <ul className="list-disc pl-4 space-y-0.5">
                        {section.points.map((p, i) => (
                            <li key={i}>{p}</li>
                        ))}
                    </ul>
                    {section.novice_hint && (
                        <p className="text-amber-700 dark:text-amber-400/90 border-t border-slate-200 dark:border-slate-600 pt-1 mt-1">
                            <span className="font-medium">新手提示：</span>
                            {section.novice_hint}
                        </p>
                    )}
                </div>
            )}
        </div>
    )
}

export default function InsightPanel({
    insight,
    fallbackOnly,
    loading,
    error,
    awaitingStart,
    onStart,
    onRefresh,
    collapsed,
    onToggleCollapse,
    creditsBalance,
    includeAdvancedContext,
    mobileMode,
    historyOptions,
    selectedHistoryId,
    onSelectHistory,
}: {
    insight: ChartInsightResult | null
    /** 后端模型未生成成功，内容为本地规则摘要（观感偏短、像快速版） */
    fallbackOnly?: boolean
    loading: boolean
    error: string | null
    /** 为 true 时仅展示扣费/免责与「开始」，不发起请求 */
    awaitingStart: boolean
    onStart: () => void
    onRefresh: (bypassCache: boolean) => void
    collapsed: boolean
    onToggleCollapse: () => void
    /** 当前账户点数，用于提示（可选） */
    creditsBalance?: number | null
    /** 是否将纳入高级行情摘要（权益充足时） */
    includeAdvancedContext?: boolean
    /** 移动端模式适配 */
    mobileMode?: boolean
    /** 本地历史解读（最多 15 条），下拉切换 */
    historyOptions?: { id: string; label: string }[]
    selectedHistoryId?: string | null
    onSelectHistory?: (id: string) => void
}) {
    const { symbol, symbolName, symbolDisplayLabel } = useChartStore()
    const symbolTitle = stockDisplayLabel({ symbol, name: symbolName, display_label: symbolDisplayLabel })

    const historySelect =
        historyOptions && historyOptions.length > 0 && onSelectHistory ? (
            <label className={mobileMode ? 'block w-full' : 'shrink-0 min-w-0 max-w-[11rem]'}>
                <span className="sr-only">历史解读</span>
                <select
                    aria-label="历史解读"
                    value={selectedHistoryId && historyOptions.some((h) => h.id === selectedHistoryId) ? selectedHistoryId : ''}
                    onChange={(e) => {
                        const v = e.target.value
                        if (v) onSelectHistory(v)
                    }}
                    disabled={loading || awaitingStart}
                    className="w-full rounded-md border border-slate-200 bg-white px-1.5 py-1 text-[10px] text-slate-700 shadow-sm dark:border-slate-600 dark:bg-slate-800 dark:text-slate-200 disabled:opacity-40"
                >
                    <option value="">历史解读…</option>
                    {historyOptions.map((h) => (
                        <option key={h.id} value={h.id}>
                            {h.label}
                        </option>
                    ))}
                </select>
            </label>
        ) : null

    const biasCls =
        insight?.bias === 'bullish'
            ? 'bg-red-500/15 text-red-700 dark:text-red-400'
            : insight?.bias === 'bearish'
              ? 'bg-emerald-500/15 text-emerald-700 dark:text-emerald-400'
              : 'bg-slate-500/15 text-slate-600 dark:text-slate-300'

    if (collapsed && !mobileMode) {
        return (
            <button
                type="button"
                onClick={onToggleCollapse}
                className="w-14 shrink-0 flex flex-col items-center gap-2 py-4 rounded-lg border border-slate-200 dark:border-slate-700 bg-white/90 dark:bg-slate-900/80 text-xs text-cyan-600"
                aria-label="展开 Ai助手 面板"
            >
                <ChevronLeft className="w-4 h-4" />
                <span className="[writing-mode:vertical-rl] text-[10px]">Ai助手</span>
            </button>
        )
    }

    return (
        <div className={`${mobileMode ? 'w-full h-full border-none' : 'w-[min(100%,420px)] border border-slate-200 dark:border-slate-700 max-h-[calc(100vh-8rem)]'} shrink-0 flex flex-col rounded-lg bg-white/95 dark:bg-slate-900/90 overflow-hidden`}>
            {!mobileMode && (
                <div className="flex items-center gap-2 px-2 py-1.5 border-b border-slate-200 dark:border-slate-700">
                    <button type="button" onClick={onToggleCollapse} className="p-0.5 rounded hover:bg-slate-100 dark:hover:bg-slate-800" aria-label="收起 Ai助手 面板">
                        <ChevronRight className="w-4 h-4" />
                    </button>
                    <div className="flex flex-col min-w-0 flex-1 gap-0.5">
                        <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-medium text-slate-800 dark:text-slate-100 leading-tight">Ai助手</span>
                            <span
                                className="rounded-md border border-violet-400/35 bg-violet-500/12 px-1.5 py-0.5 text-[9px] font-semibold tracking-wide text-violet-800 dark:border-violet-500/40 dark:bg-violet-500/15 dark:text-violet-200"
                                title="解读请求固定为专业模式（deep）：结构化章节与证据链优先"
                            >
                                专业模式
                            </span>
                        </div>
                        <span
                            className="text-[11px] text-slate-600 dark:text-slate-400 truncate leading-tight tabular-nums"
                            title={symbolTitle}
                        >
                            {symbolTitle}
                        </span>
                    </div>
                    {historySelect}
                    <button
                        type="button"
                        onClick={() => onRefresh(true)}
                        disabled={loading || awaitingStart}
                        className="p-1 rounded hover:bg-slate-100 dark:hover:bg-slate-800 shrink-0 disabled:opacity-40 disabled:pointer-events-none"
                        title={awaitingStart ? '请先点击下方「开始解读」' : '重新解读'}
                    >
                        {loading ? <Loader2 className="w-4 h-4 animate-spin" /> : <RefreshCw className="w-4 h-4" />}
                    </button>
                </div>
            )}
            {mobileMode && (
                <div className="px-4 mb-2 space-y-2">
                    {historySelect}
                    <div className="flex justify-end">
                        <button
                            type="button"
                            onClick={() => onRefresh(true)}
                            disabled={loading || awaitingStart}
                            className="flex items-center gap-1 p-1 px-2 rounded-lg bg-slate-100 dark:bg-slate-800 shrink-0 disabled:opacity-40 disabled:pointer-events-none text-xs text-slate-600 dark:text-slate-300"
                        >
                            {loading ? <Loader2 className="w-3 h-3 animate-spin" /> : <RefreshCw className="w-3 h-3" />} 重新解读
                        </button>
                    </div>
                </div>
            )}

            <p className="px-2 py-1 text-[10px] text-slate-500 dark:text-slate-400 border-b border-slate-200 dark:border-slate-700 leading-relaxed">
                {awaitingStart
                    ? '请阅读点数与风险提示后，点击「开始解读」：将按专业模式生成（deep）。'
                    : '固定专业模式解读；若账号具备高级行情权益，将一并纳入分时/盘口等摘要（不构成投资建议）。'}
            </p>

            <div className="flex-1 overflow-y-auto p-2 space-y-2 text-xs">
                {awaitingStart && !loading && (
                    <div className="rounded-lg border border-slate-200 bg-slate-50/90 dark:border-slate-600 dark:bg-slate-800/60 p-3 space-y-3 shadow-sm">
                        <div className="flex items-start gap-2">
                            <Sparkles className="w-4 h-4 shrink-0 text-cyan-600 dark:text-cyan-400 mt-0.5" aria-hidden />
                            <div className="space-y-2 min-w-0">
                                <p className="text-[11px] font-semibold text-slate-800 dark:text-slate-100">开始前的说明</p>
                                <p className="text-[10px] text-slate-600 dark:text-slate-400 leading-snug">
                                    本次解读<span className="font-medium text-violet-700 dark:text-violet-300">固定为专业模式</span>
                                    （与后端 level=deep 一致）：侧重结构化输出与「若…则…」类推演，耗时可能长于简要模式。
                                </p>
                                <div className="rounded-md border border-amber-200/80 bg-amber-50/80 px-2.5 py-2 dark:border-amber-500/25 dark:bg-amber-950/30">
                                    <p className="text-[10px] font-medium text-amber-900 dark:text-amber-200/95 mb-1">点数与计费</p>
                                    <p className="text-[10px] leading-relaxed text-amber-900/90 dark:text-amber-100/85">
                                        每次点击「开始解读」将向后端请求一次 K 线 Ai 分析；平台可能按规则从您的账户
                                        <span className="font-mono font-medium"> 点数 </span>
                                        中扣减（与套餐、活动及后台配置一致）。命中短时间内的缓存时可能不重复扣费。
                                        {typeof creditsBalance === 'number' ? (
                                            <>
                                                {' '}
                                                当前余额：
                                                <span className="font-mono font-semibold tabular-nums">{creditsBalance}</span>
                                                。
                                            </>
                                        ) : null}{' '}
                                        <Link
                                            to="/subscription"
                                            className="text-cyan-700 underline decoration-cyan-600/50 underline-offset-2 hover:text-cyan-600 dark:text-cyan-400 dark:hover:text-cyan-300"
                                        >
                                            前往订阅/充值
                                        </Link>
                                    </p>
                                </div>
                                <div className="rounded-md border border-slate-200 bg-white/80 px-2.5 py-2 dark:border-slate-600 dark:bg-slate-900/50">
                                    <p className="text-[10px] font-medium text-slate-700 dark:text-slate-200 mb-1">风险免责</p>
                                    <p className="text-[10px] leading-relaxed text-slate-600 dark:text-slate-400">
                                        本解读基于公开行情与技术指标生成的辅助说明，不构成投资建议，不预测涨跌；市场有风险，决策请独立判断并自负盈亏。
                                        {includeAdvancedContext
                                            ? ' 本次将尝试纳入高级行情摘要（分时/盘口等），仍仅为信息整理，非成交建议。'
                                            : null}
                                    </p>
                                </div>
                            </div>
                        </div>
                        <button
                            type="button"
                            onClick={onStart}
                            className="w-full inline-flex items-center justify-center gap-2 rounded-lg bg-gradient-to-r from-cyan-600 to-blue-600 px-3 py-2.5 text-sm font-medium text-white shadow-sm border border-cyan-500/30 hover:from-cyan-500 hover:to-blue-500 focus:outline-none focus:ring-2 focus:ring-cyan-500/40 dark:focus:ring-cyan-400/30"
                        >
                            <Sparkles className="w-4 h-4 shrink-0 opacity-95" />
                            开始解读
                        </button>
                    </div>
                )}

                {loading && !insight && (
                    <div className="flex items-center gap-2 text-slate-500 py-8 justify-center">
                        <Loader2 className="w-5 h-5 animate-spin" />
                        专业模式分析中…
                    </div>
                )}
                {error && <p className="text-red-500">{error}</p>}
                {insight && fallbackOnly && (
                    <div className="rounded-md border border-amber-300/80 bg-amber-50/95 px-2 py-1.5 text-[10px] text-amber-950 dark:border-amber-500/35 dark:bg-amber-950/40 dark:text-amber-100/95 leading-snug">
                        当前为<strong className="font-semibold">离线规则摘要</strong>
                        （模型解读暂时不可用或响应未完整解析），篇幅会偏短；请点击「刷新」重试，或检查后台「深度思考模型」与 API 配额。
                    </div>
                )}
                {insight && (
                    <>
                        <div className={`rounded-lg p-3 ${biasCls}`}>
                            <div className="flex items-center justify-between gap-2 mb-1">
                                <span className="font-semibold">
                                    {insight.bias === 'bullish' ? '偏多' : insight.bias === 'bearish' ? '偏空' : '中性'}
                                </span>
                                <span className="text-[10px] opacity-80">
                                    置信 {(insight.bias_confidence * 100).toFixed(0)}%
                                </span>
                            </div>
                            <p className="leading-relaxed">{insight.summary_plain}</p>
                        </div>

                        {(() => {
                            const d = {
                                title: '',
                                points: [] as string[],
                                novice_hint: '',
                            }
                            const S = insight.sections
                            return (
                                <>
                                    <SectionCard title="趋势" section={S?.trend ?? { ...d, title: '趋势' }} />
                                    <SectionCard title="均线" section={S?.moving_average ?? { ...d, title: '均线' }} />
                                    <SectionCard title="量能" section={S?.volume ?? { ...d, title: '量能' }} />
                                    <SectionCard title="动量" section={S?.momentum ?? { ...d, title: '动量' }} />
                                    <SectionCard title="波动" section={S?.volatility ?? { ...d, title: '波动' }} />
                                    <SectionCard title="形态" section={S?.pattern ?? { ...d, title: '形态' }} />
                                    <SectionCard title="关键位" section={S?.support_resistance ?? { ...d, title: '关键位' }} />
                                </>
                            )
                        })()}

                        {(insight.opportunities?.length || insight.risks?.length) ? (
                            <div className="grid grid-cols-2 gap-2">
                                <div className="rounded border border-emerald-500/30 p-2">
                                    <p className="font-medium text-emerald-600 dark:text-emerald-400 mb-1">机会</p>
                                    <ul className="list-disc pl-3 space-y-0.5 text-[11px]">
                                        {insight.opportunities?.map((x, i) => (
                                            <li key={i}>{x}</li>
                                        ))}
                                    </ul>
                                </div>
                                <div className="rounded border border-orange-500/30 p-2">
                                    <p className="font-medium text-orange-600 dark:text-orange-400 mb-1">风险</p>
                                    <ul className="list-disc pl-3 space-y-0.5 text-[11px]">
                                        {insight.risks?.map((x, i) => (
                                            <li key={i}>{x}</li>
                                        ))}
                                    </ul>
                                </div>
                            </div>
                        ) : null}

                        {Object.keys(insight.glossary || {}).length > 0 && (
                            <div className="text-[10px] text-slate-500 border-t border-slate-200 dark:border-slate-600 pt-2">
                                <p className="font-medium mb-1">术语表</p>
                                <dl className="space-y-0.5">
                                    {Object.entries(insight.glossary).map(([k, v]) => (
                                        <div key={k}>
                                            <dt className="inline font-mono text-cyan-600">{k}</dt>
                                            <dd className="inline ml-1">{v}</dd>
                                        </div>
                                    ))}
                                </dl>
                            </div>
                        )}
                    </>
                )}
            </div>
        </div>
    )
}
