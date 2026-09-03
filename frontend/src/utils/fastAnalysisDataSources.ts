import type { DataSourceBundle, DataSourceItem, DataSourceStatus } from '@/types'

export const FAST_FEATURE_SLOT_COUNT = 22

/** 与后端 `data_snapshot.collect_snapshot` 展示顺序对齐：日K / RT / 竞价优先 */
export const FAST_SNAPSHOT_SOURCE_ORDER = [
    'kline_60d',
    'rt_k',
    'auction',
    'factor',
    'mins',
    'moneyflow',
    'industry_flow',
    'index_pulse',
    'basic',
    'anns',
    'limit_list',
    'top_list',
] as const

const DISPLAY_NAME: Record<string, string> = {
    rt_k: '实时行情 rt_k',
    index_pulse: '大盘指数 index_realtime',
    mins: '分钟K线 stk_mins',
    moneyflow: '个股资金流 moneyflow_dc',
    industry_flow: '行业资金流 moneyflow_industry_dc',
    factor: '技术因子 stk_factor_pro',
    top_list: '龙虎榜 top_list',
    limit_list: '涨停池 limit_list_d',
    anns: '公告 anns_d',
    basic: '估值 daily_basic',
    kline_60d: '60 日日K kline',
    auction: '集合竞价 stk_auction',
}

const CATEGORY: Record<string, string> = {
    kline_60d: 'K 线 / 技术',
    rt_k: '当日行情',
    auction: '集合竞价',
    factor: '技术因子',
    mins: '分时',
    moneyflow: '资金面',
    industry_flow: '行业',
    index_pulse: '大盘',
    basic: '基本面',
    anns: '公告',
    limit_list: '涨跌停',
    top_list: '龙虎榜',
}

const ORDER_RANK = new Map<string, number>(FAST_SNAPSHOT_SOURCE_ORDER.map((k, i) => [k, i]))

export function sortFastSnapshotSources<T extends { key: string }>(rows: T[]): T[] {
    return [...rows].sort((a, b) => (ORDER_RANK.get(a.key) ?? 99) - (ORDER_RANK.get(b.key) ?? 99))
}

export function buildFastAnalysisDataSourceBundle(
    snapshot: Record<string, unknown> | null | undefined,
    detail: { symbol: string; trade_date: string; created_at?: string | null; finished_at?: string | null },
): DataSourceBundle | null {
    if (!snapshot || typeof snapshot !== 'object') return null
    const raw = snapshot.sources
    if (!raw || typeof raw !== 'object') return null

    const sourcesObj = raw as Record<string, { status?: string; latency_ms?: number; data?: unknown[]; error?: string; hint?: string }>
    const items: DataSourceItem[] = []

    for (const [key, payload] of Object.entries(sourcesObj)) {
        const latency = typeof payload.latency_ms === 'number' ? payload.latency_ms : null
        const st = String(payload.status || '')
        const backendHint = typeof payload.hint === 'string' && payload.hint.trim() ? payload.hint : ''
        // 状态映射（与智能分析共享 DataSourceStatus）：
        //   ok + rows>0  → hit   命中
        //   ok + rows=0  → hit   命中（接口成功但当日无该项数据，UI 在 detail 里说明 0 行原因，
        //                          避免把「空命中」误标为「降级」）
        //   skipped       → internal  跳过（如非交易日的集合竞价）
        //   unsupported_channel → unsupported_channel（产品未开通/需专用通道）
        //   timeout/unavailable → error
        let status: DataSourceStatus = 'error'
        if (st === 'skipped') status = 'internal'
        else if (st === 'unsupported_channel') status = 'unsupported_channel'
        else if (st === 'ok') status = 'hit'
        else if (st === 'timeout' || st === 'unavailable') status = 'error'

        const previewRows = Array.isArray(payload.data) ? payload.data.slice(0, 8) : []
        let detail_preview: string | null = null
        try {
            const body = previewRows.length
                ? previewRows
                : {
                      _status: st,
                      _hint:
                          backendHint ||
                          (st === 'ok'
                              ? '接口调用成功，但本日 0 行 — 该标的当日无此类数据（例如：未上龙虎榜 / 未涨跌停 / 无公告 / 行业聚合接口当日无更新），不是降级。'
                              : st === 'skipped'
                              ? '已跳过（如非交易日或非 9:25 后的集合竞价）'
                              : st === 'unsupported_channel'
                              ? '该数据产品未在当前权限内启用'
                              : '调用失败'),
                      err: payload.error,
                  }
            detail_preview = JSON.stringify(body, null, 2).slice(0, 12000)
        } catch {
            detail_preview = String(payload.error || st)
        }

        const errMsg =
            st === 'timeout' || st === 'unavailable' ? String(payload.error || st) : null

        items.push({
            key: `fast-${key}`,
            display_name: DISPLAY_NAME[key] || key,
            category: CATEGORY[key] || '快速分析',
            vendor: 'cn_tushare',
            vendor_display: 'Tushare Pro（快速分析直连）',
            status,
            fetched_at: (detail.finished_at || detail.created_at || new Date().toISOString()) as string,
            latency_ms: latency,
            error: errMsg,
            method: key,
            detail_preview,
        })
    }

    items.sort((a, b) => (ORDER_RANK.get(String(a.method)) ?? 99) - (ORDER_RANK.get(String(b.method)) ?? 99))

    const totalLatency =
        typeof snapshot.elapsed_ms === 'number'
            ? (snapshot.elapsed_ms as number)
            : items.reduce((s, i) => s + (i.latency_ms || 0), 0)

    return {
        generated_at: (detail.finished_at || detail.created_at || new Date().toISOString()) as string,
        total_latency_ms: totalLatency,
        items,
    }
}

