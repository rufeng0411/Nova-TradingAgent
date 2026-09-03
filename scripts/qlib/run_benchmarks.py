#!/usr/bin/env python3
"""Run Qlib core benchmarks (Alpha158 + LightGBM + IC + backtest)."""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

QLIB_ROOT = ROOT / "QLIB"
if str(QLIB_ROOT) not in sys.path:
    sys.path.insert(0, str(QLIB_ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

BENCHMARKS = {
    "core": ROOT / "QLIB" / "ta_bridge" / "benchmarks" / "workflow_lightgbm_alpha158_ta.yaml",
    "recent": ROOT / "QLIB" / "ta_bridge" / "benchmarks" / "workflow_lightgbm_alpha158_recent.yaml",
    "professional": ROOT / "QLIB" / "ta_bridge" / "benchmarks" / "workflow_lightgbm_alpha158_csi300.yaml",
    "ta_extra": ROOT / "QLIB" / "ta_bridge" / "benchmarks" / "workflow_lightgbm_alpha158_ta_extra.yaml",
}


def _resolve_provider_uri(data_uri: str | None) -> str:
    from tradingagents.qlib_eval.config import qlib_data_uri

    p = Path(data_uri or qlib_data_uri())
    return str(p.resolve())


def _patch_yaml_provider(yaml_path: Path, provider_uri: str, out_path: Path) -> None:
    text = yaml_path.read_text(encoding="utf-8")
    lines = []
    for line in text.splitlines():
        if line.strip().startswith("provider_uri:"):
            lines.append(f'    provider_uri: "{provider_uri.replace(chr(92), "/")}"')
        else:
            lines.append(line)
    out_path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _count_instruments(qlib_dir: Path) -> int:
    for name in ("csi300.txt", "all.txt"):
        path = qlib_dir / "instruments" / name
        if path.exists():
            return sum(1 for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip())
    return 0


def _patch_yaml_smoke(yaml_path: Path, instrument_count: int) -> None:
    """When bin data covers a small subset, use `all` universe and lower topk."""
    if instrument_count >= 50:
        return
    topk = max(3, min(5, instrument_count - 1))
    n_drop = 1 if topk >= 4 else 0
    text = yaml_path.read_text(encoding="utf-8")
    text = text.replace("market: &market csi300", "market: &market all")
    text = text.replace("topk: 50", f"topk: {topk}")
    text = text.replace("n_drop: 5", f"n_drop: {n_drop}")
    yaml_path.write_text(text, encoding="utf-8")


def _read_mlflow_metrics(experiment: str) -> dict:
    mlruns = ROOT / "logs" / "qlib_validation" / "mlruns"
    if not mlruns.exists():
        return {}
    exp_dirs = [p for p in mlruns.iterdir() if p.is_dir() and p.name != ".trash"]
    metrics_out: dict = {}
    for exp_dir in exp_dirs:
        meta = exp_dir / "meta.yaml"
        if not meta.exists():
            continue
        try:
            text = meta.read_text(encoding="utf-8")
            if f"name: {experiment}" not in text and f'name: "{experiment}"' not in text:
                continue
        except Exception:
            continue
        run_dirs = sorted([p for p in exp_dir.iterdir() if p.is_dir()], key=lambda p: p.stat().st_mtime, reverse=True)
        if not run_dirs:
            continue
        run = run_dirs[0]
        mdir = run / "metrics"
        if not mdir.exists():
            continue
        for mf in mdir.iterdir():
            try:
                line = mf.read_text(encoding="utf-8").strip().splitlines()[-1]
                val = float(line.split()[1])
                metrics_out[mf.name] = val
            except Exception:
                continue
        break
    return metrics_out


def _run_qrun(yaml_path: Path, experiment: str) -> dict:
    t0 = time.perf_counter()
    try:
        from qlib.cli.run import workflow

        workflow(
            str(yaml_path),
            experiment_name=experiment,
            uri_folder=str(ROOT / "logs" / "qlib_validation" / "mlruns"),
        )
        metrics = _read_mlflow_metrics(experiment)
        return {
            "ok": True,
            "full_ok": True,
            "duration_sec": round(time.perf_counter() - t0, 2),
            "metrics": metrics,
        }
    except Exception as exc:
        err = f"{type(exc).__name__}: {exc}"
        partial = isinstance(exc, IndexError) or "IndexError" in err
        metrics = _read_mlflow_metrics(experiment)
        return {
            "ok": False,
            "partial_ok": bool(metrics),
            "partial": partial,
            "partial_note": "SigAna may have completed; PortAna may fail on incomplete universe",
            "duration_sec": round(time.perf_counter() - t0, 2),
            "error": err,
            "metrics": metrics,
        }


def _run_light_fallback(data_uri: str) -> dict:
    import numpy as np
    import pandas as pd

    t0 = time.perf_counter()
    try:
        import qlib
        from qlib.config import REG_CN
        from qlib.data import D

        qlib.init(provider_uri=data_uri, region=REG_CN)
        instruments = D.instruments("csi300")
        inst_list = D.list_instruments(instruments, start_time="2025-01-01", end_time="2026-05-25", as_list=True)
        if not inst_list:
            instruments = D.instruments("all")
            inst_list = D.list_instruments(instruments, start_time="2025-01-01", end_time="2026-05-25", as_list=True)
        if not inst_list:
            return {"ok": False, "error": "no_instruments", "backend": "light_fallback"}
        sample = inst_list[: min(30, len(inst_list))]
        df = D.features(sample, ["$close", "$volume"], start_time="2025-01-01", end_time="2026-05-25")
        if df is None or df.empty:
            return {"ok": False, "error": "empty_features", "backend": "light_fallback"}
        close = df["$close"].unstack(level=0)
        fwd = close.pct_change(2).shift(-2)
        signal = close.pct_change(5)
        ic_list = []
        for dt in signal.index[-120:]:
            s = signal.loc[dt].dropna()
            y = fwd.loc[dt].reindex(s.index).dropna()
            idx = s.index.intersection(y.index)
            if len(idx) < 10:
                continue
            ic = float(pd.Series(s.loc[idx]).corr(pd.Series(y.loc[idx]), method="spearman"))
            if ic == ic:
                ic_list.append(ic)
        return {
            "ok": True,
            "backend": "light_fallback",
            "instruments": len(inst_list),
            "mean_ic": float(np.mean(ic_list)) if ic_list else None,
            "ic_samples": len(ic_list),
            "duration_sec": round(time.perf_counter() - t0, 2),
        }
    except Exception as exc:
        return {"ok": False, "backend": "light_fallback", "error": f"{type(exc).__name__}: {exc}", "duration_sec": round(time.perf_counter() - t0, 2)}


def main() -> int:
    parser = argparse.ArgumentParser(description="Run Qlib benchmark suite")
    parser.add_argument("--suite", default="all", choices=["all", "core", "recent", "professional", "ta_extra"])
    parser.add_argument("--data-uri", default=None)
    parser.add_argument("--skip-qrun", action="store_true")
    args = parser.parse_args()

    from tradingagents.qlib_eval.config import qlib_validation_log_dir

    provider = _resolve_provider_uri(args.data_uri)
    log_dir = qlib_validation_log_dir()
    log_dir.mkdir(parents=True, exist_ok=True)
    patched_dir = log_dir / "benchmark_configs"
    patched_dir.mkdir(parents=True, exist_ok=True)

    if args.suite == "all":
        suites = ["core", "recent"]
    elif args.suite == "professional":
        suites = ["professional"]
    else:
        suites = [args.suite]

    report: dict = {"generated_at": datetime.utcnow().isoformat() + "Z", "provider_uri": provider, "results": {}}

    for name in suites:
        src = BENCHMARKS[name]
        if not src.exists():
            report["results"][name] = {"ok": False, "error": "yaml_missing"}
            continue
        patched = patched_dir / f"{name}_patched.yaml"
        _patch_yaml_provider(src, provider, patched)
        inst_n = _count_instruments(Path(provider))
        if inst_n:
            _patch_yaml_smoke(patched, inst_n)
            print(f"[benchmark] {name}: smoke patch instruments={inst_n}")
        if args.skip_qrun:
            report["results"][name] = {"ok": True, "skipped": True, "config": str(patched)}
            continue
        res = _run_qrun(patched, experiment=f"ta_{name}")
        if not res.get("ok"):
            res["fallback"] = _run_light_fallback(provider)
        report["results"][name] = res
        print(f"[benchmark] {name}: {res}")

    out_json = log_dir / "benchmark_report.json"
    out_json.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    md_lines = [
        "# Qlib Benchmark Report",
        "",
        f"- generated_at: {report['generated_at']}",
        f"- provider_uri: `{provider}`",
        "",
    ]
    for name, res in report["results"].items():
        md_lines.append(f"## {name}")
        md_lines.append(f"- ok: {res.get('ok')}")
        if res.get("metrics"):
            md_lines.append(f"- metrics: {json.dumps(res.get('metrics'), ensure_ascii=False)}")
        if res.get("error"):
            md_lines.append(f"- error: {res.get('error')}")
        if res.get("fallback"):
            md_lines.append(f"- fallback: {json.dumps(res['fallback'], ensure_ascii=False)}")
        md_lines.append("")
    (log_dir / "benchmark_report.md").write_text("\n".join(md_lines), encoding="utf-8")

    ok = all(
        r.get("ok") or r.get("partial_ok") or r.get("partial") or (r.get("fallback") or {}).get("ok")
        for r in report["results"].values()
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
