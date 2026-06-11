"""第 4 步 · AI 研判编排。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from core.config import evening_cfg
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import next_trading_day
from evening.expectations import extract_and_save_expectations
from evening.prompt_build import build_evening_user_prompt
from evening.synthesize import (
    evaluate_raw,
    needs_quality_retry,
    run_monolithic_synthesize,
    run_sharded_synthesize,
)

_CTX_DIR = DATA_DIR / "evening_context"
_AI_DIR = DATA_DIR / "scheduled_ai"
_DIGEST_DIR = DATA_DIR / "ai_digest"


def _load_context(day: date) -> dict[str, Any]:
    path = _CTX_DIR / f"{day.isoformat()}.json"
    if not path.is_file():
        raise FileNotFoundError(f"evening_context missing: {path}")
    ctx = json.loads(path.read_text(encoding="utf-8"))
    _ensure_stock_groups(ctx)
    return ctx


def _ensure_stock_groups(ctx: dict[str, Any]) -> None:
    by_code = ctx.get("by_code") or {}
    for stock in (ctx.get("prompt") or {}).get("stocks") or []:
        if stock.get("groups"):
            continue
        code = str(stock.get("code") or "")
        lb = (by_code.get(code) or {}).get("local_block") or {}
        stock["groups"] = list(lb.get("groups") or [])


def _update_synthesize_manifest(day: date, record: dict[str, Any]) -> None:
    path = _DIGEST_DIR / day.isoformat() / "manifest.json"
    if path.is_file():
        try:
            manifest = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            manifest = {"schema_version": 1, "trade_date": day.isoformat(), "stages": {}}
    else:
        manifest = {"schema_version": 1, "trade_date": day.isoformat(), "stages": {}}
    manifest.setdefault("stages", {})["synthesize"] = record
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(manifest, ensure_ascii=False, indent=2))


def _run_synthesize(ctx: dict[str, Any]) -> dict[str, Any]:
    mode = str(evening_cfg().get("synthesize_mode") or "monolithic").strip().lower()
    if mode == "sharded":
        return run_sharded_synthesize(ctx)
    user_prompt = build_evening_user_prompt(ctx)
    return run_monolithic_synthesize(ctx, user_prompt)


def run_evening_ai(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    del force
    t0 = time.monotonic()
    cal = on_date or date.today()
    ctx = _load_context(cal)
    try:
        build_evening_user_prompt(ctx)
    except ValueError as e:
        return {"outcome": "fail", "reason": "prompt_invalid", "message": str(e)}

    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    synth = _run_synthesize(ctx)
    raw = synth.get("raw") or ""
    model = synth.get("model") or ""
    err = synth.get("error") or ""
    eval_result = evaluate_raw(raw, stocks)

    if needs_quality_retry(eval_result):
        retry = _run_synthesize(ctx)
        if retry.get("raw"):
            synth = retry
            raw = retry.get("raw") or ""
            model = retry.get("model") or model
            err = retry.get("error") or err
            eval_result = evaluate_raw(raw, stocks)

    body = eval_result.get("body") or ""
    summary = eval_result.get("summary") or ""
    missing = eval_result.get("missing_codes") or []
    truncated = bool(eval_result.get("truncated_suspected"))
    critical_missing = bool(eval_result.get("critical_missing"))
    raw = eval_result.get("raw") or raw

    if not raw:
        payload = {
            "schema_version": 1,
            "slot": "evening",
            "trade_date": cal.isoformat(),
            "generated_at": now_iso(),
            "summary": "",
            "body": "",
            "raw": "",
            "model": model,
            "ai_error": err or "empty_response",
            "missing_codes": [s.get("code") for s in stocks],
            "truncated_suspected": False,
            "critical_missing": True,
        }
        out_path = _AI_DIR / f"evening_{cal.isoformat()}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
        _update_synthesize_manifest(
            cal,
            {
                "mode": synth.get("mode"),
                "ok": False,
                "duration_ms": int((time.monotonic() - t0) * 1000),
                "at": now_iso(),
            },
        )
        return {"outcome": "fail", "reason": "llm_error", "message": err, "path": str(out_path)}

    payload = {
        "schema_version": 1,
        "slot": "evening",
        "trade_date": cal.isoformat(),
        "generated_at": now_iso(),
        "context_as_of": (ctx.get("meta") or {}).get("context_as_of"),
        "summary": summary,
        "body": body,
        "raw": raw,
        "model": model,
        "ai_error": err or "",
        "missing_codes": missing,
        "truncated_suspected": truncated,
        "critical_missing": critical_missing,
        "synthesize": {"ok": not missing, "warn": bool(missing), "mode": synth.get("mode")},
    }
    out_path = _AI_DIR / f"evening_{cal.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))

    exp_path = None
    if body and not err:
        target = next_trading_day(cal)
        if target:
            exp_path = extract_and_save_expectations(body, ctx, target_date=target, missing_codes=missing)

    _update_synthesize_manifest(
        cal,
        {
            "mode": synth.get("mode"),
            "ok": not missing,
            "missing_codes": missing,
            "model": model,
            "duration_ms": int((time.monotonic() - t0) * 1000),
            "synth_duration_ms": synth.get("duration_ms"),
            "shards": synth.get("shards") or [],
            "fallback_from": synth.get("fallback_from"),
            "at": now_iso(),
        },
    )

    if evening_cfg().get("verify_enabled"):
        try:
            from evening.verify import run_evening_verify

            run_evening_verify(cal, ai_text=raw, ctx=ctx)
        except Exception:
            pass

    return {
        "outcome": "ok" if not missing else "warn",
        "path": str(out_path),
        "expectations_path": str(exp_path) if exp_path else None,
        "missing_codes": missing,
        "critical_missing": critical_missing,
        "truncated_suspected": truncated,
        "model": model,
        "synthesize_mode": synth.get("mode"),
    }


__all__ = ["run_evening_ai"]
