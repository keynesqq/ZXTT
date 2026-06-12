"""第 3 步 3.7B · evening_context 骨架 + prompt。"""
from __future__ import annotations

from typing import Any

from market.cls.finance import format_cls_prompt
from market.sentiment import format_sentiment_prompt
from intraday.digest import intraday_monitor_global_line

_STANCE_ORDER = ("holding", "candidate", "watch_right", "theme_other")


def _analysis_order(by_code: dict[str, Any], tags_by_code: dict[str, Any]) -> list[str]:
    buckets: dict[str, list[str]] = {s: [] for s in _STANCE_ORDER}
    for code in sorted(by_code.keys()):
        stance = (tags_by_code.get(code) or {}).get("primary_stance", "theme_other")
        buckets.setdefault(stance, []).append(code)
    out: list[str] = []
    for stance in _STANCE_ORDER:
        out.extend(buckets.get(stance, []))
    return out


def _priority_instructions(
    order: list[str],
    *,
    group_order: list[str],
    local_blocks: dict[str, Any],
) -> str:
    group_counts = {g: 0 for g in group_order}
    names: list[str] = []
    for code in order:
        lb = local_blocks.get(code) or {}
        gs = lb.get("groups") or []
        for g in gs:
            if g in group_counts:
                group_counts[g] += 1
        names.append(f"{code} {lb.get('name','')} [{','.join(gs)}]")
    group_line = "；".join(f"{g}({group_counts.get(g, 0)})" for g in group_order)
    return (
        "31 只同级、全部自选板块同等深度：每只正文须含情景推演+对应策略+开盘参考（与「我的」持仓同模板）。"
        "同股多板块须各写一份完整分析。\n"
        f"自选板块分章：{group_line}。\n"
        f"必分析清单：{', '.join(names[:12])}…"
    )


def build_evening_context_skeleton(
    bundle: dict[str, Any],
    *,
    health: dict[str, Any],
    events_by_code: dict[str, Any],
    tags_by_code: dict[str, Any],
    market_local: dict[str, Any],
    feeds_digest_by_code: dict[str, Any],
    local_blocks: dict[str, Any],
) -> dict[str, Any]:
    meta = dict(bundle.get("meta") or {})
    meta["pipeline_step"] = "3.7"
    order = _analysis_order(bundle.get("by_code") or {}, tags_by_code)
    group_order = bundle.get("group_order") or []

    sentiment = (bundle.get("market") or {}).get("sentiment") or {}
    cls_fin = (bundle.get("market") or {}).get("cls_finance") or {}
    global_parts = [
        f"trade_date={meta.get('trade_date')}",
        intraday_monitor_global_line(meta),
        f"health_brief: {health.get('health_brief', '')}",
        "constraints:",
        *[(f"- {c}") for c in (market_local.get("constraints") or [])],
        f"l1_brief: {market_local.get('l1_brief', '')}",
        f"l2_brief: {market_local.get('l2_brief', '')}",
        "--- 详情 ---",
        format_sentiment_prompt(sentiment),
        "\n".join(format_cls_prompt(cls_fin)),
    ]

    bundle_lines = []
    for code in order:
        fd = feeds_digest_by_code.get(code) or {}
        lb = local_blocks.get(code) or {}
        bundle_lines.append(
            f"### {code} {lb.get('name','')} [{fd.get('status','')}]"
            f"\n{fd.get('summary','')}"
            f"\nreuse: {fd.get('context_note','')}"
        )

    events_lines = []
    for g in group_order:
        codes = [c for c in order if g in ((local_blocks.get(c) or {}).get("groups") or [])]
        if not codes:
            continue
        events_lines.append(f"## {g}")
        for code in codes:
            ev = events_by_code.get(code) or {}
            disp = ev.get("display") or []
            if disp:
                events_lines.append(f"{code}: " + "；".join(f"{d.get('label')}{d.get('title','')[:16]}" for d in disp))
            else:
                events_lines.append(f"{code}: 无规则命中")

    by_code_out = {}
    for code, lb in local_blocks.items():
        by_code_out[code] = {
            "local_block": lb,
            "feeds_digest_ref": f"stock_{code}",
        }

    return {
        "schema_version": 1,
        "meta": meta,
        "group_order": bundle.get("group_order") or [],
        "memberships": bundle.get("memberships") or [],
        "structure": bundle.get("structure") or {},
        "health": health,
        "market_local": market_local,
        "events_by_code": events_by_code,
        "industry_in_hot_by_code": market_local.get("industry_in_hot_by_code") or {},
        "by_code": by_code_out,
        "feeds_digest_by_code": feeds_digest_by_code,
        "prompt": {
            "priority_instructions": _priority_instructions(
                order,
                group_order=group_order,
                local_blocks=local_blocks,
            ),
            "global": "\n".join(global_parts),
            "feeds_digest_bundle": "\n".join(bundle_lines),
            "events_block": "\n".join(events_lines),
            "stocks": [
                {
                    "code": code,
                    "name": (local_blocks.get(code) or {}).get("name", code),
                    "stance_hint": (tags_by_code.get(code) or {}).get("stance_label", ""),
                    "groups": (local_blocks.get(code) or {}).get("groups") or [],
                    "prompt_line": (local_blocks.get(code) or {}).get("prompt_line", ""),
                }
                for code in order
            ],
            "cls": "",
        },
        "cls_digest": {"complete": False, "slots": {}},
        "cls_mentions_by_code": {},
    }


__all__ = ["build_evening_context_skeleton"]
