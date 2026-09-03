import { test, expect } from '@playwright/test'

test.describe('公开静态页', () => {
    test('/sponsor 可访问', async ({ page }) => {
        await page.goto('/sponsor')
        await expect(page.getByRole('heading', { name: /支持 Nova-TradingAgent/i })).toBeVisible()
    })

    test('/thanks 可访问', async ({ page }) => {
        await page.goto('/thanks')
        await expect(page.getByRole('heading', { name: '致谢' })).toBeVisible()
    })

    test('从登录点击「注册账号」进入注册页', async ({ page }) => {
        await page.goto('/login')
        await page.getByRole('link', { name: '注册账号' }).click()
        await expect(page).toHaveURL(/\/register$/)
        await expect(page.getByRole('heading', { name: '注册' })).toBeVisible()
    })
})
