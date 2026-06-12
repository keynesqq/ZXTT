"""第 4 步 4A · 从 midday_context 组装 user prompt。"""
from __future__ import annotations

from typing import Any

from ai.prompts import MIDDAY_STOCK_BODY_FORMAT
from midday.groups import group_order, stocks_for_group

_MIDDAY_NOTE = """## [午间分析说明]
- 当前为午间休市分析，行情与指数/资金流反映上午盘。
- 请复盘各股上午表现，并给出服务于下午午盘的研判。
- 勿按「明日盘后/次日开盘」主框架输出。"""


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析请求时刻]\n{context_as_of or '—'}\n"


def _filter_events_block(events_block: str, group_name: str) -> str:
    if not events_block:
        return ""
    lines = events_block.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() == f"## {group_name}"
            if in_section:
                out.append(line)
            continue
        if in_section:
            out.append(line)
    return "\n".join(out)


def _global_brief(global_text: str) -> str:
    keep: list[str] = []
    for line in (global_text or "").splitlines():
        if line.startswith("---"):
            break
        if any(
            line.startswith(p)
            for p in (
                "session=",
                "data_scope=",
                "serve_for=",
                "index_flow_slot=",
                "trade_date=",
                "health_brief:",
                "constraints:",
                "- ",
                "l1_brief:",
                "l2_brief:",
            )
        ):
            keep.append(line)
    return "\n".join(keep)


def build_midday_global_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = prompt.get("stocks") or []
    groups = group_order(ctx)
    group_counts = ", ".join(
        f"{g}({len(stocks_for_group(stocks, g))})" for g in groups if stocks_for_group(stocks, g)
    )
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        (
            "本任务仅输出【环境】【操作】及分析时刻。"
            f"全池 {len(stocks)} 只；自选板块：{group_counts or '—'}。"
            "个股推送行由各板块分片输出。"
        ),
        str(prompt.get("global") or ""),
        str(prompt.get("cls") or ""),
    ]
    return "\n\n".join(p for p in parts if p)


def build_midday_shard_prompt(ctx: dict[str, Any], group_name: str) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = stocks_for_group(prompt.get("stocks") or [], group_name)
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        (
            f"推送标签：【{group_name}】；正文章节：## {group_name}；"
            f"本板块 {len(stocks)} 只，逐只不可漏。"
            "同股若在其它板块也会出现，本板块仍须独立写一份。"
        ),
        MIDDAY_STOCK_BODY_FORMAT,
        _global_brief(str(prompt.get("global") or "")),
        _filter_events_block(str(prompt.get("events_block") or ""), group_name),
        "## [个股压缩输入]",
    ]
    for s in stocks:
        gs = ",".join(s.get("groups") or [])
        parts.append(f"### {s.get('code')} {s.get('name')} [板块:{gs}]")
        parts.append(str(s.get("prompt_line") or ""))
    return "\n\n".join(p for p in parts if p)


def build_midday_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = prompt.get("stocks") or []
    expected = int(meta.get("code_count") or 0)
    if expected and len(stocks) != expected:
        raise ValueError(f"prompt.stocks={len(stocks)} != code_count={expected}")

    group_lines = []
    for g in group_order(ctx):
        tier = stocks_for_group(stocks, g)
        if tier:
            group_lines.append(f"## {g}（{len(tier)} 只）")

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        str(prompt.get("priority_instructions") or ""),
        MIDDAY_STOCK_BODY_FORMAT,
        "【正文分章】按自选板块，每章 `## {板块名}`，章下直接 `###` 个股：\n" + "\n".join(group_lines),
        str(prompt.get("global") or ""),
        str(prompt.get("feeds_digest_bundle") or ""),
        str(prompt.get("events_block") or ""),
        str(prompt.get("cls") or ""),
        "## [个股压缩输入]",
    ]
    for s in stocks:
        gs = ",".join(s.get("groups") or [])
        parts.append(f"### {s.get('code')} {s.get('name')} [板块:{gs}]")
        parts.append(str(s.get("prompt_line") or ""))
    return "\n\n".join(p for p in parts if p)


__all__ = [
    "build_midday_user_prompt",
    "build_midday_global_prompt",
    "build_midday_shard_prompt",
]
