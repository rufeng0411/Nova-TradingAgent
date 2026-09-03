import type { Report, ReportOutcomeDetail, ReportOutcomeSummaryLite } from '@/types'
import type { ChartInsightHistoryItem } from '@/lib/chartInsightHistory'

export type OutcomeStatus = 'hit' | 'neutral' | 'miss' | 'pending'

export const OUTCOME_STATUS_LABEL: Record<OutcomeStatus, string> = {
    hit: '命中',
    neutral: '震荡',
    miss: '偏离',
    pending: '待观察',
}

export const OUTCOME_STATUS_CLASS: Record<OutcomeStatus, string> = {
    hit: 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300',
    neutral: 'bg-amber-100 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300',
    miss: 'bg-rose-100 text-rose-700 dark:bg-rose-900/30 dark:text-rose-300',
    pending: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-300',
}

export function outcomeLiteFromReport(report: Report): ReportOutcomeSummaryLite | null {
    if (!report.outcome_summary) return null
    return report.outcome_summary
}

export function pickOutcomeStatus(v?: string | null): OutcomeStatus {
    if (v === 'hit' || v === 'neutral' || v === 'miss') return v
    return 'pending'
}

export function formatScore(v?: number | null): string {
    if (typeof v !== 'number' || Number.isNaN(v)) return '--'
    return `${Math.round(v)}`
}

function shiftDays(dateStr: string, days: number): string {
    const d = new Date(`${dateStr}T00:00:00`)
    if (Number.isNaN(d.getTime())) return dateStr
    d.setDate(d.getDate() + days)
    return d.toISOString().slice(0, 10)
}

function nextWeekday(dateStr: string, tradingDays: number): string {
    if (tradingDays <= 0) return dateStr
    let cur = dateStr
    let remain = tradingDays
    while (remain > 0) {
        cur = shiftDays(cur, 1)
        const wd = new Date(`${cur}T00:00:00`).getDay()
        if (wd !== 0 && wd !== 6) remain -= 1
    }
    return cur
}

function toDirectionFromBias(bias: string): 'bull' | 'bear' | 'neutral' {
    if (bias === 'bullish') return 'bull'
    if (bias === 'bearish') return 'bear'
    return 'neutral'
}

type FetchKline = (
    symbol: string,
    startDate: string,
    endDate: string,
) => Promise<{ candles: Array<{ date?: string; trade_date?: string; close: number; high?: number; low?: number }> }>

export async function computeKlineOutcomeLocal(
    row: ChartInsightHistoryItem,
    fetchKline: FetchKline,
): Promise<ReportOutcomeDetail | null> {
    const baseDate = row.at.slice(0, 10)
    if (!baseDate) return null
    const endDate = nextWeekday(baseDate, 5)
    const startDate = shiftDays(baseDate, -80)
    const res = await fetchKline(row.symbol, startDate, endDate)
    const candles = Array.isArray(res.candles) ? res.candles : []
    if (candles.length === 0) return null

    const parsed = candles
        .map((c) => {
            const date = String(c.date || c.trade_date || '').slice(0, 10)
            const close = Number(c.close)
            const high = Number(c.high ?? c.close)
            const low = Number(c.low ?? c.close)
            if (!date || Number.isNaN(close)) return null
            return { date, close, high, low }
        })
        .filter((x): x is { date: string; close: number; high: number; low: number } => !!x)
        .sort((a, b) => a.date.localeCompare(b.date))
    if (parsed.length === 0) return null

    const baselineRow = [...parsed].reverse().find((x) => x.date <= baseDate) ?? parsed[parsed.length - 1]
    const baseline = baselineRow.close
    const baselineIdx = parsed.findIndex((x) => x.date === baselineRow.date)
    const trWindow = parsed.slice(Math.max(0, baselineIdx - 20), baselineIdx + 1)
    const trList = trWindow.map((cur, idx) => {
        const prev = trWindow[Math.max(0, idx - 1)]
        return Math.max(cur.high - cur.low, Math.abs(cur.high - prev.close), Math.abs(cur.low - prev.close))
    })
    const atr20 = trList.length ? trList.reduce((a, b) => a + b, 0) / trList.length : baseline * 0.01
    const threshold = atr20 * 0.5
    const direction = toDirectionFromBias(row.insight.bias)

    const horizons = ['t1', 't2', 't5'] as const
    const weights: Record<string, number> = { t1: 0.2, t2: 0.5, t5: 0.3 }
    const outcomes: Record<string, any> = {}
    let settled = 0
    let scoreAcc = 0
    let weightAcc = 0
    for (const h of horizons) {
        const days = Number(h.slice(1))
        const targetDate = nextWeekday(baselineRow.date, days)
        const rowN = parsed.find((x) => x.date === targetDate)
        if (!rowN) {
            outcomes[h] = { horizon: h, target_date: targetDate, status: 'pending' }
            continue
        }
        const delta = rowN.close - baseline
        const deltaPct = baseline ? (delta / baseline) * 100 : null
        const atrMult = atr20 ? delta / atr20 : null
        let status: OutcomeStatus = 'neutral'
        if (direction === 'bull') status = delta >= threshold ? 'hit' : delta <= -threshold ? 'miss' : 'neutral'
        else if (direction === 'bear') status = delta <= -threshold ? 'hit' : delta >= threshold ? 'miss' : 'neutral'
        else status = Math.abs(delta) < threshold ? 'hit' : 'miss'
        const score = status === 'hit' ? 100 : status === 'neutral' ? 50 : 0
        settled += 1
        scoreAcc += score * weights[h]
        weightAcc += weights[h]
        outcomes[h] = { horizon: h, target_date: targetDate, close_price: rowN.close, delta, delta_pct: deltaPct, atr_mult: atrMult, status, score }
    }

    return {
        report_id: row.id,
        task_kind: 'kline',
        release_version: 'local',
        baseline_price: baseline,
        baseline_source: 'kline_close',
        atr20,
        atr_window_end: baselineRow.date,
        weighted_score: weightAcc > 0 ? scoreAcc / weightAcc : null,
        settled_count: settled,
        total_windows: horizons.length,
        primary_horizon: 't2',
        primary_status: outcomes.t2?.status ?? 'pending',
        outcomes,
    }
}
