# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: analysis-job-recovery.e2e.ts >> 智能分析 · 执行中任务恢复 >> 有焦点任务时可连续提交新任务并进入队列
- Location: e2e\analysis-job-recovery.e2e.ts:292:5

# Error details

```
Error: expect(locator).toBeVisible() failed

Locator: getByText('已入队：天通股份 600330.SH（前方 2 个）')
Expected: visible
Timeout: 10000ms
Error: element(s) not found

Call log:
  - Expect "toBeVisible" with timeout 10000ms
  - waiting for getByText('已入队：天通股份 600330.SH（前方 2 个）')

```

# Page snapshot

```yaml
- generic [ref=e3]:
  - complementary [ref=e4]:
    - generic [ref=e6]:
      - img [ref=e8]
      - generic: TradingAgents
    - navigation [ref=e11]:
      - link "控制台" [ref=e12] [cursor=pointer]:
        - /url: /
        - img [ref=e13]
        - generic: 控制台
      - link "智能分析" [ref=e18] [cursor=pointer]:
        - /url: /analysis
        - img [ref=e19]
        - generic: 智能分析
      - link "快速分析" [ref=e21] [cursor=pointer]:
        - /url: /analysis/fast
        - img [ref=e22]
        - generic: 快速分析
      - link "K线分析" [ref=e24] [cursor=pointer]:
        - /url: /chart
        - img [ref=e25]
        - generic: K线分析
      - link "任务中心" [ref=e29] [cursor=pointer]:
        - /url: /tasks
        - img [ref=e30]
        - generic: 任务中心
      - link "历史报告" [ref=e33] [cursor=pointer]:
        - /url: /reports
        - img [ref=e34]
        - generic: 历史报告
      - link "自选 & 定时" [ref=e37] [cursor=pointer]:
        - /url: /portfolio
        - img [ref=e38]
        - generic: 自选 & 定时
      - link "跟踪看板" [ref=e41] [cursor=pointer]:
        - /url: /tracking-board
        - img [ref=e42]
        - generic: 跟踪看板
      - link "实时盘" [ref=e46] [cursor=pointer]:
        - /url: /realtime-board
        - img [ref=e47]
        - generic: 实时盘
      - link "账户" [ref=e49] [cursor=pointer]:
        - /url: /account
        - img [ref=e50]
        - generic: 账户
      - link "订阅" [ref=e54] [cursor=pointer]:
        - /url: /subscription
        - img [ref=e55]
        - generic: 订阅
      - link "反馈留言" [ref=e57] [cursor=pointer]:
        - /url: /feedback
        - img [ref=e58]
        - generic: 反馈留言
      - link "设置" [ref=e60] [cursor=pointer]:
        - /url: /settings
        - img [ref=e61]
        - generic: 设置
    - generic [ref=e65]: 065ac89
  - generic [ref=e66]:
    - banner [ref=e67]:
      - generic [ref=e68]:
        - generic [ref=e70]:
          - generic [ref=e73]: A 股投研终端
          - generic [ref=e75]: 工作台在线
        - generic [ref=e76]:
          - button "0 点" [ref=e77]:
            - img [ref=e78]
            - generic [ref=e80]: "0"
            - generic [ref=e81]: 点
          - button "E2" [ref=e83]:
            - generic [ref=e84]: E2
            - img [ref=e85]
    - main [ref=e87]:
      - generic [ref=e89]:
        - complementary [ref=e90]:
          - complementary [ref=e92]:
            - generic [ref=e93]:
              - generic [ref=e94]:
                - img [ref=e95]
                - heading "智能分析" [level=2] [ref=e98]
              - button "清空对话" [ref=e100]:
                - img [ref=e101]
            - generic [ref=e104]:
              - img [ref=e105]
              - text: 示例：分析贵州茅台 600519.SH 今天走势
            - generic [ref=e107]:
              - button "分析一下贵州茅台(600519.SH)今天走势" [ref=e108]
              - button "请分析稀土ETF嘉实(516150)在2026-03-03的情况" [ref=e109]
              - button "分析宁德时代300750.SZ，做一轮投研沙盘梳理" [ref=e110]
            - generic [ref=e111]:
              - paragraph [ref=e115]: 我是你的 A 股多智能体投研助手。直接告诉我你想分析的标的和日期。
              - generic [ref=e117]: 分析宏昌电子 603002.SH 今日走势
              - generic [ref=e120]:
                - paragraph [ref=e121]: 已入队：宏昌电子 603002.SH（前方 1 个）。
                - paragraph [ref=e122]:
                  - link "去任务中心" [ref=e123] [cursor=pointer]:
                    - /url: /tasks
                  - text: ·
                  - link "取消该排队任务" [ref=e124] [cursor=pointer]:
                    - /url: ""
            - generic [ref=e126]:
              - textbox "Enter 发送，Ctrl+Enter 也可发送" [active] [ref=e127]:
                - /placeholder: 直接描述你的分析需求...
                - text: 分析天通股份 600330.SH 今日走势
              - button "发送" [ref=e128]:
                - img [ref=e129]
        - generic [ref=e132]:
          - generic [ref=e134]:
            - generic [ref=e135]:
              - generic [ref=e136]:
                - generic [ref=e137]:
                  - img [ref=e138]
                  - generic [ref=e142]:
                    - generic [ref=e143]:
                      - heading "603002.SH" [level=2] [ref=e144]
                      - generic "实时行情" [ref=e145]:
                        - generic [ref=e146]: 现价 --
                    - generic [ref=e147]:
                      - generic [ref=e148]: "--"
                      - generic [ref=e149]: "--"
                      - generic [ref=e150]: "--"
                - button "K线分析" [ref=e151]:
                  - img [ref=e152]
              - generic [ref=e157]:
                - generic [ref=e158]:
                  - button "1M" [ref=e159]
                  - button "3M" [ref=e160]
                  - button "6M" [ref=e161]
                  - generic [ref=e162]:
                    - checkbox "MA5" [checked] [ref=e163]
                    - text: MA5
                  - generic [ref=e164]:
                    - checkbox "MA20" [checked] [ref=e165]
                    - text: MA20
                - generic [ref=e166]:
                  - button "上证指数" [ref=e167]
                  - button "深证成指" [ref=e168]
                  - button "创业板指" [ref=e169]
                  - button "科创50" [ref=e170]
                  - button "北证50" [ref=e171]
              - generic [ref=e172]: O -- · H -- · L -- · 量 -- · 换手 --
            - generic [ref=e173]:
              - table [ref=e176]:
                - row [ref=e177]:
                  - cell
                  - cell [ref=e178]
                  - cell [ref=e182]
              - table [ref=e188]:
                - row [ref=e189]:
                  - cell
                  - cell [ref=e190]
                  - cell [ref=e194]
                - row [ref=e198]:
                  - cell
                  - cell [ref=e199]
                  - cell [ref=e203]
              - generic [ref=e206]: Failed to fetch
          - generic [ref=e207]:
            - generic [ref=e209]:
              - generic [ref=e210]:
                - heading "多Agents量化研究分析" [level=3] [ref=e212]
                - group "工作流风格" [ref=e214]:
                  - button "原风格" [ref=e215]
                  - button "n8n风格" [ref=e216]
              - paragraph [ref=e217]: 当前标的·603002.SH
            - application [ref=e219]:
              - generic [ref=e221]:
                - generic:
                  - generic:
                    - img
                    - img:
                      - img "Edge from Market Analyst to Bull Researcher" [ref=e222] [cursor=pointer]
                    - img:
                      - img "Edge from Social Analyst to Bull Researcher" [ref=e225] [cursor=pointer]
                    - img:
                      - img "Edge from News Analyst to Bull Researcher" [ref=e228] [cursor=pointer]
                    - img:
                      - img "Edge from Fundamentals Analyst to Bull Researcher" [ref=e231] [cursor=pointer]
                    - img:
                      - img "Edge from Macro Analyst to Bull Researcher" [ref=e234] [cursor=pointer]
                    - img:
                      - img "Edge from Smart Money Analyst to Bull Researcher" [ref=e237] [cursor=pointer]
                    - img:
                      - img "Edge from Volume Price Analyst to Bull Researcher" [ref=e240] [cursor=pointer]
                    - img:
                      - img "Edge from Market Analyst to Bear Researcher" [ref=e243] [cursor=pointer]
                    - img:
                      - img "Edge from Social Analyst to Bear Researcher" [ref=e246] [cursor=pointer]
                    - img:
                      - img "Edge from News Analyst to Bear Researcher" [ref=e249] [cursor=pointer]
                    - img:
                      - img "Edge from Fundamentals Analyst to Bear Researcher" [ref=e252] [cursor=pointer]
                    - img:
                      - img "Edge from Macro Analyst to Bear Researcher" [ref=e255] [cursor=pointer]
                    - img:
                      - img "Edge from Smart Money Analyst to Bear Researcher" [ref=e258] [cursor=pointer]
                    - img:
                      - img "Edge from Volume Price Analyst to Bear Researcher" [ref=e261] [cursor=pointer]
                    - img:
                      - img "Edge from Bull Researcher to Bear Researcher" [ref=e264] [cursor=pointer]:
                        - generic [ref=e265]:
                          - generic: 辩论
                    - img:
                      - img "Edge from Bull Researcher to Research Manager" [ref=e267] [cursor=pointer]
                    - img:
                      - img "Edge from Bear Researcher to Research Manager" [ref=e270] [cursor=pointer]
                    - img:
                      - img "Edge from Research Manager to Trader" [ref=e273] [cursor=pointer]:
                        - generic [ref=e274]:
                          - generic: 沙盘草案
                    - img:
                      - img "Edge from Trader to Aggressive Analyst" [ref=e276] [cursor=pointer]
                    - img:
                      - img "Edge from Trader to Neutral Analyst" [ref=e279] [cursor=pointer]:
                        - generic [ref=e280]:
                          - generic: 路径预案摘要
                    - img:
                      - img "Edge from Trader to Conservative Analyst" [ref=e282] [cursor=pointer]
                    - img:
                      - img "Edge from Aggressive Analyst to Portfolio Manager" [ref=e285] [cursor=pointer]
                    - img:
                      - img "Edge from Neutral Analyst to Portfolio Manager"
                    - img:
                      - img "Edge from Conservative Analyst to Portfolio Manager" [ref=e288] [cursor=pointer]
                  - generic:
                    - generic [ref=e291]:
                      - generic:
                        - generic: 技术分析
                    - generic [ref=e292]:
                      - generic:
                        - generic: 研究团队
                    - generic [ref=e293]:
                      - generic:
                        - generic: 风控团队
                    - generic [ref=e298] [cursor=pointer]:
                      - img [ref=e300]
                      - generic [ref=e303]: 技术面
                      - generic [ref=e304]: 待命
                    - generic [ref=e309] [cursor=pointer]:
                      - img [ref=e311]
                      - generic [ref=e313]: 舆情
                      - generic [ref=e314]: 待命
                    - generic [ref=e319] [cursor=pointer]:
                      - img [ref=e321]
                      - generic [ref=e324]: 新闻
                      - generic [ref=e325]: 待命
                    - generic [ref=e330] [cursor=pointer]:
                      - img [ref=e332]
                      - generic [ref=e334]: 基本面
                      - generic [ref=e335]: 待命
                    - generic [ref=e340] [cursor=pointer]:
                      - img [ref=e342]
                      - generic [ref=e343]: 宏观
                      - generic [ref=e344]: 待命
                    - generic [ref=e349] [cursor=pointer]:
                      - img [ref=e351]
                      - generic [ref=e353]: 主力资金
                      - generic [ref=e354]: 待命
                    - generic [ref=e359] [cursor=pointer]:
                      - img [ref=e361]
                      - generic [ref=e363]: 量价
                      - generic [ref=e364]: 待命
                    - generic [ref=e370] [cursor=pointer]:
                      - img [ref=e372]
                      - generic [ref=e374]: 多头
                      - generic [ref=e375]: 待命
                    - generic [ref=e381] [cursor=pointer]:
                      - img [ref=e383]
                      - generic [ref=e385]: 空头
                      - generic [ref=e386]: 待命
                    - generic [ref=e391] [cursor=pointer]:
                      - img [ref=e393]
                      - generic [ref=e403]: 研究总监
                      - generic [ref=e404]: 待命
                    - generic [ref=e409] [cursor=pointer]:
                      - img [ref=e411]
                      - generic [ref=e414]: 交易员
                      - generic [ref=e415]: 待命
                    - generic [ref=e420] [cursor=pointer]:
                      - img [ref=e422]
                      - generic [ref=e424]: 激进
                      - generic [ref=e425]: 待命
                    - generic [ref=e430] [cursor=pointer]:
                      - img [ref=e432]
                      - generic [ref=e436]: 中性
                      - generic [ref=e437]: 待命
                    - generic [ref=e442] [cursor=pointer]:
                      - img [ref=e444]
                      - generic [ref=e446]: 稳健
                      - generic [ref=e447]: 待命
                    - generic [ref=e452] [cursor=pointer]:
                      - img [ref=e454]
                      - generic [ref=e457]: 组合经理
                      - generic [ref=e458]: 待命
              - generic "Control Panel" [ref=e459]:
                - button "Zoom In" [ref=e460] [cursor=pointer]:
                  - img [ref=e461]
                - button "Zoom Out" [ref=e463] [cursor=pointer]:
                  - img [ref=e464]
                - button "Fit View" [ref=e466] [cursor=pointer]:
                  - img [ref=e467]
          - generic [ref=e470]:
            - generic [ref=e471]:
              - generic [ref=e472]:
                - generic [ref=e473]:
                  - img [ref=e475]
                  - heading "603002.SH" [level=3] [ref=e479]
                - generic [ref=e480]: 待汇总
              - generic [ref=e481]:
                - generic [ref=e482]:
                  - generic [ref=e483]:
                    - img [ref=e484]
                    - generic [ref=e488]: 偏多参考峰值
                  - paragraph [ref=e489]: "--"
                - generic [ref=e490]:
                  - generic [ref=e491]:
                    - img [ref=e492]
                    - generic [ref=e494]: 偏空参考风控
                  - paragraph [ref=e495]: "--"
            - generic [ref=e496]:
              - generic [ref=e497]:
                - img [ref=e499]
                - heading "风险雷达" [level=3] [ref=e501]
              - generic [ref=e502]:
                - img [ref=e503]
                - paragraph [ref=e505]: 分析完成后展示风险评估
            - generic [ref=e506]:
              - generic [ref=e507]:
                - img [ref=e509]
                - heading "关键指标速览" [level=3] [ref=e511]
              - generic [ref=e512]:
                - img [ref=e513]
                - paragraph [ref=e515]: 分析完成后展示关键指标
          - generic [ref=e517]:
            - generic [ref=e518]:
              - generic [ref=e519]:
                - img [ref=e520]
                - generic [ref=e523]:
                  - heading "分析报告" [level=2] [ref=e524]
                  - paragraph [ref=e525]: 标的：603002.SH
                  - paragraph [ref=e526]: 点击上方智能体卡片查看完整报告
              - button "数据源" [disabled] [ref=e528]:
                - img [ref=e529]
                - text: 数据源
            - generic [ref=e534]:
              - img [ref=e535]
              - paragraph [ref=e541]: 点击上方智能体卡片查看报告
```

