/**
 * Helpers for waiting on analysis jobs in live E2E tests.
 *
 * Supports both:
 *   - Fast analysis:  POST /v1/analyze/fast  -> poll GET /v1/fast-analyses/{id}
 *   - Full analysis:  poll GET /v1/jobs/{id}
 */

import { type Page, type APIRequestContext } from '@playwright/test'
import { API_BASE, TIMEOUT } from './env'

// ── Types ──────────────────────────────────────────────────────────────────

export interface FastAnalysisStatus {
    fast_analysis_id: string
    job_id: string
    status: string
    result?: Record<string, unknown> | null
    snapshot_json?: Record<string, unknown> | null
    [key: string]: unknown
}

export interface FullJobStatus {
    job_id: string
    status: string
    result?: Record<string, unknown> | null
    [key: string]: unknown
}

// ── Polling utilities ──────────────────────────────────────────────────────

const TERMINAL_STATUSES = new Set(['succeeded', 'degraded', 'failed', 'completed', 'cancelled'])

/** Poll a URL until the returned JSON's `status` is terminal or timeout. */
async function pollStatus<T extends { status: string }>(
    token: string,
    url: string,
    timeoutMs: number,
    intervalMs = 5_000,
): Promise<T> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
        const res = await fetch(url, {
            headers: { Authorization: `Bearer ${token}` },
        })
        if (res.ok) {
            const body = (await res.json()) as T
            if (TERMINAL_STATUSES.has(body.status)) return body
        }
        await new Promise((r) => setTimeout(r, intervalMs))
    }
    throw new Error(`Timed out polling ${url} after ${timeoutMs}ms`)
}

// ── Fast analysis ──────────────────────────────────────────────────────────

export interface SubmitFastOptions {
    symbol: string
    tradeDate?: string
    /** Bearer token; if omitted, reads from page localStorage */
    token?: string
}

/** Submit a fast analysis job and wait for terminal state. */
export async function submitAndWaitFast(
    page: Page,
    options: SubmitFastOptions,
    timeoutMs = TIMEOUT.ANALYSIS_FAST,
): Promise<FastAnalysisStatus> {
    const token = options.token || (await page.evaluate(() => localStorage.getItem('ta-access-token') || ''))
    const tradeDate = options.tradeDate || new Date().toISOString().slice(0, 10)

    const res = await fetch(`${API_BASE}/v1/analyze/fast`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({ symbol: options.symbol, trade_date: tradeDate }),
    })
    if (!res.ok) {
        const text = await res.text()
        throw new Error(`POST /v1/analyze/fast failed (${res.status}): ${text}`)
    }
    const created = (await res.json()) as { fast_analysis_id: string; job_id: string; status: string }
    const pollUrl = `${API_BASE}/v1/fast-analyses/${created.fast_analysis_id}`
    return pollStatus<FastAnalysisStatus>(token, pollUrl, timeoutMs)
}

// ── Full (intelligent) analysis ────────────────────────────────────────────

export interface SubmitFullOptions {
    symbol: string
    tradeDate?: string
    horizon?: 'short' | 'long'
    token?: string
}

/** Submit a full analysis job via chat-submit endpoint and wait for terminal state. */
export async function submitAndWaitFull(
    page: Page,
    options: SubmitFullOptions,
    timeoutMs = TIMEOUT.ANALYSIS_FULL,
): Promise<FullJobStatus> {
    const token = options.token || (await page.evaluate(() => localStorage.getItem('ta-access-token') || ''))
    const tradeDate = options.tradeDate || new Date().toISOString().slice(0, 10)

    const res = await fetch(`${API_BASE}/v1/me/tasks/submit`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` },
        body: JSON.stringify({
            task_kind: 'full_analysis',
            symbol: options.symbol,
            trade_date: tradeDate,
            horizon: options.horizon || 'short',
        }),
    })
    if (!res.ok) {
        const text = await res.text()
        throw new Error(`POST /v1/me/tasks/submit failed (${res.status}): ${text}`)
    }
    const created = (await res.json()) as { job_id: string; status: string }
    const pollUrl = `${API_BASE}/v1/jobs/${created.job_id}`
    return pollStatus<FullJobStatus>(token, pollUrl, timeoutMs, 10_000)
}

// ── Page-level wait helpers ────────────────────────────────────────────────

/**
 * Wait for the FastAnalysisProgress panel to reach a terminal stage label.
 * Typically "结果落库" (finalizing) or shows a VERDICT card.
 */
export async function waitForFastAnalysisTerminal(page: Page, timeoutMs = TIMEOUT.ANALYSIS_FAST): Promise<void> {
    await page.waitForFunction(
        () => {
            const text = document.body.innerText
            return (
                text.includes('看多') ||
                text.includes('看空') ||
                text.includes('中性') ||
                text.includes('VERDICT') ||
                text.includes('分析失败') ||
                text.includes('分析结论')
            )
        },
        { timeout: timeoutMs },
    )
}

/**
 * Wait for full analysis workflow to show ≥50% progress or reach terminal state.
 */
export async function waitForFullAnalysisProgress(page: Page, timeoutMs = TIMEOUT.ANALYSIS_FULL): Promise<void> {
    await page.waitForFunction(
        () => {
            const pct = document.body.innerText.match(/(\d+)%/)
            if (pct && parseInt(pct[1]) >= 50) return true
            const text = document.body.innerText
            return (
                text.includes('分析完成') ||
                text.includes('沙盘综合研判') ||
                text.includes('最终交易决策') ||
                text.includes('分析失败')
            )
        },
        { timeout: timeoutMs },
    )
}
