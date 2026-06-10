"""第 4 步 4A · 从 evening_context 组装 user prompt。"""
from __future__ import annotations

from typing import Any


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析请求时刻]\n{context_as_of or '—'}\n"


def build_evening_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = prompt.get("stocks") or []
    expected = int(meta.get("code_count") or 0)
    if expected and len(stocks) != expected:
        raise ValueError(f"prompt.stocks={len(stocks)} != code_count={expected}")

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        str(prompt.get("priority_instructions") or ""),
        str(prompt.get("global") or ""),
        str(prompt.get("feeds_digest_bundle") or ""),
        str(prompt.get("events_block") or ""),
        str(prompt.get("cls") or ""),
        "## [个股压缩输入]",
    ]
    for s in stocks:
        parts.append(f"### {s.get('code')} {s.get('name')} [{s.get('stance_hint', '')}]")
        parts.append(str(s.get("prompt_line") or ""))

    mentions = ctx.get("cls_mentions_by_code") or {}
    if mentions:
        parts.append("## [财联社点名自选]")
        for code, slots in sorted(mentions.items()):
            parts.append(f"{code}: {', '.join(slots)}")

    return "\n\n".join(p for p in parts if p)


__all__ = ["build_evening_user_prompt", "format_analysis_time_block"]
