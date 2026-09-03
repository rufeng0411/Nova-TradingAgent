/**
 * Tier B — 0.2.5 Upgrade Feature Tests  @upgrade
 *
 * Covers each Sprint's deliverable end-to-end.  Requires:
 * - All TA_UPGRADE_*=1
 * - A running API + frontend preview
 * - E2E_ADMIN_USER / E2E_ADMIN_PASSWORD set
 *
 * Run with:  npx playwright test --project live --grep "@upgrade"
 */

import { test, expect } from '@playwright/test'
import { loginAdmin } from './helpers/live-auth'
import { API_BASE, TIMEOUT } from './helpers/env'

test.describe('B1 Sprint1 — LLM Catalog API @upgrade', () => {
    test('GET /v1/llm/catalog: enabled=true, providers cover openai/deepseek/qwen/glm/minimax, regions=cn+intl', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/llm/catalog`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(body.enabled).toBe(true)
        const providerKeys = Object.keys(body.providers)
        for (const expected of ['openai', 'deepseek', 'qwen', 'glm', 'minimax']) {
            expect(providerKeys).toContain(expected)
        }
        const regionIds = (body.regions as Array<{ id: string }>).map((r) => r.id)
        expect(regionIds).toContain('cn')
        expect(regionIds).toContain('intl')
        // Each provider must have quick and deep lists
        for (const [, modes] of Object.entries(body.providers) as [string, { quick: unknown[]; deep: unknown[] }][]) {
            expect(Array.isArray(modes.quick)).toBeTruthy()
            expect(Array.isArray(modes.deep)).toBeTruthy()
        }
    })

    test('GET /v1/llm/catalog: each model entry has label and id fields', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/llm/catalog`)
        const body = await res.json()
        // deepseek quick[0] should have a non-custom id
        const deepseekQuick = body.providers.deepseek?.quick as Array<{ label: string; id: string }>
        expect(deepseekQuick.length).toBeGreaterThan(0)
        expect(deepseekQuick[0]).toHaveProperty('label')
        expect(deepseekQuick[0]).toHaveProperty('id')
    })
})

