import type { AnalysisRequest, AnalysisResponse, Announcement, AuthUser, AuthVerifyResponse, JobStatus, AnalysisReport, KlineResponse, KlinePeriod, KlineAdjust, ChartInsightRequestPayload, ChartInsightResponsePayload, LatestAnnouncementResponse, PortfolioImportState, PortfolioOverviewResponse, PortfolioPositionInput, Report, ReportDetail, ReportListResponse, RuntimeConfig, RuntimeConfigUpdate, RuntimeConfigUpdateResponse, RuntimeWarmupRequest, RuntimeWarmupResponse, WatchlistItem, WatchlistBatchResponse, ScheduledAnalysis, ScheduledBatchTriggerResponse, StockSearchResult, TrackingBoardResponse, UserToken, UserTokenCreateRequest, WecomWarmupRequest, WecomWarmupResponse, FeedbackItem, FeedbackListResponse, FeedbackUnreadResponse, RealtimeQuoteResponse, RtBoardResponse, RtDailyResponse, UserEntitlements, TaskCenterListResponse, TaskSubmitResponse, FastAnalyzeRequest, FastAnalyzeResponse, FastAnalysisDetail, FastRiskProfile, ChartAuctionResponse, ChartCyqResponse, ChartSeriesResponse, OutcomeGroupBy, ReportOutcomeDetail, ReportOutcomeSummaryResponse, QlibEvalGateSummaryResponse, LlmCatalogResponse, SystemVersionResponse, JobCheckpointStatus } from '@/types'
import { formatApiErrorDetail } from '@/lib/apiErrorZh'

export type AdminDateRangeParams = { start_date?: string; end_date?: string; grain?: 'day' | 'hour' }

function isLoopbackHost(hostname: string): boolean {
    return hostname === 'localhost' || hostname === '127.0.0.1'
}

/** 典型局域网 IPv4（RFC1918），用于预览/直连 API 时推断宿主机上的 FastAPI 端口。 */
function looksLikeLanIPv4(hostname: string): boolean {
    const m = /^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$/.exec(hostname)
    if (!m) return false
    const a = Number(m[1])
    const b = Number(m[2])
    if (a === 10) return true
    if (a === 172 && b >= 16 && b <= 31) return true
    if (a === 192 && b === 168) return true
    return false
}

/** 页面通过局域网 IP 打开时，将 VITE_API_URL 中的 localhost/127.0.0.1 换成当前页 hostname，避免请求打到用户设备本机。 */
function normalizeLoopbackApiForLan(apiBase: string): string {
    const trimmed = apiBase.replace(/\/$/, '')
    if (typeof window === 'undefined') return trimmed
    const pageHost = window.location.hostname
    if (isLoopbackHost(pageHost)) return trimmed
    try {
        const u = new URL(trimmed)
        if (!isLoopbackHost(u.hostname)) return trimmed
        u.hostname = pageHost
        return u.toString().replace(/\/$/, '')
    } catch {
        return trimmed
    }
}

function defaultLocalApiBase(): string {
    return (import.meta.env.VITE_LOCAL_API_URL as string) || (import.meta.env.VITE_API_URL as string) || 'http://127.0.0.1:8001'
}

export function getBaseUrl(): string {
    const envUrl = (import.meta.env.VITE_API_URL as string) || ''
    const devDirect =
        import.meta.env.VITE_DEV_API_DIRECT === '1' || import.meta.env.VITE_DEV_API_DIRECT === 'true'
    // In `vite dev`, prefer same-origin `/v1` so devServer proxy reaches the API. This avoids CORS when
    // the page is opened via a LAN IP (e.g. http://192.168.x.x:5173) while VITE_API_URL points at localhost:8000.
    if (import.meta.env.DEV && !devDirect) {
        return ''
    }
    if (envUrl) {
        return normalizeLoopbackApiForLan(envUrl.replace(/\/$/, ''))
    }
    if (typeof window !== 'undefined' && window.location) {
        const h = window.location.hostname
        // 生产构建在 localhost 预览/本地静态服务时，页面 origin 上没有 API，沿用同源会得到 405；默认直连本机 FastAPI。
        if (!import.meta.env.DEV && isLoopbackHost(h)) {
            const port = window.location.port
            // Golden path: uvicorn hosts SPA + API on 8000. Do not send XHR to 8001.
            if (port === '8000' || port === '80' || port === '') {
                return window.location.origin.replace(/\/$/, '')
            }
            return normalizeLoopbackApiForLan(defaultLocalApiBase())
        }
        // 预览/静态站通过局域网 IP 访问且未配置 VITE_API_URL 时，同源是前端端口；假定 API 与页面同主机 :8000（需 uvicorn 监听 0.0.0.0）。
        if (!import.meta.env.DEV && looksLikeLanIPv4(h)) {
            return normalizeLoopbackApiForLan(defaultLocalApiBase())
        }
        if (window.location.origin && window.location.origin !== 'null') {
            return window.location.origin.replace(/\/$/, '')
        }
    }
    return defaultLocalApiBase()
}


function getAuthToken(): string | null {
    try {
        return localStorage.getItem('ta-access-token')
    } catch {
        return null
    }
}

