export type SseStreamOptions = {
    /** Persist server monotonic event id (SSE `id:`) for replay via ?after= / Last-Event-ID */
    onEventId?: (id: number) => void
}

/**
 * Consume a text/event-stream body (SSE) and dispatch parsed JSON payloads.
 * Returns `terminal` when the stream ends with `event: done` or `[DONE]` payload.
 *
 * 容错：每个 SSE 块独立解析 `event:`，避免上一块的 `ping` 等事件名泄漏到下一块仅有 `data:` 的行。
 */
export async function consumeSseStream(
    body: ReadableStream<Uint8Array>,
    dispatch: (eventName: string, data: Record<string, unknown>) => void,
    options?: SseStreamOptions,
): Promise<'terminal' | 'truncated'> {
    const onEventId = options?.onEventId
    const reader = body.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
        const { value, done } = await reader.read()
        if (done) break
        buffer += decoder.decode(value, { stream: true })

        const blocks = buffer.split('\n\n')
        buffer = blocks.pop() || ''

        for (const block of blocks) {
            const lines = block.split('\n')
            let dataLine = ''
            let blockEvent = 'message'
            let idStr: string | null = null
            for (const raw of lines) {
                const line = raw.trim()
                if (!line) continue
                if (line.startsWith('event:')) blockEvent = line.slice(6).trim()
                else if (line.startsWith('data:')) dataLine = line.slice(5).trim()
                else if (line.startsWith('id:')) idStr = line.slice(3).trim()
            }

            if (idStr && onEventId) {
                const n = Number(idStr)
                if (Number.isFinite(n)) onEventId(n)
            }

            if (!dataLine) continue
            if (dataLine === '[DONE]' || blockEvent === 'done') {
                return 'terminal'
            }
            if (blockEvent === 'ping') continue

            try {
                const data = JSON.parse(dataLine) as Record<string, unknown>
                dispatch(blockEvent, data)
            } catch {
                // ignore malformed line
            }
        }
    }

    return 'truncated'
}
