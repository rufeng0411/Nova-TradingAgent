import type { FastAnalysisDetail } from '@/types'
import { stockSafeFilename } from '@/utils/stockDisplay'

const DISCLAIMER =
    '> 免责声明：以上内容由模型基于公开数据、历史信息与预设规则自动生成，仅供研究参考，不构成任何投资建议、收益承诺或实际交易指令。'

function str(v: unknown): string {
    if (v === null || v === undefined) return ''
    if (typeof v === 'string') return v
    if (typeof v === 'number' || typeof v === 'boolean') return String(v)
    return ''
}

function mdList(items: unknown[]): string {
    if (!items.length) return '_无_\n'
    return items.map((x) => `- ${str(x)}`).join('\n') + '\n'
}

const DIRECTION_ZH: Record<string, string> = {
    bullish: '看多',
    bearish: '看空',
    neutral: '中性',
}

const HORIZON_ZH: Record<string, string> = {
    next_2h: '未来约 2 小时',
    same_day: '当日剩余时段',
    next_session: '下一交易日',
}

const PHASE_ZH: Record<string, string> = {
    morning_10_to_11_30: '上午 10:00–11:30',
    afternoon_13_to_14_30: '午后 13:00–14:30',
    closing_14_30_to_15_00: '尾盘 14:30–15:00',
}

function phaseTitle(key: string): string {
    return PHASE_ZH[key] || key
}

export function buildFastAnalysisMarkdown(detail: FastAnalysisDetail): string {
    const v = (detail.verdict_json || {}) as Record<string, unknown>
    const tp = (detail.time_phased_json || {}) as Record<string, Record<string, unknown>>
    const pos = (detail.position_advice_json || {}) as Record<string, unknown>
    const ex = (detail.executability_json || {}) as Record<string, unknown>
    const kl = (detail.kline_insight_json || {}) as Record<string, unknown>

    const dir = str(v.direction)
    const dirZh = DIRECTION_ZH[dir] || dir || '—'
    const hz = str(v.horizon)
    const hzZh = HORIZON_ZH[hz] || hz

    let body = `# 快速分析报告\n\n`
    body += `**标的**：${detail.symbol}  \n`
    body += `**交易日**：${detail.trade_date}  \n`
    body += `**状态**：${detail.status}  \n\n`

    body += `## 综合结论（沙盘倾向）\n\n`
    body += `- **方向**：${dirZh}\n`
    body += `- **时间尺度**：${hzZh || '—'}\n`
    if (typeof v.confidence === 'number') body += `- **模型信心**：${v.confidence}/5\n`
    body += `\n### 结论摘要\n\n${str(v.reason) || '_（无）_'}\n\n`
    body += `### 主要驱动\n\n${mdList(Array.isArray(v.key_drivers) ? (v.key_drivers as unknown[]) : [])}\n`
    body += `### 主要风险\n\n${mdList(Array.isArray(v.risks) ? (v.risks as unknown[]) : [])}\n`

    body += `## 分时段策略\n\n`
    const phaseKeys = Object.keys(tp)
    if (!phaseKeys.length) body += '_（无）_\n\n'
    else {
        for (const key of phaseKeys) {
            const b = tp[key]
            body += `### ${phaseTitle(key)}\n\n`
            body += `- 动作：${str(b?.action)}\n`
            body += `- 仓位比例：${str(b?.size_pct)}\n`
            if (b?.key_levels && typeof b.key_levels === 'object') {
                const kl2 = b.key_levels as Record<string, unknown>
                body += `- 支撑 / 压力：${str(kl2.support)} / ${str(kl2.resistance)}\n`
            }
            body += `- 触发：${str(b?.trigger_condition)}\n\n`
        }
    }

    body += `## 仓位建议\n\n\`\`\`json\n${JSON.stringify(pos, null, 2)}\n\`\`\`\n\n`

    body += `## 可执行性\n\n\`\`\`json\n${JSON.stringify(ex, null, 2)}\n\`\`\`\n\n`

    body += `## K 线即时摘要\n\n`
    if (str(kl.summary)) body += `${str(kl.summary)}\n\n`
    else body += `\`\`\`json\n${JSON.stringify(kl, null, 2)}\n\`\`\`\n\n`

    body += `---\n\n${DISCLAIMER}\n`
    return body
}

export function exportFastAnalysisMarkdown(detail: FastAnalysisDetail): void {
    const text = buildFastAnalysisMarkdown(detail)
    const blob = new Blob([text], { type: 'text/markdown;charset=utf-8' })
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${stockSafeFilename({ symbol: detail.symbol })}-fast-${detail.trade_date || 'report'}.md`
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
}