class ApiService {
    private async request<T>(endpoint: string, options?: RequestInit): Promise<T> {
        const url = `${getBaseUrl()}${endpoint}`
        const token = getAuthToken()
        const response = await fetch(url, {
            ...options,
            headers: {
                'Content-Type': 'application/json',
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
                ...options?.headers,
            },
        })

        if (!response.ok) {
            const contentType = response.headers.get('content-type') || ''
            if (contentType.includes('application/json')) {
                const data = await response.json().catch(() => null)
                const detail = data?.detail || data?.message
                const msg = formatApiErrorDetail(detail || `HTTP error! status: ${response.status}`)
                if (response.status === 405) {
                    if (endpoint === '/v1/market/chart/insight') {
                        throw new Error(
                            `${msg}。解读接口需 POST 到后端 /v1/market/chart/insight；若使用静态托管或未代理 /v1，请设置 VITE_API_URL 指向 API，或用 vite dev / 配置 Nginx 反代。`,
                        )
                    }
                    throw new Error(
                        `${msg}。接口 ${endpoint} 返回 405：请确认后端已更新并重启，且 /v1 已正确反向代理到 FastAPI。`,
                    )
                }
                throw new Error(msg)
            }
            const error = await response.text()
            const base = error || `HTTP error! status: ${response.status}`
            if (response.status === 405) {
                if (endpoint === '/v1/market/chart/insight') {
                    throw new Error(
                        `${base}。解读接口需 POST 到后端；静态站未转发 /v1 时常出现此错误，请设置 VITE_API_URL 或反向代理 /v1。`,
                    )
                }
                throw new Error(
                    `${base}。接口 ${endpoint} 返回 405：请确认后端已更新并重启，且 /v1 已正确反向代理到 FastAPI。`,
                )
            }
            throw new Error(base)
        }

        if (response.status === 204 || response.status === 205) {
            return undefined as T
        }

        const contentType = response.headers.get('content-type') || ''
        if (!contentType.includes('application/json')) {
            const text = await response.text()
            if (endpoint.startsWith('/v1/') && /<html|<!doctype/i.test(text.slice(0, 200))) {
                throw new Error(
                    'API 返回了前端页面而不是 JSON：请确认后端已启动，并且 /v1 已正确代理到 FastAPI。',
                )
            }
            return (text ? (text as T) : undefined) as T
        }

        const raw = await response.text()
        if (!raw) {
            return undefined as T
        }

        return JSON.parse(raw) as T
    }

    async startAnalysis(request: AnalysisRequest): Promise<AnalysisResponse> {
        return this.request<AnalysisResponse>('/v1/analyze', {
            method: 'POST',
            body: JSON.stringify(request),
        })
    }

    async startFastAnalysis(request: FastAnalyzeRequest): Promise<FastAnalyzeResponse> {
        return this.request<FastAnalyzeResponse>('/v1/analyze/fast', {
            method: 'POST',
            body: JSON.stringify(request),
        })
    }

    async getFastAnalysis(id: string): Promise<FastAnalysisDetail> {
        return this.request<FastAnalysisDetail>(`/v1/fast-analyses/${id}`)
    }

    async getRecentFastAnalyses(symbol?: string, limit = 20): Promise<{ items: FastAnalysisDetail[] }> {
        const q = new URLSearchParams()
        if (symbol) q.set('symbol', symbol)
        q.set('limit', String(limit))
        return this.request<{ items: FastAnalysisDetail[] }>(`/v1/fast-analyses/recent?${q.toString()}`)
    }

    async getFastRiskProfile(): Promise<FastRiskProfile> {
        return this.request<FastRiskProfile>('/v1/user/risk-profile')
    }

    async setFastRiskProfile(body: FastRiskProfile): Promise<FastRiskProfile> {
        return this.request<FastRiskProfile>('/v1/user/risk-profile', {
            method: 'PUT',
            body: JSON.stringify(body),
        })
    }

    async getJobStatus(jobId: string): Promise<JobStatus> {
        return this.request<JobStatus>(`/v1/jobs/${jobId}`)
    }

    async cancelAnalysisJob(jobId: string): Promise<{ status: string; job_id: string }> {
        return this.request(`/v1/jobs/${jobId}/cancel`, { method: 'POST' })
    }

    async getJobResult(jobId: string): Promise<{ job_id: string; status: string; decision: string; result: AnalysisReport }> {
        return this.request(`/v1/jobs/${jobId}/result`)
    }

    async listMyTasks(): Promise<TaskCenterListResponse> {
        return this.request<TaskCenterListResponse>('/v1/me/tasks')
    }

    async submitAnalysisTask(payload: {
        text: string
        selected_analysts?: string[]
        config_overrides?: Record<string, unknown>
        dry_run?: boolean
        objective?: string
        risk_profile?: string
        investment_horizon?: string
        cash_available?: number
        current_position?: number
        current_position_pct?: number
        average_cost?: number
        max_loss_pct?: number
        constraints?: string[]
        user_notes?: string
    }): Promise<TaskSubmitResponse> {
        return this.request<TaskSubmitResponse>('/v1/me/tasks/submit', {
            method: 'POST',
            body: JSON.stringify(payload),
        })
    }

    async reorderMyTasks(job_ids: string[]): Promise<{ ok: boolean; job_id: string; status: string; detail?: string }> {
        return this.request('/v1/me/tasks/reorder', {
            method: 'PATCH',
            body: JSON.stringify({ job_ids }),
        })
    }

    async pauseQueueTask(jobId: string): Promise<{ ok: boolean; job_id: string; status: string; detail?: string }> {
        return this.request(`/v1/me/tasks/${jobId}/pause`, { method: 'POST' })
    }

    async resumeQueueTask(jobId: string): Promise<{ ok: boolean; job_id: string; status: string; detail?: string }> {
        return this.request(`/v1/me/tasks/${jobId}/resume`, { method: 'POST' })
    }

    async cancelQueueTask(jobId: string): Promise<{ ok: boolean; job_id: string; status: string; detail?: string }> {
        return this.request(`/v1/me/tasks/${jobId}`, { method: 'DELETE' })
    }

    async deleteTaskRecord(jobId: string): Promise<{ ok: boolean; job_id: string; status: string; detail?: string }> {
        return this.request(`/v1/me/tasks/${jobId}/record`, { method: 'DELETE' })
    }

