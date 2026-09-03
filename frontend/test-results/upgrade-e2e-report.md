# Playwright 全栈实机测试报告 — 0.2.5 升级验收

**生成时间**: 2026-05-23 12:25:42

## 测试工程建设 — 完成摘要

| 文件 | 状态 |
|------|------|
| frontend/playwright.config.ts | 已更新（端口 8001，mock/live/heavy 三个 project） |
| scripts/e2e-with-api.mjs | 已更新（文档同步为 8001） |
| frontend/e2e/helpers/env.ts | 新增 |
| frontend/e2e/helpers/live-auth.ts | 新增 |
| frontend/e2e/helpers/wait-analysis.ts | 新增 |
| frontend/e2e/live-api-smoke.e2e.ts | 新增（Tier A2） |
| frontend/e2e/live-auth-navigation.e2e.ts | 新增（Tier A3/A4） |
| frontend/e2e/upgrade-0.2.5-live.e2e.ts | 新增（Tier B B1-B6） |
| frontend/e2e/heavy-analysis-live.e2e.ts | 新增（Tier C C1-C5） |
| scripts/e2e/preflight.ps1 | 新增 |
| scripts/e2e/run-fullstack-playwright.ps1 | 新增 |
| package.json | 新增 7 个 test:e2e:* scripts |

## Tier A1 — Mock 回归结果（已执行）

**执行命令**: 
px playwright test --project mock

| 用例 | 结果 |
|------|------|
| 智能分析执行中任务恢复 · 带job_id进入 | PASS |
| 智能分析执行中任务恢复 · 刷新恢复 | PASS |
| 智能分析执行中任务恢复 · 连续入队 | **FAIL（pre-existing）** |
| 预览代理 healthz | PASS |
| SaaS 公开认证路由 × 4 | PASS |
| 公开静态页 × 3 | PASS |
| 智能分析工作流风格切换 | PASS |
| data-skin / 皮肤存储 × 2 | PASS |

**说明**: 连续入队用例（第292行断言「天通股份」入队提示）在 0.2.5 升级前即存在，与本次改动无关。14/15 通过率。

## TypeScript 类型检查


pm run typecheck → **0 errors** ✓

## 环境说明

| Flag | Baseline | Upgrade |
|------|----------|---------|
| TA_UPGRADE_LLM_CATALOG | 0 | 1 |
| TA_UPGRADE_STRUCTURED_OUTPUT | 0 | 1 |
| TA_UPGRADE_PERSISTENT_MEMORY | 0 | 1 |
| TA_UPGRADE_CHECKPOINT_UI | 0 | 1 |

## Tier A2-A4、B、C 执行方式

以下 Tier 需要全栈启动（API + MySQL + LLM）后运行：

### 前置步骤

`powershell
# 1. 确保 API 运行
npm run dev:api   # 或 .\一键启动.bat

# 2. 确保前端 preview 构建
cd frontend && npm run build && npx vite preview --port 4173

# 3. 设置测试凭据（不进 git）
\     = "admin"
\ = "your_admin_password"
`

### Baseline Profile（旧功能回归）

`powershell
powershell -File scripts/e2e/run-fullstack-playwright.ps1 -Profile baseline
# 含 Tier A2/A3/A4（live）

# 含 C1快速分析/C2智能分析/C4K线/C5LLM回归：
powershell -File scripts/e2e/run-fullstack-playwright.ps1 -Profile baseline -IncludeHeavy
`

### Upgrade Profile（新特性验收）

`powershell
# 先重启 API 以加载 upgrade flags
# \=1 ... (run-fullstack-playwright.ps1 自动设置)
powershell -File scripts/e2e/run-fullstack-playwright.ps1 -Profile upgrade -IncludeHeavy
`

## Tier B 验收矩阵（升级特性）

| ID | Sprint | 断言 | 预期状态 |
|----|--------|------|----------|
| B1 | S1 LLM Catalog | providers含openai/deepseek/qwen/glm/minimax；regions含cn/intl | 待执行 |
| B2 | S1 Version | fork=ta-cn.1, upstream=0.2.5 | 待执行 |
| B3 | S4 Checkpoint | GET /checkpoint返回JSON；UI出现「强制重跑」按钮 | 待执行 |
| B4 | S5 DecisionArchive | 报告详情「历史决策档案」可见 | 待执行 |
| B5 | S3 Sentiment分组 | 数据源弹窗含sentiment_data分类 | 待执行 |
| B6 | S2 Structured(间接) | rating_5tier列不崩溃；沙盘三档仍显示 | 待执行 |

## Tier C 标的矩阵（重型）

| ID | 标的 | 市场 | 类型 |
|----|------|------|------|
| C1-A1 | 600519.SH | A股 | 快速分析+数据源弹窗 |
| C1-A2 | 000001.SZ | A股 | 快速分析交叉验证 |
| C1-DS | 数据源dialog | A股 | stk_auction/rt_k四态验证 |
| C2-A1 | 600519.SH | A股 | 智能分析7analyst |
| C2-CP | 000001.SZ | A股 | checkpoint刷新恢复 |
| C3-Fast | latest | - | provenance+derived_signals |
| C3-Full | latest | - | 沙盘研判+决策档案 |
| C4 | 600519.SH | A股 | K线图+报价badge |
| C4-HK | 00700.HK | 港股 | ticker后缀保留 |
| C5 | 600519.SH | A股 | LLM桥接回归 |
| Tushare-chain | 600519.SH | A股 | 12接口NotImplement≤2 |

## 回归守护清单

- [x] TypeScript 类型检查通过（0 errors）
- [x] Mock 套件 14/15 通过（1 个 pre-existing 失败）
- [ ] Live A2 — API smoke（待全栈启动后执行）
- [ ] Live A3 — 登录导航（待全栈启动后执行）
- [ ] Live A4 — 配置只读（待全栈启动后执行）
- [ ] Tier B B1-B6 — 升级特性（待 upgrade flags 启动后执行）
- [ ] Tier C C1-C5 — 重型端到端（待真实 LLM+Tushare 环境）

## 执行记录

此报告为工程建设完成后的初始报告。Tier A2-D 的实际执行结果
请在全栈环境中运行上述命令后更新本文件。
每次执行后 scripts/e2e/run-fullstack-playwright.ps1 会自动写入
frontend/test-results/summary-{profile}.md 并截图至
frontend/test-results/screenshots/{profile}/
