import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { ChevronUp, Loader2, Zap } from 'lucide-react'

import FastAnalysisProgress from '@/components/FastAnalysisProgress'
import FastAnalysisResult from '@/components/FastAnalysisResult'
import { FAST_FEATURE_SLOT_COUNT } from '@/utils/fastAnalysisDataSources'
import { api } from '@/services/api'
import type { FastAnalysisDetail, FastRiskProfile } from '@/types'
import { stockDisplayLabel } from '@/utils/stockDisplay'

const DISCLAIMER = '仅供研究参考，不构成投资建议'

export default function FastAnalysis() {
    const [searchParams] = useSearchParams()
    const [symbol, setSymbol] = useState(searchParams.get('symbol') || '600519.SH')
    const [intentHint, setIntentHint] = useState('')
    const [risk, setRisk] = useState<FastRiskProfile['risk_profile']>('balanced')
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)
    const [fastId, setFastId] = useState<string | null>(null)
    const [detail, setDetail] = useState<FastAnalysisDetail | null>(null)
    const [recent, setRecent] = useState<FastAnalysisDetail[]>([])

    useEffect(() => {
        api.getFastRiskProfile().then((p) => setRisk(p.risk_profile)).catch(() => void 0)
        api.getRecentFastAnalyses().then((r) => setRecent(r.items || [])).catch(() => void 0)
    }, [])

    useEffect(() => {
        if (!fastId) return
        let timer: number | null = null
        let cancelled = false
        const poll = async () => {
            if (cancelled) return
            try {
                const d = await api.getFastAnalysis(fastId)
                if (cancelled) return
                setDetail(d)
                if (!['succeeded', 'degraded', 'failed'].includes(d.status)) {
                    timer = window.setTimeout(poll, 700)
                } else {
                    const r = await api.getRecentFastAnalyses(symbol, 20)
                    setRecent(r.items || [])
                }
            } catch (e) {
                if (cancelled) return
                setError(e instanceof Error ? e.message : '获取快速分析进度失败')
                timer = window.setTimeout(poll, 2000)
            }
        }
        void poll()
        return () => {
            cancelled = true
            if (timer) window.clearTimeout(timer)
        }
    }, [fastId, symbol])

    const isRunning = !!detail && !['succeeded', 'degraded', 'failed'].includes(detail.status)
    const verdictReady = !!detail && ['succeeded', 'degraded'].includes(detail.status)
    const detailError = useMemo(() => {
        const snap = (detail?.snapshot_json || {}) as Record<string, unknown>
        const err = typeof snap.error === 'string' ? (snap.error as string) : ''
        const llm = typeof snap.llm_error === 'string' ? (snap.llm_error as string) : ''
        if (err) return err
        if (llm) return `LLM 调用失败：${llm}（已返回降级结论）`
        return ''
    }, [detail])

    const dismissDetail = () => {
        setFastId(null)
        setDetail(null)
        setError(null)
    }

    const openRecent = (id: string) => {
        if (fastId === id) {
            dismissDetail()
            return
        }
        setDetail(null)
        setFastId(id)
    }

    const submit = async () => {
        setLoading(true)
        setError(null)
        try {
            // 风险偏好是增强能力：保存失败不应阻断快速分析主流程
            try {
                await api.setFastRiskProfile({ risk_profile: risk })
            } catch {
                // no-op
            }
            const resp = await api.startFastAnalysis({
                symbol,
                intent_hint: intentHint || undefined,
                risk_profile: risk,
                include_market_context: true,
            })
            setFastId(resp.fast_analysis_id)
            const d = await api.getFastAnalysis(resp.fast_analysis_id)
            setDetail(d)
        } catch (e) {
            setError(e instanceof Error ? e.message : '触发快速分析失败')
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="space-y-4">
            <section className="card space-y-3">
                <div className="flex items-center gap-2">
                    <Zap className="h-5 w-5 text-amber-500" />
                    <h1 className="text-xl font-semibold text-slate-900 dark:text-slate-100">快速分析</h1>
                    <span className="rounded-full bg-amber-50 px-2 py-0.5 text-xs text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                        2 分钟决策辅助
                    </span>
                </div>
                <p className="text-sm text-slate-500 dark:text-slate-400">
                    并行采集 Tushare 快照明细（60 日日K、日线 RT、集合竞价 stk_auction 等）→ 抽取{' '}
                    {FAST_FEATURE_SLOT_COUNT} 个特征槽位 → 单轮 LLM 推断，输出可读结论、分时段策略、仓位建议、可执行性与 K 线摘要。
                </p>
                <div className="grid gap-3 md:grid-cols-3">
                    <input
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                        value={symbol}
                        onChange={(e) => setSymbol(e.target.value.toUpperCase())}
                        placeholder="标的代码，如 600519.SH"
                    />
                    <select
                        aria-label="风险偏好"
                        className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                        value={risk}
                        onChange={(e) => setRisk(e.target.value as FastRiskProfile['risk_profile'])}
                    >
                        <option value="conservative">保守</option>
                        <option value="balanced">平衡</option>
                        <option value="aggressive">激进</option>
                    </select>
                    <button
                        className="btn-primary inline-flex items-center justify-center gap-2"
                        onClick={() => void submit()}
                        disabled={loading || isRunning || !symbol}
                    >
                        {loading || isRunning ? <Loader2 className="h-4 w-4 animate-spin" /> : <Zap className="h-4 w-4" />}
                        {loading ? '提交中…' : isRunning ? '分析进行中…' : '开始快速分析'}
                    </button>
                </div>
                <input
                    className="w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm dark:border-slate-700 dark:bg-slate-900"
                    value={intentHint}
                    onChange={(e) => setIntentHint(e.target.value)}
                    placeholder="可选：例如 早盘 10:30 大单流入是否值得跟进"
                />
                <div className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-2 text-xs text-rose-700 dark:border-rose-900/40 dark:bg-rose-950/20 dark:text-rose-300">
                    {DISCLAIMER}
                </div>
                {error ? <p className="text-sm text-rose-500">{error}</p> : null}
            </section>

            {detail ? <FastAnalysisProgress detail={detail} /> : null}

            {detail ? (
                <div className="flex justify-end">
                    <button
                        type="button"
                        className="btn-secondary inline-flex items-center gap-1.5 px-3 py-1.5 text-sm"
                        onClick={() => dismissDetail()}
                    >
                        <ChevronUp className="h-4 w-4" />
                        收起
                    </button>
                </div>
            ) : null}

            {detail && verdictReady ? (
                <>
                    {detailError ? (
                        <div className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-2 text-xs text-amber-700 dark:border-amber-900/40 dark:bg-amber-950/20 dark:text-amber-300">
                            <span className="font-medium">注意：</span>
                            <span className="ml-1 break-all">{detailError}</span>
                        </div>
                    ) : null}
                    <FastAnalysisResult detail={detail} />
                </>
            ) : null}

            <section className="card">
                <h2 className="mb-3 text-base font-semibold text-slate-900 dark:text-slate-100">最近快速分析</h2>
                {recent.length === 0 ? (
                    <p className="text-sm text-slate-500">暂无记录</p>
                ) : (
                    <div className="space-y-2">
                        {recent.map((r) => (
                            <button
                                key={r.id}
                                type="button"
                                className="w-full rounded-lg border border-slate-200 px-3 py-2 text-left text-sm hover:bg-slate-50 dark:border-slate-700 dark:hover:bg-slate-800/50"
                                onClick={() => openRecent(r.id)}
                            >
                                <div className="flex items-center justify-between gap-2">
                                    <span className="min-w-0 truncate">
                                        {stockDisplayLabel({
                                            symbol: r.symbol,
                                            name: r.symbol_name,
                                        })}{' '}
                                        · {r.trade_date}
                                    </span>
                                    <span className="shrink-0 text-xs text-slate-500">{r.status}</span>
                                </div>
                                {fastId === r.id ? (
                                    <p className="mt-1 text-[11px] text-slate-400">再次点击可收起</p>
                                ) : null}
                            </button>
                        ))}
                    </div>
                )}
            </section>
        </div>
    )
}