    /** Same SSE event stream as chat completions; use to resume after fetch disconnect. */
    async openJobEventStream(jobId: string, afterSeq?: number): Promise<Response> {
        const q =
            typeof afterSeq === 'number' && afterSeq > 0 ? `?after=${encodeURIComponent(String(afterSeq))}` : ''
        const headers: Record<string, string> = {
            ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
        }
        if (typeof afterSeq === 'number' && afterSeq > 0) {
            headers['Last-Event-ID'] = String(afterSeq)
        }
        const response = await fetch(`${getBaseUrl()}/v1/jobs/${jobId}/events${q}`, {
            headers,
        })
        if (!response.ok) {
            throw new Error(`job events HTTP ${response.status}`)
        }
        return response
    }

    async getKline(
        symbol: string,
        startDate?: string,
        endDate?: string,
        options?: { period?: KlinePeriod; adjust?: KlineAdjust; signal?: AbortSignal },
    ): Promise<KlineResponse> {
        const params = new URLSearchParams({ symbol })
        if (startDate) params.append('start_date', startDate)
        if (endDate) params.append('end_date', endDate)
        if (options?.period) params.append('period', options.period)
        if (options?.adjust) params.append('adjust', options.adjust)
        const fallbackSignal =
            typeof AbortSignal !== 'undefined' && 'timeout' in AbortSignal && !options?.signal
                ? AbortSignal.timeout(90_000)
                : undefined
        const signal = options?.signal ?? fallbackSignal
        return this.request<KlineResponse>(`/v1/market/kline?${params}`, { signal })
    }

    async getRealtimeQuotes(symbols: string[]): Promise<RealtimeQuoteResponse> {
        return this.request<RealtimeQuoteResponse>('/v1/market/quotes', {
            method: 'POST',
            cache: 'no-store',
            body: JSON.stringify({ symbols }),
        })
    }

    async getUserEntitlements(options?: { signal?: AbortSignal }): Promise<UserEntitlements> {
        return this.request<UserEntitlements>('/v1/users/entitlements', { signal: options?.signal })
    }

    async getMarketIntraday(symbol: string): Promise<Record<string, unknown>> {
        const q = new URLSearchParams({ symbol })
        return this.request<Record<string, unknown>>(`/v1/market/intraday?${q}`)
    }

    async getMarketOrderbook(symbol: string): Promise<Record<string, unknown>> {
        const q = new URLSearchParams({ symbol })
        return this.request<Record<string, unknown>>(`/v1/market/orderbook?${q}`)
    }

    async getMarketTrades(symbol: string, limit = 40): Promise<Record<string, unknown>> {
        const q = new URLSearchParams({ symbol, limit: String(limit) })
        return this.request<Record<string, unknown>>(`/v1/market/trades?${q}`)
    }

    async getMarketCompanyProfile(symbol: string): Promise<Record<string, unknown>> {
        const q = new URLSearchParams({ symbol })
        return this.request<Record<string, unknown>>(`/v1/market/company-profile?${q}`)
    }

    async getRtDaily(symbols: string[]): Promise<RtDailyResponse> {
        const q = new URLSearchParams({ symbols: symbols.join(',') })
        return this.request<RtDailyResponse>(`/v1/market/rt-daily?${q}`)
    }

    async getRtBoard(pattern: string, sort: 'change_pct' | 'change' | 'amount' | 'vol' = 'change_pct', limit = 50): Promise<RtBoardResponse> {
        const q = new URLSearchParams({ pattern, sort, limit: String(limit) })
        return this.request<RtBoardResponse>(`/v1/market/rt-board?${q}`)
    }

    async getChartAuction(symbol: string): Promise<ChartAuctionResponse> {
        const q = new URLSearchParams({ symbol })
        return this.request<ChartAuctionResponse>(`/v1/market/chart/auction?${q}`)
    }

    async getChartCyq(symbol: string, days = 60): Promise<ChartCyqResponse> {
        const q = new URLSearchParams({ symbol, days: String(days) })
        return this.request<ChartCyqResponse>(`/v1/market/chart/cyq?${q}`)
    }

