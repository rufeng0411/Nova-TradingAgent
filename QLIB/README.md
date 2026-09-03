# QLIB 独立工作区

本目录用于挂载 **官方 Qlib 仓库**（git submodule 或独立 clone），与主项目 FastAPI 进程隔离。

## 推荐初始化

```bash
# 在项目根目录执行
git submodule add https://github.com/microsoft/qlib.git QLIB/qlib-official
git submodule update --init --recursive
```

若无法使用 submodule，也可手动 clone：

```bash
git clone https://github.com/microsoft/qlib.git QLIB/qlib-official
```

## 独立 Python 环境

```bash
cd QLIB
uv venv .venv
# Windows: .venv\Scripts\activate
uv pip install -e ./qlib-official  # 若已 clone 官方仓库
uv pip install lightgbm pandas pyarrow
```

或使用根目录可选依赖组（与主 venv 分离仍推荐本目录 `.venv`）：

```bash
uv sync --group quant
```

## 文件队列桥接

主系统写入：`data/qlib_bridge/inbox/{run_id}/`

Worker 读取 inbox、输出：`data/qlib_bridge/outbox/{run_id}/`

```bash
# 主系统投递（需 TA_QLIB_BRIDGE_ENABLED=1）
uv run python scripts/qlib_bridge_submit.py --since-days 90

# QLIB worker（独立环境）
uv run python QLIB/ta_bridge/worker.py --once

# 主系统回收结果
uv run python scripts/qlib_bridge_import.py
```

## 目录说明

| 路径 | 用途 |
|------|------|
| `qlib-official/` | 官方 Qlib 源码（submodule，勿直接改主项目业务代码） |
| `ta_bridge/` | Nova-TradingAgent 侧 worker 与契约适配 |
| `.venv/` | 独立虚拟环境（已 gitignore） |

主 FastAPI **不得** `import qlib`；量化训练仅在 worker 子进程/独立环境中运行。
