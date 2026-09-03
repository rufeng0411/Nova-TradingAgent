import { test, expect } from '@playwright/test'

/**
 * `vite preview` 已将 `/healthz` 代理到 `http://127.0.0.1:8000`（见 vite.config.ts）。
 * 本机未起 API 时跳过，不判失败。
 */
test.describe('预览对后端的代理（可选）', () => {
    test('GET /healthz 若后端在线则返回 status=ok', async ({ request }) => {
        const res = await request.get('/healthz').catch(() => null)
        test.skip(!res || !res.ok(), '本机未启动 FastAPI :8000 或未连通，跳过 healthz')
        const body = (await res!.json()) as { status?: string }
        expect(body.status).toBe('ok')
    })
})
