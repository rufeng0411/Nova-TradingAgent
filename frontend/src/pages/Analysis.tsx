import { useCallback, useEffect, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import AgentCollaboration from '@/components/AgentCollaboration'
import DebateDrawer from '@/components/DebateDrawer'
import ReportViewer from '@/components/ReportViewer'
import ChatCopilotPanel from '@/components/ChatCopilotPanel'
import KlinePanel from '@/components/KlinePanel'
import DecisionCard from '@/components/DecisionCard'
import RiskRadar from '@/components/RiskRadar'
import KeyMetrics from '@/components/KeyMetrics'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useActiveRunningAnalysisBootstrap } from '@/hooks/useActiveRunningAnalysisBootstrap'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { lookupStockName, pickExchangeListedSymbol } from '@/utils/stockDisplay'
import { excerptForDecisionCard } from '@/utils/reportText'

function mapDecision(decision?: string): 'buy' | 'sell' | 'hold' | 'add' | 'reduce' | 'watch' | undefined {
    if (!decision) return undefined
    const d = decision.toUpperCase()
    if (d.includes('SELL') || d.includes('卖出')) return 'sell'
    if (d.includes('REDUCE') || d.includes('减持')) return 'reduce'
    if (d.includes('WATCH') || d.includes('观望')) return 'watch'
    if (d.includes('HOLD') || d.includes('持有')) return 'hold'
    if (d.includes('ADD') || d.includes('增持')) return 'add'
    if (d.includes('BUY') || d.includes('买入')) return 'buy'
    return undefined
}

function extractConfidence(text?: string): number | undefined {
    if (!text) return undefined
    const m = text.match(/置信度[:：]\s*(\d+)%/i) ?? text.match(/confidence[:：]\s*(\d+)%/i)
    if (m) {
        const v = parseInt(m[1])
        return v >= 0 && v <= 100 ? v : undefined
    }
    return undefined
}

function extractPrice(text: string | undefined, type: 'target' | 'stop'): number | undefined {
    if (!text) return undefined
    const patterns = type === 'target'
        ? [/目标价[:：]\s*[¥$]?\s*([\d.]+)/, /目标价格[:：]\s*[¥$]?\s*([\d.]+)/, /target[:：]\s*[¥$]?\s*([\d.]+)/i]
        : [/止损价[:：]\s*[¥$]?\s*([\d.]+)/, /止损价格[:：]\s*[¥$]?\s*([\d.]+)/, /stop[-\s_]?loss[:：]\s*[¥$]?\s*([\d.]+)/i]
    for (const p of patterns) {
        const m = text.match(p)
        if (m) return parseFloat(m[1])
    }
    return undefined
}

