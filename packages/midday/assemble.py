"""第 3 步 3.7B · midday_context 骨架 + prompt。"""
from __future__ import annotations

from typing import Any

from market.cls.finance import format_cls_prompt
from market.sentiment import format_sentiment_prompt

_STANCE_ORDER = ("holding", "candidate", "watch_right", "theme_other")
_MIDDAY_NOTE = """## [午间分析说明]
- 当前为午间休市分析，行情与指数/资金流反映上午盘。
- 请复盘各股上午表现，并给出服务于下午午盘的研判。
- 勿按「明日盘后/次日开盘」主框架输出。"""


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
        "【报告类型】午间作战卡 | 【数据】上午盘+今晨～午间素材 | 【目标】下午午盘\n"
        "31 只均须在所属各自选板块章内各写一份正文+推送摘要（同股多板块允许内容呼应但不可省略）。"
        "个股结构：上午复盘+午后研判+午后情景子项+操作纪律，禁止散文简写。\n"
        f"自选板块分章：{group_line}。\n"
        f"必分析清单：{', '.join(names[:12])}…"
    )


def build_midday_context_skeleton(
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
    meta.setdefault("slot", "midday")
    meta.setdefault("session_label", "午间休市")
    order = _analysis_order(bundle.get("by_code") or {}, tags_by_code)

    sentiment = (bundle.get("market") or {}).get("sentiment") or {}
    cls_fin = (bundle.get("market") or {}).get("cls_finance") or {}
    global_parts = [
        "session=午间休市",
        "data_scope=上午收盘态",
        "serve_for=下午午盘",
        "index_flow_slot=midday",
        f"trade_date={meta.get('trade_date')}",
        f"health_brief: {health.get('health_brief', '')}",
        "constraints:",
        *[(f"- {c}") for c in (market_local.get("constraints") or [])],
        f"l1_brief: {market_local.get('l1_brief', '')}",
        f"l2_brief: {market_local.get('l2_brief', '')}",
        "--- 详情 ---",
        format_sentiment_prompt(sentiment),
        "\n".join(format_cls_prompt(cls_fin)),
        _MIDDAY_NOTE,
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
    group_order = bundle.get("group_order") or []
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

    cls_prompt = "\n".join(format_cls_prompt(cls_fin))

    return {
        "schema_version": 1,
        "slot": "midday",
        "session_label": "午间休市",
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
            "cls": cls_prompt,
            "midday_note": _MIDDAY_NOTE,
        },
    }


__all__ = ["build_midday_context_skeleton"]
