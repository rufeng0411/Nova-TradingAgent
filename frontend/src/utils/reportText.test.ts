import { describe, expect, it } from 'vitest'

import { sanitizeReportMarkdown } from './reportText'

describe('sanitizeReportMarkdown', () => {
    it('maps English templates and conditional-trigger phrases', () => {
        const raw =
            'FINAL TRANSACTION PROPOSAL: **BUY**\nFINAL VERDICT: ok\nBUY with Conditional Trigger'
        const out = sanitizeReportMarkdown(raw)
        expect(out).toContain('沙盘情景：偏多（模型归纳，非交易指令）')
        expect(out).toContain('沙盘综合研判结论：')
        expect(out).toContain('偏多情景（条件触发）')
    })

    it('maps common Chinese trader closing lines', () => {
        const raw = '最终交易建议：买入\n最终裁决：观望'
        const out = sanitizeReportMarkdown(raw)
        expect(out).toContain('沙盘情景：偏多（模型归纳，非交易指令）')
        expect(out).toContain('沙盘综合研判结论：')
    })

    it('neutralizes bold BUY/SELL and directive Chinese phrases', () => {
        const raw = '结论：**BUY**，建议买入；目标价 12 元。'
        const out = sanitizeReportMarkdown(raw)
        expect(out).toContain('**偏多**')
        expect(out).toContain('偏多（模型归纳，非交易指令）')
        expect(out).toContain('偏多参考峰值')
    })

    it('replaces standalone symbol and bare code with display_label outside code fences', () => {
        const raw = '关注 600519.SH 与 600519。\n\n```\n600519.SH\n```'
        const out = sanitizeReportMarkdown(raw, {
            symbol: '600519.SH',
            name: '贵州茅台',
            display_label: '贵州茅台 600519.SH',
        })
        expect(out).toContain('贵州茅台 600519.SH')
        expect(out).toMatch(/```\s*600519\.SH\s*```/)
    })

    it('does not duplicate display_label when markdown already has name + listed sym', () => {
        const raw = '# 天通股份 600330.SH 短线技术分析（2026-05-13）\n\n正文。'
        const out = sanitizeReportMarkdown(raw, {
            symbol: '600330.SH',
            name: '天通股份',
            display_label: '天通股份 600330.SH',
        })
        expect(out).not.toMatch(/天通股份\s+天通股份\s+天通股份/)
        expect(out).not.toContain('600330.SH.SH')
        expect(out).toContain('天通股份 600330.SH')
    })

    it('collapses .SH.SH suffix and triple repeated issuer name in title', () => {
        const raw = '天通股份 天通股份 天通股份 600330.SH.SH 短线技术分析'
        const out = sanitizeReportMarkdown(raw, {
            symbol: '600330.SH',
            name: '天通股份',
            display_label: '天通股份 600330.SH',
        })
        expect(out).not.toContain('600330.SH.SH')
        expect(out).not.toMatch(/天通股份(?:\s+天通股份){2,}/)
        expect(out).toContain('天通股份 600330.SH')
    })

    it('removes debate machine-read HTML comments and 机读块 label', () => {
        const raw =
            '正文。\n\n机读块\n<!-- DEBATE_STATE: {"responded_claim_ids": ["INV-1"], "new_claims": [{"claim": "c", "evidence": ["e"], "confidence": 0.7}], "resolved_claim_ids": [], "unresolved_claim_ids": [], "next_focus_claim_ids": [], "round_summary": "s", "round_goal": "g"} -->\n\n尾部'
        const out = sanitizeReportMarkdown(raw)
        expect(out).not.toContain('<!-- DEBATE_STATE')
        expect(out).not.toContain('机读块')
        expect(out).toContain('正文')
        expect(out).toContain('尾部')
    })
})
