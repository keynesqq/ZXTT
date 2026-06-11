"""第 4 步 4A · 从 midday_context 组装 user prompt。"""
from __future__ import annotations

from typing import Any

from ai.prompts import MIDDAY_STOCK_BODY_FORMAT

_HINT_TO_STANCE = {
    "持仓": "holding",
    "候选": "candidate",
    "观察": "watch_right",
    "其它": "theme_other",
}

_STANCE_CHAPTER = {
    "holding": "我的·持仓深度",
    "candidate": "想买的·候选跟踪",
    "watch_right": "观察·跌幅达预期",
    "theme_other": "其它·风向跟踪",
}

_STANCE_PUSH = {
    "holding": "【我的】",
    "candidate": "【想买的】",
    "watch_right": "【观察】",
    "theme_other": "【其它】",
}

_MIDDAY_NOTE = """## [午间分析说明]
- 当前为午间休市分析，行情与指数/资金流反映上午盘。
- 请复盘各股上午表现，并给出服务于下午午盘的研判。
- 勿按「明日盘后/次日开盘」主框架输出。"""


def format_analysis_time_block(context_as_of: str) -> str:
    return f"## [分析请求时刻]\n{context_as_of or '—'}\n"


def _stock_stance(stock: dict[str, Any]) -> str:
    return _HINT_TO_STANCE.get(str(stock.get("stance_hint") or ""), "theme_other")


def _filter_events_block(events_block: str, stance: str) -> str:
    if not events_block:
        return ""
    lines = events_block.splitlines()
    out: list[str] = []
    in_section = False
    for line in lines:
        if line.startswith("## "):
            in_section = line.strip() == f"## {stance}"
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
    counts = {s: 0 for s in _STANCE_CHAPTER}
    for st in stocks:
        counts[_stock_stance(st)] = counts.get(_stock_stance(st), 0) + 1
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        (
            "本任务仅输出【环境】【仓位】【操作】及分析时刻。"
            f"全池 {len(stocks)} 只：我的({counts.get('holding', 0)}) "
            f"想买的({counts.get('candidate', 0)}) "
            f"观察({counts.get('watch_right', 0)}) "
            f"其它({counts.get('theme_other', 0)})。"
        ),
        str(prompt.get("global") or ""),
        str(prompt.get("cls") or ""),
    ]
    return "\n\n".join(p for p in parts if p)


def build_midday_shard_prompt(ctx: dict[str, Any], stance: str) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = [s for s in (prompt.get("stocks") or []) if _stock_stance(s) == stance]
    chapter = _STANCE_CHAPTER.get(stance, "")
    push = _STANCE_PUSH.get(stance, "")
    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        f"推送标签：{push}；正文章节：## {chapter}；本档 {len(stocks)} 只，逐只不可漏。",
        MIDDAY_STOCK_BODY_FORMAT,
        _global_brief(str(prompt.get("global") or "")),
        _filter_events_block(str(prompt.get("events_block") or ""), stance),
        "## [个股压缩输入]",
    ]
    for s in stocks:
        parts.append(f"### {s.get('code')} {s.get('name')} [{s.get('stance_hint', '')}]")
        parts.append(str(s.get("prompt_line") or ""))
    return "\n\n".join(p for p in parts if p)


def build_midday_user_prompt(ctx: dict[str, Any]) -> str:
    meta = ctx.get("meta") or {}
    prompt = ctx.get("prompt") or {}
    stocks = prompt.get("stocks") or []
    expected = int(meta.get("code_count") or 0)
    if expected and len(stocks) != expected:
        raise ValueError(f"prompt.stocks={len(stocks)} != code_count={expected}")

    parts = [
        format_analysis_time_block(str(meta.get("context_as_of") or "")),
        _MIDDAY_NOTE,
        str(prompt.get("priority_instructions") or ""),
        MIDDAY_STOCK_BODY_FORMAT,
        str(prompt.get("global") or ""),
        str(prompt.get("feeds_digest_bundle") or ""),
        str(prompt.get("events_block") or ""),
        str(prompt.get("cls") or ""),
        "## [个股压缩输入]",
    ]
    for s in stocks:
        parts.append(f"### {s.get('code')} {s.get('name')} [{s.get('stance_hint', '')}]")
        parts.append(str(s.get("prompt_line") or ""))
    return "\n\n".join(p for p in parts if p)


__all__ = [
    "build_midday_user_prompt",
    "build_midday_global_prompt",
    "build_midday_shard_prompt",
]
