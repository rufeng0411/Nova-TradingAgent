import { FileText, Download, ChevronDown, ChevronRight, Loader2, MousePointerClick, Database } from 'lucide-react'
import { useState, useEffect, useMemo } from 'react'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import { useAnalysisStore } from '@/stores/analysisStore'
import type { ReportDetail } from '@/types'
import { sanitizeReportMarkdown, type InstrumentDisplayContext } from '@/utils/reportText'
import { stockDisplayLabel, stockSafeFilename } from '@/utils/stockDisplay'
import DataSourceDialog from '@/components/DataSourceDialog'

const REPORT_SECTIONS = [
    { key: 'market_report', title: '市场分析报告', team: '分析团队' },
    { key: 'sentiment_report', title: '舆情分析报告', team: '分析团队' },
    { key: 'news_report', title: '新闻分析报告', team: '分析团队' },
    { key: 'fundamentals_report', title: '基本面分析报告', team: '分析团队' },
    { key: 'macro_report', title: '宏观板块报告', team: '分析团队' },
    { key: 'smart_money_report', title: '主力资金报告', team: '分析团队' },
    { key: 'volume_price_report', title: '量价分析报告', team: '分析团队' },
    { key: 'investment_plan', title: '研究团队研判结论', team: '研究团队' },
    { key: 'trader_investment_plan', title: '执行路径草稿', team: '交易团队' },
    { key: 'final_trade_decision', title: '沙盘综合研判结论', team: '组合管理' },
]

const REPORT_DISCLAIMER =
    '> 免责声明：以上内容由模型基于公开数据、历史信息与预设规则自动生成，仅供研究参考，不构成任何投资建议、收益承诺或实际交易指令。'

const MD_COMPONENTS = {
    table: ({ children }: { children?: React.ReactNode }) => (
        <table className="w-full border-collapse border border-slate-300 dark:border-slate-600 my-4">{children}</table>
    ),
    thead: ({ children }: { children?: React.ReactNode }) => (
        <thead className="bg-slate-100 dark:bg-slate-700">{children}</thead>
    ),
    th: ({ children }: { children?: React.ReactNode }) => (
        <th className="border border-slate-300 dark:border-slate-600 px-3 py-2 text-left font-semibold text-slate-700 dark:text-slate-300">{children}</th>
    ),
    td: ({ children }: { children?: React.ReactNode }) => (
        <td className="border border-slate-300 dark:border-slate-600 px-3 py-2 text-slate-600 dark:text-slate-400">{children}</td>
    ),
    tr: ({ children }: { children?: React.ReactNode }) => (
        <tr className="even:bg-slate-50 dark:even:bg-slate-800/50">{children}</tr>
    ),
}

interface ReportViewerProps {
    /** 传入后进入历史报告模式，不读取 store */
    reportData?: ReportDetail
    /** 当前选中章节（实时模式：点哪个智能体就显示哪个） */
    activeSection?: string
}

