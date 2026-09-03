/**
 * 纯函数技术指标（与轻量 K 线页共用，无外部图表依赖）
 */

export interface OhlcvRow {
    date: string
    open: number
    high: number
    low: number
    close: number
    volume?: number | null
}

export interface SeriesPoint {
    time: string
    value: number | null
}

function sma(values: number[], period: number): (number | null)[] {
    const out: (number | null)[] = []
    for (let i = 0; i < values.length; i++) {
        if (i < period - 1) {
            out.push(null)
            continue
        }
        let s = 0
        for (let j = 0; j < period; j++) s += values[i - j]
        out.push(s / period)
    }
    return out
}

export function calcSma(closes: number[], period: number): (number | null)[] {
    return sma(closes, period)
}

export function calcEma(closes: number[], period: number): (number | null)[] {
    const k = 2 / (period + 1)
    const out: (number | null)[] = []
    let ema: number | null = null
    for (let i = 0; i < closes.length; i++) {
        if (i < period - 1) {
            out.push(null)
            continue
        }
        if (i === period - 1) {
            let s = 0
            for (let j = 0; j < period; j++) s += closes[i - j]
            ema = s / period
            out.push(ema)
            continue
        }
        ema = (closes[i] - (ema as number)) * k + (ema as number)
        out.push(ema)
    }
    return out
}

export interface BollResult {
    upper: (number | null)[]
    mid: (number | null)[]
    lower: (number | null)[]
}

export function calcBoll(closes: number[], period = 20, mult = 2): BollResult {
    const mid = sma(closes, period)
    const upper: (number | null)[] = []
    const lower: (number | null)[] = []
    for (let i = 0; i < closes.length; i++) {
        const m = mid[i]
        if (m == null) {
            upper.push(null)
            lower.push(null)
            continue
        }
        if (i < period - 1) {
            upper.push(null)
            lower.push(null)
            continue
        }
        let sum = 0
        for (let j = 0; j < period; j++) {
            const d = closes[i - j] - m
            sum += d * d
        }
        const sd = Math.sqrt(sum / period)
        upper.push(m + mult * sd)
        lower.push(m - mult * sd)
    }
    return { upper, mid, lower }
}

export interface MacdResult {
    dif: (number | null)[]
    dea: (number | null)[]
    macd: (number | null)[]
}

function emaArray(values: number[], period: number): (number | null)[] {
    const k = 2 / (period + 1)
    const out: (number | null)[] = values.map(() => null)
    let ema: number | null = null
    for (let i = 0; i < values.length; i++) {
        if (i < period - 1) continue
        if (i === period - 1) {
            let s = 0
            for (let j = 0; j < period; j++) s += values[i - j]
            ema = s / period
            out[i] = ema
        } else {
            ema = (values[i] - (ema as number)) * k + (ema as number)
            out[i] = ema
        }
    }
    return out
}

export function calcMacd(closes: number[], fast = 12, slow = 26, signal = 9): MacdResult {
    const emaFast = calcEma(closes, fast)
    const emaSlow = calcEma(closes, slow)
    const dif: (number | null)[] = closes.map((_, i) => {
        const a = emaFast[i]
        const b = emaSlow[i]
        if (a == null || b == null) return null
        return a - b
    })
    const firstDif = dif.findIndex((v) => v != null)
    if (firstDif < 0) {
        return { dif, dea: dif.map(() => null), macd: dif.map(() => null) }
    }
    const difSlice = dif.slice(firstDif).map((v) => v as number)
    const deaSlice = emaArray(difSlice, signal)
    const dea: (number | null)[] = dif.map(() => null)
    for (let i = 0; i < deaSlice.length; i++) {
        dea[firstDif + i] = deaSlice[i]
    }
    const macd: (number | null)[] = dif.map((d, i) => {
        const e = dea[i]
        if (d == null || e == null) return null
        return d - e
    })
    return { dif, dea, macd }
}

export interface KdjResult {
    k: (number | null)[]
    d: (number | null)[]
    j: (number | null)[]
}

