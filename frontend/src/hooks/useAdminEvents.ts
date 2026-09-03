import { useEffect, useRef } from 'react'
import { getBaseUrl } from '@/services/api'

/** 使用 fetch 流式读取 SSE（可带 Authorization；原生 EventSource 无法自定义头）。 */
export function useAdminEvents(enabled: boolean, onSignal: (message: string) => void) {
    const abortRef = useRef<AbortController | null>(null)

    useEffect(() => {
        if (!enabled) return
        const token = localStorage.getItem('ta-access-token')
        if (!token) return

        const ac = new AbortController()
        abortRef.current = ac
        const base = getBaseUrl()
        const url = `${base}/v1/admin/events/stream`

        let buf = ''

        ;(async () => {
            try {
                const res = await fetch(url, {
                    headers: { Authorization: `Bearer ${token}` },
                    signal: ac.signal,
                })
                if (!res.ok || !res.body) return
                const reader = res.body.getReader()
                const dec = new TextDecoder()
                for (;;) {
                    const { done, value } = await reader.read()
                    if (done) break
                    buf += dec.decode(value, { stream: true })
                    let idx: number
                    while ((idx = buf.indexOf('\n\n')) >= 0) {
                        const chunk = buf.slice(0, idx)
                        buf = buf.slice(idx + 2)
                        const lines = chunk.split('\n')
                        for (const line of lines) {
                            if (!line.startsWith('data:')) continue
                            const raw = line.slice(5).trim()
                            if (!raw || raw === '{"kind":"ping"}') continue
                            try {
                                const ev = JSON.parse(raw) as { kind?: string; type?: string; severity?: string }
                                if (ev.kind === 'admin_signal' && ev.type) {
                                    onSignal(`[${ev.severity || 'info'}] ${ev.type}`)
                                }
                            } catch {
                                /* ignore */
                            }
                        }
                    }
                }
            } catch {
                /* aborted or network */
            }
        })()

        return () => {
            ac.abort()
        }
    }, [enabled, onSignal])
}