# Test source

```ts
  323 |                         jobStopLoss: null,
  324 |                         chatMessages: [],
  325 |                         lastEventIdByJob: { [jobId]: 0 },
  326 |                     },
  327 |                     version: 3,
  328 |                 }),
  329 |             )
  330 |         }, RUNNING_JOB_ID)
  331 | 
  332 |         await page.route('**/v1/features', (route) =>
  333 |             route.fulfill({
  334 |                 status: 200,
  335 |                 contentType: 'application/json',
  336 |                 body: JSON.stringify({
  337 |                     allow_registration: true,
  338 |                     maintenance: false,
  339 |                     captcha_enabled: false,
  340 |                     ta_cost_analysis: 0,
  341 |                     chat_task_submit_v2_enabled: true,
  342 |                 }),
  343 |             }),
  344 |         )
  345 |         await page.route('**/v1/auth/me', (route) =>
  346 |             route.fulfill({
  347 |                 status: 200,
  348 |                 contentType: 'application/json',
  349 |                 body: JSON.stringify({
  350 |                     id: 'e2e-user',
  351 |                     email: 'e2e@test.com',
  352 |                     username: 'e2e',
  353 |                     role: 'user',
  354 |                     display_name: 'E2E User',
  355 |                 }),
  356 |             }),
  357 |         )
  358 |         await page.route('**/v1/users/entitlements', (route) =>
  359 |             route.fulfill({
  360 |                 status: 200,
  361 |                 contentType: 'application/json',
  362 |                 body: JSON.stringify({ plan: 'free', features: {} }),
  363 |             }),
  364 |         )
  365 |         await page.route('**/v1/me/tasks', (route) =>
  366 |             route.fulfill({
  367 |                 status: 200,
  368 |                 contentType: 'application/json',
  369 |                 body: JSON.stringify({ running: [], queued: [], recent: [] }),
  370 |             }),
  371 |         )
  372 |         await page.route(`**/v1/jobs/${RUNNING_JOB_ID}`, (route) =>
  373 |             route.fulfill({
  374 |                 status: 200,
  375 |                 contentType: 'application/json',
  376 |                 body: JSON.stringify({
  377 |                     job_id: RUNNING_JOB_ID,
  378 |                     status: 'running',
  379 |                     created_at: new Date(Date.now() - 30_000).toISOString(),
  380 |                     symbol: RUNNING_SYMBOL,
  381 |                     trade_date: '2026-05-13',
  382 |                     display_label: '贵州茅台 600519.SH',
  383 |                 }),
  384 |             }),
  385 |         )
  386 |         await page.route(`**/v1/jobs/${RUNNING_JOB_ID}/events**`, (route) =>
  387 |             route.fulfill({
  388 |                 status: 200,
  389 |                 contentType: 'text/event-stream',
  390 |                 body: buildSseResponse([{ event: 'job.running', id: 1, data: { job_id: RUNNING_JOB_ID } }]),
  391 |             }),
  392 |         )
  393 | 
  394 |         let submitCalls = 0
  395 |         await page.route('**/v1/me/tasks/submit', (route) => {
  396 |             submitCalls += 1
  397 |             const idx = submitCalls
  398 |             return route.fulfill({
  399 |                 status: 200,
  400 |                 contentType: 'application/json',
  401 |                 body: JSON.stringify({
  402 |                     job_id: `queued-job-${idx}`,
  403 |                     status: 'queued',
  404 |                     symbol: idx === 1 ? '603002.SH' : '600330.SH',
  405 |                     trade_date: '2026-05-13',
  406 |                     task_label: idx === 1 ? '宏昌电子 603002.SH' : '天通股份 600330.SH',
  407 |                     waiting_ahead_count: idx,
  408 |                     message: '任务已进入排队队列。',
  409 |                 }),
  410 |             })
  411 |         })
  412 | 
  413 |         await page.goto('/analysis')
  414 |         await expect(page).toHaveURL(/\/analysis/)
  415 | 
  416 |         const input = page.getByPlaceholder('直接描述你的分析需求...')
  417 |         await input.fill('分析宏昌电子 603002.SH 今日走势')
  418 |         await input.press('Enter')
  419 |         await input.fill('分析天通股份 600330.SH 今日走势')
  420 |         await input.press('Enter')
  421 | 
  422 |         await expect(page.getByText('已入队：宏昌电子 603002.SH（前方 1 个）')).toBeVisible({ timeout: 10_000 })
> 423 |         await expect(page.getByText('已入队：天通股份 600330.SH（前方 2 个）')).toBeVisible({ timeout: 10_000 })
      |                                                                    ^ Error: expect(locator).toBeVisible() failed
  424 |         await expect(page.getByText('任务正在提交处理中，请稍候几秒再发起新任务。')).toHaveCount(0)
  425 |         expect(submitCalls).toBe(2)
  426 |     })
  427 | })
  428 | 
```