export function calcKdj(
    highs: number[],
    lows: number[],
    closes: number[],
    n = 9,
    _m1 = 3,
    _m2 = 3,
): KdjResult {
    const rsv: (number | null)[] = []
    for (let i = 0; i < closes.length; i++) {
        if (i < n - 1) {
            rsv.push(null)
            continue
        }
        let hh = -Infinity
        let ll = Infinity
        for (let j = 0; j < n; j++) {
            hh = Math.max(hh, highs[i - j])
            ll = Math.min(ll, lows[i - j])
        }
        const c = closes[i]
        if (hh === ll) rsv.push(50)
        else rsv.push(((c - ll) / (hh - ll)) * 100)
    }
    const k: (number | null)[] = rsv.map(() => null)
    const d: (number | null)[] = rsv.map(() => null)
    const j: (number | null)[] = rsv.map(() => null)
    let pk = 50
    let pd = 50
    for (let i = 0; i < rsv.length; i++) {
        const r = rsv[i]
        if (r == null) {
            k[i] = null
            d[i] = null
            j[i] = null
            continue
        }
        const nk = (2 * pk + r) / 3
        const nd = (2 * pd + nk) / 3
        k[i] = nk
        d[i] = nd
        j[i] = 3 * nk - 2 * nd
        pk = nk
        pd = nd
    }
    return { k, d, j }
}

export function calcRsi(closes: number[], period = 14): (number | null)[] {
    const out: (number | null)[] = closes.map(() => null)
    if (closes.length < period + 1) return out

    let sumGain = 0
    let sumLoss = 0
    for (let i = 1; i <= period; i++) {
        const ch = closes[i] - closes[i - 1]
        if (ch >= 0) sumGain += ch
        else sumLoss -= ch
    }
    let avgGain = sumGain / period
    let avgLoss = sumLoss / period
    const rs0 = avgLoss === 0 ? 100 : avgGain / avgLoss
    out[period] = 100 - 100 / (1 + rs0)

    for (let i = period + 1; i < closes.length; i++) {
        const ch = closes[i] - closes[i - 1]
        const g = ch > 0 ? ch : 0
        const l = ch < 0 ? -ch : 0
        avgGain = (avgGain * (period - 1) + g) / period
        avgLoss = (avgLoss * (period - 1) + l) / period
        const rs = avgLoss === 0 ? 100 : avgGain / avgLoss
        out[i] = 100 - 100 / (1 + rs)
    }
    return out
}

export function calcAtr(highs: number[], lows: number[], closes: number[], period = 14): (number | null)[] {
    const tr: number[] = []
    for (let i = 0; i < closes.length; i++) {
        if (i === 0) {
            tr.push(highs[i] - lows[i])
            continue
        }
        const a = highs[i] - lows[i]
        const b = Math.abs(highs[i] - closes[i - 1])
        const c = Math.abs(lows[i] - closes[i - 1])
        tr.push(Math.max(a, b, c))
    }
    const out: (number | null)[] = tr.map(() => null)
    let sum = 0
    for (let i = 0; i < period && i < tr.length; i++) sum += tr[i]
    if (tr.length >= period) {
        out[period - 1] = sum / period
        for (let i = period; i < tr.length; i++) {
            const prev = out[i - 1]
            if (prev == null) continue
            out[i] = ((prev * (period - 1) + tr[i]) / period)
        }
    }
    return out
}

export function calcObv(closes: number[], volumes: number[]): (number | null)[] {
    const out: (number | null)[] = []
    let obv = 0
    for (let i = 0; i < closes.length; i++) {
        const vol = volumes[i] ?? 0
        if (i === 0) {
            obv = vol
        } else if (closes[i] > closes[i - 1]) obv += vol
        else if (closes[i] < closes[i - 1]) obv -= vol
        out.push(obv)
    }
    return out
}

