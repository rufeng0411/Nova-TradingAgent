import { useEffect, useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { api } from '@/services/api'
import type { TrackingBoardResponse } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'

export default function MobileTrackingBoard() {
    const [board, setBoard] = useState<TrackingBoardResponse | null>(null)
    const [loading, setLoading] = useState(true)

    const loadData = () => {
        setLoading(true)
        api.getDashboardTrackingBoard().then(res => {
            setBoard(res)
            setLoading(false)
        }).catch(() => setLoading(false))
    }

    useEffect(() => {
        loadData()
    }, [])

    return (
        <div className="flex flex-col gap-4 p-4 min-h-[100dvh] bg-slate-50 dark:bg-slate-950">
            <div className="flex justify-between items-center mb-2">
                <div>
                    <h1 className="text-xl font-bold text-slate-900 dark:text-slate-100">跟踪看板</h1>
                    <p className="text-sm text-slate-500 dark:text-slate-400 mt-1">
                        最新交易日 {board?.previous_trade_date || '--'}
                    </p>
                </div>
                <button onClick={loadData} className="p-2 rounded-full bg-white dark:bg-slate-800 text-blue-600 dark:text-blue-400 active:scale-95 shadow-sm">
                    <RefreshCw className={`w-4 h-4 ${loading ? 'animate-spin' : ''}`} />
                </button>
            </div>

            {loading && !board ? (
                <div className="text-center text-slate-400 py-10">加载中...</div>
            ) : !board || !board.items || board.items.length === 0 ? (
                <div className="text-center text-slate-400 py-10">暂无跟踪标的</div>
            ) : (
                <div className="flex flex-col gap-3">
                    {board.items.map(item => {
                        const isUp = (item.price_change_pct ?? 0) > 0
                        const isDown = (item.price_change_pct ?? 0) < 0
                        const colorClass = isUp ? 'text-red-500' : isDown ? 'text-green-500' : 'text-slate-500'
                        
                        return (
                            <div key={item.symbol} className="bg-white dark:bg-slate-900 rounded-2xl p-4 shadow-sm border border-slate-100 dark:border-slate-800">
                                <div className="flex justify-between items-start mb-2">
                                    <div>
                                        <div className="font-semibold text-slate-900 dark:text-slate-100 text-base">
                                            {stockDisplayLabel({ symbol: item.symbol, name: item.name, display_label: item.display_label })}
                                        </div>
                                    </div>
                                    <div className="text-right">
                                        <div className={`font-bold text-lg ${colorClass}`}>
                                            {item.live_price?.toFixed(2) || '--'}
                                        </div>
                                        <div className={`text-xs font-medium ${colorClass}`}>
                                            {item.price_change_pct ? `${item.price_change_pct > 0 ? '+' : ''}${item.price_change_pct.toFixed(2)}%` : '--'}
                                        </div>
                                    </div>
                                </div>

                                <div className="grid grid-cols-3 gap-2 mt-3 pt-3 border-t border-slate-100 dark:border-slate-800">
                                    <div>
                                        <div className="text-[10px] text-slate-400 uppercase">持仓</div>
                                        <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                            {item.current_position || 0}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-slate-400 uppercase">成本</div>
                                        <div className="text-sm font-medium text-slate-700 dark:text-slate-300">
                                            {item.average_cost ? `¥${item.average_cost.toFixed(2)}` : '--'}
                                        </div>
                                    </div>
                                    <div>
                                        <div className="text-[10px] text-slate-400 uppercase">浮动盈亏</div>
                                        <div className={`text-sm font-medium ${
                                            (item.floating_pnl ?? 0) > 0 ? 'text-red-500' : (item.floating_pnl ?? 0) < 0 ? 'text-green-500' : 'text-slate-700 dark:text-slate-300'
                                        }`}>
                                            {item.floating_pnl ? `${item.floating_pnl > 0 ? '+' : ''}${item.floating_pnl.toFixed(2)}` : '--'}
                                        </div>
                                    </div>
                                </div>
                            </div>
                        )
                    })}
                </div>
            )}
        </div>
    )
}
