import { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Activity, FileText, CheckCircle, ArrowRight } from 'lucide-react'
import { api } from '@/services/api'
import { useAnalysisStore } from '@/stores/analysisStore'
import { useAuthStore } from '@/stores/authStore'
import type { Report, TrackingBoardResponse } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'

export default function MobileDashboard() {
    const { agents, isAnalyzing } = useAnalysisStore()
    const { user } = useAuthStore()
    const [recentReports, setRecentReports] = useState<Report[]>([])
    const [trackingBoard, setTrackingBoard] = useState<TrackingBoardResponse | null>(null)
    const navigate = useNavigate()

    useEffect(() => {
        if (!user?.id) return
        api.getReports(undefined, 0, 5).then(res => setRecentReports(res.reports)).catch(() => {})
        api.getDashboardTrackingBoard().then(res => setTrackingBoard(res)).catch(() => {})
    }, [user?.id])

    return (
        <div className="flex flex-col gap-4 p-4">
            <div className="mb-2">
                <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">控制台</h1>
                <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                    {user?.email ? user.email : '欢迎使用 Nova-TradingAgent'}
                </p>
            </div>

            <div className="grid grid-cols-2 gap-3">
                <div className="rounded-2xl bg-blue-50 dark:bg-blue-900/20 p-4 border border-blue-100 dark:border-blue-800/30">
                    <Activity className="w-5 h-5 text-blue-600 dark:text-blue-400 mb-2" />
                    <div className="text-sm text-slate-600 dark:text-slate-400">Agent 状态</div>
                    <div className="text-lg font-bold text-slate-900 dark:text-slate-100">{agents.filter(a => a.status === 'in_progress').length} 进行中</div>
                </div>
                <div className="rounded-2xl bg-green-50 dark:bg-green-900/20 p-4 border border-green-100 dark:border-green-800/30">
                    <CheckCircle className="w-5 h-5 text-green-600 dark:text-green-400 mb-2" />
                    <div className="text-sm text-slate-600 dark:text-slate-400">分析任务</div>
                    <div className="text-lg font-bold text-slate-900 dark:text-slate-100">{isAnalyzing ? '分析中' : '空闲'}</div>
                </div>
            </div>

            <div className="card mt-2">
                <div className="flex justify-between items-center mb-3">
                    <h2 className="font-semibold text-slate-900 dark:text-slate-100">跟踪摘要</h2>
                    <button onClick={() => navigate('/m/tracking-board')} className="text-xs text-blue-600 dark:text-blue-400 flex items-center">
                        完整看板 <ArrowRight className="w-3 h-3 ml-1" />
                    </button>
                </div>
                <div className="flex overflow-x-auto snap-x gap-3 pb-2 -mx-2 px-2 hide-scrollbar">
                    <div className="snap-center shrink-0 w-40 rounded-xl bg-slate-50 dark:bg-slate-800/50 p-3 border border-slate-100 dark:border-slate-800">
                        <div className="text-xs text-slate-400">跟踪标的</div>
                        <div className="text-xl font-semibold mt-1">{trackingBoard?.items?.length ?? 0}</div>
                    </div>
                    <div className="snap-center shrink-0 w-40 rounded-xl bg-slate-50 dark:bg-slate-800/50 p-3 border border-slate-100 dark:border-slate-800">
                        <div className="text-xs text-slate-400">价格覆盖</div>
                        <div className="text-xl font-semibold mt-1">
                            {trackingBoard?.items?.length ? `${trackingBoard.items.filter(i => i.quote_source).length}/${trackingBoard.items.length}` : '--'}
                        </div>
                    </div>
                </div>
            </div>

            <div className="card">
                <div className="flex justify-between items-center mb-3">
                    <h2 className="font-semibold text-slate-900 dark:text-slate-100">最近分析</h2>
                    {recentReports.length > 0 && (
                        <button onClick={() => navigate('/m/reports')} className="text-xs text-blue-600 dark:text-blue-400 flex items-center">
                            全部 <ArrowRight className="w-3 h-3 ml-1" />
                        </button>
                    )}
                </div>
                <div className="flex flex-col gap-3">
                    {recentReports.length === 0 ? (
                        <div className="text-center text-sm text-slate-400 py-4">暂无分析记录</div>
                    ) : (
                        recentReports.map(report => {
                            const decisionColor = report.decision?.toUpperCase().includes('BUY') || report.decision?.includes('增持')
                                ? 'text-red-600 dark:text-red-400'
                                : report.decision?.toUpperCase().includes('SELL') || report.decision?.includes('减持')
                                    ? 'text-green-600 dark:text-green-400'
                                    : 'text-slate-500 dark:text-slate-400'
                            
                            return (
                                <div 
                                    key={report.id} 
                                    onClick={() => navigate(`/m/reports?report=${report.id}`)}
                                    className="flex items-center gap-3 p-3 rounded-xl bg-slate-50 dark:bg-slate-800/30 active:scale-95 transition-transform"
                                >
                                    <div className="w-10 h-10 rounded-full bg-blue-100 dark:bg-blue-900/30 flex items-center justify-center shrink-0">
                                        <FileText className="w-5 h-5 text-blue-600 dark:text-blue-400" />
                                    </div>
                                    <div className="flex-1 min-w-0">
                                        <div className="font-semibold text-sm text-slate-900 dark:text-slate-100 truncate">
                                            {stockDisplayLabel({ symbol: report.symbol, name: report.name, display_label: report.display_label })}
                                        </div>
                                        <div className="text-xs text-slate-400 mt-0.5">{report.trade_date}</div>
                                    </div>
                                    <div className={`text-sm font-bold ${decisionColor}`}>
                                        {report.decision || '-'}
                                    </div>
                                </div>
                            )
                        })
                    )}
                </div>
            </div>
            
            {/* 底部占位确保可以滚动 */}
            <div className="h-6" />
        </div>
    )
}
