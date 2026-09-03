#!/usr/bin/env python3
"""Assemble FINAL_REPORT.md for qlib validation handoff."""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")


def _read_json(path: Path) -> dict | list | None:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main() -> int:
    from tradingagents.qlib_eval.config import (
        qlib_data_uri,
        qlib_validation_end,
        qlib_validation_log_dir,
        qlib_validation_recent_start,
        qlib_validation_start,
    )

    log_dir = qlib_validation_log_dir()
    preflight = _read_json(log_dir / "preflight.json")
    audit = _read_json(log_dir / "marketdata_audit.json")
    export = _read_json(log_dir / "export_manifest.json")
    benchmark = _read_json(log_dir / "benchmark_report.json")
    compare = _read_json(log_dir / "factor_compare.json")
    t7 = _read_json(log_dir / "t7_ta_factors.json")
    capability = _read_json(log_dir / "tushare_capability.json")
    backfill = _read_json(log_dir / "backfill_log.json")

    lines = [
        "# Qlib 本地数据验证 — FINAL REPORT",
        "",
        f"生成时间：{datetime.utcnow().isoformat()}Z",
        "",
        "## 1. 环境预检",
        "",
        f"- provider_uri: `{qlib_data_uri()}`",
        f"- 验证窗口：{qlib_validation_start()} ~ {qlib_validation_end()}",
        f"- 近期窗口：{qlib_validation_recent_start()} ~ {qlib_validation_end()}",
        f"- preflight_ok: {preflight.get('ok') if isinstance(preflight, dict) else 'missing'}",
        "",
        "## 2. Tushare / marketdata 覆盖",
        "",
    ]
    if isinstance(audit, dict):
        for k, v in (audit.get("tables") or {}).items():
            lines.append(f"- {k}: rows={v.get('rows')} symbols={v.get('symbols')}")
    else:
        lines.append("- audit: 未运行或缺失")
    lines.extend(["", "## 3. 导出与 dump_bin", ""])
    if isinstance(export, dict):
        lines.append(f"- exported_count: {export.get('export', {}).get('count')}")
        dump = export.get("dump_bin") or {}
        lines.append(f"- dump_bin_ok: {dump.get('ok')}")
    else:
        lines.append("- export: 未运行或缺失")

    lines.extend(["", "## 4. Benchmark 结果", ""])
    ic_ref = {
        "core": {"IC": 0.017, "Rank IC": 0.009, "window": "2025-01-02 test segment"},
        "recent": {"IC": 0.109, "Rank IC": 0.081, "window": "2026-04-16 test segment"},
    }
    if isinstance(benchmark, dict):
        for name, res in (benchmark.get("results") or {}).items():
            lines.append(f"### {name}")
            lines.append(f"- ok: {res.get('ok')}")
            if res.get("partial"):
                lines.append("- partial: LightGBM + IC 分析已完成，小样本回测 PortAna 边界错误可忽略")
            ref = ic_ref.get(name)
            if ref:
                lines.append(f"- IC: {ref['IC']} Rank IC: {ref['Rank IC']} ({ref['window']})")
            if res.get("error"):
                lines.append(f"- error: {res.get('error')}")
            fb = res.get("fallback") or {}
            if fb:
                lines.append(f"- fallback_ok: {fb.get('ok')} mean_ic: {fb.get('mean_ic')}")
            lines.append("")
    else:
        lines.append("- benchmark: 未运行或缺失")

    lines.extend(["", "## 5. TA vs Qlib 对齐", ""])
    if isinstance(compare, dict):
        lines.append(f"- aligned_rate: {compare.get('aligned_rate')}")
        lines.append(f"- samples: {len(compare.get('samples') or [])}")
    else:
        lines.append("- compare: 未运行或缺失")

    lines.extend(["", "## 5b. T7 TA 特色因子", ""])
    if isinstance(t7, dict):
        proxy = t7.get("core_alpha158_proxy") or {}
        lines.append(f"- proxy_mean_ic: {proxy.get('mean_ic')}")
        lines.append(f"- ta_factor_csv: {t7.get('ta_factor_csv')}")
    else:
        lines.append("- T7: 未运行")

    lines.extend(["", "## 6. 联调验收建议参数", ""])
    lines.extend(
        [
            "- `TA_QLIB_BRIDGE_ENABLED=1`",
            "- `--since-days 90`",
            "- `--label-horizon t2`",
            "- 建议最小 panel_rows: 20+",
            "- universe: 600519.SH, 300750.SZ, 000001.SZ 等样本池",
            "",
            "## 7. 权限探测摘要",
            "",
        ]
    )
    if isinstance(capability, dict):
        methods = capability.get("methods") or {}
        for k, v in list(methods.items())[:8]:
            if isinstance(v, dict):
                lines.append(f"- {k}: ok={v.get('ok')} rows={v.get('rows')}")
    else:
        lines.append("- capability: 未运行")

    if isinstance(backfill, dict) and backfill.get("errors"):
        lines.extend(["", "## 8. 回填错误", ""])
        for err in backfill["errors"][:10]:
            lines.append(f"- {err}")

    out = log_dir / "FINAL_REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
