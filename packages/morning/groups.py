"""早盘 · 自选板块分片（对齐 midday）。"""
from __future__ import annotations

from typing import Any

from core.config import morning_cfg

_CRITICAL_GROUPS = ("我的", "想买的")


def group_order(ctx: dict[str, Any]) -> list[str]:
    order = [str(g).strip() for g in (ctx.get("group_order") or []) if str(g).strip()]
    if order:
        return order
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    seen: list[str] = []
    for s in stocks:
        for g in s.get("groups") or []:
            g = str(g).strip()
            if g and g not in seen:
                seen.append(g)
    if seen:
        return seen
    return ["我的", "想买的", "其它"]


def stocks_for_group(stocks: list[dict[str, Any]], group_name: str) -> list[dict[str, Any]]:
    by_group = [s for s in stocks if group_name in (s.get("groups") or [])]
    if by_group:
        return by_group
    if group_name == "我的":
        return [s for s in stocks if s.get("stance_hint") == "holding"]
    if group_name == "想买的":
        return [s for s in stocks if s.get("stance_hint") == "candidate"]
    if group_name == "其它":
        return [s for s in stocks if s.get("stance_hint") == "theme_other"]
    return []


def _chunk_size() -> int:
    return max(4, int(morning_cfg().get("shard_max_stocks") or 12))


def _shard_timeout(stock_count: int) -> float:
    return min(95.0, 40.0 + stock_count * 4.5)


def stocks_for_shard(stocks: list[dict[str, Any]], shard_key: str) -> list[dict[str, Any]]:
    if "#" not in shard_key:
        return stocks_for_group(stocks, shard_key)
    group, idx_s = shard_key.split("#", 1)
    try:
        idx = int(idx_s)
    except ValueError:
        return []
    if idx < 1:
        return []
    tier = stocks_for_group(stocks, group)
    size = _chunk_size()
    start = (idx - 1) * size
    return tier[start : start + size]


def build_shard_specs(ctx: dict[str, Any]) -> list[tuple[str, str, str, str, float]]:
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    size = _chunk_size()
    specs: list[tuple[str, str, str, str, float]] = []
    for g in group_order(ctx):
        tier = stocks_for_group(stocks, g)
        n = len(tier)
        if not n:
            continue
        if n <= size:
            specs.append((g, g, g, f"【{g}】", _shard_timeout(n)))
            continue
        for i in range(0, n, size):
            idx = i // size + 1
            chunk_n = min(size, n - i)
            key = f"{g}#{idx}"
            chapter = g if idx == 1 else f"{g}·{idx}"
            push = f"【{g}】" if idx == 1 else f"【{g}·续{idx}】"
            specs.append((key, g, chapter, push, _shard_timeout(chunk_n)))
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
    "stocks_for_shard",
]
