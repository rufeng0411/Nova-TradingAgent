"""Qlib evaluation service — sandbox export, sweeps, gates (feature-flagged)."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy.orm import Session

from api.database import MarketdataSessionLocal, QlibEvalMetricsDB, QlibEvalRunDB, ReportDB
from api.services import report_outcome_service
from tradingagents.qlib_eval.agent.quant_context import build_quant_signal_context
from tradingagents.qlib_eval.bridge.inbox import submit_inbox_package
from tradingagents.qlib_eval.bridge.outbox import import_outbox_result, list_pending_outbox, load_outbox_package
from tradingagents.qlib_eval.config import (
    qlib_bridge_enabled,
    qlib_eval_enabled,
    qlib_sandbox_enabled,
    qlib_sweeps_enabled,
    release_version,
)
from tradingagents.qlib_eval.eval.version_gate import aggregate_version_gates, evaluate_gate
from tradingagents.qlib_eval.sandbox.exporter import build_panel_from_reports, export_panel
from tradingagents.qlib_eval.sandbox.lightgbm_baseline import run_lightgbm_baseline
from tradingagents.qlib_eval.sweeps.rule_sweeps import sweep_all_rules


def _disabled() -> dict[str, Any]:
    return {"enabled": False, "error": "qlib_eval_disabled"}


def is_enabled() -> bool:
    return qlib_eval_enabled()


def persist_metrics(
    db: Session,
    *,
    run_id: str,
    release_ver: str,
    metric_kind: str,
    payload: dict[str, Any],
    label_horizon: str | None = None,
) -> QlibEvalMetricsDB:
    gate = evaluate_gate(
        {
            "hit_rate_pct": payload.get("hit_rate_pct"),
            "ic": payload.get("ic") or payload.get("rank_ic"),
            "coverage_pct": payload.get("coverage_pct"),
        }
    )
    row = QlibEvalMetricsDB(
        id=str(uuid.uuid4()),
        run_id=run_id,
        release_version=release_ver,
        metric_kind=metric_kind,
        label_horizon=label_horizon,
        ic=payload.get("ic"),
        rank_ic=payload.get("rank_ic"),
        hit_rate_pct=payload.get("hit_rate_pct"),
        coverage_pct=payload.get("coverage_pct"),
        gate_passed=bool(gate.get("passed")),
        details_json={"gate": gate, "payload": payload},
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def run_sandbox_export(
    db: Session,
    *,
    user_id: str | None = None,
    since_days: int = 90,
    limit: int = 500,
    created_by: str | None = None,
    async_bridge: bool = True,
) -> dict[str, Any]:
    if not qlib_sandbox_enabled():
        return _disabled()

    if async_bridge and qlib_bridge_enabled():
        return submit_bridge_job(
            db,
            user_id=user_id,
            since_days=since_days,
            limit=limit,
            created_by=created_by,
        )

    run_id = str(uuid.uuid4())
    run = QlibEvalRunDB(
        id=run_id,
        run_type="sandbox",
        release_version=release_version(),
        status="running",
        created_by=created_by,
    )
    db.add(run)
    db.commit()

    mdb = MarketdataSessionLocal()
    try:
        panel = build_panel_from_reports(db, mdb, user_id=user_id, since_days=since_days, limit=limit)
        manifest = export_panel(panel, run_id=run_id)
        baseline = run_lightgbm_baseline(panel, label_col="label_t2")
        run.status = "completed" if baseline.get("status") == "ok" else "failed"
        run.panel_rows = int(len(panel))
        run.manifest_json = manifest
        run.result_json = baseline
        run.error = baseline.get("error")
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

        if baseline.get("status") == "ok":
            persist_metrics(
                db,
                run_id=run_id,
                release_ver=release_version(),
                metric_kind="baseline",
                payload=baseline,
                label_horizon="t2",
            )
        return {
            "enabled": True,
            "run_id": run_id,
            "manifest": manifest,
            "baseline": baseline,
            "panel_rows": int(len(panel)),
        }
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"enabled": True, "run_id": run_id, "error": run.error}
    finally:
        mdb.close()


def submit_bridge_job(
    db: Session,
    *,
    user_id: str | None = None,
    since_days: int = 90,
    limit: int = 500,
    label_horizon: str = "t2",
    created_by: str | None = None,
) -> dict[str, Any]:
    if not qlib_bridge_enabled():
        return _disabled()

    run_id = str(uuid.uuid4())
    run = QlibEvalRunDB(
        id=run_id,
        run_type="bridge",
        release_version=release_version(),
        status="queued",
        created_by=created_by,
    )
    db.add(run)
    db.commit()

    mdb = MarketdataSessionLocal()
    try:
        panel = build_panel_from_reports(db, mdb, user_id=user_id, since_days=since_days, limit=limit)
        if panel.empty:
            run.status = "failed"
            run.error = "empty_panel"
            run.updated_at = datetime.now(timezone.utc)
            db.commit()
            return {"enabled": True, "run_id": run_id, "status": "failed", "error": "empty_panel"}

        inbox = submit_inbox_package(panel, run_id=run_id, label_horizon=label_horizon)
        run.status = "queued"
        run.panel_rows = int(len(panel))
        run.manifest_json = inbox.get("manifest")
        run.result_json = {"mode": "async_bridge", "inbox_dir": inbox.get("inbox_dir")}
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {
            "enabled": True,
            "run_id": run_id,
            "status": "queued",
            "inbox": inbox,
            "panel_rows": int(len(panel)),
            "message": "任务已写入 inbox，请运行 QLIB worker 后执行 import",
        }
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"enabled": True, "run_id": run_id, "status": "failed", "error": run.error}
    finally:
        mdb.close()


def import_bridge_result(db: Session, *, run_id: str) -> dict[str, Any]:
    if not qlib_bridge_enabled():
        return _disabled()

    pkg = import_outbox_result(run_id)
    if not pkg.get("imported"):
        return {"enabled": True, "run_id": run_id, **pkg}

    run = db.query(QlibEvalRunDB).filter(QlibEvalRunDB.id == run_id).first()
    metrics = dict(pkg.get("metrics") or {})
    model_card = dict(pkg.get("model_card") or {})
    agent_ctx = build_quant_signal_context(
        metrics=metrics,
        model_card=model_card,
        summary_md=pkg.get("summary_md"),
    )

    if run:
        run.status = "completed"
        run.result_json = {
            "metrics": metrics,
            "model_card": model_card,
            "agent_context": agent_ctx,
            "predictions_path": pkg.get("predictions_path"),
        }
        run.error = None
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

    persist_metrics(
        db,
        run_id=run_id,
        release_ver=release_version(),
        metric_kind="bridge",
        payload=dict(pkg.get("payload_for_gate") or metrics),
        label_horizon=str(model_card.get("label_horizon") or "t2"),
    )

    return {
        "enabled": True,
        "run_id": run_id,
        "imported": True,
        "metrics": metrics,
        "agent_context": agent_ctx,
    }


def import_all_pending_outbox(db: Session) -> dict[str, Any]:
    if not qlib_bridge_enabled():
        return _disabled()
    pending = list_pending_outbox()
    results = [import_bridge_result(db, run_id=rid) for rid in pending]
    return {"enabled": True, "pending_count": len(pending), "results": results}


def get_quant_context_for_run(db: Session, run_id: str, *, report_direction: str | None = None) -> dict[str, Any]:
    run = db.query(QlibEvalRunDB).filter(QlibEvalRunDB.id == run_id).first()
    if run and isinstance(run.result_json, dict) and run.result_json.get("agent_context"):
        ctx = dict(run.result_json["agent_context"])
        if report_direction:
            from tradingagents.qlib_eval.agent.quant_context import build_quant_signal_context

            ctx = build_quant_signal_context(
                metrics=(run.result_json or {}).get("metrics"),
                model_card=(run.result_json or {}).get("model_card"),
                summary_md=None,
                report_direction=report_direction,
            )
        return ctx
    pkg = load_outbox_package(run_id)
    if not pkg or not pkg.get("valid"):
        return {"error": "quant_context_unavailable"}
    return build_quant_signal_context(
        metrics=pkg.get("metrics"),
        model_card=pkg.get("model_card"),
        summary_md=pkg.get("summary_md"),
        report_direction=report_direction,
    )


def run_rule_sweeps(
    db: Session,
    *,
    user_id: str | None = None,
    since_days: int = 90,
    limit: int = 500,
    created_by: str | None = None,
) -> dict[str, Any]:
    if not qlib_sweeps_enabled():
        return _disabled()

    run_id = str(uuid.uuid4())
    run = QlibEvalRunDB(
        id=run_id,
        run_type="sweep",
        release_version=release_version(),
        status="running",
        created_by=created_by,
    )
    db.add(run)
    db.commit()

    mdb = MarketdataSessionLocal()
    try:
        panel = build_panel_from_reports(db, mdb, user_id=user_id, since_days=since_days, limit=limit)
        sweep = sweep_all_rules(panel)
        best = dict(sweep.get("best") or {})
        run.status = "completed"
        run.panel_rows = int(len(panel))
        run.result_json = sweep
        run.updated_at = datetime.now(timezone.utc)
        db.commit()

        if best:
            persist_metrics(
                db,
                run_id=run_id,
                release_ver=release_version(),
                metric_kind="sweep",
                payload={
                    "hit_rate_pct": best.get("hit_rate_pct"),
                    "coverage_pct": best.get("coverage_pct"),
                    "ic": None,
                    "rank_ic": None,
                    "rule": best.get("rule"),
                    "threshold": best.get("threshold"),
                },
                label_horizon=str(best.get("label_col") or "").replace("label_", "") or None,
            )
        return {"enabled": True, "run_id": run_id, "sweep": sweep, "panel_rows": int(len(panel))}
    except Exception as exc:
        run.status = "failed"
        run.error = f"{type(exc).__name__}: {exc}"
        run.updated_at = datetime.now(timezone.utc)
        db.commit()
        return {"enabled": True, "run_id": run_id, "error": run.error}
    finally:
        mdb.close()


def get_gate_summary(db: Session, *, since_days: int = 90) -> dict[str, Any]:
    if not qlib_eval_enabled():
        return _disabled()

    rows = (
        db.query(QlibEvalMetricsDB)
        .order_by(QlibEvalMetricsDB.created_at.desc())
        .limit(200)
        .all()
    )
    items = [
        {
            "release_version": r.release_version,
            "metric_kind": r.metric_kind,
            "hit_rate_pct": r.hit_rate_pct,
            "ic": r.ic,
            "rank_ic": r.rank_ic,
            "coverage_pct": r.coverage_pct,
            "gate_passed": bool(r.gate_passed),
            "label_horizon": r.label_horizon,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]
    version_gates = aggregate_version_gates(items)

    outcome_summary = None
    try:
        admin_user = (
            db.query(ReportDB.user_id)
            .filter(ReportDB.status == "completed")
            .order_by(ReportDB.created_at.desc())
            .first()
        )
        if admin_user and admin_user[0]:
            outcome_summary = report_outcome_service.summarize_outcomes(
                db,
                user_id=str(admin_user[0]),
                task_kind="full_analysis",
                since_days=since_days,
                group_by="version",
            )
    except Exception:
        outcome_summary = None

    return {
        "enabled": True,
        "release_version": release_version(),
        "quant_metrics": items,
        "version_gates": version_gates,
        "report_outcomes_by_version": outcome_summary,
    }


def list_recent_runs(db: Session, *, limit: int = 20) -> dict[str, Any]:
    if not qlib_eval_enabled():
        return _disabled()
    rows = (
        db.query(QlibEvalRunDB)
        .order_by(QlibEvalRunDB.created_at.desc())
        .limit(max(1, int(limit)))
        .all()
    )
    return {
        "enabled": True,
        "items": [
            {
                "id": r.id,
                "run_type": r.run_type,
                "release_version": r.release_version,
                "status": r.status,
                "panel_rows": r.panel_rows,
                "error": r.error,
                "created_at": r.created_at.isoformat() if r.created_at else None,
            }
            for r in rows
        ],
    }
