#!/usr/bin/env python3
"""Generate FULL_BACKTEST_REPORT.md for CSI300 professional backtest handoff."""

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
        gate_min_ic,
        qlib_data_uri,
        qlib_universe,
        qlib_validation_end,
        qlib_validation_log_dir,
        qlib_validation_start,
        qlib_validation_test_start,
    )

    log_dir = qlib_validation_log_dir()
    audit = _read_json(log_dir / "marketdata_audit_csi300.json") or _read_json(log_dir / "marketdata_audit.json")
    export = _read_json(log_dir / "export_manifest.json")
    benchmark = _read_json(log_dir / "benchmark_report.json")
    compare = _read_json(log_dir / "factor_compare.json")
    universe_meta = _read_json(ROOT / "data" / "qlib_exports" / "universe" / "csi300_meta.json")
    backfill = _read_json(log_dir / "backfill_log_csi300.json")

    lines = [
        "# Qlib 全面回测 — FULL BACKTEST REPORT",
        "",
        f"生成时间：{datetime.utcnow().isoformat()}Z",
        "",
        "## 1. 配置摘要",
        "",
        f"- universe: `{qlib_universe()}`",
        f"- provider_uri: `{qlib_data_uri()}`",
        f"- 数据窗口：{qlib_validation_start()} ~ {qlib_validation_end()}",
        f"- OOS test 窗：{qlib_validation_test_start()} ~ {qlib_validation_end()}",
        f"- gate_min_ic 建议参考：{gate_min_ic()}",
        "",
        "## 2. Universe",
        "",
    ]
    if isinstance(universe_meta, dict):
        lines.append(f"- CSI300 union 标的数：{universe_meta.get('symbol_count')}")
        lines.append(f"- index_code：{universe_meta.get('index_code')}")
    else:
        lines.append("- universe meta: 未生成，请先运行 universe_csi300.py")

    lines.extend(["", "## 3. 数据覆盖门禁", ""])
    if isinstance(audit, dict):
        cov = (audit.get("coverage") or {}).get("test_window") or {}
        lines.append(f"- test_window 覆盖率：{cov.get('coverage_pct')}%")
        lines.append(f"- gate_pass：{audit.get('gate_pass')}")
        for k, v in (audit.get("tables") or {}).items():
            lines.append(f"- {k}: rows={v.get('rows')} symbols={v.get('symbols')}")
    else:
        lines.append("- audit: 缺失")

    lines.extend(["", "## 4. 导出", ""])
    if isinstance(export, dict):
        lines.append(f"- exported_count: {export.get('export', {}).get('count')}")
        lines.append(f"- dump_bin_ok: {(export.get('dump_bin') or {}).get('ok')}")
    else:
        lines.append("- export: 缺失")

    lines.extend(["", "## 5. Benchmark（professional / ta_extra）", ""])
    if isinstance(benchmark, dict):
        for name, res in (benchmark.get("results") or {}).items():
            lines.append(f"### {name}")
            lines.append(f"- ok: {res.get('ok')}")
            if res.get("metrics"):
                m = res["metrics"]
                lines.append(f"- IC: {m.get('IC')} Rank IC: {m.get('Rank IC')} ICIR: {m.get('ICIR')}")
            if res.get("error"):
                lines.append(f"- error: {res.get('error')}")
            lines.append("")
    else:
        lines.append("- benchmark: 缺失")

    lines.extend(["", "## 6. TA vs Qlib 对齐", ""])
    t7 = _read_json(log_dir / "t7_ta_factors.json")
    if isinstance(compare, dict):
        lines.append(f"- aligned_rate: {compare.get('aligned_rate')}")
        lines.append(f"- samples: {len(compare.get('samples') or [])}")
    else:
        lines.append("- compare: 缺失")
    if isinstance(t7, dict):
        lines.extend(["", "### T7 TA 因子 IC 对照", ""])
        core = t7.get("core_alpha158_proxy") or {}
        lines.append(f"- core Alpha158 proxy IC: {core.get('mean_ic')}")
        best = (t7.get("ta_factor_csv") or {}).get("best_factor")
        if best:
            lines.append(f"- best TA CSV factor: {best.get('factor')} IC={best.get('mean_ic')}")
        if t7.get("ic_uplift_best_ta_vs_core") is not None:
            lines.append(f"- uplift vs core: {t7.get('ic_uplift_best_ta_vs_core')}")

    bridge = _read_json(log_dir / "bridge_e2e_smoke.json")
    lines.extend(["", "## 7. Bridge E2E", ""])
    if isinstance(bridge, dict):
        lines.append(f"- run_id: {bridge.get('run_id')}")
        lines.append(f"- status: {(bridge.get('worker') or {}).get('status')}")
    else:
        lines.append("- bridge_e2e: 未运行")

    lines.extend(
        [
            "",
            "## 8. 联调建议",
            "",
            "- `TA_QLIB_EVAL_ENABLED=1`",
            "- `TA_QLIB_BRIDGE_ENABLED=1`",
            "- `TA_QLIB_UNIVERSE=csi300`",
            "- worker: `uv run python QLIB/ta_bridge/worker.py --daemon`",
            "- e2e: `uv run python scripts/qlib/bridge_e2e_smoke.py`",
            "",
        ]
    )

    if isinstance(backfill, dict) and backfill.get("errors"):
        lines.extend(["## 9. 回填错误", ""])
        for err in backfill["errors"][:15]:
            lines.append(f"- {err}")

    out = log_dir / "FULL_BACKTEST_REPORT.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"Wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