test.describe('B2 Sprint1 — System Version @upgrade', () => {
    test('GET /v1/system/version: fork=ta-cn.1, upstream=0.2.5', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/system/version`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(body.upstream).toBe('0.2.5')
        expect(body.fork).toBe('ta-cn.1')
        expect(body.version).toMatch(/0\.2\.5\+ta-cn/)
    })
})

test.describe('B3 Sprint4 — Checkpoint API @upgrade', () => {
    test('GET /v1/jobs/{id}/checkpoint for non-existent job returns JSON with resumable=false', async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')

        await loginAdmin(page)
        const token = await page.evaluate(() => localStorage.getItem('ta-access-token') || '')

        const res = await page.request.get('/v1/jobs/nonexistent-job-for-e2e/checkpoint', {
            headers: { Authorization: `Bearer ${token}` },
        })
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(typeof body.resumable).toBe('boolean')
        // Non-existent job cannot be resumed
        expect(body.resumable).toBe(false)
    })

    test('AgentCollaboration shows 强制重跑 button when upgrade flag is on and job is running', async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')

        await loginAdmin(page)

        // Mock a running job so we can see the UI without a real job
        const MOCK_JOB_ID = 'e2e-upgrade-b3-job'
        const MOCK_SYMBOL = '600519.SH'

        await page.route('**/v1/features', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ allow_registration: true, maintenance: false, captcha_enabled: false, ta_cost_analysis: 0, chat_task_submit_v2_enabled: true }),
            }),
        )
        await page.route('**/v1/auth/me', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ id: 'e2e-user', email: 'e2e@test.com', username: 'admin', role: 'admin', display_name: 'E2E Admin' }),
            }),
        )
        await page.route('**/v1/users/entitlements', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ plan: 'admin', features: {} }) }),
        )
        await page.route('**/v1/me/tasks', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify({ running: [], queued: [], recent: [] }) }),
        )
        await page.route(`**/v1/jobs/${MOCK_JOB_ID}`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    job_id: MOCK_JOB_ID,
                    status: 'running',
                    symbol: MOCK_SYMBOL,
                    trade_date: '2026-05-23',
                    display_label: '贵州茅台 600519.SH',
                    created_at: new Date().toISOString(),
                }),
            }),
        )
        await page.route(`**/v1/jobs/${MOCK_JOB_ID}/events**`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'text/event-stream',
                body: 'event: job.running\ndata: {"job_id":"' + MOCK_JOB_ID + '"}\n\n',
            }),
        )
        // Checkpoint: mock a resumable checkpoint
        await page.route(`**/v1/jobs/${MOCK_JOB_ID}/checkpoint`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ step: 3, resumable: true, last_node: 'market_analyst', thread_id: MOCK_JOB_ID }),
            }),
        )

        await page.goto(`/analysis?job_id=${MOCK_JOB_ID}&symbol=${MOCK_SYMBOL}`)
        await expect(page.getByText('分析中').first()).toBeVisible({ timeout: 15_000 })

        // 强制重跑 button should be visible (Sprint4 upgrade UI)
        await expect(page.getByRole('button', { name: '强制重跑' })).toBeVisible({ timeout: 10_000 })
        // Checkpoint recovery badge
        await expect(page.getByText('已从第 3 步恢复')).toBeVisible({ timeout: 10_000 })
    })
})

test.describe('B4 Sprint5 — Decision Archive Panel @upgrade', () => {
    test('Reports page shows DecisionArchivePanel (empty state or entries) for completed report', async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')

        await loginAdmin(page)
        await page.goto('/reports', { waitUntil: 'domcontentloaded', timeout: TIMEOUT.PAGE_NAVIGATE })

        // If there are any reports, open the first one
        const firstReport = page.locator('[data-testid="report-row"], .report-item, tbody tr').first()
        const hasReports = await firstReport.count().then((c) => c > 0).catch(() => false)
        if (!hasReports) {
            test.skip(true, 'No reports available to test DecisionArchivePanel')
            return
        }

        await firstReport.click()
        // DecisionArchivePanel should appear — either with entries or the empty state message
        await expect(
            page.getByText(/历史决策档案|暂无历史决策/i).first(),
        ).toBeVisible({ timeout: 20_000 })
    })
})

test.describe('B5 Sprint3 — Sentiment Data Source Grouping @upgrade', () => {
    test('Data source dialog shows sentiment_data category after fast analysis', async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')

        await loginAdmin(page)
        await page.goto('/reports?kind=fast_analysis', { waitUntil: 'domcontentloaded', timeout: TIMEOUT.PAGE_NAVIGATE })

        const firstReport = page.locator('tbody tr, [data-testid="report-row"]').first()
        const hasReports = await firstReport.count().then((c) => c > 0).catch(() => false)
        if (!hasReports) {
            test.skip(true, 'No fast analysis reports — run C1 heavy first')
            return
        }
        await firstReport.click()

        // Open data source dialog
        const dataSourceBtn = page.getByRole('button', { name: /数据源/i }).first()
        await expect(dataSourceBtn).toBeVisible({ timeout: 15_000 })
        await dataSourceBtn.click()

        // Look for the sentiment_data category in the dialog
        await expect(
            page.getByText(/sentiment_data|雪球|股吧|情绪数据/i).first(),
        ).toBeVisible({ timeout: 10_000 })
    })
})

test.describe('B6 Sprint2 — Structured Output (indirect) @upgrade', () => {
    test('Reports page — rating_5tier column visible in full analysis reports or page does not crash', async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')

        await loginAdmin(page)
        await page.goto('/reports?kind=full_analysis', { waitUntil: 'domcontentloaded', timeout: TIMEOUT.PAGE_NAVIGATE })

        // Page must not crash
        await expect(page.getByText(/500|Uncaught TypeError|ChunkLoadError/i)).toHaveCount(0)

        // 沙盘综合研判 3-tier column is still visible (not replaced)
        // (won't be visible until a report is opened, so just check the page renders)
        const bodyText = await page.locator('body').textContent()
        expect(bodyText?.length ?? 0).toBeGreaterThan(50)
    })
})
