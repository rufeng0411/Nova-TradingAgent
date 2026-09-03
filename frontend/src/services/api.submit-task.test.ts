import { afterEach, describe, expect, it, vi } from 'vitest'

import { api } from '@/services/api'

describe('api.submitAnalysisTask', () => {
    afterEach(() => {
        vi.restoreAllMocks()
    })

    it('posts to /v1/me/tasks/submit and returns parsed payload', async () => {
        const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValueOnce(
            new Response(
                JSON.stringify({
                    job_id: 'job-1',
                    status: 'queued',
                    symbol: '603002.SH',
                    trade_date: '2026-05-13',
                    waiting_ahead_count: 1,
                }),
                {
                    status: 200,
                    headers: { 'Content-Type': 'application/json' },
                },
            ),
        )

        const resp = await api.submitAnalysisTask({ text: '分析宏昌电子 603002.SH 今日走势' })

        expect(resp.status).toBe('queued')
        expect(resp.job_id).toBe('job-1')
        expect(fetchMock).toHaveBeenCalledTimes(1)
        const [url, init] = fetchMock.mock.calls[0]
        expect(String(url)).toContain('/v1/me/tasks/submit')
        expect(init?.method).toBe('POST')
    })
})
