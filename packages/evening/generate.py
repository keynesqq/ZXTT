"""第 4 步 · AI 研判编排。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from ai.llm import chat
from ai.parse import codes_in_body, split_ai_report
from ai.prompts import EVENING_SYSTEM
from core.config import evening_cfg, load_config
from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import next_trading_day
from evening.expectations import extract_and_save_expectations
from evening.prompt_build import build_evening_user_prompt

_CTX_DIR = DATA_DIR / "evening_context"
_AI_DIR = DATA_DIR / "scheduled_ai"
_DIGEST_DIR = DATA_DIR / "ai_digest"

_STANCE_FROM_HINT = {
    "持仓": "holding",
    "候选": "candidate",
    "观察": "watch_right",
    "其它": "theme_other",
}


def _load_context(day: date) -> dict[str, Any]:
    path = _CTX_DIR / f"{day.isoformat()}.json"
    if not path.is_file():
        raise FileNotFoundError(f"evening_context missing: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def _stance_counts(stocks: list[dict]) -> dict[str, int]:
    counts = {"holding": 0, "candidate": 0, "watch_right": 0, "theme_other": 0}
    for s in stocks:
        hint = str(s.get("stance_hint") or "")
        key = _STANCE_FROM_HINT.get(hint, "theme_other")
        counts[key] = counts.get(key, 0) + 1
    return counts


def _max_tokens(stocks: list[dict]) -> int:
    c = _stance_counts(stocks)
    est = 2000 + c["holding"] * 480 + c["candidate"] * 360 + c["watch_right"] * 180 + c["theme_other"] * 80
    llm_cfg = load_config().get("llm") or {}
    cap = int(llm_cfg.get("group_max_tokens") or 12000)
    return min(cap, est)


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


def run_evening_ai(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cal = on_date or date.today()
    ctx = _load_context(cal)
    try:
        user_prompt = build_evening_user_prompt(ctx)
    except ValueError as e:
        return {"outcome": "fail", "reason": "prompt_invalid", "message": str(e)}

    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    max_tok = _max_tokens(stocks)
    raw, model, err = chat(EVENING_SYSTEM, user_prompt, max_tokens=max_tok, timeout_sec=180.0)
    if err and not raw:
        raw, model, err2 = chat(EVENING_SYSTEM, user_prompt, max_tokens=max_tok, timeout_sec=180.0)
        err = err2 or err

    truncated = bool(raw) and raw.rstrip().endswith("…")
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
        }
        out_path = _AI_DIR / f"evening_{cal.isoformat()}.json"
        out_path.parent.mkdir(parents=True, exist_ok=True)
        atomic_write_text(out_path, json.dumps(payload, ensure_ascii=False, indent=2))
        return {"outcome": "fail", "reason": "llm_error", "message": err, "path": str(out_path)}

    if not raw.lstrip().startswith("##"):
        raw = f"## 推送摘要\n（模型未按模板输出，见正文）\n\n{raw}"

    body, summary = split_ai_report(raw)
    parsed = codes_in_body(body)
    expected = [str(s.get("code")) for s in stocks if s.get("code")]
    missing = [c for c in expected if c not in parsed]
    missing_set = set(missing)
    critical_missing = any(
        str(s.get("code")) in missing_set
        and _STANCE_FROM_HINT.get(str(s.get("stance_hint") or ""), "") in ("holding", "candidate")
        for s in stocks
    )

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
        "synthesize": {"ok": not missing, "warn": bool(missing)},
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
            "ok": not missing,
            "missing_codes": missing,
            "model": model,
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
    }


__all__ = ["run_evening_ai"]
