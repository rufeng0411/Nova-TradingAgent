/**
 * Live authentication helper for E2E tests.
 *
 * Performs a real POST /v1/auth/login and injects the resulting JWT +
 * user object into localStorage so Playwright tests start as authenticated.
 *
 * Usage:
 *   import { loginAdmin } from './helpers/live-auth'
 *   await loginAdmin(page)
 */

import { type Page, type BrowserContext } from '@playwright/test'
import { API_BASE, ADMIN_USER, ADMIN_PASSWORD } from './env'

export interface LoginResult {
    access_token: string
    user: {
        id: string
        email: string
        username: string
        role: string
        display_name: string
    }
}

/** POST /v1/auth/login with admin credentials; returns raw response body. */
export async function apiLogin(identifier = ADMIN_USER, password = ADMIN_PASSWORD): Promise<LoginResult> {
    const res = await fetch(`${API_BASE}/v1/auth/login`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ identifier, password }),
    })
    if (!res.ok) {
        const text = await res.text()
        throw new Error(`Login failed (${res.status}): ${text}`)
    }
    return res.json() as Promise<LoginResult>
}

/**
 * Inject auth state into localStorage before page navigation.
 * Call this BEFORE page.goto() so the app boots as logged-in.
 */
export async function loginAdmin(page: Page, identifier?: string, password?: string): Promise<LoginResult> {
    const result = await apiLogin(identifier, password)
    await page.addInitScript(
        ({ token, user }: { token: string; user: LoginResult['user'] }) => {
            localStorage.setItem('ta-access-token', token)
            localStorage.setItem('ta-user', JSON.stringify(user))
        },
        { token: result.access_token, user: result.user },
    )
    return result
}

/**
 * Inject auth state into a BrowserContext's storage state so ALL pages
 * in that context start as logged-in (useful with storageState fixture).
 */
export async function injectAuthToContext(context: BrowserContext, identifier?: string, password?: string): Promise<LoginResult> {
    const result = await apiLogin(identifier, password)
    await context.addInitScript(
        ({ token, user }: { token: string; user: LoginResult['user'] }) => {
            localStorage.setItem('ta-access-token', token)
            localStorage.setItem('ta-user', JSON.stringify(user))
        },
        { token: result.access_token, user: result.user },
    )
    return result
}