export function toLinePoints(dates: string[], values: (number | null)[]): SeriesPoint[] {
    return dates.map((d, i) => ({
        time: d.slice(0, 10),
        value: values[i] ?? null,
    })).filter((p) => p.value != null && Number.isFinite(p.value)) as SeriesPoint[]
}

/** 当日振幅(%) = (high - low) / pre_close * 100；pre_close 取上一根收盘 */
export function calcAmplitudePct(
    high: number | null | undefined,
    low: number | null | undefined,
    preClose: number | null | undefined,
): number | null {
    const h = Number(high)
    const l = Number(low)
    const p = Number(preClose)
    if (!Number.isFinite(h) || !Number.isFinite(l) || !Number.isFinite(p) || p === 0) return null
    return ((h - l) / p) * 100
}

/** 量比 = 当日成交量 / 过去 N 日的平均成交量（默认 5）。N 不足时返回 null。 */
export function calcVolumeRatio(volumes: number[], windowDays = 5): number | null {
    if (!Array.isArray(volumes) || volumes.length < windowDays + 1) return null
    const cur = Number(volumes[volumes.length - 1])
    if (!Number.isFinite(cur)) return null
    let sum = 0
    let cnt = 0
    for (let i = volumes.length - 1 - windowDays; i < volumes.length - 1; i++) {
        const v = Number(volumes[i])
        if (Number.isFinite(v)) {
            sum += v
            cnt += 1
        }
    }
    if (cnt === 0) return null
    const avg = sum / cnt
    if (avg === 0) return null
    return cur / avg
}

/** 黄金/死亡交叉信号识别：返回最近一次交叉的 idx 与方向（向上 = golden, 向下 = death）。 */
export function detectLastCross(
    fastSeries: (number | null)[],
    slowSeries: (number | null)[],
): { index: number; type: 'golden' | 'death' } | null {
    let last: { index: number; type: 'golden' | 'death' } | null = null
    for (let i = 1; i < fastSeries.length; i++) {
        const f1 = fastSeries[i - 1]
        const s1 = slowSeries[i - 1]
        const f2 = fastSeries[i]
        const s2 = slowSeries[i]
        if (f1 == null || s1 == null || f2 == null || s2 == null) continue
        if (f1 <= s1 && f2 > s2) last = { index: i, type: 'golden' }
        else if (f1 >= s1 && f2 < s2) last = { index: i, type: 'death' }
    }
    return last
}

/** MACD 状态：基于最近一根 DIF/DEA、柱体增减判定。 */
export function detectMacdState(
    dif: (number | null)[],
    dea: (number | null)[],
    macd: (number | null)[],
    sampleCount: number,
): {
    label: 'golden_recent' | 'death_recent' | 'bullish' | 'bearish' | 'neutral'
    text: string
    tone: 'bullish' | 'bearish' | 'neutral'
} {
    const last = macd[macd.length - 1]
    const prev = macd[macd.length - 2]
    if (last == null || prev == null) {
        // EMA12 + EMA26 + DEA9 ≈ 35 根才能算出完整 DEA
        return { label: 'neutral', text: `MACD 待 ≥35 根（当前 ${sampleCount}）`, tone: 'neutral' }
    }
    const cross = detectLastCross(dif, dea)
    const recentBars = macd.length - 1 - (cross?.index ?? -1)
    if (cross && recentBars >= 0 && recentBars <= 2) {
        return cross.type === 'golden'
            ? { label: 'golden_recent', text: 'MACD 金叉', tone: 'bullish' }
            : { label: 'death_recent', text: 'MACD 死叉', tone: 'bearish' }
    }
    if (last > 0 && last >= prev) return { label: 'bullish', text: 'MACD 多头放大', tone: 'bullish' }
    if (last > 0 && last < prev) return { label: 'bullish', text: 'MACD 多头收敛', tone: 'bullish' }
    if (last < 0 && last <= prev) return { label: 'bearish', text: 'MACD 空头放大', tone: 'bearish' }
    if (last < 0 && last > prev) return { label: 'bearish', text: 'MACD 空头收敛', tone: 'bearish' }
    return { label: 'neutral', text: 'MACD 走平', tone: 'neutral' }
}

