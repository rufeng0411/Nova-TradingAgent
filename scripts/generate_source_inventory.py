"""Generate docs/source-files-inventory.md: repo .py/.ts/.tsx (excl. node_modules, dist, .venv)."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "source-files-inventory.md"

EXCLUDE_DIR_NAMES = {
    "node_modules",
    "dist",
    ".venv",
    "venv",
    "__pycache__",
    ".git",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
}
EXTS = {".py", ".ts", ".tsx"}


def collect() -> list[Path]:
    out: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(ROOT):
        dpath = Path(dirpath)
        # prune
        dirnames[:] = [d for d in dirnames if d not in EXCLUDE_DIR_NAMES and not d.startswith(".")]
        for name in filenames:
            p = dpath / name
            if p.suffix.lower() in EXTS:
                out.append(p)
    return sorted(out, key=lambda x: str(x).lower())


def phase(p: Path) -> str:
    rel = p.relative_to(ROOT)
    parts = rel.parts
    if not parts:
        return "other"
    top = parts[0]
    if top == "tradingagents":
        return "A–D 核心包"
    if top == "api":
        return "E HTTP 与 api.services"
    if top == "frontend" and "src" in parts:
        return "F 前端"
    if top == "scheduler":
        return "G 调度"
    if top == "tests":
        return "G 测试"
    if top in ("cli",) or (top == "scripts" and p.suffix == ".py"):
        return "G 其它/脚本"
    if top == "scripts":
        return "G 其它/脚本"
    return "G 其它/根目录"


def main() -> None:
    files = collect()
    buckets: dict[str, list[Path]] = {}
    for f in files:
        ph = phase(f)
        buckets.setdefault(ph, []).append(f)

    lines = [
        "# 自有源码文件清单",
        "",
        "由 `scripts/generate_source_inventory.py` 生成。包含扩展名: "
        + ", ".join(sorted(EXTS))
        + f"。排除目录: `{', '.join(sorted(EXCLUDE_DIR_NAMES))}`。",
        "",
        f"**合计**（去重文件数）: {len(files)}",
        "",
        "## 计划阶段映射",
        "",
        "| 阶段 | 说明 | 本清单 bucket |",
        "|------|------|----------------|",
        "| A | default_config / llm_clients / prompts | `tradingagents` 子路径见下 |",
        "| B | dataflows | `tradingagents/dataflows` |",
        "| C | agents | `tradingagents/agents` |",
        "| D | graph | `tradingagents/graph` |",
        "| E | api | `api/` |",
        "| F | frontend | `frontend/` 下 ts/tsx |",
        "| G | scheduler / tests / scripts | 对应 bucket |",
        "",
    ]

    order = [
        "A–D 核心包",
        "E HTTP 与 api.services",
        "F 前端",
        "G 调度",
        "G 测试",
        "G 其它/脚本",
        "G 其它/根目录",
    ]
    for bucket in order:
        if bucket not in buckets:
            continue
        lines.append(f"## {bucket}")
        lines.append("")
        for f in buckets[bucket]:
            rel = f.relative_to(ROOT).as_posix()
            lines.append(f"- `{rel}`")
        lines.append("")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {OUT} ({len(files)} files)")


if __name__ == "__main__":
    main()
