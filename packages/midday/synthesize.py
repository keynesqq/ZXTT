"""第 4 步 4B · 午间 AI 合成（参数化）。"""
from __future__ import annotations

from datetime import date
from typing import Any

from ai.prompts import MIDDAY_GLOBAL_SYSTEM, MIDDAY_SHARD_SYSTEM, MIDDAY_SYSTEM
from ai.report_synthesis import (
    merge_sharded,
    needs_quality_retry,
    run_monolithic_synthesize as _run_mono,
    run_sharded_synthesize as _run_sharded,
)
from core.config import load_config, midday_cfg
from midday.groups import build_shard_specs, critical_group_keys, stocks_for_group
from midday.prompt_build import (
    build_midday_global_prompt,
    build_midday_shard_prompt,
    build_midday_user_prompt,
)


def _group_max_tokens() -> int:
    llm_cfg = load_config().get("llm") or {}
    return int(llm_cfg.get("group_max_tokens") or 12000)


def _midday_max_tokens(stocks: list[dict], *, cap: int) -> int:
    return min(cap, 600 + len(stocks) * 500)


def evaluate_midday_raw(raw: str, stocks: list[dict]) -> dict[str, Any]:
    from ai.parse import codes_in_body, split_ai_report
    if not raw:
        return {
            "body": "",
            "summary": "",
            "missing_codes": [s.get("code") for s in stocks],
            "truncated_suspected": False,
            "critical_missing": True,
        }
    if not raw.lstrip().startswith("##"):
        raw = f"## 推送摘要\n（模型未按模板输出，见正文）\n\n{raw}"
    truncated = bool(raw) and raw.rstrip().endswith("…")
    body, summary = split_ai_report(raw)
    parsed = set(codes_in_body(body))
    expected = [str(s.get("code")) for s in stocks if s.get("code")]
    missing = [c for c in expected if c not in parsed]
    missing_set = set(missing)
    critical_missing = any(
        str(s.get("code")) in missing_set
        and ("我的" in (s.get("groups") or []) or "想买的" in (s.get("groups") or []))
        for s in stocks
    )
    return {
        "body": body,
        "summary": summary,
        "missing_codes": missing,
        "truncated_suspected": truncated,
        "critical_missing": critical_missing,
        "raw": raw,
    }


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
        estimate_max_tokens=_midday_max_tokens,
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
        estimate_max_tokens=_midday_max_tokens,
        shard_specs=build_shard_specs(ctx),
        stocks_for_shard=stocks_for_group,
        critical_shard_keys=critical_group_keys(ctx),
    )


__all__ = [
    "run_monolithic_synthesize",
    "run_sharded_synthesize",
    "merge_sharded",
    "evaluate_midday_raw",
    "needs_quality_retry",
]
