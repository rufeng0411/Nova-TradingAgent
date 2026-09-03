import { test, expect } from '@playwright/test'

test.describe('data-skin 与皮肤存储', () => {
    test('默认登录页 data-skin 为 default', async ({ page }) => {
        await page.goto('/login')
        await expect(page.locator('html')).toHaveAttribute('data-skin', 'default')
    })

    test('localStorage ta-skin=linear 刷新后 html 带 linear', async ({ page }) => {
        await page.goto('/login')
        await page.evaluate(() => {
            localStorage.setItem('ta-skin', 'linear')
        })
        await page.reload()
        await expect(page.locator('html')).toHaveAttribute('data-skin', 'linear')
    })

    test('localStorage ta-skin=graphite 刷新后 html 带 graphite', async ({ page }) => {
        await page.goto('/login')
        await page.evaluate(() => {
            localStorage.setItem('ta-skin', 'graphite')
        })
        await page.reload()
        await expect(page.locator('html')).toHaveAttribute('data-skin', 'graphite')
    })
})
