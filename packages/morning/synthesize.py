"""早盘单次 AI 合成（110s timeout）。"""
from __future__ import annotations

import time
from typing import Any

from ai.llm import chat
from ai.prompts import MORNING_SYSTEM
from ai.report_synthesis import evaluate_raw
from core.config import load_config, morning_cfg


def _group_max_tokens() -> int:
    llm_cfg = load_config().get("llm") or {}
    return int(llm_cfg.get("group_max_tokens") or 12000)


def _llm_timeout() -> float:
    return float(morning_cfg().get("llm_timeout_sec") or 110)


def _max_tokens() -> int:
    return int(morning_cfg().get("llm_max_tokens") or 8000)


def run_morning_synthesize(ctx: dict[str, Any], user_prompt: str) -> dict[str, Any]:
    t0 = time.monotonic()
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    max_tok = min(_max_tokens(), _group_max_tokens())
    raw, model, err = chat(
        MORNING_SYSTEM,
        user_prompt,
        max_tokens=max_tok,
        timeout_sec=_llm_timeout(),
    )
    return {
        "mode": "monolithic",
        "raw": raw,
        "model": model,
        "error": err,
        "duration_ms": int((time.monotonic() - t0) * 1000),
        "shards": [],
        "eval": evaluate_raw(raw, stocks),
    }


__all__ = ["run_morning_synthesize"]
