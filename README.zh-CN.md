# Nova-TradingAgent

[English](README.md) · [简体中文](README.zh-CN.md) · [日本語](README.ja.md) · [한국어](README.ko.md) · [Español](README.es.md) · [Français](README.fr.md)

**十五名投研智能体，一张可自托管的 A 股研究台。**

把上游 TradingAgents 的多智能体辩论图，做成能登录、能看 K 线、能按点数给多人用的本机投研台。默认**不会自动下单**。

[![License: AGPL v3](https://img.shields.io/badge/License-AGPL_v3-blue.svg)](LICENSE)
[![Release](https://img.shields.io/github/v/release/rufeng0411/Nova-TradingAgent)](https://github.com/rufeng0411/Nova-TradingAgent/releases)
[![Docs](https://img.shields.io/badge/docs-GitHub_Pages-2ea44f)](https://rufeng0411.github.io/Nova-TradingAgent/)
[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)

**[安装](docs/zh-CN/install.md)** · **[使用手册](docs/zh-CN/user-guide.md)** · **[能力亮点](docs/zh-CN/capabilities.md)** · **[Releases](https://github.com/rufeng0411/Nova-TradingAgent/releases)** · **[交流合作](#交流合作)**

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

---

## 产品介绍

### 是什么

**Nova-TradingAgent** 是面向 A 股的自托管多智能体投研工作台。你在本机（或自己的服务器）跑一套 FastAPI + 前端 SPA：登录后提交标的，十五个智能体按角色分工——分析、多空辩论、交易草案、风控裁决——最后落到结构化研报，而不是一段无法复核的聊天记录。

它继承了原版 TradingAgents 的核心：用图把研究员、多空双方、交易员和风控串成一轮可复现的研究。本仓库在此之上补上 Web 工作台、专业 K 线、短链路快速分析、数据翻译层、可选 Tushare L2 委托队列、可选 Microsoft Qlib 量化桥，以及给多用户用的点数订阅与管理后台。

这是**研究与决策辅助**，不是交易执行系统。默认不连券商下单。

### 能干什么

- **完整投研一轮：** 侧栏「智能分析」提交代码或名称，看工作流画布、多空/风控辩论 Drawer、决策卡与历史研报。
- **看盘与短判断：** 「K 线分析」用 ChartPro 看日/周/月 K、复权、均线布林、MACD 标注和 Ai 盘面解读；「快速分析」用约 22 个特征槽走单轮 LLM，大约两分钟出结论卡（默认关闭，需自行打开）。
- **把数据喂给模型之前先整理：** 行情、财务、资金先变成结论与证据，而不是把原始大表塞进提示词；缺某一数据源时软降级，整单不崩。
- **按需加深盘口：** 有 Tushare L2 / 委托队列权限时打开开关，智能分析可引用队列压力；没权限则该项为空，分析照常结束。
- **按需接量化评估：** 本机已有 Qlib 数据时，用独立工作区 `QLIB/` 走 inbox/outbox 文件桥；主进程不 `import qlib`，Docker 镜像也不带 Qlib。
- **多人共用一台实例：** 账户、点数、Free/Pro/Team 套餐申请（管理员审核）、流水；管理员在 `/admin` 看用户、套餐、用量、审计与运营报表。
- **值班向功能：** 自选定时在交易日夜间窗口跑分析、跟踪看板、任务中心、设置里换模型厂商。

### 有什么优势

| | 原版 TradingAgents | 本仓库 Nova-TradingAgent |
| --- | --- | --- |
| 形态 | 脚本 / 笔记本跑一轮辩论图 | 可登录的 Web 投研台（同源 `/v1`，端口 **8000**） |
| 智能体 | 上游公开叙述多为十四人图 | **十五人**：默认图含**量价分析师** |
| 看盘 | 无专业 K 线工作台 | ChartPro + Ai 解读 |
| 短链路 | 无 | 快速分析（单轮 LLM，默认关） |
| 数据进模型 | 容易把原始表直接塞进提示词 | **翻译层**：结论 + 证据 |
| L2 | 无产品级委托队列接入 | Tushare L2 **opt-in** |
| 量化 | 无独立 Qlib 桥 | `QLIB/` 沙盒 + 文件队列，默认关 |
| 用户与商业化 | 单次本地运行 | 多用户、点数订阅、完整管理后台 |
| 许可 | 视上游版本而定 | 全树 **AGPL-3.0** |

相对「只跑一轮 Agent 图」，这里多出来的是：**看得见过程、留得下研报、分得清权限、运营得了多人**。相对「网上随便一个看盘站」，这里多出来的是：**辩论可复核、数据先翻译再进模型、L2/Qlib 按你的权限与本机数据打开**。

---

## 从原版继承了什么

上游 TradingAgents 把投研拆成一条图：分析师写材料 → 多空研究员对辩 → 研究总监收口 → 交易员出草案 → 风控角色挑刺 → 风控裁决拍板。本仓库**没有丢掉这条链**，默认节点仍是：

市场 · 情绪 · 新闻 · 基本面 · 宏观 · 主力资金 · **量价** · 多空研究员 · 研究总监 · 交易员 · 三风控 · 风控裁决。

<p align="center">
  <img src="assets/schema.png" width="100%" alt="十五名投研智能体协作图">
</p>

在 Web 里，这条链变成可盯的画布和按轮次流式发言的辩论 Drawer，最后是结构化决策卡，而不是终端里一闪而过的日志。

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

---

## 本仓库相对原版多了什么

下面这些是原项目（脚本/笔记本辩论图）**没有**的产品面。K 线与快速分析用实拍；L2 / Qlib 用标识说明能力，不配未开通权限的假盘口；订阅与后台用本机实拍。

### 1. 专业 K 线工作台（ChartPro）

原项目没有独立看盘页。这里是日/周/月 K、复权、均线与布林、MACD 金叉/死叉标注、报价头条、**Ai 盘面解读**。分时 / 五档按账户权益可选。不是券商下单终端。

<p align="center">
  <img src="assets/web/chartpro.png" width="100%" alt="K 线分析：上证指数日K、均线布林、MACD 金叉死叉、报价头条">
</p>

入口：侧栏 **K 线分析** → `/chart`。手册：[user-guide.md §4](docs/zh-CN/user-guide.md)。

### 2. 快速分析（约两分钟短链路）

原项目没有「跳过十五人辩论、先出一张结论卡」的路径。这里并行采集快照明细（60 日日 K、日线 RT、集合竞价等）→ 约 22 个特征槽 → **单轮 LLM**。默认 `TA_FAST_ANALYSIS_ENABLED=0`。

<p align="center">
  <img src="assets/web/fast-analysis.png" width="100%" alt="快速分析：2 分钟决策辅助，标的输入与风险偏好">
</p>

入口：侧栏 **快速分析** → `/analysis/fast`。手册：[user-guide.md §3](docs/zh-CN/user-guide.md)。

### 3. L2 数据接入（Tushare 委托队列，按需打开）

<p align="center">
  <img src="assets/web/tushare.svg" height="56" alt="Tushare">
  &nbsp;&nbsp;&nbsp;
  <img src="assets/web/l2-orderqueue.svg" height="72" alt="L2 买卖盘队列示意">
</p>

原版图不会把 **L2 委托队列 / 盘口压力** 做成产品开关。本仓库把 Tushare 的队列类数据接到翻译层和智能分析的数据源里，用来回答「买盘/卖盘挂单厚度、队列拥挤」这类原版日线级数据回答不了的问题。

它**不是开箱功能**：

- `.env` 默认 `TA_TUSHARE_L2_ENABLED=0`。没有 Tushare L2 / 委托队列权限时不要打开。
- 打开后，无权限或接口失败时**该项为空或软失败**，智能分析仍会走完——不会因为没有 L2 整单崩溃。
- 需要时再设 `TA_TUSHARE_L2_ENABLED=1`（可选 `TA_TUSHARE_L2_API`），重启 API，在智能分析「数据源」或 K 线高级盘口核对是否命中。

上图左侧是本仓库使用的 Tushare 数据源标识；右侧是买卖队列的示意，**不是**某一时刻的真实盘口截图。没有 L2 权限的环境截出来也是空的，所以这里不用假图充数。配置见 [configure.md](docs/zh-CN/configure.md)，操作见 [user-guide.md](docs/zh-CN/user-guide.md)「L2 委托队列」。

### 4. Qlib 分析集成（独立工作区，默认关闭）

<p align="center">
  <img src="assets/web/qlib-logo.png" height="72" alt="Microsoft Qlib">
</p>

原版没有把 [Microsoft Qlib](https://github.com/microsoft/qlib) 做成与主站隔离的评估沙盒。本仓库在仓库根提供 **`QLIB/` 独立工作区**：官方 Qlib 源码进 submodule 或单独 clone，用**另一套 Python 环境**跑 worker；主 FastAPI **不得** `import qlib`。

工作方式是文件队列，而不是把量化训练塞进 Web 请求里：

1. 主系统把评估任务写到 `data/qlib_bridge/inbox/{run_id}/`（需 `TA_QLIB_BRIDGE_ENABLED=1`）。
2. `QLIB/ta_bridge/worker.py` 在独立环境读取 inbox，把结果写到 `outbox/`。
3. 主系统再 `qlib_bridge_import` 收回结论，供投研链路引用。

默认所有 `TA_QLIB_*_ENABLED=0`。**Docker 镜像不含 Qlib**（镜像只带 API、智能体包、调度与前端 dist）。适合本机已经有 Qlib 数据与因子实验的人；不是「clone 完就能回测全市场」的开箱承诺。说明见仓库内 [QLIB/README.md](QLIB/README.md)。

### 5. 可订阅的多用户（点数、套餐、流水）

原版是一次本地运行、没有账户体系。这里每台自托管实例可以有多名登录用户：分析消耗**点数**，用户在 **订阅** 页看余额、申请 Free / Pro / Team 套餐（默认需管理员审核），并查看点数流水。运营的是**你这台实例**，不是本仓库对外承诺托管计费或代收款。

<p align="center">
  <img src="assets/web/subscription.png" width="100%" alt="订阅与流水：余额、Free/Pro 套餐申请、点数流水">
</p>

入口：侧栏 **订阅** → `/subscription`。账户页也可看点数与套餐到期。空库管理员带初始点数；`TA_ALLOW_REGISTRATION=0` 时不开放公开注册，由管理员在后台加用户。

### 6. 管理后台（报表、结算、观测、审计）

原版没有运营后台。管理员从顶栏进入 `/admin`，侧栏按「分析报表 / 商业化与结算 / 运行与观测 / 安全与审计 / 内容与品牌」分组：用户趋势、收入与用量、订单与套餐、点数账本与对账、API 成本、任务与 AI 调用日志、操作审计、用户管理等。用来管**本实例**的人、点和用量，而不是把开源仓库变成对外 SaaS 承诺。

<p align="center">
  <img src="assets/web/admin.png" width="100%" alt="管理后台运营概览：用户与用量趋势、P95 延迟">
</p>

<p align="center">
  <img src="assets/web/admin-users.png" width="100%" alt="管理后台用户管理：邮箱、角色、状态、点数">
</p>

手册：[user-guide.md §10](docs/zh-CN/user-guide.md)。验收时空库用户表应只有你创建的管理员。

### 7. 翻译层、自选定时与跟踪

- **翻译层：** 模型读整理过的结论，不是整张原始表。这是相对「把 CSV 糊进 prompt」的原版用法的产品化差异，和 L2/Qlib 一样默认对缺数据宽容。
- **自选 & 定时：** 对自选标的在交易日夜间窗口自动跑分析。
- **跟踪看板、任务中心、设置：** 持仓跟踪、异步任务、换模型厂商与 API Key。

<p align="center">
  <img src="assets/web/timer_analysis.png" width="70%" alt="自选标的的定时分析：交易日夜间窗口自动跑">
  <img src="assets/web/settings.png" width="28%" alt="设置页：模型厂商与 API Key">
</p>

---

## 安装

安装请按 [docs/zh-CN/install.md](docs/zh-CN/install.md)。推荐：SQLite、源码构建前端，uvicorn 开在 **8000**。本机开发用的 Electron / MySQL、Vite 5173、API 8001 是另一套，不要和这条混用。没有 `frontend/dist` 时页面不会出来。

Docker 镜像在打 `v*` 标签后才会推到 `ghcr.io/rufeng0411/Nova-TradingAgent`。镜像还没出来时 `docker pull :latest` 会失败，先走源码安装即可。镜像里没有 Qlib。

## 基本配置

干净启动必填：管理员口令、`TA_APP_SECRET_KEY`（≥32 字节）、`data/` 下的 SQLite。进 UI 不必先填 LLM；真要跑分析再配 `TA_API_KEY` / `TUSHARE_TOKEN`。L2、快速分析、Qlib 桥、公开注册都是默认关闭的开关。详见 [docs/zh-CN/configure.md](docs/zh-CN/configure.md) 与 `.env.example` 顶部 Quick start。

## 文档

- [安装](docs/zh-CN/install.md) · [Install](docs/en/install.md)
- [使用手册](docs/zh-CN/user-guide.md)
- [故障排除](docs/zh-CN/troubleshooting.md)
- [基本配置](docs/zh-CN/configure.md)
- [能力亮点](docs/zh-CN/capabilities.md)
- [FAQ](docs/zh-CN/faq.md)

## 交流合作

商务与合作请加微信 **山君**，扫码添加。

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
