"""Morning user prompt。"""
from __future__ import annotations

from typing import Any


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析时刻]\n{context_as_of or '—'}\n"


def build_morning_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    pre = ctx.get("morning_pre") or {}
    checks = ctx.get("checks") or {}
    open_m = ctx.get("open_market") or {}
    prompt = ctx.get("prompt") or {}
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        prompt.get("priority_instructions") or "",
        "## [昨晚推送摘要]\n" + (meta.get("evening_summary") or "（无）"),
    ]
    if open_m:
        parts.append("## [9:25 大盘环境]\n" + str(open_m.get("pool_hint") or open_m.get("position_hint") or ""))
        gaps = open_m.get("index_open_gaps") or []
        if gaps:
            gap_lines = [
                f"{g.get('name') or g.get('symbol')}: 缺口 {g.get('open_gap_pct')}%"
                for g in gaps[:4]
                if isinstance(g, dict)
            ]
            if gap_lines:
                parts.append("\n".join(gap_lines))
    pre_sum = pre.get("summary") or {}
    parts.append(
        "## [9:15 素材汇总]\n"
        f"refresh={pre_sum.get('refresh', 0)} reuse={pre_sum.get('reuse', 0)} "
        f"no_new={pre_sum.get('no_new', 0)} failed={pre_sum.get('failed', 0)}"
    )
    parts.append("## [核对表]\n")
    for row in checks.get("rows") or []:
        parts.append(
            f"- {row.get('code')} {row.get('name')} | 组={','.join(row.get('groups') or [])} | "
            f"预期={row.get('expected_open')} | 缺口={row.get('end_gap')}% | "
            f"形态={row.get('shape_after_920')} | {row.get('verdict')} | 素材={row.get('pre_status')}"
        )
    parts.append("## [个股压缩输入]")
    for s in prompt.get("stocks") or []:
        parts.append(
            f"### {s.get('code')} {s.get('name')} tier={s.get('tier')}\n{s.get('prompt_line')}"
        )
    return "\n\n".join(parts)


__all__ = ["build_morning_user_prompt"]
