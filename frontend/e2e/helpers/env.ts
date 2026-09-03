/**
 * Shared environment constants for E2E tests.
 *
 * API_PORT matches TA_DEV_API_PORT (default 8001) — same as dev-api.mjs.
 * ADMIN_USER / ADMIN_PASSWORD are read from process.env so credentials
 * never appear in source; set them in your shell or CI secrets.
 */

export const API_PORT = process.env.TA_DEV_API_PORT || '8001'
export const API_BASE = `http://127.0.0.1:${API_PORT}`
export const FRONTEND_BASE = 'http://127.0.0.1:4173'

export const ADMIN_USER = process.env.E2E_ADMIN_USER || process.env.TA_ADMIN_USERNAME || 'admin'
export const ADMIN_PASSWORD = process.env.E2E_ADMIN_PASSWORD || process.env.TA_ADMIN_PASSWORD || ''

/** Tags used to grep-filter tests by tier. */
export const TAG = {
    LIVE: '@live',
    UPGRADE: '@upgrade',
    HEAVY: '@heavy',
} as const

/** Timeouts (ms) */
export const TIMEOUT = {
    API_REQUEST: 15_000,
    PAGE_NAVIGATE: 30_000,
    ANALYSIS_FAST: 180_000,
    ANALYSIS_FULL: Number(process.env.E2E_ANALYSIS_TIMEOUT_MS) || 20 * 60_000,
} as const
