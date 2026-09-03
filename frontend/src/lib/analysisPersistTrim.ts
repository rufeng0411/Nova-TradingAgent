import type { Agent, DebateMessage, StreamingSectionState } from '@/types'

import {
    PERSIST_DEBATE_MESSAGES_PER_KEY,
    PERSIST_MIN_AGENT_COUNT,
    PERSIST_STREAMING_CHAR_BUDGET,
} from '@/lib/analysisResumePolicy'

export function trimStreamingSectionsForPersist(
    sections: Record<string, StreamingSectionState>,
    maxChars: number = PERSIST_STREAMING_CHAR_BUDGET,
): Record<string, StreamingSectionState> {
    let budget = maxChars
    const out: Record<string, StreamingSectionState> = {}
    for (const [key, v] of Object.entries(sections)) {
        if (budget <= 0) break
        const buf = String(v.displayed ?? v.buffer ?? '')
        if (!buf) {
            out[key] = { ...v, buffer: '', displayed: '', isTyping: false, isComplete: v.isComplete }
            continue
        }
        const take = buf.slice(Math.max(0, buf.length - budget))
        budget -= take.length
        out[key] = {
            ...v,
            buffer: take,
            displayed: take,
            isTyping: false,
            isComplete: v.isComplete,
        }
    }
    return out
}

export function trimDebateMessagesForPersist(
    dm: Record<string, DebateMessage[]>,
    maxPerKey: number = PERSIST_DEBATE_MESSAGES_PER_KEY,
): Record<string, DebateMessage[]> {
    const out: Record<string, DebateMessage[]> = {}
    for (const [k, arr] of Object.entries(dm)) {
        if (!Array.isArray(arr) || arr.length === 0) continue
        out[k] = arr.slice(-maxPerKey)
    }
    return out
}

export function isPersistableAgentList(agents: unknown): agents is Agent[] {
    return Array.isArray(agents) && agents.length >= PERSIST_MIN_AGENT_COUNT && typeof (agents as Agent[])[0]?.name === 'string'
}
