# Nova-TradingAgent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md)

**十五名投研智能体，一张可自托管的 A 股研究台。**

自己部署、面向 A 股的投研台。十五个智能体一起辩论；K 线带 Ai 解读；Tushare L2 委托队列按需打开。模型读的是整理过的结论，不是整张原始表。

这是**投研工作台**，默认**不会自动下单**。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/rufeng0411/Nova-TradingAgent)](https://github.com/rufeng0411/Nova-TradingAgent/releases)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**[安装](docs/zh-CN/install.md)** · **[使用手册](docs/zh-CN/user-guide.md)** · **[Releases](https://github.com/rufeng0411/Nova-TradingAgent/releases)** · **[交流合作](#交流合作)**

| 自托管 | 文档 | 交流合作 |
| --- | --- | --- |
| SQLite + `uv` + 构建后的前端，端口 **8000** | [安装](docs/zh-CN/install.md) · [使用手册](docs/zh-CN/user-guide.md) | 微信 **山君** |

```bash
git clone https://github.com/rufeng0411/Nova-TradingAgent.git
cd Nova-TradingAgent
cp .env.example .env          # Windows: Copy-Item .env.example .env
# 填写 TA_ADMIN_PASSWORD、TA_APP_SECRET_KEY、DATABASE_URL（见 .env.example 顶部 Quick start）
uv sync
cd frontend && npm install && npm run build && cd ..
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

浏览器打开 `http://127.0.0.1:8000`。健康检查：`GET http://127.0.0.1:8000/healthz`。

不构成投资建议。行情与财务数据可能延迟。

## 相对原版多了什么

上游 TradingAgents 是**多智能体辩论图**（脚本/笔记本跑一轮研究）。**Nova-TradingAgent** 做成可自托管的 A 股 Web 工作台。下面这些页面是原项目没有的，也是本仓库的重点。

### 1. K 线分析（ChartPro）

原项目**没有**专业 K 线工作台。本页是独立终端：日/周/月 K、复权、均线与布林、MACD 金叉/死叉标注、报价头条、**Ai 盘面解读**；分时 / 五档盘口按账户权益可选。不是券商下单终端。

<p align="center">
  <img src="assets/web/chartpro.png" width="100%" alt="K 线分析：上证指数日K、均线布林、MACD 金叉死叉、报价头条">
</p>

入口：侧栏 **K 线分析** → `/chart`。手册：[user-guide.md §4](docs/zh-CN/user-guide.md)。

### 2. 快速分析

原项目**没有** 2 分钟短链路。这里并行采集快照明细（60 日日 K、日线 RT、集合竞价等）→ 抽取约 22 个特征槽 → **单轮 LLM**，输出结论卡；不是完整 15 人辩论。默认 `TA_FAST_ANALYSIS_ENABLED=0`，打开后侧栏可用。

<p align="center">
  <img src="assets/web/fast-analysis.png" width="100%" alt="快速分析：2 分钟决策辅助，标的输入与风险偏好">
</p>

入口：侧栏 **快速分析** → `/analysis/fast`。手册：[user-guide.md §3](docs/zh-CN/user-guide.md)。

### 3. 15 名智能体、翻译层、可选 L2

- **量价分析师**进默认图（15 节点，不是旧文的 14）。
- **翻译层**：行情/财务/资金先整理成结论再进模型，而不是把原始大表塞进提示词。
- **Tushare L2 委托队列**是 opt-in（`TA_TUSHARE_L2_ENABLED=0`）。无权限时盘口为空，智能分析继续。

### 4. Web 智能分析（画布 + 辩论 + 研报）

原版多在终端跑图；这里有工作流画布、辩论 Drawer、结构化研报。嵌入行情区也是本产品补上的，不是上游 CLI。

<p align="center">
  <img src="assets/web/analysis.png" width="100%" alt="智能分析：对话提交、协同工作流画布、嵌入 K 线">
</p>

<p align="center">
  <img src="assets/web/debate_drawer.png" width="90%" alt="多智能体多空/风控辩论 Drawer，按轮次流式发言">
</p>

<p align="center">
  <img src="assets/web/detail.png" width="48%" alt="结构化研报与决策卡片">
  <img src="assets/web/reports.png" width="48%" alt="历史研报列表">
</p>

### 5. 自选定时、跟踪看板、完整登录后台

原项目没有自选定时、持仓跟踪看板、点数/套餐/管理后台。这些都在本树里，按需配置。

<p align="center">
  <img src="assets/web/timer_analysis.png" width="70%" alt="自选标的的定时分析：交易日夜间窗口自动跑">
  <img src="assets/web/settings.png" width="28%" alt="设置页：模型厂商与 API Key">
</p>

Qlib 桥默认关闭且 **不在 Docker 镜像**；有本机数据再开，不配假图。

## 工作台如何运转

<p align="center">
  <img src="assets/schema.png" width="100%" alt="十五名投研智能体协作图">
</p>

默认图节点：市场、情绪、新闻、基本面、宏观、主力资金、量价，加上多空研究员、研究总监、交易员、三风控与风控裁决。

## 安装

陌生人请**只按** [docs/zh-CN/install.md](docs/zh-CN/install.md) 操作。黄金路径是 SQLite + 源码构建 + **8000** 端口的 `uvicorn`。这不是维护者本机的 Electron + MySQL 开发栈（Vite **5173** / API **8001**）。

Docker 镜像随 `v*` 标签由 workflow 发布到 `ghcr.io/rufeng0411/Nova-TradingAgent`。在该构建完成前 `docker pull :latest` 会 404 — 请用源码安装。

当前 Dockerfile **不含** Qlib。

## 基本配置

干净启动必填：管理员口令、`TA_APP_SECRET_KEY`（≥32 字节）、`data/` 下的 SQLite。分析另需 `TA_API_KEY` / `TUSHARE_TOKEN`（不填也能进 UI）。详见 [docs/zh-CN/configure.md](docs/zh-CN/configure.md) 与 `.env.example` 顶部 Quick start。

## 文档

- [安装](docs/zh-CN/install.md) · [Install](docs/en/install.md)
- [使用手册](docs/zh-CN/user-guide.md)
- [故障排除](docs/zh-CN/troubleshooting.md)
- [基本配置](docs/zh-CN/configure.md)
- [能力亮点](docs/zh-CN/capabilities.md)
- [FAQ](docs/zh-CN/faq.md)

## 自托管说明（点数 / 后台）

首次启动按 `TA_ADMIN_*` 创建管理员 `admin` / `admin@localhost`。黄金路径建议 `TA_ALLOW_REGISTRATION=0`，空库只有管理员。点数、套餐与 `/admin` 面向运营本实例的人，不是对外 SaaS 承诺。

## 交流合作

商务与合作请加微信 **山君**，扫码添加（不只是报 bug）。

<p align="center">
  <img src="assets/community/wechat-contact.png" width="280" alt="微信：山君">
</p>

Issue 请用仓库模板。不要粘贴 API Key。

## 许可

GNU Affero General Public License v3.0。若你修改本软件并通过网络向用户提供，必须向用户提供对应源码。见 [LICENSE](LICENSE)、[NOTICE](NOTICE)、[THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md)。

## 免责声明

- **不构成投资建议。** 输出是算法研究结果，不是买卖推荐。
- **数据可能延迟或不完整。** 请以交易所公告与你的券商为准。
- 不出现稳赚、必涨类表述。
