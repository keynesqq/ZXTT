"""午间 · 自选板块分片辅助。"""
from __future__ import annotations

from typing import Any

_CRITICAL_GROUPS = ("我的", "想买的")


def group_order(ctx: dict[str, Any]) -> list[str]:
    return [str(g).strip() for g in (ctx.get("group_order") or []) if str(g).strip()]


def stocks_for_group(stocks: list[dict[str, Any]], group_name: str) -> list[dict[str, Any]]:
    return [s for s in stocks if group_name in (s.get("groups") or [])]


def build_shard_specs(ctx: dict[str, Any]) -> list[tuple[str, str, str, str, float]]:
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    specs: list[tuple[str, str, str, str, float]] = []
    for g in group_order(ctx):
        n = len(stocks_for_group(stocks, g))
        if not n:
            continue
        timeout = min(240.0, 80.0 + n * 10.0)
        specs.append((g, g, g, f"【{g}】", timeout))
    return specs


def critical_group_keys(ctx: dict[str, Any]) -> list[str]:
    order = group_order(ctx)
    picked = [g for g in _CRITICAL_GROUPS if g in order]
    return picked or order[:2]


__all__ = [
    "build_shard_specs",
    "critical_group_keys",
    "group_order",
    "stocks_for_group",
]
