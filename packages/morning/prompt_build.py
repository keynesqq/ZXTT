"""Morning user prompt。"""
from __future__ import annotations

from datetime import date
from typing import Any

from morning.checks import load_evening_expectations
from morning.evening_ref import build_evening_expectations_section, merge_evening_into_row, stock_tier
from morning.pre_format import format_pre_material, format_stock_prompt_line


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析时刻]\n{context_as_of or '—'}\n"


def _format_check_row(row: dict[str, Any]) -> str:
    bits = [
        f"{row.get('code')} {row.get('name')}",
        f"组={','.join(row.get('groups') or [])}",
        f"预期={row.get('expected_open') or '—'}",
        f"缺口={row.get('end_gap')}%",
        f"形态={row.get('shape_after_920')}",
        str(row.get("verdict") or ""),
        f"素材={row.get('pre_status')}",
    ]
    discipline = str(row.get("discipline") or "").strip()
    if discipline:
        bits.append(f"纪律={discipline}")
    check = str(row.get("check_925") or "").strip()
    if check:
        bits.append(f"9:25={check}")
    return "- " + " | ".join(bits)


def build_morning_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    pre = ctx.get("morning_pre") or {}
    checks = ctx.get("checks") or {}
    open_m = ctx.get("open_market") or {}
    prompt = ctx.get("prompt") or {}
    expectations = ctx.get("evening_expectations") or {}
    if not expectations:
        cal_str = str((meta.get("calendar_date") or checks.get("calendar_date") or "")).strip()
        if cal_str:
            try:
                expectations = load_evening_expectations(date.fromisoformat(cal_str))
            except ValueError:
                expectations = {}
    rows = checks.get("rows") or []
    exp_stocks = expectations.get("stocks") or {}
    enriched_rows = [
        merge_evening_into_row(row, exp_stocks.get(str(row.get("code") or "")) or {})
        for row in rows
    ]

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        prompt.get("priority_instructions") or "",
    ]

    evening_section = build_evening_expectations_section(
        expectations=expectations,
        rows=enriched_rows,
    )
    if evening_section:
        parts.append(evening_section)

    parts.append("## [昨晚推送摘要]\n" + (meta.get("evening_summary") or "（无）"))

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
    if pre_sum.get("no_new") and not pre_sum.get("refresh"):
        parts.append("全池 no_new：【9:15素材】可写「自昨晚 22:00 后无新公告/资讯」。")
    else:
        parts.append(
            "存在 refresh/reuse：【9:15素材】须按股说明；refresh 股引用下列新素材标题，"
            "禁止笼统写全无新素材。"
        )
    refresh_rows = [r for r in enriched_rows if r.get("pre_status") == "refresh"]
    if refresh_rows:
        parts.append("## [9:15 refresh 明细]")
        for row in refresh_rows:
            titles = row.get("pre_titles") or []
            mat = format_pre_material(status="refresh", titles=titles)
            parts.append(f"- {row.get('code')} {row.get('name')}: {mat}")
    tier0_rows = [r for r in enriched_rows if r.get("primary_stance") in ("holding", "candidate")]
    if tier0_rows:
        tier0_line = "；".join(
            f"{r.get('code')} {r.get('name')}({','.join(r.get('groups') or [])})"
            for r in tier0_rows
        )
        parts.append(f"## [推送 tier0 须逐只覆盖]\n{tier0_line}")
    parts.append("## [核对表]\n")
    for row in enriched_rows:
        parts.append(_format_check_row(row))
    parts.append("## [个股压缩输入]")
    stock_lines = prompt.get("stocks") or []
    if stock_lines:
        by_code = {str(s.get("code") or ""): s for s in stock_lines}
        for row in enriched_rows:
            code = str(row.get("code") or "")
            st = by_code.get(code) or {}
            tier = st.get("tier") or stock_tier(row)
            parts.append(
                f"### {code} {row.get('name')} tier={tier}\n"
                f"{format_stock_prompt_line(row, include_evening_recap=(tier != 'tier0'))}"
            )
    else:
        for row in enriched_rows:
            tier = stock_tier(row)
            parts.append(
                f"### {row.get('code')} {row.get('name')} tier={tier}\n"
                f"{format_stock_prompt_line(row, include_evening_recap=(tier != 'tier0'))}"
            )
    return "\n\n".join(parts)


__all__ = ["build_morning_user_prompt"]
