# 能力亮点

一页对照：**原版辩论图继承了什么**，以及本仓库多出来的产品面。没有目录树、没有数据流实现、没有二次开发路线图。

## 产品一句话

自托管 A 股投研台：十五个智能体辩论出结构化研报；K 线与快速分析补看盘和短判断；翻译层先整理再进模型；L2 / Qlib / 多用户订阅与后台按你的权限和运营需要打开。默认不下单。

## 从原版继承

默认一条投研链：七名分析师（市场、情绪、新闻、基本面、宏观、主力资金、**量价**）→ 多空辩论 → 研究总监 → 交易员 → 三风控 → 风控裁决。Web 画布与辩论 Drawer 让原版图变得可见、可复核。

## 翻译层

行情、财务、资金等先被整理成**结论与证据**，再交给模型，而不是把原始大表塞进提示词。缺少某一数据源时该槽位软降级，整单不崩。

## Web 工作台（原项目没有的页面）

同一套 FastAPI，构建后的 SPA 挂在 **8000**：

- **K 线分析** ChartPro（`/chart`）：专业 K 线 + Ai 解读 — `assets/web/chartpro.png`
- **快速分析**（`/analysis/fast`）：约 2 分钟单轮 LLM — `assets/web/fast-analysis.png`
- 智能分析画布 / 辩论 Drawer / 研报 — `assets/web/analysis.png` 等
- 自选定时、跟踪看板、设置

## L2 数据接入（原项目没有）

Tushare **委托队列 / 盘口压力**做成产品开关，默认关（`TA_TUSHARE_L2_ENABLED=0`）。用来补日线回答不了的挂单厚度与队列拥挤。需要独立 L2 权限；无权限时该项为空，智能分析继续。不用未开通环境的空盘口冒充实拍；标识见 README `assets/web/tushare.svg` 与 `l2-orderqueue.svg`。

## Qlib 分析集成（原项目没有）

独立工作区 `QLIB/` + inbox/outbox 文件桥，主进程不 `import qlib`。全部 `TA_QLIB_*` 默认 0。**不进 Docker 镜像**。适合本机已有 Qlib 数据的人。标识见 `assets/web/qlib-logo.png`。

## 可订阅多用户（原项目没有）

账户、点数、Free/Pro/Team 套餐申请（管理员审核）、流水。侧栏 **订阅** `/subscription` — `assets/web/subscription.png`。管的是本实例配额，不是托管收款 SLA。

## 管理后台（原项目没有）

`/admin`：报表、套餐与订单、点数账本、API 成本、任务与 AI 日志、审计、用户管理。实拍 `assets/web/admin.png`、`admin-users.png`。
