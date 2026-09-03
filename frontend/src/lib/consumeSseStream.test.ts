import { describe, expect, it, vi } from 'vitest'

import { consumeSseStream } from '@/lib/consumeSseStream'

function encodeSse(chunks: string[]): ReadableStream<Uint8Array> {
    const encoder = new TextEncoder()
    const joined = chunks.join('')
    return new ReadableStream({
        start(controller) {
            controller.enqueue(encoder.encode(joined))
            controller.close()
        },
    })
}

describe('consumeSseStream', () => {
    it('returns terminal on [DONE] payload', async () => {
        const body = encodeSse(['event: done\ndata: [DONE]\n\n'])
        const dispatch = vi.fn()
        const end = await consumeSseStream(body, dispatch)
        expect(end).toBe('terminal')
        expect(dispatch).not.toHaveBeenCalled()
    })

    it('dispatches events then terminal on done', async () => {
        const body = encodeSse([
            'event: job.running\ndata: {"symbol":"600519.SH"}\n\n',
            'event: done\ndata: [DONE]\n\n',
        ])
        const dispatch = vi.fn()
        const end = await consumeSseStream(body, dispatch)
        expect(end).toBe('terminal')
        expect(dispatch).toHaveBeenCalledTimes(1)
        expect(dispatch).toHaveBeenNthCalledWith(1, 'job.running', { symbol: '600519.SH' })
    })

    it('ignores ping without treating as prior event name', async () => {
        const body = encodeSse([
            'event: ping\ndata: {}\n\n',
            'data: {"x":1}\n\n',
        ])
        const dispatch = vi.fn()
        const end = await consumeSseStream(body, dispatch)
        expect(end).toBe('truncated')
        expect(dispatch).toHaveBeenCalledTimes(1)
        expect(dispatch).toHaveBeenCalledWith('message', { x: 1 })
    })

    it('returns truncated when stream closes without done', async () => {
        const body = encodeSse(['event: job.ready\ndata: {"job_id":"abc"}\n\n'])
        const dispatch = vi.fn()
        const end = await consumeSseStream(body, dispatch)
        expect(end).toBe('truncated')
        expect(dispatch).toHaveBeenCalledWith('job.ready', { job_id: 'abc' })
    })

    it('handles split chunks across reads', async () => {
        const encoder = new TextEncoder()
        const part1 = 'event: a\ndata: {"k"'
        const part2 = ':1}\n\n'
        const body = new ReadableStream<Uint8Array>({
            async start(controller) {
                controller.enqueue(encoder.encode(part1))
                await Promise.resolve()
                controller.enqueue(encoder.encode(part2))
                controller.close()
            },
        })
        const dispatch = vi.fn()
        const end = await consumeSseStream(body, dispatch)
        expect(end).toBe('truncated')
        expect(dispatch).toHaveBeenCalledWith('a', { k: 1 })
    })

    it('parses id field and notifies onEventId', async () => {
        const body = encodeSse([
            'id: 7\n',
            'event: job.running\ndata: {"symbol":"600519.SH"}\n\n',
        ])
        const dispatch = vi.fn()
        const onEventId = vi.fn()
        const end = await consumeSseStream(body, dispatch, { onEventId })
        expect(end).toBe('truncated')
        expect(onEventId).toHaveBeenCalledWith(7)
        expect(dispatch).toHaveBeenCalledWith('job.running', { symbol: '600519.SH' })
    })
})