    async getChartMoneyflow(symbol: string, days = 90): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, days: String(days) })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/moneyflow?${q}`)
    }

    async getChartFactorPro(symbol: string, days = 120): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, days: String(days) })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/factor-pro?${q}`)
    }

    async getChartDailyBasic(symbol: string, days = 90): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, days: String(days) })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/daily-basic?${q}`)
    }

    async getChartEvents(symbol: string, start: string, end: string): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, start, end })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/events?${q}`)
    }

    async getChartHsgt(symbol: string, days = 90): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, days: String(days) })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/hsgt?${q}`)
    }

    async getChartCorpEvents(symbol: string, start: string, end: string): Promise<ChartSeriesResponse> {
        const q = new URLSearchParams({ symbol, start, end })
        return this.request<ChartSeriesResponse>(`/v1/market/chart/corp-events?${q}`)
    }

    async chartInsight(
        body: ChartInsightRequestPayload,
        options?: { signal?: AbortSignal },
    ): Promise<ChartInsightResponsePayload> {
        const signal = options?.signal ?? (typeof AbortSignal !== 'undefined' ? AbortSignal.timeout(72_000) : undefined)
        return this.request<ChartInsightResponsePayload>('/v1/market/chart/insight', {
            method: 'POST',
            body: JSON.stringify(body),
            signal,
        })
    }

    async chatCompletion(
        messages: Array<{ role: string; content: string }>,
        stream = true,
        selectedAnalysts?: string[],
    ) {
        const response = await fetch(`${getBaseUrl()}/v1/chat/completions`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(getAuthToken() ? { Authorization: `Bearer ${getAuthToken()}` } : {}),
            },
            body: JSON.stringify({
                messages,
                stream,
                selected_analysts: selectedAnalysts,
            }),
        })

        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`)
        }

        return response
    }

    // Report API Methods
    async getReports(
        symbol?: string,
        skip = 0,
        limit = 100,
        taskKind?: 'full_analysis' | 'fast_analysis',
    ): Promise<ReportListResponse> {
        const params = new URLSearchParams()
        if (symbol) params.append('symbol', symbol)
        if (taskKind) params.append('task_kind', taskKind)
        params.append('skip', skip.toString())
        params.append('limit', limit.toString())
        return this.request<ReportListResponse>(`/v1/reports?${params}`, { cache: 'no-store' })
    }

    async getLatestReportsBySymbols(symbols: string[]): Promise<{ reports: Report[] }> {
        return this.request<{ reports: Report[] }>('/v1/reports/latest-by-symbols', {
            method: 'POST',
            body: JSON.stringify({ symbols }),
        })
    }

    async getReport(reportId: string): Promise<ReportDetail> {
        return this.request<ReportDetail>(`/v1/reports/${reportId}`)
    }

    async getReportOutcome(reportId: string): Promise<ReportOutcomeDetail> {
        return this.request<ReportOutcomeDetail>(`/v1/reports/${reportId}/outcome`, { cache: 'no-store' })
    }

    async getReportOutcomeSummary(params?: {
        taskKind?: 'full_analysis' | 'fast_analysis'
        sinceDays?: number
        groupBy?: OutcomeGroupBy
    }): Promise<ReportOutcomeSummaryResponse> {
        const u = new URLSearchParams()
        if (params?.taskKind) u.append('task_kind', params.taskKind)
        if (typeof params?.sinceDays === 'number') u.append('since_days', String(params.sinceDays))
        if (params?.groupBy) u.append('group_by', params.groupBy)
        const q = u.toString()
        return this.request<ReportOutcomeSummaryResponse>(`/v1/reports/outcomes/summary${q ? `?${q}` : ''}`, { cache: 'no-store' })
    }

    async getQlibEvalGates(params?: { sinceDays?: number }): Promise<QlibEvalGateSummaryResponse> {
        const u = new URLSearchParams()
        if (typeof params?.sinceDays === 'number') u.append('since_days', String(params.sinceDays))
        const q = u.toString()
        return this.request<QlibEvalGateSummaryResponse>(`/v1/qlib-eval/gates${q ? `?${q}` : ''}`, { cache: 'no-store' })
    }

    async getLatestAnnouncement(): Promise<Announcement | null> {
        const data = await this.request<LatestAnnouncementResponse>('/v1/announcements/latest')
        return data.announcement
    }

    async deleteReport(reportId: string): Promise<{ message: string }> {
        return this.request<{ message: string }>(`/v1/reports/${reportId}`, {
            method: 'DELETE',
        })
    }


    async createReport(report: {
        symbol: string
        trade_date: string
        decision?: string
        result_data?: AnalysisReport
    }): Promise<Report> {
        return this.request<Report>('/v1/reports', {
            method: 'POST',
            body: JSON.stringify(report),
        })
    }

    // Watchlist
    async getWatchlist(): Promise<{ items: WatchlistItem[] }> {
        return this.request<{ items: WatchlistItem[] }>('/v1/watchlist')
    }
    async addToWatchlist(input: string): Promise<WatchlistBatchResponse> {
        return this.request<WatchlistBatchResponse>('/v1/watchlist', {
            method: 'POST',
            body: JSON.stringify({ text: input }),
        })
    }
    async removeFromWatchlist(id: string): Promise<void> {
        await this.request('/v1/watchlist/' + id, { method: 'DELETE' })
    }

    // Scheduled Analysis
    async getScheduled(): Promise<{ items: ScheduledAnalysis[] }> {
        return this.request<{ items: ScheduledAnalysis[] }>('/v1/scheduled')
    }
    async getPortfolioOverview(): Promise<PortfolioOverviewResponse> {
        return this.request<PortfolioOverviewResponse>('/v1/portfolio/overview')
    }
    async createScheduled(symbol: string, horizon?: string, trigger_time?: string): Promise<ScheduledAnalysis> {
        return this.request<ScheduledAnalysis>('/v1/scheduled', {
            method: 'POST',
            body: JSON.stringify({ symbol, horizon, trigger_time }),
        })
    }
    async updateScheduled(id: string, data: { is_active?: boolean; horizon?: string; trigger_time?: string }): Promise<ScheduledAnalysis> {
        return this.request<ScheduledAnalysis>('/v1/scheduled/' + id, {
            method: 'PATCH',
            body: JSON.stringify(data),
        })
    }
    async updateScheduledBatch(
        item_ids: string[],
        data: { is_active?: boolean; horizon?: string; trigger_time?: string }
    ): Promise<{ items: ScheduledAnalysis[] }> {
        return this.request<{ items: ScheduledAnalysis[] }>('/v1/scheduled/batch', {
            method: 'PATCH',
            body: JSON.stringify({ item_ids, ...data }),
        })
    }
    async deleteScheduled(id: string): Promise<void> {
        await this.request('/v1/scheduled/' + id, { method: 'DELETE' })
    }
    async deleteScheduledBatch(item_ids: string[]): Promise<{ deleted_ids: string[]; missing_ids: string[] }> {
        return this.request<{ deleted_ids: string[]; missing_ids: string[] }>('/v1/scheduled/batch/delete', {
            method: 'POST',
            body: JSON.stringify({ item_ids }),
        })
    }
    async triggerScheduledTest(id: string): Promise<AnalysisResponse> {
        return this.request<AnalysisResponse>(`/v1/scheduled/${id}/trigger`, {
            method: 'POST',
        })
    }
    async triggerScheduledBatch(item_ids: string[]): Promise<ScheduledBatchTriggerResponse> {
        return this.request<ScheduledBatchTriggerResponse>('/v1/scheduled/batch/trigger', {
            method: 'POST',
            body: JSON.stringify({ item_ids }),
        })
    }

    async getPortfolioImportState(): Promise<PortfolioImportState> {
        return this.request<PortfolioImportState>('/v1/portfolio/imports')
    }

    async syncPortfolioImport(data: {
        positions: PortfolioPositionInput[]
        source?: string
        auto_apply_scheduled: boolean
    }): Promise<PortfolioImportState> {
        return this.request<PortfolioImportState>('/v1/portfolio/imports', {
            method: 'POST',
            body: JSON.stringify(data),
        })
    }

    async clearPortfolioImport(): Promise<void> {
        await this.request('/v1/portfolio/imports', { method: 'DELETE' })
    }

    async parsePositionImage(file: File): Promise<{ positions: PortfolioPositionInput[] }> {
        const formData = new FormData()
        formData.append('file', file)
        const url = `${getBaseUrl()}/v1/portfolio/parse-image`
        const token = getAuthToken()
        const response = await fetch(url, {
            method: 'POST',
            headers: {
                ...(token ? { Authorization: `Bearer ${token}` } : {}),
            },
            body: formData,
        })
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: response.statusText }))
            throw new Error(error.detail || '图片解析失败')
        }
        return response.json()
    }

    async getDashboardTrackingBoard(): Promise<TrackingBoardResponse> {
        return this.request<TrackingBoardResponse>('/v1/dashboard/tracking-board', {
            cache: 'no-store',
        })
    }

    // Stock Search
    async searchStocks(q: string, signal?: AbortSignal): Promise<{ results: StockSearchResult[] }> {
        return this.request<{ results: StockSearchResult[] }>(`/v1/market/stock-search?q=${encodeURIComponent(q)}`, {
            signal,
        })
    }

    async getConfig(): Promise<RuntimeConfig> {
        return this.request<RuntimeConfig>('/v1/config')
    }

    async getLlmCatalog(): Promise<LlmCatalogResponse> {
        return this.request<LlmCatalogResponse>('/v1/llm/catalog')
    }

    async getSystemVersion(): Promise<SystemVersionResponse> {
        return this.request<SystemVersionResponse>('/v1/system/version')
    }

    async getJobCheckpoint(jobId: string): Promise<JobCheckpointStatus> {
        return this.request<JobCheckpointStatus>(`/v1/jobs/${encodeURIComponent(jobId)}/checkpoint`)
    }

    async deleteJobCheckpoint(jobId: string): Promise<{ ok: boolean }> {
        return this.request<{ ok: boolean }>(`/v1/jobs/${encodeURIComponent(jobId)}/checkpoint`, {
            method: 'DELETE',
        })
    }

    async updateConfig(updates: RuntimeConfigUpdate): Promise<RuntimeConfigUpdateResponse> {
        return this.request<RuntimeConfigUpdateResponse>('/v1/config', {
            method: 'PATCH',
            body: JSON.stringify(updates),
        })
    }

    async warmupConfig(request: RuntimeWarmupRequest): Promise<RuntimeWarmupResponse> {
        return this.request<RuntimeWarmupResponse>('/v1/config/warmup', {
            method: 'POST',
            body: JSON.stringify(request),
        })
    }

    async warmupWecom(request: WecomWarmupRequest): Promise<WecomWarmupResponse> {
        return this.request<WecomWarmupResponse>('/v1/config/wecom/warmup', {
            method: 'POST',
            body: JSON.stringify(request),
        })
    }

    async getCaptcha(): Promise<{ captcha_id: string; image: string; enabled?: boolean }> {
        return this.request('/v1/auth/captcha')
    }

    async checkUsername(username: string): Promise<{ available: boolean }> {
        return this.request(`/v1/auth/check-username?username=${encodeURIComponent(username)}`)
    }

    async register(body: {
        username: string
        email: string
        password: string
        phone?: string
        display_name?: string
    }): Promise<AuthVerifyResponse> {
        return this.request('/v1/auth/register', { method: 'POST', body: JSON.stringify(body) })
    }

    async login(body: { identifier: string; password: string }): Promise<AuthVerifyResponse> {
        return this.request('/v1/auth/login', { method: 'POST', body: JSON.stringify(body) })
    }

    async getMe(options?: { signal?: AbortSignal }): Promise<AuthUser> {
        return this.request<AuthUser>('/v1/auth/me', { signal: options?.signal })
    }

    async forgotPassword(body: { email: string }): Promise<Record<string, unknown>> {
        return this.request('/v1/auth/forgot-password', { method: 'POST', body: JSON.stringify(body) })
    }

    async resetPassword(token: string, new_password: string): Promise<{ message: string }> {
        return this.request('/v1/auth/reset-password', {
            method: 'POST',
            body: JSON.stringify({ token, new_password }),
        })
    }

    async changePassword(old_password: string, new_password: string): Promise<{ message: string }> {
        return this.request('/v1/users/me/change-password', {
            method: 'POST',
            body: JSON.stringify({ old_password, new_password }),
        })
    }

    async patchMe(body: { email?: string; display_name?: string; phone?: string }): Promise<{ message: string }> {
        return this.request('/v1/users/me', { method: 'PATCH', body: JSON.stringify(body) })
    }

    async getBillingPlans(): Promise<
        {
            id: string
            code: string
            name: string
            price_cents: number
            currency: string
            period_days: number
            monthly_credits: number
        }[]
    > {
        return this.request('/v1/billing/plans')
    }

    async getBillingBalance(): Promise<{
        credits: number
        plan_code?: string | null
        subscription_status?: string | null
        subscription_expires_at?: string | null
        admin_permissions?: string[] | null
    }> {
        return this.request('/v1/billing/balance')
    }

    async getBillingTransactions(skip = 0, limit = 50): Promise<{
        total: number
        items: {
            id: string
            delta: number
            type: string
            reason?: string | null
            balance_after: number
            created_at?: string | null
        }[]
    }> {
        return this.request(`/v1/billing/transactions?skip=${skip}&limit=${limit}`)
    }

    async subscribePlan(plan_code: string): Promise<{ message: string; subscription_id?: string }> {
        return this.request('/v1/billing/subscribe', {
            method: 'POST',
            body: JSON.stringify({ plan_code }),
        })
    }

    async getBillingSubscription(): Promise<{
        id: string
        plan_id: string
        plan_code?: string | null
        status: string
        started_at?: string | null
        expires_at?: string | null
        auto_renew?: boolean
    } | null> {
        return this.request('/v1/billing/subscription')
    }

    async getPublicFeatures(options?: { signal?: AbortSignal }): Promise<{
        allow_registration: boolean
        maintenance: boolean
        captcha_enabled: boolean
        ta_cost_analysis: number
        task_queue_enabled?: boolean
        chat_task_submit_v2_enabled?: boolean
    }> {
        return this.request('/v1/features', { signal: options?.signal })
    }

    async adminBootstrap(): Promise<{
        admin: { id: string; email: string; role: string; admin_permissions?: string[] | null }
        features: Record<string, unknown>
        server_time: string
        api_version: string
        enabled_modules: Record<string, boolean>
    }> {
        return this.request('/v1/admin/bootstrap')
    }

    async adminMetricsOverview(params: {
        from: string
        to: string
        granularity: 'day' | 'hour'
    }): Promise<{ items: { ts: string; key: string; value: number }[]; granularity: string }> {
        const u = new URLSearchParams()
        u.set('from', params.from)
        u.set('to', params.to)
        u.set('granularity', params.granularity)
        return this.request(`/v1/admin/metrics/overview?${u.toString()}`)
    }

    async adminMetricsCredits(params: {
        from: string
        to: string
        granularity: 'day' | 'hour'
        user_id?: string
    }): Promise<{ items: { ts: string; key: string; value: number }[] }> {
        const u = new URLSearchParams()
        u.set('from', params.from)
        u.set('to', params.to)
        u.set('granularity', params.granularity)
        if (params.user_id) u.set('user_id', params.user_id)
        return this.request(`/v1/admin/metrics/credits?${u.toString()}`)
    }

    async adminMetricsTraffic(params: {
        from: string
        to: string
        granularity: 'day' | 'hour'
        path_prefix?: string
    }): Promise<{ counts: { ts: string; key: string; value: number }[]; p95: { ts: string; key: string; value: number }[] }> {
        const u = new URLSearchParams()
        u.set('from', params.from)
        u.set('to', params.to)
        u.set('granularity', params.granularity)
        if (params.path_prefix) u.set('path_prefix', params.path_prefix)
        return this.request(`/v1/admin/metrics/traffic?${u.toString()}`)
    }

    async adminSignals(params: {
        page?: number
        page_size?: number
        severity?: string
        type?: string
        from?: string
        to?: string
    } = {}): Promise<{
        total: number
        page: number
        page_size: number
        items: { id: string; type: string; severity: string; user_id?: string | null; payload?: unknown; created_at?: string | null }[]
    }> {
        const u = new URLSearchParams()
        if (params.page) u.set('page', String(params.page))
        if (params.page_size) u.set('page_size', String(params.page_size))
        if (params.severity) u.set('severity', params.severity)
        if (params.type) u.set('type', params.type)
        if (params.from) u.set('from', params.from)
        if (params.to) u.set('to', params.to)
        return this.request(`/v1/admin/signals?${u.toString()}`)
    }

    async adminConfirm(password: string): Promise<{ confirm_token: string; expires_at: string }> {
        return this.request('/v1/admin/confirm', { method: 'POST', body: JSON.stringify({ password }) })
    }

    async adminExportCreate(export_type: 'users' | 'access_logs' | 'credits'): Promise<{ id: string; status: string }> {
        return this.request(`/v1/admin/export?export_type=${encodeURIComponent(export_type)}`, { method: 'POST' })
    }

    async adminExportStatus(id: string): Promise<{
        id: string
        export_type: string
        status: string
        error_message?: string | null
        created_at?: string | null
        completed_at?: string | null
        download_ready?: boolean
        download_token?: string | null
    }> {
        return this.request(`/v1/admin/export/${id}`)
    }

    async adminUserCreditTransactions(
        userId: string,
        params: { page?: number; page_size?: number } = {},
    ): Promise<{
        total: number
        page: number
        page_size: number
        items: { id: string; delta: number; type: string; reason?: string | null; ref_type?: string | null; ref_id?: string | null; created_at?: string | null }[]
    }> {
        const u = new URLSearchParams()
        if (params.page) u.set('page', String(params.page))
        if (params.page_size) u.set('page_size', String(params.page_size))
        return this.request(`/v1/admin/users/${userId}/credit-transactions?${u.toString()}`)
    }

    async adminDashboard(): Promise<{
        total_users: number
        users_today: number
        credits_consumed_today: number
        active_subscriptions: number
    }> {
        return this.request('/v1/admin/dashboard')
    }

    async adminUsers(params: { q?: string; role?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: {
            id: string
            email: string
            username?: string | null
            role: string
            status: string
            credits: number
            created_at?: string | null
            last_login_at?: string | null
        }[]
    }> {
        const u = new URLSearchParams()
        if (params.q) u.set('q', params.q)
        if (params.role) u.set('role', params.role)
        if (params.page) u.set('page', String(params.page))
        if (params.page_size) u.set('page_size', String(params.page_size))
        return this.request(`/v1/admin/users?${u.toString()}`)
    }

    async adminGetUser(userId: string): Promise<{
        id: string
        email: string
        username?: string | null
        display_name?: string | null
        role: string
        status: string
        credits: number
        plan_code?: string | null
        subscription_expires_at?: string | null
        created_at?: string | null
        last_login_at?: string | null
        admin_permissions?: string[] | null
    }> {
        return this.request(`/v1/admin/users/${userId}`)
    }

    async adminPatchUser(
        userId: string,
        body: {
            email?: string
            username?: string
            display_name?: string
            role?: string
            status?: string
            is_active?: boolean
            admin_permissions?: string[]
        },
    ): Promise<{ message: string; id: string }> {
        return this.request(`/v1/admin/users/${userId}`, { method: 'PATCH', body: JSON.stringify(body) })
    }

    async adminSetSubscription(
        userId: string,
        body: { plan_code: string; days?: number; status?: string },
        extraHeaders?: Record<string, string>,
    ): Promise<{ message: string }> {
        return this.request(`/v1/admin/users/${userId}/subscription`, {
            method: 'POST',
            body: JSON.stringify(body),
            headers: extraHeaders,
        })
    }

    async adminAdjustCredits(
        userId: string,
        delta: number,
        reason: string,
        extraHeaders?: Record<string, string>,
    ): Promise<{ balance: number }> {
        return this.request(`/v1/admin/users/${userId}/credits`, {
            method: 'POST',
            body: JSON.stringify({ delta, reason }),
            headers: extraHeaders,
        })
    }

    async adminResetPassword(userId: string, new_password: string, extraHeaders?: Record<string, string>): Promise<{ message: string }> {
        return this.request(`/v1/admin/users/${userId}/reset-password`, {
            method: 'POST',
            body: JSON.stringify({ new_password }),
            headers: extraHeaders,
        })
    }

    async adminAccessLogs(params: {
        page?: number
        page_size?: number
        user_id?: string
        path?: string
        status_code?: number
        failures_only?: boolean
    } = {}): Promise<{
        total: number
        items: {
            id: string
            user_id?: string | null
            ip?: string | null
            method?: string | null
            path?: string | null
            status_code?: number | null
            latency_ms?: number | null
            created_at?: string | null
        }[]
    }> {
        const u = new URLSearchParams()
        u.set('page', String(params.page ?? 1))
        if (params.page_size) u.set('page_size', String(params.page_size))
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.path) u.set('path', params.path)
        if (params.status_code != null) u.set('status_code', String(params.status_code))
        if (params.failures_only) u.set('failures_only', 'true')
        return this.request(`/v1/admin/access-logs?${u.toString()}`)
    }

    async adminAuditLogs(
        page = 1,
        page_size = 50,
        target_user_id?: string,
    ): Promise<{
        total: number
        items: {
            id: string
            admin_id: string
            action: string
            target_user_id?: string | null
            payload?: Record<string, unknown> | null
            ip?: string | null
            created_at?: string | null
        }[]
    }> {
        const u = new URLSearchParams()
        u.set('page', String(page))
        u.set('page_size', String(page_size))
        if (target_user_id) u.set('target_user_id', target_user_id)
        return this.request(`/v1/admin/audit-logs?${u.toString()}`)
    }

    async adminPlans(): Promise<
        {
            id: string
            code: string
            name: string
            price_cents: number
            currency: string
            period_days: number
            monthly_credits: number
            is_active?: boolean
        }[]
    > {
        return this.request('/v1/admin/plans')
    }

    async adminCreatePlan(body: {
        code: string
        name: string
        price_cents: number
        currency?: string
        period_days: number
        monthly_credits: number
        is_active?: boolean
    }): Promise<Record<string, unknown>> {
        return this.request('/v1/admin/plans', { method: 'POST', body: JSON.stringify(body) })
    }

    async adminPatchPlan(
        planId: string,
        body: Partial<{ name: string; price_cents: number; period_days: number; monthly_credits: number; is_active: boolean }>,
        extraHeaders?: Record<string, string>,
    ): Promise<Record<string, unknown>> {
        return this.request(`/v1/admin/plans/${planId}`, {
            method: 'PATCH',
            body: JSON.stringify(body),
            headers: extraHeaders,
        })
    }

    async adminReportsOverview(params: AdminDateRangeParams = {}): Promise<Record<string, unknown>> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return this.request(`/v1/admin/reports/overview?${u.toString()}`)
    }

    async adminReportsUsersTrend(params: AdminDateRangeParams = {}): Promise<{ items: Record<string, unknown>[] }> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return this.request(`/v1/admin/reports/users-trend?${u.toString()}`)
    }

    async adminReportsProjectsTrend(params: AdminDateRangeParams = {}): Promise<{ items: Record<string, unknown>[] }> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return this.request(`/v1/admin/reports/projects-trend?${u.toString()}`)
    }

    async adminReportsRevenueTrend(params: AdminDateRangeParams = {}): Promise<{ items: Record<string, unknown>[] }> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return this.request(`/v1/admin/reports/revenue-trend?${u.toString()}`)
    }

    async adminReportsUsageTrend(params: AdminDateRangeParams = {}): Promise<{ items: Record<string, unknown>[] }> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return this.request(`/v1/admin/reports/usage-trend?${u.toString()}`)
    }

    async adminReportsOpsStats(params: { start_date?: string; end_date?: string } = {}): Promise<Record<string, unknown>> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        return this.request(`/v1/admin/reports/ops-stats?${u.toString()}`)
    }

    async adminReportsFeatureToken(params: { start_date?: string; end_date?: string } = {}): Promise<Record<string, unknown>> {
        const u = new URLSearchParams()
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        return this.request(`/v1/admin/reports/feature-token?${u.toString()}`)
    }

    async adminReportsOutcomeTrend(params: { days?: number; group_by?: 'release_version' | 'all' } = {}): Promise<{
        days: number
        group_by: string
        items: { release_version: string; month: string; weighted_hit_rate: number; count: number }[]
        total_reports: number
    }> {
        const u = new URLSearchParams()
        if (typeof params.days === 'number') u.set('days', String(params.days))
        if (params.group_by) u.set('group_by', params.group_by)
        return this.request(`/v1/admin/reports/outcome-trend?${u.toString()}`)
    }

    adminReportsExportCsvUrl(report: string, params: AdminDateRangeParams = {}): string {
        const u = new URLSearchParams()
        u.set('report', report)
        if (params.start_date) u.set('start_date', params.start_date)
        if (params.end_date) u.set('end_date', params.end_date)
        if (params.grain) u.set('grain', params.grain)
        return `${getBaseUrl()}/v1/admin/reports/export.csv?${u.toString()}`
    }

    async adminReportsExportCsvBlob(report: string, params: AdminDateRangeParams = {}): Promise<Blob> {
        const url = this.adminReportsExportCsvUrl(report, params)
        const token = getAuthToken()
        const response = await fetch(url, {
            headers: token ? { Authorization: `Bearer ${token}` } : {},
        })
        if (!response.ok) {
            const t = await response.text().catch(() => '')
            throw new Error(t || `导出失败 HTTP ${response.status}`)
        }
        return response.blob()
    }

    async adminCommerceOrders(params: { user_id?: string; status?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: Record<string, unknown>[]
    }> {
        const u = new URLSearchParams()
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.status) u.set('status', params.status)
        if (params.page) u.set('page', String(params.page))
        if (params.page_size) u.set('page_size', String(params.page_size))
        return this.request(`/v1/admin/commerce/orders?${u.toString()}`)
    }

    async adminCommerceOrder(orderId: string): Promise<Record<string, unknown>> {
        return this.request(`/v1/admin/commerce/orders/${orderId}`)
    }

    async adminCommerceCreditLedger(params: { user_id?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: Record<string, unknown>[]
    }> {
        const u = new URLSearchParams()
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.page) u.set('page', String(params.page ?? 1))
        if (params.page_size) u.set('page_size', String(params.page_size ?? 50))
        return this.request(`/v1/admin/commerce/credit-ledger?${u.toString()}`)
    }

    async adminCommerceCreditPackages(): Promise<Record<string, unknown>[]> {
        return this.request('/v1/admin/commerce/credit-packages')
    }

    async adminCommerceReconciliationRuns(): Promise<{ items: Record<string, unknown>[] }> {
        return this.request('/v1/admin/commerce/reconciliation/runs')
    }

    async adminCommerceApiCosts(): Promise<Record<string, unknown>> {
        return this.request('/v1/admin/commerce/api-costs')
    }

    async adminCommercePaymentSettings(): Promise<Record<string, unknown>> {
        return this.request('/v1/admin/commerce/payment-settings')
    }

    async adminCommercePricingTable(): Promise<Record<string, unknown>[]> {
        return this.request('/v1/admin/commerce/pricing-table')
    }

    async adminOpsTasks(params: { user_id?: string; status?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: Record<string, unknown>[]
    }> {
        const u = new URLSearchParams()
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.status) u.set('status', params.status)
        if (params.page) u.set('page', String(params.page ?? 1))
        if (params.page_size) u.set('page_size', String(params.page_size ?? 50))
        return this.request(`/v1/admin/ops/tasks?${u.toString()}`)
    }

    async adminOpsUsage(params: { user_id?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: Record<string, unknown>[]
    }> {
        const u = new URLSearchParams()
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.page) u.set('page', String(params.page ?? 1))
        if (params.page_size) u.set('page_size', String(params.page_size ?? 50))
        return this.request(`/v1/admin/ops/usage?${u.toString()}`)
    }

    async adminOpsAiCalls(params: { user_id?: string; page?: number; page_size?: number } = {}): Promise<{
        total: number
        items: Record<string, unknown>[]
    }> {
        const u = new URLSearchParams()
        if (params.user_id) u.set('user_id', params.user_id)
        if (params.page) u.set('page', String(params.page ?? 1))
        if (params.page_size) u.set('page_size', String(params.page_size ?? 50))
        return this.request(`/v1/admin/ops/ai-calls?${u.toString()}`)
    }

    async adminContentBlocks(): Promise<{ items: Record<string, unknown>[] }> {
        return this.request('/v1/admin/content/blocks')
    }

    async adminContentAssets(): Promise<{ items: Record<string, unknown>[] }> {
        return this.request('/v1/admin/content/assets')
    }

    async adminContentMessages(): Promise<{ items: Record<string, unknown>[] }> {
        return this.request('/v1/admin/content/messages')
    }

    async adminContentAppearance(): Promise<Record<string, unknown>> {
        return this.request('/v1/admin/content/appearance')
    }

    // Token Management
    async getTokens(): Promise<UserToken[]> {
        return this.request<UserToken[]>('/v1/tokens')
    }

    async createToken(request: UserTokenCreateRequest): Promise<UserToken> {
        return this.request<UserToken>('/v1/tokens', {
            method: 'POST',
            body: JSON.stringify(request),
        })
    }

    async deleteToken(tokenId: string): Promise<{ message: string }> {
        return this.request<{ message: string }>(`/v1/tokens/${tokenId}`, {
            method: 'DELETE',
        })
    }

    // Feedback
    async createFeedback(subject: string, content: string): Promise<FeedbackItem> {
        return this.request<FeedbackItem>('/v1/feedbacks', {
            method: 'POST',
            body: JSON.stringify({ subject, content }),
        })
    }

    async listFeedbacks(page = 1, pageSize = 20): Promise<FeedbackListResponse> {
        return this.request<FeedbackListResponse>(`/v1/feedbacks?page=${page}&page_size=${pageSize}`)
    }

    async getFeedback(id: string): Promise<FeedbackItem> {
        return this.request<FeedbackItem>(`/v1/feedbacks/${id}`)
    }

    async getFeedbackUnreadCount(): Promise<FeedbackUnreadResponse> {
        return this.request<FeedbackUnreadResponse>('/v1/feedbacks/unread-count')
    }

    async markFeedbackRead(id: string): Promise<void> {
        return this.request<void>(`/v1/feedbacks/${id}/read`, { method: 'POST' })
    }
}

export const api = new ApiService()