export default function ReportViewer({ reportData, activeSection }: ReportViewerProps = {}) {
    const { report, streamingSections, isAnalyzing, currentSymbol, currentSymbolDisplayName } = useAnalysisStore()
    const [expandedSections, setExpandedSections] = useState<string[]>([])
    const [dataSourceOpen, setDataSourceOpen] = useState(false)
    const isHistorical = !!reportData
    const currentReport = reportData ?? report
    const resolvedDataSources =
        currentReport?.data_sources ||
        (isHistorical ? reportData?.result_data?.data_sources : report?.data_sources) ||
        undefined
    const resolvedDerivedSignals =
        currentReport?.derived_signals ||
        (isHistorical ? reportData?.result_data?.derived_signals : report?.derived_signals) ||
        undefined
    const dataSourceCount = resolvedDataSources?.items?.length || 0
    const hasDataSources = dataSourceCount > 0

    const instrumentForSanitize: InstrumentDisplayContext | null = useMemo(() => {
        if (isHistorical && reportData) {
            return {
                symbol: reportData.symbol,
                name: reportData.name,
                display_label: stockDisplayLabel({
                    symbol: reportData.symbol,
                    name: reportData.name,
                    display_label: reportData.display_label,
                }),
            }
        }
        const sym = (report?.symbol ?? currentSymbol ?? '').trim()
        if (!sym) return null
        return {
            symbol: sym,
            name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
            display_label: stockDisplayLabel({
                symbol: sym,
                name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
                display_label: report?.instrument_context?.display_label,
            }),
        }
    }, [
        isHistorical,
        reportData,
        report?.symbol,
        report?.instrument_context?.security_name,
        report?.instrument_context?.display_label,
        currentSymbol,
        currentSymbolDisplayName,
    ])

    const getSectionContent = (key: string): string => {
        if (isHistorical) {
            return sanitizeReportMarkdown(
                (reportData?.[key as keyof ReportDetail] as string | undefined) || '',
                instrumentForSanitize,
            )
        }
        const s = streamingSections[key]
        return sanitizeReportMarkdown(
            s?.displayed || (report?.[key as keyof typeof report] as string | undefined) || '',
            instrumentForSanitize,
        )
    }

    const getSectionState = (key: string) => {
        if (isHistorical) return { isStreaming: false, isComplete: true }
        const s = streamingSections[key]
        return {
            isStreaming: s?.isTyping || false,
            isComplete: s?.isComplete || !!(report?.[key as keyof typeof report]),
        }
    }

    const hasAnyContent = isHistorical
        ? REPORT_SECTIONS.some(s => !!reportData?.[s.key as keyof ReportDetail])
        : Object.keys(streamingSections).length > 0 || (report && Object.values(report).some(v => typeof v === 'string' && v.length > 0))

    /** 仅用 id + 各章节正文长度作为签名，避免父组件每次传入新 report 对象引用时反复重置折叠态 */
    const historicalSectionPresenceKey = useMemo(() => {
        if (!reportData?.id) return ''
        const bits = REPORT_SECTIONS.map((s) => {
            const v = reportData[s.key as keyof ReportDetail]
            return typeof v === 'string' && v.trim().length > 0 ? '1' : '0'
        }).join('')
        const lens = REPORT_SECTIONS.map((s) => {
            const v = reportData[s.key as keyof ReportDetail]
            return typeof v === 'string' ? v.length : 0
        }).join(',')
        return `${reportData.id}|${bits}|${lens}`
    }, [
        reportData?.id,
        ...(reportData ? REPORT_SECTIONS.map((s) => reportData[s.key as keyof ReportDetail]) : []),
    ])

    // ── Historical mode: auto-expand first 2 sections with content ────────────
    useEffect(() => {
        if (!isHistorical || !reportData) return
        const withContent = REPORT_SECTIONS
            .filter(s => {
                const v = reportData[s.key as keyof ReportDetail]
                return typeof v === 'string' && v.trim().length > 0
            })
            .map(s => s.key)
        setExpandedSections(withContent.slice(0, 2))
    }, [isHistorical, historicalSectionPresenceKey])

    // Historical mode: accordion toggle
    const toggleSection = (key: string) =>
        setExpandedSections(prev => prev.includes(key) ? prev.filter(k => k !== key) : [...prev, key])

    const handleExport = () => {
        const source = isHistorical ? reportData : report
        if (!source) return
        const text = REPORT_SECTIONS
            .filter(s => source[s.key as keyof typeof source])
            .map(s => `## ${s.title}\n\n${source[s.key as keyof typeof source]}`)
            .join('\n\n---\n\n') + `\n\n---\n\n${REPORT_DISCLAIMER}\n`
        const blob = new Blob([text], { type: 'text/markdown' })
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        const stock = isHistorical
            ? {
                  symbol: reportData?.symbol || '',
                  name: reportData?.name,
                  display_label: reportData?.display_label,
              }
            : {
                  symbol: (report?.symbol ?? currentSymbol) || '',
                  name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
                  display_label: report?.instrument_context?.display_label,
              }
        a.download = `${stockSafeFilename(stock)}-${(isHistorical ? reportData?.trade_date : report?.trade_date) || 'report'}.md`
        document.body.appendChild(a)
        a.click()
        document.body.removeChild(a)
        URL.revokeObjectURL(url)
    }

    // ── Historical mode: full accordion ──────────────────────────────────────
    if (isHistorical) {
        const historicalSubject = reportData
            ? stockDisplayLabel({
                  symbol: reportData.symbol,
                  name: reportData.name,
                  display_label: reportData.display_label,
              })
            : ''
        if (!hasAnyContent) {
            return (
                <div className="flex items-center justify-center py-12">
                    <div className="text-center">
                        <FileText className="w-12 h-12 text-slate-300 dark:text-slate-600 mx-auto mb-4" />
                        <p className="text-slate-500 dark:text-slate-400">暂无分析报告</p>
                    </div>
                </div>
            )
        }
        return (
            <>
                <div className="space-y-2">
                    <div className="flex items-center justify-between mb-4">
                        <div className="flex items-center gap-2">
                            <FileText className="w-5 h-5 text-blue-500" />
                            <div>
                                <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">分析报告</h2>
                                {historicalSubject ? (
                                    <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 tabular-nums">标的：{historicalSubject}</p>
                                ) : null}
                            </div>
                        </div>
                        <div className="flex items-center gap-2">
                            <button
                                onClick={() => setDataSourceOpen(true)}
                                disabled={!hasDataSources}
                                title={hasDataSources ? '查看本次分析使用的数据源' : '该报告未记录数据源'}
                                className="btn-secondary flex items-center gap-2 text-sm py-1.5 px-3 disabled:cursor-not-allowed disabled:opacity-50"
                            >
                                <Database className="w-4 h-4" />
                                数据源{dataSourceCount ? ` · ${dataSourceCount}` : ''}
                            </button>
                            <button onClick={handleExport} className="btn-secondary flex items-center gap-2 text-sm py-1.5 px-3">
                                <Download className="w-4 h-4" />
                                导出
                            </button>
                        </div>
                    </div>
                    <div className="space-y-3">
                        {REPORT_SECTIONS.map((section) => {
                            const content = getSectionContent(section.key)
                            if (!content) return null
                            const isExpanded = expandedSections.includes(section.key)
                            return (
                                <div key={section.key} className="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden bg-white dark:bg-slate-900/40">
                                    <button
                                        onClick={() => toggleSection(section.key)}
                                        className="w-full flex items-center justify-between p-4 bg-slate-50/90 dark:bg-slate-800/50 hover:bg-slate-100 dark:hover:bg-slate-800 transition-colors"
                                    >
                                        <div className="flex items-center gap-2">
                                            {isExpanded ? <ChevronDown className="w-4 h-4 text-slate-400" /> : <ChevronRight className="w-4 h-4 text-slate-400" />}
                                            <span className="font-medium text-slate-900 dark:text-slate-100">{section.title}</span>
                                            <span className="text-xs text-slate-500 dark:text-slate-400">{section.team}</span>
                                        </div>
                                        <span className="text-xs text-green-500">✓</span>
                                    </button>
                                    {isExpanded && (
                                        <div className="p-5 bg-white dark:bg-slate-800/30">
                                            <div className="prose dark:prose-invert prose-sm md:prose-base max-w-none">
                                                <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>{content}</ReactMarkdown>
                                            </div>
                                        </div>
                                    )}
                                </div>
                            )
                        })}
                        <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-xs leading-6 text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
                            <ReactMarkdown remarkPlugins={[remarkGfm]}>{REPORT_DISCLAIMER}</ReactMarkdown>
                        </div>
                    </div>
                </div>
                <DataSourceDialog
                    open={dataSourceOpen}
                    onClose={() => setDataSourceOpen(false)}
                    dataSources={resolvedDataSources}
                    derivedSignals={resolvedDerivedSignals}
                    symbol={currentReport?.symbol}
                    tradeDate={currentReport?.trade_date}
                />
            </>
        )
    }

    // ── Live mode: single-section viewer ─────────────────────────────────────
    const activeMeta = activeSection ? REPORT_SECTIONS.find(s => s.key === activeSection) : null
    const activeContent = activeSection ? getSectionContent(activeSection) : ''
    const { isStreaming: activeStreaming } = activeSection ? getSectionState(activeSection) : { isStreaming: false }

    const liveSubject = stockDisplayLabel({
        symbol: report?.symbol ?? currentSymbol,
        name: currentSymbolDisplayName ?? report?.instrument_context?.security_name,
        display_label: report?.instrument_context?.display_label,
    })

    const hasLiveSubject = Boolean((report?.symbol ?? currentSymbol ?? '').trim())

    return (
        <>
        <div className="card flex-1 flex flex-col min-h-0 ring-1 ring-slate-200/70 dark:ring-slate-800 shadow-[0_16px_40px_rgba(15,23,42,0.06)] dark:shadow-none">
            {/* Header */}
            <div className="flex items-center justify-between mb-4">
                <div className="flex items-center gap-2">
                    <FileText className="w-5 h-5 text-blue-500" />
                    <div>
                        <h2 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
                            {activeMeta ? activeMeta.title : '分析报告'}
                        </h2>
                        {hasLiveSubject && (
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400 tabular-nums">标的：{liveSubject}</p>
                        )}
                        {activeMeta ? (
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                                {activeMeta.team} · 点击其他智能体切换报告
                            </p>
                        ) : (
                            <p className="mt-0.5 text-xs text-slate-500 dark:text-slate-400">
                                点击上方智能体卡片查看完整报告
                            </p>
                        )}
                    </div>
                    {isAnalyzing && (
                        <span className="badge-orange animate-pulse">生成中</span>
                    )}
                </div>
                <div className="flex items-center gap-2">
                    <button
                        onClick={() => setDataSourceOpen(true)}
                        disabled={!hasDataSources}
                        title={hasDataSources ? '查看本次分析使用的数据源' : '该报告未记录数据源'}
                        className="btn-secondary flex items-center gap-2 text-sm py-1.5 px-3 disabled:cursor-not-allowed disabled:opacity-50"
                    >
                        <Database className="w-4 h-4" />
                        数据源{dataSourceCount ? ` · ${dataSourceCount}` : ''}
                    </button>
                    {hasAnyContent && (
                        <button onClick={handleExport} className="btn-secondary flex items-center gap-2 text-sm py-1.5 px-3">
                            <Download className="w-4 h-4" />
                            导出全部
                        </button>
                    )}
                </div>
            </div>

            {/* Body */}
            <div className="flex-1 overflow-y-auto min-h-0">
                {!activeMeta ? (
                    /* Empty state */
                    <div className="flex flex-col items-center justify-center py-16 gap-3">
                        <MousePointerClick className="w-10 h-10 text-slate-300 dark:text-slate-600" />
                        <p className="text-sm font-medium text-slate-400 dark:text-slate-500">
                            点击上方智能体卡片查看报告
                        </p>
                        {isAnalyzing && !hasAnyContent && (
                            <div className="flex items-center gap-1.5 mt-1 text-xs text-slate-400 dark:text-slate-500">
                                <Loader2 className="w-3 h-3 animate-spin" />
                                等待首个章节输出...
                            </div>
                        )}
                    </div>
                ) : (
                    /* Single section content */
                    <div className="space-y-4">
                        <div className="border border-slate-200 dark:border-slate-700 rounded-2xl overflow-hidden bg-white dark:bg-slate-900/40">
                            <div className="p-5 bg-white dark:bg-slate-800/30">
                                {activeContent ? (
                                    <div className="prose dark:prose-invert prose-sm md:prose-base max-w-none">
                                        <ReactMarkdown remarkPlugins={[remarkGfm]} components={MD_COMPONENTS}>
                                            {activeContent}
                                        </ReactMarkdown>
                                        {activeStreaming && (
                                            <span className="inline-block w-2 h-4 bg-blue-500 animate-pulse ml-1" />
                                        )}
                                    </div>
                                ) : (
                                    <div className="flex items-center justify-center py-10 text-slate-400 dark:text-slate-500">
                                        <Loader2 className="w-4 h-4 animate-spin mr-2" />
                                        正在生成报告...
                                    </div>
                                )}
                            </div>
                        </div>

                        {activeContent && (
                            <div className="rounded-2xl border border-amber-200/80 bg-amber-50/80 px-4 py-3 text-xs leading-6 text-amber-800 dark:border-amber-500/20 dark:bg-amber-500/10 dark:text-amber-200">
                                <ReactMarkdown remarkPlugins={[remarkGfm]}>{REPORT_DISCLAIMER}</ReactMarkdown>
                            </div>
                        )}
                    </div>
                )}
            </div>
        </div>
        <DataSourceDialog
            open={dataSourceOpen}
            onClose={() => setDataSourceOpen(false)}
            dataSources={resolvedDataSources}
            derivedSignals={resolvedDerivedSignals}
            symbol={currentReport?.symbol}
            tradeDate={currentReport?.trade_date}
        />
        </>
    )
}
