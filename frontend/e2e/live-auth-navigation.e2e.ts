/**
 * Tier A3 / A4 — Live authentication and navigation tests  @live
 *
 * Verifies that after the 0.2.5 upgrade:
 * - Admin login succeeds
 * - All main routes load without 5xx / white-screen
 * - GET /v1/config returns a valid LLM provider
 * - Settings page still renders the provider preset dropdown
 *
 * Run with:  npx playwright test --project live
 */

import { test, expect, type Page } from '@playwright/test'
import { loginAdmin } from './helpers/live-auth'
import { TIMEOUT } from './helpers/env'

test.describe('A3 Live auth & navigation @live', () => {
    test.beforeEach(async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        if (!adminPass) {
            test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set — skipping live-auth tests')
        }
        await loginAdmin(page)
    })

    test('admin login redirects to /analysis', async ({ page }) => {
        await page.goto('/login')
        // Because loginAdmin injected the token, the app should redirect away from login
        await page.goto('/login')
        // If already authenticated, the app should redirect to /analysis
        await expect(page).toHaveURL(/\/(analysis|dashboard|\/)/, { timeout: TIMEOUT.PAGE_NAVIGATE })
    })

    test('/analysis loads without 5xx or white-screen', async ({ page }) => {
        await page.goto('/analysis', { waitUntil: 'domcontentloaded' })
        await expect(page).toHaveURL(/\/analysis/, { timeout: TIMEOUT.PAGE_NAVIGATE })
        // No server error banner
        await expect(page.getByText(/500|服务器内部错误|Internal Server Error/i)).toHaveCount(0)
        // Page has some meaningful content
        const body = await page.locator('body').textContent()
        expect(body?.length).toBeGreaterThan(50)
    })

    test('/analysis/fast loads without error', async ({ page }) => {
        await page.goto('/analysis/fast', { waitUntil: 'domcontentloaded' })
        await expect(page).toHaveURL(/\/analysis\/fast/, { timeout: TIMEOUT.PAGE_NAVIGATE })
        await expect(page.getByText(/500|Internal Server Error/i)).toHaveCount(0)
    })

    test('/reports loads without error', async ({ page }) => {
        await page.goto('/reports', { waitUntil: 'domcontentloaded' })
        await expect(page).toHaveURL(/\/reports/, { timeout: TIMEOUT.PAGE_NAVIGATE })
        await expect(page.getByText(/500|Internal Server Error/i)).toHaveCount(0)
    })

    test('/chart (K线分析) loads without error', async ({ page }) => {
        await page.goto('/chart', { waitUntil: 'domcontentloaded' })
        await expect(page).toHaveURL(/\/chart/, { timeout: TIMEOUT.PAGE_NAVIGATE })
        await expect(page.getByText(/500|Internal Server Error/i)).toHaveCount(0)
    })

    test('/settings loads without error', async ({ page }) => {
        await page.goto('/settings', { waitUntil: 'domcontentloaded' })
        await expect(page).toHaveURL(/\/settings/, { timeout: TIMEOUT.PAGE_NAVIGATE })
        await expect(page.getByText(/500|Internal Server Error/i)).toHaveCount(0)
    })
})

test.describe('A4 Live config read-only @live', () => {
    test.beforeEach(async ({ page }) => {
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        if (!adminPass) {
            test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set')
        }
        await loginAdmin(page)
    })

    test('GET /v1/config returns valid provider and model fields', async ({ page }) => {
        await loginAdmin(page)
        const token = await page.evaluate(() => localStorage.getItem('ta-access-token') || '')
        // Use page.request to inherit the base URL
        const res = await page.request.get('/v1/config', {
            headers: { Authorization: `Bearer ${token}` },
        })
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(typeof body.llm_provider).toBe('string')
        expect(body.llm_provider.length).toBeGreaterThan(0)
        expect(typeof body.deep_think_llm).toBe('string')
        expect(typeof body.quick_think_llm).toBe('string')
    })

    test('Settings page renders model-provider section without crashing', async ({ page }) => {
        await page.goto('/settings', { waitUntil: 'networkidle', timeout: TIMEOUT.PAGE_NAVIGATE })
        // The settings page has a provider preset dropdown (硬编码 presets)
        await expect(page.getByText(/模型厂商|LLM 提供商|Provider|openai/i).first()).toBeVisible({
            timeout: 15_000,
        })
        // No JS error indicators
        await expect(page.getByText(/Uncaught TypeError|ChunkLoadError/i)).toHaveCount(0)
    })
})
