"""第 4 步 4B · 午间 AI 合成（参数化）。"""
from __future__ import annotations

from datetime import date
from typing import Any

from ai.prompts import MIDDAY_GLOBAL_SYSTEM, MIDDAY_SHARD_SYSTEM, MIDDAY_SYSTEM
from ai.report_synthesis import (
    evaluate_raw,
    merge_sharded,
    needs_quality_retry,
    run_monolithic_synthesize as _run_mono,
    run_sharded_synthesize as _run_sharded,
)
from core.config import load_config, midday_cfg
from midday.prompt_build import (
    build_midday_global_prompt,
    build_midday_shard_prompt,
    build_midday_user_prompt,
)


def _group_max_tokens() -> int:
    llm_cfg = load_config().get("llm") or {}
    return int(llm_cfg.get("group_max_tokens") or 12000)


def _touch_ai_progress(ctx: dict[str, Any], detail: str, progress_pct: int) -> None:
    try:
        from midday.run_status import touch_progress

        td = (ctx.get("meta") or {}).get("trade_date") or ""
        if td:
            touch_progress(date.fromisoformat(str(td)), detail=detail, progress_pct=progress_pct)
    except Exception:
        pass


def run_monolithic_synthesize(ctx: dict[str, Any], user_prompt: str) -> dict[str, Any]:
    return _run_mono(
        ctx,
        user_prompt,
        system=MIDDAY_SYSTEM,
        group_max_tokens=_group_max_tokens(),
    )


def run_sharded_synthesize(ctx: dict[str, Any]) -> dict[str, Any]:
    return _run_sharded(
        ctx,
        systems=(MIDDAY_SYSTEM, MIDDAY_GLOBAL_SYSTEM, MIDDAY_SHARD_SYSTEM),
        build_global_prompt=build_midday_global_prompt,
        build_shard_prompt=build_midday_shard_prompt,
        build_user_prompt=build_midday_user_prompt,
        cfg=midday_cfg(),
        group_max_tokens=_group_max_tokens(),
        touch_progress=_touch_ai_progress,
    )


__all__ = [
    "run_monolithic_synthesize",
    "run_sharded_synthesize",
    "merge_sharded",
    "evaluate_raw",
    "needs_quality_retry",
]
