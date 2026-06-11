"""第 4 步 4B · 单体/分片 AI 合成。"""
from __future__ import annotations

import re
from datetime import date
from typing import Any

from ai.prompts import EVENING_GLOBAL_SYSTEM, EVENING_SHARD_SYSTEM, EVENING_SYSTEM
from ai.report_synthesis import (
    merge_sharded,
    needs_quality_retry as _base_needs_quality_retry,
    run_monolithic_synthesize as _run_mono,
    run_sharded_synthesize as _run_sharded,
)
from core.config import evening_cfg, load_config
from evening.groups import build_shard_specs, critical_group_keys, stocks_for_group
from evening.prompt_build import (
    build_evening_global_prompt,
    build_evening_shard_prompt,
    build_evening_user_prompt,
)

_STOCK_SECTION = re.compile(r"(?ms)^###\s+(\d{6})\s.+?(?=^###\s+|^##\s+|\Z)")
_DEPTH_KEYS = ("情景推演", "对应策略", "开盘参考")


def _group_max_tokens() -> int:
    llm_cfg = load_config().get("llm") or {}
    return int(llm_cfg.get("group_max_tokens") or 12000)


def _evening_max_tokens(stocks: list[dict], *, cap: int) -> int:
    return min(cap, max(4000, 1000 + len(stocks) * 1100))


def _shallow_codes(body: str, codes: list[str]) -> list[str]:
    shallow: list[str] = []
    sections = {m.group(1): m.group(0) for m in _STOCK_SECTION.finditer(body or "")}
    for code in codes:
        chunk = sections.get(code)
        if not chunk or not all(key in chunk for key in _DEPTH_KEYS):
            shallow.append(code)
    return shallow


def evaluate_evening_raw(raw: str, stocks: list[dict]) -> dict[str, Any]:
    from ai.parse import codes_in_body, split_ai_report

    if not raw:
        return {
            "body": "",
            "summary": "",
            "missing_codes": [s.get("code") for s in stocks],
            "truncated_suspected": False,
            "critical_missing": True,
            "shallow_codes": [str(s.get("code")) for s in stocks if s.get("code")],
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
    shallow = _shallow_codes(body, [c for c in expected if c in parsed])
    return {
        "body": body,
        "summary": summary,
        "missing_codes": missing,
        "truncated_suspected": truncated,
        "critical_missing": critical_missing,
        "shallow_codes": shallow,
        "raw": raw,
    }


def needs_quality_retry(eval_result: dict[str, Any]) -> bool:
    if _base_needs_quality_retry(eval_result):
        return True
    return bool(eval_result.get("shallow_codes"))


def _touch_ai_progress(ctx: dict[str, Any], detail: str, progress_pct: int) -> None:
    try:
        from evening.run_status import touch_progress

        td = (ctx.get("meta") or {}).get("trade_date") or ""
        if td:
            touch_progress(date.fromisoformat(str(td)), detail=detail, progress_pct=progress_pct)
    except Exception:
        pass


def run_monolithic_synthesize(ctx: dict[str, Any], user_prompt: str) -> dict[str, Any]:
    return _run_mono(
        ctx,
        user_prompt,
        system=EVENING_SYSTEM,
        group_max_tokens=_group_max_tokens(),
        estimate_max_tokens=_evening_max_tokens,
    )


def run_sharded_synthesize(ctx: dict[str, Any]) -> dict[str, Any]:
    return _run_sharded(
        ctx,
        systems=(EVENING_SYSTEM, EVENING_GLOBAL_SYSTEM, EVENING_SHARD_SYSTEM),
        build_global_prompt=build_evening_global_prompt,
        build_shard_prompt=build_evening_shard_prompt,
        build_user_prompt=build_evening_user_prompt,
        cfg=evening_cfg(),
        group_max_tokens=_group_max_tokens(),
        touch_progress=_touch_ai_progress,
        estimate_max_tokens=_evening_max_tokens,
        shard_specs=build_shard_specs(ctx),
        stocks_for_shard=stocks_for_group,
        critical_shard_keys=critical_group_keys(ctx),
    )


evaluate_raw = evaluate_evening_raw

__all__ = [
    "run_monolithic_synthesize",
    "run_sharded_synthesize",
    "merge_sharded",
    "evaluate_evening_raw",
    "evaluate_raw",
    "needs_quality_retry",
]
