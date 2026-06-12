"""Morning user prompt。"""
from __future__ import annotations

from datetime import date
from typing import Any

from morning.checks import format_checks_summary_prompt, load_evening_expectations
from morning.evening_ref import (
    build_evening_expectations_section,
    format_evening_global,
    merge_evening_into_row,
    stock_tier,
)
from morning.groups import stocks_for_group, stocks_for_shard
from morning.pre_format import format_pre_material, format_stock_prompt_line


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析时刻]\n{context_as_of or '—'}\n"


def _format_open_market_block(open_m: dict[str, Any], checks: dict[str, Any]) -> str:
    lines: list[str] = []
    hint = str(open_m.get("pool_hint") or open_m.get("position_hint") or "").strip()
    if hint:
        lines.append(hint)
    gaps = open_m.get("index_open_gaps") or []
    if gaps:
        gap_lines = [
            f"{g.get('name') or g.get('symbol')}: 缺口 {g.get('open_gap_pct')}%"
            for g in gaps[:4]
            if isinstance(g, dict)
        ]
        lines.extend(gap_lines)
    prev_n = open_m.get("prev_limit_count")
    if prev_n is not None:
        avg = open_m.get("prev_limit_avg_pct")
        up = open_m.get("prev_limit_up")
        down = open_m.get("prev_limit_down")
        prem = open_m.get("prev_limit_premium_3pct")
        lines.append(
            f"昨涨停今开: 样本{prev_n}只 · 均涨{avg}% · 上涨{up}/下跌{down} · 溢价≥3% {prem}只"
        )
    chk_line = format_checks_summary_prompt(checks)
    if chk_line:
        lines.append(f"核对统计: {chk_line}")
    return "\n".join(lines)


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


def _enriched_rows(ctx: dict[str, Any]) -> list[dict[str, Any]]:
    meta = ctx.get("meta") or {}
    checks = ctx.get("checks") or {}
    expectations = ctx.get("evening_expectations") or {}
    if not expectations:
        cal_str = str((meta.get("calendar_date") or checks.get("calendar_date") or "")).strip()
        if cal_str:
            try:
                expectations = load_evening_expectations(date.fromisoformat(cal_str))
            except ValueError:
                expectations = {}
    exp_stocks = expectations.get("stocks") or {}
    return [
        merge_evening_into_row(row, exp_stocks.get(str(row.get("code") or "")) or {})
        for row in (checks.get("rows") or [])
    ]


def _open_market_and_pre_parts(ctx: dict[str, Any], enriched_rows: list[dict[str, Any]]) -> list[str]:
    pre = ctx.get("morning_pre") or {}
    checks = ctx.get("checks") or {}
    open_m = ctx.get("open_market") or {}
    parts: list[str] = []
    if open_m:
        block = _format_open_market_block(open_m, checks)
        if block:
            parts.append("## [9:25 大盘环境]\n" + block)
    pre_sum = pre.get("summary") or {}
    parts.append(
        "## [9:15 素材汇总]\n"
        f"refresh={pre_sum.get('refresh', 0)} reuse={pre_sum.get('reuse', 0)} "
        f"no_new={pre_sum.get('no_new', 0)} failed={pre_sum.get('failed', 0)}"
    )
    refresh_rows = [r for r in enriched_rows if r.get("pre_status") == "refresh"]
    if refresh_rows:
        parts.append("## [9:15 refresh 明细]")
        for row in refresh_rows:
            titles = row.get("pre_titles") or []
            mat = format_pre_material(status="refresh", titles=titles)
            parts.append(f"- {row.get('code')} {row.get('name')}: {mat}")
    return parts


def build_morning_global_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    enriched_rows = _enriched_rows(ctx)
    expectations = ctx.get("evening_expectations") or {}
    global_line = format_evening_global(expectations)
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        (
            "本任务仅输出【环境】【超预期】【操作】及分析时刻；"
            f"全池 {len(enriched_rows)} 只；个股推送与正文由各板块分片并行输出。"
        ),
        prompt.get("priority_instructions") or "",
    ]
    if global_line:
        parts.append("### 大盘环境\n" + global_line)
    parts.append("## [昨晚推送摘要]\n" + (meta.get("evening_summary") or "（无）"))
    parts.extend(_open_market_and_pre_parts(ctx, enriched_rows))
    tier0_rows = [r for r in enriched_rows if r.get("primary_stance") in ("holding", "candidate")]
    if tier0_rows:
        tier0_line = "；".join(
            f"{r.get('code')} {r.get('name')}({','.join(r.get('groups') or [])})"
            for r in tier0_rows
        )
        parts.append(f"## [推送 tier0 须逐只覆盖（由分片输出）]\n{tier0_line}")
    return "\n\n".join(p for p in parts if p)


def build_morning_shard_prompt(ctx: dict[str, Any], shard_key: str) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stock_lines = prompt.get("stocks") or []
    by_code = {str(s.get("code") or ""): s for s in stock_lines}
    enriched_rows = _enriched_rows(ctx)
    shard_stocks = stocks_for_shard(stock_lines, shard_key)
    shard_codes = {str(s.get("code") or "") for s in shard_stocks}
    shard_rows = [r for r in enriched_rows if str(r.get("code") or "") in shard_codes]

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        prompt.get("priority_instructions") or "",
        f"本批板块键={shard_key}；{len(shard_stocks)} 只，逐只不可漏。",
    ]
    parts.extend(_open_market_and_pre_parts(ctx, shard_rows))
    parts.append("## [核对表·本批]\n")
    for row in shard_rows:
        parts.append(_format_check_row(row))
    parts.append("## [个股压缩输入]")
    for row in shard_rows:
        code = str(row.get("code") or "")
        st = by_code.get(code) or {}
        tier = st.get("tier") or stock_tier(row)
        parts.append(
            f"### {code} {row.get('name')} tier={tier}\n"
            f"{format_stock_prompt_line(row, include_evening_recap=(tier != 'tier0'))}"
        )
    return "\n\n".join(p for p in parts if p)


def build_morning_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    pre = ctx.get("morning_pre") or {}
    checks = ctx.get("checks") or {}
    open_m = ctx.get("open_market") or {}
    prompt = ctx.get("prompt") or {}
    enriched_rows = _enriched_rows(ctx)

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        prompt.get("priority_instructions") or "",
    ]

    expectations = ctx.get("evening_expectations") or {}
    if not expectations:
        cal_str = str((meta.get("calendar_date") or checks.get("calendar_date") or "")).strip()
        if cal_str:
            try:
                expectations = load_evening_expectations(date.fromisoformat(cal_str))
            except ValueError:
                expectations = {}

    evening_section = build_evening_expectations_section(
        expectations=expectations,
        rows=enriched_rows,
    )
    if evening_section:
        parts.append(evening_section)

    parts.append("## [昨晚推送摘要]\n" + (meta.get("evening_summary") or "（无）"))
    parts.extend(_open_market_and_pre_parts(ctx, enriched_rows))
    if pre.get("summary", {}).get("no_new") and not pre.get("summary", {}).get("refresh"):
        parts.append("全池 no_new：正文无 refresh 股时可写「自昨晚 22:00 后无新公告/资讯」。")
    else:
        parts.append(
            "存在 refresh/reuse：正文须按股说明素材；refresh 股引用下列新素材标题，"
            "禁止笼统写全无新素材。"
        )
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


__all__ = [
    "build_morning_user_prompt",
    "build_morning_global_prompt",
    "build_morning_shard_prompt",
    "format_analysis_time_block",
]
