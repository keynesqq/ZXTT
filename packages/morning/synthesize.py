"""早盘 AI 合成（分片并发 / 单次 fallback）。"""
from __future__ import annotations

import time
from datetime import date
from typing import Any

from ai.prompts import MORNING_GLOBAL_SYSTEM, MORNING_SHARD_SYSTEM, MORNING_SYSTEM
from ai.report_synthesis import (
    evaluate_raw,
    needs_quality_retry,
    run_monolithic_synthesize as _run_mono,
    run_sharded_synthesize as _run_sharded,
)
from core.config import load_config, morning_cfg
from morning.groups import build_shard_specs, critical_group_keys, stocks_for_shard
from morning.prompt_build import (
    build_morning_global_prompt,
    build_morning_shard_prompt,
    build_morning_user_prompt,
)


def _group_max_tokens() -> int:
    llm_cfg = load_config().get("llm") or {}
    return int(llm_cfg.get("group_max_tokens") or 12000)


def _llm_timeout() -> float:
    return float(morning_cfg().get("llm_timeout_sec") or 110)


def _max_tokens() -> int:
    return int(morning_cfg().get("llm_max_tokens") or 8000)


def _morning_max_tokens(stocks: list[dict], *, cap: int) -> int:
    tier0 = sum(1 for s in stocks if s.get("tier") == "tier0")
    tier1_star = sum(1 for s in stocks if s.get("tier") == "tier1_star")
    tier1 = len(stocks) - tier0 - tier1_star
    est = 500 + tier0 * 480 + tier1_star * 360 + max(tier1, 0) * 120
    return min(cap, est)


def _touch_ai_progress(ctx: dict[str, Any], detail: str, progress_pct: int) -> None:
    try:
        from morning.run_status import touch_progress

        cal_str = (ctx.get("meta") or {}).get("calendar_date") or ""
        if cal_str:
            touch_progress(date.fromisoformat(str(cal_str)), detail=detail, progress_pct=progress_pct)
    except Exception:
        pass


def run_monolithic_synthesize(ctx: dict[str, Any], user_prompt: str) -> dict[str, Any]:
    max_tok = min(_max_tokens(), _group_max_tokens())
    synth = _run_mono(
        ctx,
        user_prompt,
        system=MORNING_SYSTEM,
        group_max_tokens=max_tok,
        estimate_max_tokens=_morning_max_tokens,
    )
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    synth["eval"] = evaluate_raw(synth.get("raw") or "", stocks)
    return synth


def run_sharded_synthesize(ctx: dict[str, Any]) -> dict[str, Any]:
    cfg = morning_cfg()
    max_tok = min(_max_tokens(), _group_max_tokens())
    synth = _run_sharded(
        ctx,
        systems=(MORNING_SYSTEM, MORNING_GLOBAL_SYSTEM, MORNING_SHARD_SYSTEM),
        build_global_prompt=build_morning_global_prompt,
        build_shard_prompt=build_morning_shard_prompt,
        build_user_prompt=build_morning_user_prompt,
        cfg=cfg,
        group_max_tokens=max_tok,
        touch_progress=_touch_ai_progress,
        estimate_max_tokens=_morning_max_tokens,
        shard_specs=build_shard_specs(ctx),
        stocks_for_shard=stocks_for_shard,
        critical_shard_keys=critical_group_keys(ctx),
    )
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    synth["eval"] = evaluate_raw(synth.get("raw") or "", stocks)
    return synth


def run_morning_synthesize(ctx: dict[str, Any], user_prompt: str) -> dict[str, Any]:
    mode = str(morning_cfg().get("synthesize_mode") or "sharded").strip().lower()
    if mode == "sharded":
        return run_sharded_synthesize(ctx)
    return run_monolithic_synthesize(ctx, user_prompt)


__all__ = [
    "run_morning_synthesize",
    "run_monolithic_synthesize",
    "run_sharded_synthesize",
    "needs_quality_retry",
]
