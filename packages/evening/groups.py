"""晚间 · 自选板块分片辅助。"""
from __future__ import annotations

from typing import Any

from core.config import evening_cfg

_CRITICAL_GROUPS = ("我的", "想买的")


def group_order(ctx: dict[str, Any]) -> list[str]:
    return [str(g).strip() for g in (ctx.get("group_order") or []) if str(g).strip()]


def base_group_name(shard_key: str) -> str:
    return str(shard_key or "").split("__part", 1)[0]


def _shard_chunk_size() -> int:
    return max(3, int(evening_cfg().get("shard_chunk_size") or 6))


def stocks_for_group(stocks: list[dict[str, Any]], group_name: str) -> list[dict[str, Any]]:
    base = base_group_name(group_name)
    tier = [s for s in stocks if base in (s.get("groups") or [])]
    if group_name == base:
        return tier
    part_s = group_name.rsplit("__part", 1)[-1]
    try:
        part_idx = int(part_s) - 1
    except ValueError:
        return tier
    chunk = _shard_chunk_size()
    start = part_idx * chunk
    return tier[start : start + chunk]


def build_shard_specs(ctx: dict[str, Any]) -> list[tuple[str, str, str, str, float]]:
    stocks = (ctx.get("prompt") or {}).get("stocks") or []
    chunk = _shard_chunk_size()
    specs: list[tuple[str, str, str, str, float]] = []
    for g in group_order(ctx):
        tier = [s for s in stocks if g in (s.get("groups") or [])]
        n = len(tier)
        if not n:
            continue
        parts = (n + chunk - 1) // chunk
        for pi in range(parts):
            key = g if parts == 1 else f"{g}__part{pi + 1}"
            sub_n = min(chunk, n - pi * chunk)
            timeout = min(300.0, 90.0 + sub_n * 28.0)
            specs.append((key, g, g, f"【{g}】", timeout))
    return specs


def critical_group_keys(ctx: dict[str, Any]) -> list[str]:
    order = group_order(ctx)
    picked = [g for g in _CRITICAL_GROUPS if g in order]
    return picked or order[:2]


__all__ = [
    "base_group_name",
    "build_shard_specs",
    "critical_group_keys",
    "group_order",
    "stocks_for_group",
]
