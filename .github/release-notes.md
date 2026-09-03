## v0.2.5 — Public AGPL release of Nova-TradingAgent

Self-hosted A-share research desk: 15-agent debate, optional Tushare L2 (opt-in), K-line workstation, translation layer.

### Install

See `docs/en/install.md` / `docs/zh-CN/install.md`.

```bash
uv sync
cd frontend && npm install && npm run build && cd ..
uv run python -m uvicorn api.main:app --host 127.0.0.1 --port 8000
```

Health: `GET /healthz` (not `/health`).

### 中文

完整产品树 AGPL-3.0 发布。请按安装文档从源码构建前端后使用 8000 端口。L2 默认关闭。Docker 镜像随 `v*` 标签构建，不含 Qlib。
