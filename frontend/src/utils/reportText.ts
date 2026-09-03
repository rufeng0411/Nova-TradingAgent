/** Compliance-facing display transforms only — does not alter Agent prompts or stored raw output upstream. */

export interface InstrumentDisplayContext {
    symbol: string
    name?: string | null
    display_label?: string | null
}

function reEscRegex(s: string): string {
    return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
}

/** 折叠误拼的 600330.SH.SH → 600330.SH（展示层）。 */
function collapseDuplicateListingSuffixes(text: string): string {
    return text.replace(/(\d{6}\.(?:SH|SZ|BJ))(?:\.(?:SH|SZ|BJ))+/gi, (_, core: string) => String(core).toUpperCase())
}

/** 从「名称 代码」展示串解析名称与规范代码；无法解析时返回 null。 */
function parseLabelNameAndListedSym(label: string): { name: string; sym: string } | null {
    const m = /^(.+?)\s+(\d{6}\.(?:SH|SZ|BJ))$/i.exec(label.trim())
    if (!m) return null
    return { name: m[1].trim(), sym: m[2].toUpperCase() }
}

function replaceListedSymToken(
    input: string,
    sym: string,
    label: string,
    parsed: { name: string; sym: string } | null,
): string {
    const symPat = reEscRegex(sym)
    const re = new RegExp(`(?<![A-Z0-9.])${symPat}(?![A-Z0-9])`, 'gi')
    return input.replace(re, (_match: string, offset: number, full: string) => {
        if (parsed && parsed.sym === sym.toUpperCase()) {
            const lookStart = Math.max(0, offset - Math.min(offset, 96))
            const before = full.slice(lookStart, offset)
            if (new RegExp(`${reEscRegex(parsed.name)}\\s*$`).test(before)) {
                return sym.toUpperCase()
            }
        }
        return label
    })
}

/** 将正文中独立出现的代码/裸六位替换为统一展示名（跳过 fenced code block）。 */
export function unifyInstrumentDisplayInMarkdown(chunk: string, ctx: InstrumentDisplayContext): string {
    const label = (ctx.display_label || '').trim()
    if (!label || !chunk) return chunk
    const sym = ctx.symbol.trim().toUpperCase()
    if (!sym) return chunk
    const m = /^(\d{6})\.(SH|SZ|BJ)$/.exec(sym)
    const code = m?.[1]

    const parsed = parseLabelNameAndListedSym(label)
    let s = collapseDuplicateListingSuffixes(chunk)
    if (parsed) {
        const nameEsc = reEscRegex(parsed.name)
        s = s.replace(new RegExp(`(?:${nameEsc}\\s+){2,}`, 'g'), `${parsed.name} `)
    }

    s = replaceListedSymToken(s, sym, label, parsed)

    if (sym.endsWith('.SH')) {
        const alt = reEscRegex(sym.replace(/\.SH$/i, '.SS'))
        s = s.replace(new RegExp(`(?<![A-Z0-9.])${alt}(?![A-Z0-9])`, 'gi'), (_match: string, offset: number, full: string) => {
            if (parsed && parsed.sym === sym.toUpperCase()) {
                const lookStart = Math.max(0, offset - Math.min(offset, 96))
                const before = full.slice(lookStart, offset)
                if (new RegExp(`${reEscRegex(parsed.name)}\\s*$`).test(before)) {
                    return sym.toUpperCase()
                }
            }
            return label
        })
    }
    if (code) {
        s = s.replace(new RegExp(`(?<!\\d)${code}(?!\\d)(?!\\.(?:SH|SZ|BJ)\\b)`, 'gi'), label)
    }

    const name = ctx.name?.trim()
    if (name && name.length >= 2 && name !== label && !label.includes(name)) {
        s = s.replace(new RegExp(reEscRegex(name), 'g'), label)
    }
    return s
}

export function detectDecisionLabel(text?: string | null): string | null {
    if (!text) return null
    const normalized = text.toLowerCase()
    if (normalized.includes('增持')) return '偏多'
    if (normalized.includes('减持')) return '偏空'
    if (normalized.includes('buy') || normalized.includes('买入')) return '偏多'
    if (normalized.includes('sell') || normalized.includes('卖出')) return '偏空'
    if (normalized.includes('watch') || normalized.includes('观望')) return '中性'
    if (normalized.includes('hold') || normalized.includes('持有')) return '中性'
    return null
}

