"""health.global 中 block 级拦截。"""
from __future__ import annotations

from typing import Any


def first_global_health_block(health: dict[str, Any]) -> dict[str, Any] | None:
    for item in health.get("global") or []:
        if item.get("level") == "block":
            return item
    return None


__all__ = ["first_global_health_block"]
