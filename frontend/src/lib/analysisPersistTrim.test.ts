import { describe, expect, it } from 'vitest'

import {
    isPersistableAgentList,
    trimDebateMessagesForPersist,
    trimStreamingSectionsForPersist,
} from '@/lib/analysisPersistTrim'
import {
    PERSIST_DEBATE_MESSAGES_PER_KEY,
    PERSIST_MIN_AGENT_COUNT,
    PERSIST_STREAMING_CHAR_BUDGET,
} from '@/lib/analysisResumePolicy'
import type { Agent, DebateMessage, StreamingSectionState } from '@/types'

function makeSection(buf: string): StreamingSectionState {
    return { buffer: buf, displayed: buf, isTyping: true, isComplete: false }
}

describe('trimStreamingSectionsForPersist', () => {
    it('keeps suffix within budget across keys', () => {
        const sections: Record<string, StreamingSectionState> = {
            a: makeSection('x'.repeat(30)),
            b: makeSection('y'.repeat(30)),
        }
        const out = trimStreamingSectionsForPersist(sections, 40)
        const joined = Object.values(out)
            .map(s => s.displayed)
            .join('')
        expect(joined.length).toBeLessThanOrEqual(40)
        expect(joined.endsWith('y'.repeat(10))).toBe(true)
    })

    it('marks trimmed sections as not typing', () => {
        const out = trimStreamingSectionsForPersist({ m: makeSection('abc') }, 100)
        expect(out.m.isTyping).toBe(false)
    })
})

describe('trimDebateMessagesForPersist', () => {
    it('keeps only last N messages per debate key', () => {
        const arr: DebateMessage[] = Array.from({ length: 10 }, (_, i) => ({
            debate: 'research',
            agent: 'Bull',
            round: i,
            content: String(i),
        }))
        const out = trimDebateMessagesForPersist({ research: arr }, 4)
        expect(out.research?.map(m => m.round)).toEqual([6, 7, 8, 9])
    })
})

describe('analysisPersistTrim vs analysisResumePolicy', () => {
    it('default trim budgets match exported policy constants', () => {
        const huge = makeSection('z'.repeat(PERSIST_STREAMING_CHAR_BUDGET + 500))
        const out = trimStreamingSectionsForPersist({ only: huge })
        expect(out.only.displayed.length).toBe(PERSIST_STREAMING_CHAR_BUDGET)

        const msgs: DebateMessage[] = Array.from({ length: PERSIST_DEBATE_MESSAGES_PER_KEY + 5 }, (_, i) => ({
            debate: 'risk',
            agent: 'A',
            round: i,
            content: '',
        }))
        const dm = trimDebateMessagesForPersist({ risk: msgs })
        expect(dm.risk?.length).toBe(PERSIST_DEBATE_MESSAGES_PER_KEY)

        expect(PERSIST_MIN_AGENT_COUNT).toBeGreaterThanOrEqual(10)
    })
})

describe('isPersistableAgentList', () => {
    it('rejects short or invalid arrays', () => {
        expect(isPersistableAgentList([])).toBe(false)
        expect(isPersistableAgentList([{ name: 'x' }])).toBe(false)
    })

    it('accepts full agent roster shape', () => {
        const agents = Array.from({ length: 12 }, (_, i) => ({
            id: `a${i}`,
            name: `Agent ${i}`,
            team: 't',
            status: 'pending' as const,
        })) as Agent[]
        expect(isPersistableAgentList(agents)).toBe(true)
    })
})
