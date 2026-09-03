import { useState } from 'react'
import { CheckCircle2, Circle, Loader2, Play, Search, Activity } from 'lucide-react'
import { useAnalysisStore } from '@/stores/analysisStore'
import BottomSheetDrawer from '@/components/mobile/BottomSheetDrawer'
import ReactMarkdown from 'react-markdown'
import remarkGfm from 'remark-gfm'
import DecisionCard from '@/components/DecisionCard'
import { fetchAshareDisplayName } from '@/lib/enrichSymbolDisplayName'
import { lookupStockName } from '@/utils/stockDisplay'
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

export default function MobileAnalysis() {
    const { 
        agents, 
        isAnalyzing, 
        report, 
        currentSymbol, 
        setCurrentSymbol,
        jobConfidence,
        jobTargetPrice,
        jobStopLoss,
        currentSymbolDisplayName,
        setCurrentSymbolDisplayName
    } = useAnalysisStore()

    const [inputVal, setInputVal] = useState('')
    const [drawerOpen, setDrawerOpen] = useState(false)
    const [selectedAgent, setSelectedAgent] = useState<any>(null)

    const handleAnalyze = () => {
        if (!inputVal.trim()) return
        const s = inputVal.trim().toUpperCase()
        setCurrentSymbol(s)
        const name = lookupStockName(s)
        if (name) {
            setCurrentSymbolDisplayName(name)
        } else {
            fetchAshareDisplayName(s).then(n => {
                if (n) setCurrentSymbolDisplayName(n)
            })
        }
        alert('移动端精简模式，请使用桌面端发起深度分析')
        // useAnalysisStore.getState().startAnalysis()
        setInputVal('')
    }

    const openAgentDetail = (agent: any) => {
        if (!agent.output) return
        setSelectedAgent(agent)
        setDrawerOpen(true)
    }

    const isDone = agents.length > 0 && !isAnalyzing && agents.every(a => a.status === 'completed')

    return (
        <div className="flex flex-col h-full bg-slate-50 dark:bg-slate-950">
            {/* 悬浮搜索栏 */}
            <div className="sticky top-14 z-30 bg-slate-50/90 dark:bg-slate-950/90 backdrop-blur-md px-4 py-3 border-b border-slate-200 dark:border-slate-800">
                <div className="relative flex items-center">
                    <Search className="absolute left-3 w-4 h-4 text-slate-400" />
                    <input 
                        type="text" 
                        value={inputVal}
                        onChange={e => setInputVal(e.target.value)}
                        placeholder="输入股票代码 (如 000001.SH)"
                        className="w-full bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded-full py-2 pl-9 pr-12 text-sm focus:outline-none focus:border-blue-500"
                        onKeyDown={e => e.key === 'Enter' && handleAnalyze()}
                    />
                    <button 
                        onClick={handleAnalyze}
                        disabled={isAnalyzing || !inputVal.trim()}
                        className="absolute right-1 w-8 h-8 flex items-center justify-center bg-blue-600 text-white rounded-full disabled:opacity-50 active:scale-95 transition-transform"
                    >
                        {isAnalyzing ? <Loader2 className="w-4 h-4 animate-spin" /> : <Play className="w-4 h-4 ml-0.5" />}
                    </button>
                </div>
            </div>

            <div className="flex-1 overflow-y-auto px-4 py-6">
                {agents.length === 0 && !isAnalyzing ? (
                    <div className="flex flex-col items-center justify-center h-48 text-slate-400">
                        <Activity className="w-12 h-12 mb-3 opacity-20" />
                        <p>输入代码，开始多 Agent 智能分析</p>
                    </div>
                ) : (
                    <div className="relative">
                        {/* 纵向时间轴连线 */}
                        <div className="absolute left-[19px] top-4 bottom-4 w-px bg-slate-200 dark:bg-slate-800" />
                        
                        <div className="flex flex-col gap-6 relative z-10">
                            {agents.map((agent) => {
                                const isCompleted = agent.status === 'completed'
                                const isRunning = agent.status === 'in_progress'
                                
                                return (
                                    <div 
                                        key={agent.id} 
                                        className="flex items-start gap-4"
                                        onClick={() => openAgentDetail(agent)}
                                    >
                                        <div className="w-10 h-10 shrink-0 flex items-center justify-center bg-slate-50 dark:bg-slate-950 relative">
                                            {isCompleted ? (
                                                <CheckCircle2 className="w-6 h-6 text-emerald-500" />
                                            ) : isRunning ? (
                                                <div className="relative flex items-center justify-center w-6 h-6">
                                                    <div className="absolute w-full h-full border-2 border-blue-500 rounded-full opacity-20 animate-ping" />
                                                    <div className="w-3 h-3 bg-blue-500 rounded-full" />
                                                </div>
                                            ) : (
                                                <Circle className="w-4 h-4 text-slate-300 dark:text-slate-600" />
                                            )}
                                        </div>
                                        
                                        <div className={`flex-1 rounded-2xl p-4 transition-all duration-300 ${
                                            isRunning 
                                                ? 'bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 shadow-sm' 
                                                : isCompleted
                                                    ? 'bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-800 active:scale-[0.98]'
                                                    : 'opacity-50'
                                        }`}>
                                            <div className="font-semibold text-slate-900 dark:text-slate-100 text-sm">{agent.name}</div>
                                            <div className="text-xs text-slate-500 dark:text-slate-400 mt-1">{agent.description}</div>
                                            {isCompleted && (
                                                <div className="mt-2 text-[10px] text-blue-600 dark:text-blue-400 font-medium">点击查看报告</div>
                                            )}
                                            {isRunning && (
                                                <div className="mt-2 text-xs text-blue-600 dark:text-blue-400 flex items-center gap-1">
                                                    <Loader2 className="w-3 h-3 animate-spin" /> 分析中...
                                                </div>
                                            )}
                                        </div>
                                    </div>
                                )
                            })}
                        </div>

                        {isDone && report && (
                            <div className="mt-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
                                <h3 className="font-bold text-slate-900 dark:text-slate-100 mb-3 px-1 text-lg">综合决策</h3>
                                <DecisionCard
                                    symbol={currentSymbol || ''}
                                    name={currentSymbolDisplayName ?? report?.instrument_context?.security_name}
                                    report={report}
                                    decision={mapDecision(report?.decision)}
                                    direction={report?.direction}
                                    confidence={jobConfidence ?? undefined}
                                    targetPrice={jobTargetPrice ?? undefined}
                                    stopLoss={jobStopLoss ?? undefined}
                                    reasoning={
                                        (report.final_decision_summary && report.final_decision_summary.trim()) ||
                                        excerptForDecisionCard(report.final_trade_decision, 420)
                                    }
                                    reasoningFull={report.final_trade_decision ?? undefined}
                                />
                            </div>
                        )}
                    </div>
                )}
            </div>

            <BottomSheetDrawer 
                isOpen={drawerOpen} 
                onClose={() => setDrawerOpen(false)}
                title={selectedAgent?.name}
                heightClass="h-[85vh]"
            >
                {selectedAgent?.output ? (
                    <div className="prose prose-sm dark:prose-invert max-w-none prose-p:leading-relaxed prose-headings:font-bold">
                        <ReactMarkdown remarkPlugins={[remarkGfm]}>
                            {selectedAgent.output}
                        </ReactMarkdown>
                    </div>
                ) : (
                    <div className="text-center text-slate-500 py-10">无输出内容</div>
                )}
            </BottomSheetDrawer>
        </div>
    )
}