export default function Analysis() {
    const [searchParams] = useSearchParams()
    const [resumeSignal, setResumeSignal] = useState(0)
    const bumpResume = useCallback(() => setResumeSignal((n) => n + 1), [])
    useActiveRunningAnalysisBootstrap({ bumpResume })

    const querySymbol = (searchParams.get('symbol') || '').trim().toUpperCase()
    const [activeSymbol, setActiveSymbol] = useState(
        () => querySymbol || useAnalysisStore.getState().currentSymbol || '000001.SH',
    )
    const [activeSection, setActiveSection] = useState<string | undefined>()
    const [debateDrawer, setDebateDrawer] = useState<'research' | 'risk' | null>(null)
    const reportRef = useRef<HTMLDivElement | null>(null)
    const {
        report,
        currentSymbol,
        setCurrentSymbol,
        currentSymbolDisplayName,
        setCurrentSymbolDisplayName,
        jobConfidence,
        jobTargetPrice,
        jobStopLoss,
        riskItems,
        keyMetrics,
    } = useAnalysisStore()

    const handleKlineSymbolChange = useCallback((symbol: string) => {
        const s = symbol.trim().toUpperCase()
        setActiveSymbol(s)
        setCurrentSymbol(s)
    }, [setCurrentSymbol])

    const handleShowReport = (section?: string) => {
        setActiveSection(section)
        reportRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' })
    }

    const initialChatInput = querySymbol ? `分析 ${querySymbol} 今日走势` : undefined

    useEffect(() => {
        if (querySymbol) {
            setActiveSymbol(querySymbol)
            setCurrentSymbol(querySymbol)
        }
    }, [querySymbol, setCurrentSymbol])

    useEffect(() => {
        if (currentSymbol) {
            setActiveSymbol(currentSymbol)
        }
    }, [currentSymbol])

    /** 与 K 线、工作流同一套：在分析标的与 store 一致时，主动 stock-search 补全简称（不依赖 job 完成） */
    useEffect(() => {
        const sym = pickExchangeListedSymbol(activeSymbol, report?.symbol ?? null).trim().toUpperCase()
        const cur = pickExchangeListedSymbol(currentSymbol, report?.symbol ?? null).trim().toUpperCase()
        if (!sym || sym !== cur) return

        const quick = lookupStockName(sym)
        if (quick) {
            setCurrentSymbolDisplayName(quick)
            return
        }

        let cancelled = false
        void fetchAshareDisplayName(sym).then((n) => {
            if (cancelled || !n) return
            const st = useAnalysisStore.getState()
            if (pickExchangeListedSymbol(st.currentSymbol, st.report?.symbol ?? null).trim().toUpperCase() !== sym)
                return
            setCurrentSymbolDisplayName(n)
        })
        return () => {
            cancelled = true
        }
    }, [activeSymbol, currentSymbol, report?.symbol, setCurrentSymbolDisplayName])

    const finalDecision = report?.final_trade_decision
    const decisionCardReasoning =
        (report?.final_decision_summary && report.final_decision_summary.trim()) ||
        excerptForDecisionCard(finalDecision, 420)
    const confidence = jobConfidence ?? extractConfidence(finalDecision)
    const targetPrice = jobTargetPrice ?? extractPrice(finalDecision, 'target')
    const stopLoss = jobStopLoss ?? extractPrice(finalDecision, 'stop')

    return (
        <div className="space-y-4">
            <div className="grid grid-cols-[340px_minmax(0,1fr)] gap-4 min-h-[calc(100vh-5rem)]">
                <aside className="h-[calc(100vh-5rem)] sticky top-0 flex flex-col gap-4">
                    <div className="min-h-0 flex-1">
                        <ChatCopilotPanel
                            resumeSignal={resumeSignal}
                            onSymbolDetected={(symbol) => {
                                setActiveSymbol(symbol)
                                setCurrentSymbol(symbol)
                            }}
                            onShowReport={handleShowReport}
                            initialInput={initialChatInput}
                        />
                    </div>
                </aside>

                <div className="min-w-0 space-y-4">
                    <div className="h-[360px]">
                        <KlinePanel
                            symbol={activeSymbol}
                            onSymbolChange={handleKlineSymbolChange}
                        />
                    </div>

                    <AgentCollaboration onSelectSection={handleShowReport} onOpenDebate={setDebateDrawer} selectedSection={activeSection} />

                    <div className="grid grid-cols-1 xl:grid-cols-3 gap-4">
                        <DecisionCard
                            symbol={activeSymbol}
                            name={currentSymbolDisplayName ?? report?.instrument_context?.security_name}
                            report={report || undefined}
                            decision={mapDecision(report?.decision)}
                            direction={report?.direction}
                            confidence={confidence}
                            targetPrice={targetPrice}
                            stopLoss={stopLoss}
                            reasoning={decisionCardReasoning}
                            reasoningFull={finalDecision ?? undefined}
                        />
                        <RiskRadar items={riskItems} />
                        <KeyMetrics items={keyMetrics} />
                    </div>

                    <div ref={reportRef}>
                        <ReportViewer activeSection={activeSection} />
                    </div>
                </div>
            </div>

            <DebateDrawer debate={debateDrawer} onClose={() => setDebateDrawer(null)} />
        </div>
    )
}
