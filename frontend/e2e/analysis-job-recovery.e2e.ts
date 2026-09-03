import { test, expect } from '@playwright/test'

/**
 * 智能分析任务恢复 E2E
 *
 * 目标：刷新或从任务中心跳入「执行中任务」时，
 *  - 工作流图正确进入执行态（"分析中"徽标可见，总进度 > 0%）；
 *  - 不会与 chat 主流并行打开重复的 `/v1/jobs/:id/events` SSE 流。
 *
 * 该用例不启动真实后端：使用 page.route 拦截所有依赖接口，并以受控 SSE 响应模拟服务端推送。
 */

const RUNNING_JOB_ID = 'job-e2e-running'
const RUNNING_SYMBOL = '600519.SH'

function buildSseResponse(events: Array<{ event: string; data: Record<string, unknown>; id?: number }>): string {
    const lines: string[] = []
    for (const evt of events) {
        if (typeof evt.id === 'number') lines.push(`id: ${evt.id}`)
        lines.push(`event: ${evt.event}`)
        lines.push(`data: ${JSON.stringify(evt.data)}`)
        lines.push('')
    }
    lines.push('data: [DONE]')
    lines.push('')
    return lines.join('\n')
}

test.describe('智能分析 · 执行中任务恢复', () => {
    test('带 ?job_id 进入分析页：工作流显示执行中，且不会双流并发', async ({ page }) => {
        await page.addInitScript(() => {
            localStorage.setItem('ta-access-token', 'playwright-e2e-token')
            localStorage.setItem(
                'ta-user',
                JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            )
        })

        const featuresBody = JSON.stringify({
            allow_registration: true,
            maintenance: false,
            captcha_enabled: false,
            ta_cost_analysis: 0,
            chat_task_submit_v2_enabled: true,
        })
        const userBody = JSON.stringify({
            id: 'e2e-user',
            email: 'e2e@test.com',
            username: 'e2e',
            role: 'user',
            display_name: 'E2E User',
        })

        await page.route('**/v1/features', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: featuresBody }),
        )
        await page.route('**/v1/auth/me', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: userBody }),
        )
        await page.route('**/v1/users/entitlements', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ plan: 'free', features: {} }),
            }),
        )
        await page.route('**/v1/me/tasks', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ running: [], queued: [], recent: [] }),
            }),
        )

        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    job_id: RUNNING_JOB_ID,
                    status: 'running',
                    created_at: new Date(Date.now() - 30_000).toISOString(),
                    started_at: new Date(Date.now() - 25_000).toISOString(),
                    finished_at: null,
                    symbol: RUNNING_SYMBOL,
                    trade_date: '2026-05-13',
                    display_label: '贵州茅台 600519.SH',
                }),
            }),
        )

        // 计算 `/v1/jobs/:id/events` 的调用次数，验证不会并行多开
        let eventStreamCalls = 0
        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}/events**`, async (route) => {
            eventStreamCalls += 1
            const body = buildSseResponse([
                { event: 'job.created', id: 1, data: { job_id: RUNNING_JOB_ID, symbol: RUNNING_SYMBOL } },
                { event: 'job.running', id: 2, data: { job_id: RUNNING_JOB_ID, symbol: RUNNING_SYMBOL } },
                {
                    event: 'agent.status',
                    id: 3,
                    data: { agent: 'Market Analyst', status: 'in_progress', horizon: 'short' },
                },
                {
                    event: 'agent.status',
                    id: 4,
                    data: { agent: 'Market Analyst', status: 'completed', horizon: 'short' },
                },
                {
                    event: 'agent.snapshot',
                    id: 5,
                    data: {
                        agents: [
                            { team: 'Analyst Team', agent: 'Market Analyst', status: 'completed' },
                            { team: 'Analyst Team', agent: 'News Analyst', status: 'in_progress' },
                            { team: 'Analyst Team', agent: 'Fundamentals Analyst', status: 'pending' },
                            { team: 'Analyst Team', agent: 'Social Analyst', status: 'pending' },
                            { team: 'Analyst Team', agent: 'Macro Analyst', status: 'pending' },
                            { team: 'Analyst Team', agent: 'Smart Money Analyst', status: 'pending' },
                            { team: 'Analyst Team', agent: 'Volume Price Analyst', status: 'pending' },
                            { team: 'Research Team', agent: 'Bull Researcher', status: 'pending' },
                            { team: 'Research Team', agent: 'Bear Researcher', status: 'pending' },
                            { team: 'Research Team', agent: 'Research Manager', status: 'pending' },
                            { team: 'Trading Team', agent: 'Trader', status: 'pending' },
                            { team: 'Risk Management', agent: 'Aggressive Analyst', status: 'pending' },
                            { team: 'Risk Management', agent: 'Neutral Analyst', status: 'pending' },
                            { team: 'Risk Management', agent: 'Conservative Analyst', status: 'pending' },
                            { team: 'Portfolio Management', agent: 'Portfolio Manager', status: 'pending' },
                        ],
                    },
                },
            ])
            await route.fulfill({
                status: 200,
                contentType: 'text/event-stream',
                body,
            })
        })

        await page.goto(`/analysis?job_id=${RUNNING_JOB_ID}&symbol=${RUNNING_SYMBOL}`)
        await expect(page).toHaveURL(/\/analysis/)

        // 工作流卡片中的「分析中」徽标
        await expect(page.getByText('分析中').first()).toBeVisible({ timeout: 10_000 })

        // 「分析总进度」标签存在（出现在 isAnalyzing 时）
        await expect(page.getByText('分析总进度').first()).toBeVisible({ timeout: 10_000 })

        // 给前端足够时间消费 SSE 后，再断言没有重复并发开流
        await page.waitForTimeout(1500)
        expect(eventStreamCalls).toBeLessThanOrEqual(1)
    })

    test('刷新分析页：本地 currentJobId + running 状态恢复，不弹出"任务不存在"提示', async ({ page }) => {
        await page.addInitScript((jobId: string) => {
            localStorage.setItem('ta-access-token', 'playwright-e2e-token')
            localStorage.setItem(
                'ta-user',
                JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            )
            // 模拟刷新前的 zustand 持久化状态：有 currentJobId 且 analysisRunState=running
            // perUserLocalStorageKey: `${base}:${userId}`
            localStorage.setItem(
                'tradingagents-analysis:e2e-user',
                JSON.stringify({
                    state: {
                        currentSymbol: '600519.SH',
                        currentSymbolDisplayName: '贵州茅台',
                        currentJobId: jobId,
                        analysisRunState: 'running',
                        currentHorizon: 'short',
                        agents: [],
                        streamingSections: {},
                        debateMessages: {},
                        debateScrollTick: 0,
                        report: null,
                        riskItems: [],
                        keyMetrics: [],
                        jobConfidence: null,
                        jobTargetPrice: null,
                        jobStopLoss: null,
                        chatMessages: [],
                        lastEventIdByJob: { [jobId]: 0 },
                    },
                    version: 3,
                }),
            )
        }, RUNNING_JOB_ID)

        const featuresBody = JSON.stringify({
            allow_registration: true,
            maintenance: false,
            captcha_enabled: false,
            ta_cost_analysis: 0,
            chat_task_submit_v2_enabled: true,
        })

        await page.route('**/v1/features', (route) =>
            route.fulfill({ status: 200, contentType: 'application/json', body: featuresBody }),
        )
        await page.route('**/v1/auth/me', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            }),
        )
        await page.route('**/v1/users/entitlements', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ plan: 'free', features: {} }),
            }),
        )
        await page.route('**/v1/me/tasks', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    running: [
                        {
                            job_id: RUNNING_JOB_ID,
                            task_kind: 'full_analysis',
                            task_name: '贵州茅台 600519.SH 2026-05-13',
                            description: null,
                            symbol: RUNNING_SYMBOL,
                            trade_date: '2026-05-13',
                            status: 'running',
                            created_at: new Date(Date.now() - 30_000).toISOString(),
                            updated_at: new Date(Date.now() - 5_000).toISOString(),
                        },
                    ],
                    queued: [],
                    recent: [],
                }),
            }),
        )
        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    job_id: RUNNING_JOB_ID,
                    status: 'running',
                    created_at: new Date(Date.now() - 30_000).toISOString(),
                    symbol: RUNNING_SYMBOL,
                    trade_date: '2026-05-13',
                    display_label: '贵州茅台 600519.SH',
                }),
            }),
        )
        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}/events**`, async (route) => {
            const body = buildSseResponse([
                { event: 'job.running', id: 1, data: { job_id: RUNNING_JOB_ID } },
                {
                    event: 'agent.status',
                    id: 2,
                    data: { agent: 'Market Analyst', status: 'in_progress' },
                },
            ])
            await route.fulfill({ status: 200, contentType: 'text/event-stream', body })
        })

        await page.goto('/analysis')
        await expect(page).toHaveURL(/\/analysis/)

        // 不应出现「任务不存在」失败提示
        await expect(page.getByText('已不存在，可能是后端服务重启导致')).toHaveCount(0)

        // 工作流应进入执行态
        await expect(page.getByText('分析中').first()).toBeVisible({ timeout: 10_000 })
    })

    test('有焦点任务时可连续提交新任务并进入队列', async ({ page }) => {
        await page.addInitScript((jobId: string) => {
            localStorage.setItem('ta-access-token', 'playwright-e2e-token')
            localStorage.setItem(
                'ta-user',
                JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            )
            localStorage.setItem(
                'tradingagents-analysis:e2e-user',
                JSON.stringify({
                    state: {
                        currentSymbol: '600519.SH',
                        currentSymbolDisplayName: '贵州茅台',
                        currentJobId: jobId,
                        analysisRunState: 'running',
                        currentHorizon: 'short',
                        agents: [],
                        streamingSections: {},
                        debateMessages: {},
                        debateScrollTick: 0,
                        report: null,
                        riskItems: [],
                        keyMetrics: [],
                        jobConfidence: null,
                        jobTargetPrice: null,
                        jobStopLoss: null,
                        chatMessages: [],
                        lastEventIdByJob: { [jobId]: 0 },
                    },
                    version: 3,
                }),
            )
        }, RUNNING_JOB_ID)

        await page.route('**/v1/features', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    allow_registration: true,
                    maintenance: false,
                    captcha_enabled: false,
                    ta_cost_analysis: 0,
                    chat_task_submit_v2_enabled: true,
                }),
            }),
        )
        await page.route('**/v1/auth/me', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    id: 'e2e-user',
                    email: 'e2e@test.com',
                    username: 'e2e',
                    role: 'user',
                    display_name: 'E2E User',
                }),
            }),
        )
        await page.route('**/v1/users/entitlements', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ plan: 'free', features: {} }),
            }),
        )
        await page.route('**/v1/me/tasks', (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({ running: [], queued: [], recent: [] }),
            }),
        )
        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    job_id: RUNNING_JOB_ID,
                    status: 'running',
                    created_at: new Date(Date.now() - 30_000).toISOString(),
                    symbol: RUNNING_SYMBOL,
                    trade_date: '2026-05-13',
                    display_label: '贵州茅台 600519.SH',
                }),
            }),
        )
        await page.route(`**/v1/jobs/${RUNNING_JOB_ID}/events**`, (route) =>
            route.fulfill({
                status: 200,
                contentType: 'text/event-stream',
                body: buildSseResponse([{ event: 'job.running', id: 1, data: { job_id: RUNNING_JOB_ID } }]),
            }),
        )

        let submitCalls = 0
        await page.route('**/v1/me/tasks/submit', (route) => {
            submitCalls += 1
            const idx = submitCalls
            return route.fulfill({
                status: 200,
                contentType: 'application/json',
                body: JSON.stringify({
                    job_id: `queued-job-${idx}`,
                    status: 'queued',
                    symbol: idx === 1 ? '603002.SH' : '600330.SH',
                    trade_date: '2026-05-13',
                    task_label: idx === 1 ? '宏昌电子 603002.SH' : '天通股份 600330.SH',
                    waiting_ahead_count: idx,
                    message: '任务已进入排队队列。',
                }),
            })
        })

        await page.goto('/analysis')
        await expect(page).toHaveURL(/\/analysis/)

        const input = page.getByPlaceholder('直接描述你的分析需求...')
        await input.fill('分析宏昌电子 603002.SH 今日走势')
        await input.press('Enter')
        await input.fill('分析天通股份 600330.SH 今日走势')
        await input.press('Enter')

        await expect(page.getByText('已入队：宏昌电子 603002.SH（前方 1 个）')).toBeVisible({ timeout: 10_000 })
        await expect(page.getByText('已入队：天通股份 600330.SH（前方 2 个）')).toBeVisible({ timeout: 10_000 })
        await expect(page.getByText('任务正在提交处理中，请稍候几秒再发起新任务。')).toHaveCount(0)
        expect(submitCalls).toBe(2)
    })
})
