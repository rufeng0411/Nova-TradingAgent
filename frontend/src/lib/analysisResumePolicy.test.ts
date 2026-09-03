import { describe, expect, it } from 'vitest'

import {
    CHAT_STREAM_MAX_ATTEMPTS,
    JOB_COMPLETION_POLL_INTERVAL_MS,
    JOB_COMPLETION_POLL_MAX_ROUNDS,
    chatStreamRetryDelayMs,
    isLikelyNetworkOrStreamError,
} from '@/lib/analysisResumePolicy'

describe('analysisResumePolicy', () => {
    it('chatStreamRetryDelayMs matches legacy backoff for attempts 2..n', () => {
        expect(chatStreamRetryDelayMs(1)).toBe(0)
        expect(chatStreamRetryDelayMs(2)).toBe(1000)
        expect(chatStreamRetryDelayMs(3)).toBe(1500)
    })

    it('isLikelyNetworkOrStreamError covers common browser / fetch failures', () => {
        expect(isLikelyNetworkOrStreamError('TypeError: Failed to fetch')).toBe(true)
        expect(isLikelyNetworkOrStreamError('Load failed')).toBe(true)
        expect(isLikelyNetworkOrStreamError('stream interrupted')).toBe(true)
        expect(isLikelyNetworkOrStreamError('HTTP error! status: 400')).toBe(false)
    })

    it('documents total poll window for job completion fallback', () => {
        const totalMs = JOB_COMPLETION_POLL_MAX_ROUNDS * JOB_COMPLETION_POLL_INTERVAL_MS
        expect(totalMs).toBe(12_000)
        expect(CHAT_STREAM_MAX_ATTEMPTS).toBe(3)
    })
})
