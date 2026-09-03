/**
 * Tier A2 — Live API Smoke Tests  @live
 *
 * Validates that after the 0.2.5 upgrade the core API endpoints are
 * healthy and return the expected shapes.  These tests talk directly to
 * the FastAPI backend (no frontend page load required).
 *
 * Run with:  npx playwright test --project live
 */

import { test, expect } from '@playwright/test'
import { API_BASE } from './helpers/env'

test.describe('A2 Live API smoke @live', () => {
    test('GET /healthz returns status=ok', async ({ request }) => {
        const res = await request.get(`${API_BASE}/healthz`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(body.status).toBe('ok')
    })

    test('GET /v1/system/version returns upstream=0.2.5 and fork contains ta-cn', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/system/version`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(body.upstream).toBe('0.2.5')
        expect(typeof body.fork).toBe('string')
        expect(body.fork).toMatch(/ta-cn/)
        expect(typeof body.version).toBe('string')
        expect(body.version).toMatch(/0\.2\.5/)
    })

    test('GET /v1/features returns 200 with expected shape', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/features`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        // maintenance flag must be a boolean
        expect(typeof body.maintenance).toBe('boolean')
    })

    test('GET /v1/llm/catalog — baseline: returns enabled=false; upgrade: returns enabled=true with providers', async ({ request }) => {
        const res = await request.get(`${API_BASE}/v1/llm/catalog`)
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        const isUpgrade = process.env.TA_UPGRADE_LLM_CATALOG === '1'
        if (isUpgrade) {
            expect(body.enabled).toBe(true)
            expect(typeof body.providers).toBe('object')
            expect(Object.keys(body.providers).length).toBeGreaterThan(3)
            expect(body.providers).toHaveProperty('openai')
            expect(body.providers).toHaveProperty('deepseek')
            expect(body.providers).toHaveProperty('qwen')
            expect(Array.isArray(body.regions)).toBeTruthy()
            const regionIds = body.regions.map((r: { id: string }) => r.id)
            expect(regionIds).toContain('cn')
            expect(regionIds).toContain('intl')
        } else {
            // baseline: catalog is disabled
            expect(body.enabled).toBe(false)
        }
    })

    test('GET /v1/jobs/nonexistent/checkpoint — baseline: returns skipped; upgrade: returns JSON shape', async ({ request }) => {
        const isUpgrade = process.env.TA_UPGRADE_CHECKPOINT_UI === '1'
        const fakeId = 'smoke-test-nonexistent-job-id'
        // Need auth for this endpoint — skip if no admin password configured
        const adminUser = process.env.E2E_ADMIN_USER || process.env.TA_ADMIN_USERNAME || 'admin'
        const adminPass = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''
        if (!adminPass) {
            test.skip(!adminPass, 'E2E_ADMIN_PASSWORD not set — skipping checkpoint auth test')
            return
        }

        const loginRes = await request.post(`${API_BASE}/v1/auth/login`, {
            data: { identifier: adminUser, password: adminPass },
        })
        expect(loginRes.ok()).toBeTruthy()
        const { access_token } = await loginRes.json()

        const res = await request.get(`${API_BASE}/v1/jobs/${fakeId}/checkpoint`, {
            headers: { Authorization: `Bearer ${access_token}` },
        })
        expect(res.ok()).toBeTruthy()
        const body = await res.json()
        expect(typeof body.resumable).toBe('boolean')
        if (!isUpgrade) {
            // baseline: checkpoint UI disabled → skipped=true
            expect(body.skipped).toBe(true)
        }
    })
})
