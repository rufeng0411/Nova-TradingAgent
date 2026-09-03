import { test, expect } from '@playwright/test'

/**
 * 公开认证页 UI 与路由（不依赖后端在线；API 由 vite preview 代理到 :8000，仅测 DOM）。
 * 全链路登录见根目录联调或设 E2E_WITH_API=1 后扩展。
 */
test.describe('SaaS 公开认证路由', () => {
    test('登录页：标题、用户名/密码、提交与注册/忘记密码', async ({ page }) => {
        await page.goto('/login')
        await expect(page.getByRole('heading', { name: '登录' })).toBeVisible()
        await expect(page.getByRole('link', { name: '注册账号' })).toHaveAttribute('href', '/register')
        await expect(page.getByRole('link', { name: '忘记密码' })).toHaveAttribute('href', '/forgot-password')
        await expect(page.locator('input[autocomplete="username"]')).toBeVisible()
        await expect(page.locator('input[autocomplete="current-password"]')).toBeVisible()
        await expect(page.getByRole('button', { name: '登录' })).toBeVisible()
    })

    test('注册页：标题与返回登录', async ({ page }) => {
        await page.goto('/register')
        await expect(page.getByRole('heading', { name: '注册' })).toBeVisible()
        await expect(page.getByRole('link', { name: '已有账号？登录' })).toHaveAttribute('href', '/login')
    })

    test('忘记密码页：标题与返回登录', async ({ page }) => {
        await page.goto('/forgot-password')
        await expect(page.getByRole('heading', { name: '忘记密码' })).toBeVisible()
        await expect(page.getByRole('link', { name: '返回登录' })).toHaveAttribute('href', '/login')
    })

    test('重置密码页（带 query）：标题与返回登录', async ({ page }) => {
        await page.goto('/reset-password?token=playwright-smoke-token')
        await expect(page.getByRole('heading', { name: '设置新密码' })).toBeVisible()
        await expect(page.getByRole('link', { name: '返回登录' })).toHaveAttribute('href', '/login')
    })

    test('未登录访问受保护路径会跳到登录', async ({ page }) => {
        await page.goto('/analysis')
        await expect(page).toHaveURL(/\/login/)
    })
})