/** KDJ 状态：超买/超卖优先；其次最近 2 根的金/死叉。 */
export function detectKdjState(
    k: (number | null)[],
    d: (number | null)[],
    sampleCount: number,
): {
    label: 'overbought' | 'oversold' | 'golden_recent' | 'death_recent' | 'bullish' | 'bearish' | 'neutral'
    text: string
    tone: 'bullish' | 'bearish' | 'neutral'
} {
    const lastK = k[k.length - 1]
    const lastD = d[d.length - 1]
    if (lastK == null || lastD == null) {
        return { label: 'neutral', text: `KDJ 待 ≥9 根（当前 ${sampleCount}）`, tone: 'neutral' }
    }
    if (lastK >= 80) return { label: 'overbought', text: `KDJ 超买 ${lastK.toFixed(0)}`, tone: 'bearish' }
    if (lastK <= 20) return { label: 'oversold', text: `KDJ 超卖 ${lastK.toFixed(0)}`, tone: 'bullish' }
    const cross = detectLastCross(k, d)
    if (cross && k.length - 1 - cross.index <= 2) {
        return cross.type === 'golden'
            ? { label: 'golden_recent', text: 'KDJ 金叉', tone: 'bullish' }
            : { label: 'death_recent', text: 'KDJ 死叉', tone: 'bearish' }
    }
    if (lastK > lastD) return { label: 'bullish', text: 'KDJ 偏多', tone: 'bullish' }
    if (lastK < lastD) return { label: 'bearish', text: 'KDJ 偏空', tone: 'bearish' }
    return { label: 'neutral', text: 'KDJ 走平', tone: 'neutral' }
}

/** RSI 状态：>70 超买，<30 超卖，其它强/弱/中性。period=14 RSI 输入数组。 */
export function detectRsiState(
    rsi: (number | null)[],
    sampleCount: number,
): { label: 'overbought' | 'oversold' | 'strong' | 'weak' | 'neutral'; text: string; tone: 'bullish' | 'bearish' | 'neutral' } {
    const last = rsi[rsi.length - 1]
    if (last == null) {
        return { label: 'neutral', text: `RSI 待 ≥15 根（当前 ${sampleCount}）`, tone: 'neutral' }
    }
    if (last >= 70) return { label: 'overbought', text: `RSI ${last.toFixed(0)} 超买`, tone: 'bearish' }
    if (last <= 30) return { label: 'oversold', text: `RSI ${last.toFixed(0)} 超卖`, tone: 'bullish' }
    if (last >= 55) return { label: 'strong', text: `RSI ${last.toFixed(0)} 偏强`, tone: 'bullish' }
    if (last <= 45) return { label: 'weak', text: `RSI ${last.toFixed(0)} 偏弱`, tone: 'bearish' }
    return { label: 'neutral', text: `RSI ${last.toFixed(0)} 中性`, tone: 'neutral' }
}

/** 均线多空头排列识别（基于 MA5/MA10/MA20）。 */
export function detectMaState(
    ma5: (number | null)[],
    ma10: (number | null)[],
    ma20: (number | null)[],
    sampleCount: number,
): { label: 'bull_array' | 'bear_array' | 'mixed'; text: string; tone: 'bullish' | 'bearish' | 'neutral' } {
    const a = ma5[ma5.length - 1]
    const b = ma10[ma10.length - 1]
    const c = ma20[ma20.length - 1]
    if (a == null || b == null || c == null) {
        return { label: 'mixed', text: `MA20 待 ≥20 根（当前 ${sampleCount}）`, tone: 'neutral' }
    }
    if (a > b && b > c) return { label: 'bull_array', text: 'MA 多头排列', tone: 'bullish' }
    if (a < b && b < c) return { label: 'bear_array', text: 'MA 空头排列', tone: 'bearish' }
    return { label: 'mixed', text: 'MA 交错', tone: 'neutral' }
}
