"""资讯素材结构化 warning 码（feeds v1 · SPEC.md §8）。"""
from __future__ import annotations

from typing import Any

ANN_EMPTY = "ANN_EMPTY"
ANN_LATEST_FALLBACK = "ANN_LATEST_FALLBACK"
RES_EMPTY = "RES_EMPTY"
NEWS_EMPTY = "NEWS_EMPTY"
NEWS_FILTERED = "NEWS_FILTERED"
NEWS_STALE = "NEWS_STALE"
IND_EMPTY = "IND_EMPTY"
FEED_COLLECT_FAILED = "FEED_COLLECT_FAILED"


def feed_warning(
    code_key: str,
    message: str,
    *,
    category: str = "",
    code: str = "",
    group: str = "",
) -> dict[str, Any]:
    return {
        "code_key": code_key,
        "message": message,
        "category": category,
        "code": code,
        "group": group,
    }


def append_feed_warning(
    warnings: list[str],
    warnings_struct: list[dict[str, Any]],
    item: dict[str, Any],
) -> None:
    warnings.append(str(item.get("message") or ""))
    warnings_struct.append(item)


def has_code_key(struct: list[dict[str, Any]], code_key: str) -> bool:
    return any(str(x.get("code_key") or "") == code_key for x in struct)
