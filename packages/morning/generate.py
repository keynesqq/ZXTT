"""早盘 AI 研判。"""
from __future__ import annotations

import json
import time
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from ai.parse import resolve_ai_report_fields
from morning.prompt_build import build_morning_user_prompt
from morning.synthesize import (
    needs_quality_retry,
    run_morning_synthesize,
)

_CTX_DIR = DATA_DIR / "morning_context"
_AI_DIR = DATA_DIR / "scheduled_ai"


def _load_context(day: date) -> dict[str, Any]:
    path = _CTX_DIR / f"{day.isoformat()}.json"
    if not path.is_file():
        raise FileNotFoundError(f"morning_context missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def run_morning_ai(*, on_date: date | None = None) -> dict[str, Any]:
    t0 = time.monotonic()
    cal = on_date or date.today()
    ctx = _load_context(cal)
    user_prompt = build_morning_user_prompt(ctx)
    synth = run_morning_synthesize(ctx, user_prompt)
    eval_result = synth.get("eval") or {}
    if needs_quality_retry(eval_result):
        retry = run_morning_synthesize(ctx, user_prompt)
        if retry.get("raw"):
            retry_eval = retry.get("eval") or {}
            if len(retry_eval.get("missing_codes") or []) <= len(eval_result.get("missing_codes") or []):
                synth = retry
                eval_result = retry_eval

    raw = synth.get("raw") or ""
    model = synth.get("model") or ""
    err = synth.get("error") or ""
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    fields = resolve_ai_report_fields(
        raw=raw,
        body=eval_result.get("body") or "",
        summary=eval_result.get("summary") or "",
        stocks=stocks,
    )
    body = str(fields["body"])
    summary = str(fields["summary"])
    missing = list(fields["missing_codes"])

    if not raw:
        payload = {
            "schema_version": 1,
            "slot": "morning",
            "session_label": "集合竞价结束",
            "trade_date": cal.isoformat(),
            "generated_at": now_iso(),
            "summary": "",
            "body": "",
            "raw": "",
            "model": model,
            "ai_error": err or "empty_response",
            "missing_codes": [s.get("code") for s in (ctx.get("prompt") or {}).get("stocks") or []],
            "ai_duration_ms": synth.get("duration_ms"),
        }
        out_path = _AI_DIR / f"morning_{cal.isoformat()}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return {
            "outcome": "fail",
            "reason": "llm_error",
            "message": err,
            "path": str(out_path),
            "ai_duration_ms": synth.get("duration_ms"),
        }

    payload = {
        "schema_version": 1,
        "slot": "morning",
        "session_label": "集合竞价结束",
        "trade_date": cal.isoformat(),
        "generated_at": now_iso(),
        "context_as_of": (ctx.get("meta") or {}).get("context_as_of"),
        "summary": summary,
        "body": body,
        "raw": raw,
        "model": model,
        "ai_error": err or "",
        "missing_codes": missing,
        "truncated_suspected": bool(eval_result.get("truncated_suspected")),
        "critical_missing": bool(eval_result.get("critical_missing")),
        "ai_duration_ms": synth.get("duration_ms"),
        "synthesize": {
            "ok": not missing,
            "mode": synth.get("mode"),
            "shards": synth.get("shards") or [],
        },
    }
    out_path = _AI_DIR / f"morning_{cal.isoformat()}.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
    return {
        "outcome": "ok" if not err and not eval_result.get("critical_missing") else "warn",
        "path": str(out_path),
        "missing_codes": missing,
        "model": model,
        "ai_duration_ms": synth.get("duration_ms"),
        "total_duration_ms": int((time.monotonic() - t0) * 1000),
        "synthesize_mode": synth.get("mode"),
    }


__all__ = ["run_morning_ai"]