function stripMarkerHtmlComment(text: string, marker: string): string {
    const esc = marker.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
    const openRe = new RegExp(`<!--\\s*${esc}\\s*:\\s*`, 'i')
    let result = text
    for (let pass = 0; pass < 64; pass++) {
        openRe.lastIndex = 0
        const m = openRe.exec(result)
        if (!m) break
        const start = m.index
        let i = start + m[0].length
        while (i < result.length && /\s/.test(result[i])) i++
        if (i >= result.length || result[i] !== '{') {
            const endSimple = result.indexOf('-->', start)
            result =
                endSimple === -1
                    ? result.slice(0, start) + result.slice(start + 1)
                    : result.slice(0, start) + result.slice(endSimple + 3)
            continue
        }
        let depth = 0
        let j = i
        for (; j < result.length; j++) {
            const c = result[j]
            if (c === '{') depth++
            else if (c === '}') {
                depth--
                if (depth === 0) {
                    j++
                    break
                }
            }
        }
        if (depth !== 0) break
        const tail = result.slice(j)
        const cm = tail.match(/^\s*-->/)
        if (!cm) {
            const endSimple = result.indexOf('-->', start)
            result =
                endSimple === -1
                    ? result.slice(0, start) + result.slice(start + 1)
                    : result.slice(0, start) + result.slice(endSimple + 3)
            continue
        }
        const end = j + cm[0].length
        result = result.slice(0, start) + result.slice(end)
    }
    return result
}

/** 移除辩论/风控机读 HTML 注释及「机读块」提示行（嵌套 JSON 安全）。 */
export function stripPublicDebateMachineBlocks(text: string): string {
    let s = text
    for (const marker of ['DEBATE_STATE', 'RISK_STATE', 'RISK_JUDGE']) {
        s = stripMarkerHtmlComment(s, marker)
    }
    s = s.replace(/\n+\s*机读块\s*\n+/g, '\n\n')
    s = s.replace(/^\s*机读块\s*\n+/gm, '')
    s = s.replace(/\n\s*机读块\s*$/gm, '')
    s = s.replace(/\n{3,}/g, '\n\n')
    return s.trim()
}

/** 正文展示层：英文模板、指令性买卖用语、旧合规别名 → 沙盘中性表述（不写入库）。 */
function applyComplianceLexiconToProse(segment: string, instrument: InstrumentDisplayContext | null): string {
    let t = segment
        .replace(/<!--\s*VERDICT:[^>]*-->/gi, '')
        .replace(/最终裁决\s*[:：]/g, '沙盘综合研判结论：')
        .replace(/最终交易建议\s*[:：]\s*买入/g, '沙盘情景：偏多（模型归纳，非交易指令）')
        .replace(/最终交易建议\s*[:：]\s*卖出/g, '沙盘情景：偏空（模型归纳，非交易指令）')
        .replace(/最终交易建议\s*[:：]\s*观望/g, '沙盘情景：中性（模型归纳，非交易指令）')
        .replace(/买入\s*（条件触发）/g, '偏多情景（条件触发）')
        .replace(/卖出\s*（条件触发）/g, '偏空情景（条件触发）')
        .replace(/观望\s*（条件触发）/g, '中性情景（条件触发）')
        .replace(/FINAL TRANSACTION PROPOSAL:\s*\**\s*BUY\s*\**/gi, '沙盘情景：偏多（模型归纳，非交易指令）')
        .replace(/FINAL TRANSACTION PROPOSAL:\s*\**\s*SELL\s*\**/gi, '沙盘情景：偏空（模型归纳，非交易指令）')
        .replace(/FINAL TRANSACTION PROPOSAL:\s*\**\s*HOLD\s*\**/gi, '沙盘情景：中性（模型归纳，非交易指令）')
        .replace(/FINAL VERDICT:\s*/gi, '沙盘综合研判结论：')
        .replace(/HOLD with Conditional Trigger/gi, '中性情景（条件触发）')
        .replace(/BUY with Conditional Trigger/gi, '偏多情景（条件触发）')
        .replace(/SELL with Conditional Trigger/gi, '偏空情景（条件触发）')

    t = t
        .replace(/偏多加仓情景/g, '偏多')
        .replace(/偏空减仓情景/g, '偏空')
        .replace(/中性持仓/g, '中性')
        .replace(/中性观望/g, '中性')
        .replace(/假设参考价位/g, '偏多参考峰值')
        .replace(/风控参考价位/g, '偏空参考风控')
        .replace(/风控参考价/g, '偏空参考风控')
        .replace(/目标价格?/g, '偏多参考峰值')
        .replace(/止损价格?/g, '偏空参考风控')

    t = t
        .replace(/\*\*BUY\*\*/gi, '**偏多**')
        .replace(/\*\*SELL\*\*/gi, '**偏空**')
        .replace(/\*\*HOLD\*\*/gi, '**中性**')
        .replace(/\*\*买入\*\*/g, '**偏多**')
        .replace(/\*\*卖出\*\*/g, '**偏空**')
        .replace(/\*\*增持\*\*/g, '**偏多**')
        .replace(/\*\*减持\*\*/g, '**偏空**')
        .replace(/\*\*观望\*\*/g, '**中性**')
        .replace(/\*\*持有\*\*/g, '**中性**')

    t = t
        .replace(/(?:强烈)?(?:建议|推荐)(?:积极)?(?:的)?\s*买入/g, '偏多（模型归纳，非交易指令）')
        .replace(/(?:强烈)?(?:建议|推荐)(?:积极)?(?:的)?\s*卖出/g, '偏空（模型归纳，非交易指令）')
        .replace(/(?:建议|推荐)\s*增持/g, '偏多（模型归纳，非交易指令）')
        .replace(/(?:建议|推荐)\s*减持/g, '偏空（模型归纳，非交易指令）')
        .replace(/逢低(?:加码)?买入/g, '逢低关注偏多情景（非交易指令）')
        .replace(/逢高(?:减仓)?卖出/g, '逢高关注偏空情景（非交易指令）')
        .replace(/买入信号/g, '偏多信号（模型归纳）')
        .replace(/卖出信号/g, '偏空信号（模型归纳）')
        .replace(/增持信号/g, '偏多信号（模型归纳）')
        .replace(/减持信号/g, '偏空信号（模型归纳）')
        .replace(/看涨买入/g, '看涨偏多（非交易指令）')
        .replace(/看跌卖出/g, '看跌偏空（非交易指令）')

    t = t
        .replace(/\bBUY\s*\/\s*SELL\s*\/\s*HOLD\b/gi, '偏多 / 偏空 / 中性')
        .replace(/\bBUY\s*\/\s*SELL\b/gi, '偏多/偏空')
        .replace(/\|\s*BUY\s*\|/gi, '| 偏多 |')
        .replace(/\|\s*SELL\s*\|/gi, '| 偏空 |')
        .replace(/\|\s*HOLD\s*\|/gi, '| 中性 |')
        .replace(/\bBUY\b/gi, '偏多')
        .replace(/\bSELL\b/gi, '偏空')
        .replace(/\bHOLD\b/gi, '中性')

    if (instrument?.symbol?.trim()) {
        t = unifyInstrumentDisplayInMarkdown(t, instrument)
    }
    return t
}

