import path from 'node:path'
import { fileURLToPath } from 'node:url'

import { defineConfig, devices } from '@playwright/test'

const __dirname = path.dirname(fileURLToPath(import.meta.url))
const repoRoot = path.resolve(__dirname, '..')

// ── Ports ─────────────────────────────────────────────────────────────────
// TA_DEV_API_PORT defaults to 8001 — same as dev-api.mjs and vite.config.ts proxy.
const apiPort = process.env.TA_DEV_API_PORT || '8001'

// ── Web-server definitions ─────────────────────────────────────────────────
const previewWebServer = {
    command: 'npm run build && npx vite preview --host 127.0.0.1 --port 4173',
    url: 'http://127.0.0.1:4173',
    reuseExistingServer: !process.env.CI,
    timeout: 120_000,
}

/**
 * With `E2E_START_API=1`: Playwright spins up the FastAPI backend before the
 * frontend preview.  Port is driven by TA_DEV_API_PORT (default 8001).
 */
const apiWebServer =
    process.env.E2E_START_API === '1'
        ? {
              command: `uv run python -m uvicorn api.main:app --host 127.0.0.1 --port ${apiPort}`,
              url: `http://127.0.0.1:${apiPort}/healthz`,
              cwd: repoRoot,
              reuseExistingServer: !process.env.CI,
              timeout: 180_000,
          }
        : null

const webServer = apiWebServer ? [apiWebServer, previewWebServer] : previewWebServer

// ── Config ─────────────────────────────────────────────────────────────────
export default defineConfig({
    testDir: './e2e',
    testMatch: '**/*.e2e.ts',
    forbidOnly: !!process.env.CI,
    retries: process.env.CI ? 1 : 0,

    // Default reporter: list for CI-friendly output; HTML for local inspection
    reporter: process.env.CI ? 'list' : [['list'], ['html', { open: 'never' }]],

    use: {
        baseURL: 'http://127.0.0.1:4173',
        trace: 'on-first-retry',
        screenshot: 'only-on-failure',
        video: 'off',
    },

    webServer,

    projects: [
        /**
         * mock — Existing 6 e2e files that use page.route() mocks.
         * Fast, fully parallel, no real API needed.
         * Excludes @live, @upgrade, @heavy tagged tests.
         */
        {
            name: 'mock',
            testMatch: [
                '**/analysis-job-recovery.e2e.ts',
                '**/api-proxy-health.e2e.ts',
                '**/auth-public-routes.e2e.ts',
                '**/workflow-style.e2e.ts',
                '**/theme-skin.e2e.ts',
                '**/public-pages.e2e.ts',
            ],
            use: { ...devices['Desktop Chrome'] },
            fullyParallel: true,
        },

        /**
         * live — Tests that require a real API + authentication.
         * Includes @live and @upgrade tagged suites.
         * Runs with a reasonable parallelism but not fully parallel.
         */
        {
            name: 'live',
            testMatch: [
                '**/live-api-smoke.e2e.ts',
                '**/live-auth-navigation.e2e.ts',
                '**/upgrade-0.2.5-live.e2e.ts',
            ],
            use: { ...devices['Desktop Chrome'] },
            fullyParallel: false,
            timeout: 60_000,
        },

        /**
         * heavy — Real LLM + Tushare calls.  Strictly serial to avoid
         * AkShare/Tushare rate-limit contention and task-queue conflicts.
         * Timeout per test: 25 minutes (configurable via E2E_ANALYSIS_TIMEOUT_MS).
         */
        {
            name: 'heavy',
            testMatch: ['**/heavy-analysis-live.e2e.ts'],
            use: { ...devices['Desktop Chrome'] },
            fullyParallel: false,
            workers: 1,
            timeout: Number(process.env.E2E_ANALYSIS_TIMEOUT_MS) || 25 * 60_000,
        },
    ],
})