/** 采集中 `snapshot_json.sources` 尚未落库时，用进度里的 sources 列表生成可弹窗的明细（预览较简） */
export function buildFastAnalysisDataSourceBundleFromProgress(
    progress: { sources?: Array<{ key: string; label: string; status: string; latency_ms?: number; rows?: number }> },
    detail: { symbol: string; trade_date: string; created_at?: string | null; finished_at?: string | null },
): DataSourceBundle | null {
    const rows = progress.sources || []
    if (!rows.length) return null
    const items: DataSourceItem[] = rows.map((s) => {
        const st = String(s.status || '')
        const r = s.rows ?? 0
        let status: DataSourceStatus = 'error'
        if (st === 'skipped') status = 'internal'
        else if (st === 'unsupported_channel') status = 'unsupported_channel'
        else if (st === 'ok') status = 'hit'
        else if (st === 'timeout' || st === 'unavailable') status = 'error'
        const hint =
            st === 'ok' && r === 0
                ? '接口调用成功，但本日 0 行 — 该标的当日无此类数据（例如未上龙虎榜 / 未涨跌停 / 无公告）。'
                : st === 'skipped'
                ? '已跳过（如非交易日或非 9:25 后的集合竞价）'
                : st === 'unsupported_channel'
                ? '该数据产品未在当前权限内启用'
                : ''
        return {
            key: `fast-${s.key}`,
            display_name: s.label || s.key,
            category: CATEGORY[s.key] || '快速分析',
            vendor: 'cn_tushare',
            vendor_display: 'Tushare Pro（快速分析直连）',
            status,
            fetched_at: (detail.finished_at || detail.created_at || new Date().toISOString()) as string,
            latency_ms: typeof s.latency_ms === 'number' ? s.latency_ms : null,
            error: st === 'timeout' || st === 'unavailable' ? st : null,
            method: s.key,
            detail_preview: JSON.stringify({ rows: r, status: st, hint }, null, 2),
        }
    })
    items.sort((a, b) => (ORDER_RANK.get(String(a.method)) ?? 99) - (ORDER_RANK.get(String(b.method)) ?? 99))
    const totalLatency = items.reduce((acc, i) => acc + (i.latency_ms || 0), 0)
    return {
        generated_at: (detail.finished_at || detail.created_at || new Date().toISOString()) as string,
        total_latency_ms: totalLatency,
        items,
    }
}