export function sanitizeReportMarkdown(
    text?: string | null,
    instrument?: InstrumentDisplayContext | null,
): string {
    if (!text) return ''
    const stripped = stripPublicDebateMachineBlocks(text)
    const parts = stripped.split(/(```[\s\S]*?```)/g)
    return parts
        .map((p) => (p.startsWith('```') ? p : applyComplianceLexiconToProse(p, instrument ?? null)))
        .join('')
}

export function buildAgentSummary(text?: string | null): string {
    const cleaned = sanitizeReportMarkdown(text, null)
        .replace(/^#+\s*/gm, '')
        .replace(/\*\*/g, '')
        .replace(/\|/g, ' ')
        .replace(/\s+/g, ' ')
        .trim()
    const decision = detectDecisionLabel(cleaned)
    if (decision) return decision
    if (/偏多|看多|上涨|突破/.test(cleaned)) return '偏多'
    if (/偏空|看空|下跌|回撤/.test(cleaned)) return '偏空'
    if (/中性|震荡/.test(cleaned)) return '中性'
    if (cleaned.includes('风险')) return '风控结论'
    if (cleaned.includes('计划')) return '计划已生成'
    return cleaned.slice(0, 18) || '报告已生成'
}

export interface Verdict {
    direction: string
    reason: string
}

const DIRECTION_ALIAS: Record<string, string> = {
    BULLISH:       '看多',
    LEAN_BULLISH:  '偏多',
    BEARISH:       '看空',
    LEAN_BEARISH:  '偏空',
    NEUTRAL:       '中性',
    CAUTIOUS:      '谨慎',
}

export function extractVerdict(text?: string | null): Verdict | null {
    if (!text) return null
    const m = text.match(/<!--\s*VERDICT:\s*(\{[^>]+\})\s*-->/)
    if (!m) return null
    try {
        const parsed = JSON.parse(m[1]) as { direction?: string; reason?: string }
        if (!parsed.direction || !parsed.reason) return null
        const direction = DIRECTION_ALIAS[parsed.direction.toUpperCase()] ?? parsed.direction
        return { direction, reason: parsed.reason.trim().slice(0, 42) }
    } catch {
        return null
    }
}

/** 无 LLM 摘要时，决策卡「要点梳理」节选，避免整篇铺满。 */
export function excerptForDecisionCard(body: string | undefined | null, maxChars = 420): string | undefined {
    const t = (body || '').trim()
    if (!t) return undefined
    if (t.length <= maxChars) return t
    return `${t.slice(0, maxChars - 1)}…`
}
