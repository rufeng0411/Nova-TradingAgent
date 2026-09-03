import { test, expect } from '@playwright/test'

test.describe('智能分析工作流风格', () => {
    test('切换 n8n 后显示外壳，刷新后仍保持', async ({ page }) => {
        await page.addInitScript(() => {
            localStorage.setItem('ta-access-token', 'playwright-e2e-token')
            localStorage.setItem(
                'ta-user',
                JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            )
        })

        const featuresBody = JSON.stringify({
            allow_registration: true,
            maintenance: false,
            captcha_enabled: false,
            ta_cost_analysis: 0,
        })
        const userBody = JSON.stringify({
            id: 'e2e-user',
            email: 'e2e@test.com',
            username: 'e2e',
            role: 'user',
            display_name: 'E2E User',
        })

        await page.route('**/v1/features', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: featuresBody }),
        )
        await page.route('**/v1/auth/me', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: userBody }),
        )

        await page.goto('/analysis')
        await expect(page).toHaveURL(/\/analysis/)

        await page.getByRole('button', { name: 'n8n风格' }).click()
        await expect(page.locator('.workflow-n8n-shell')).toBeVisible()
        await page.reload()
        await expect(page.locator('.workflow-n8n-shell')).toBeVisible()
        const stored = await page.evaluate(() => localStorage.getItem('ta-workflow-style'))
        expect(stored).toBe('n8n')
    })
})
