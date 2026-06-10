"""公告+资讯合并（与 evening/normalize 同构）。"""
from __future__ import annotations

from typing import Any

from core.config import normalize_code


def _feed_item_key(item: dict) -> tuple[str, str, str]:
    return (
        str(item.get("category") or ""),
        str(item.get("pub_date") or ""),
        str(item.get("title") or "").strip(),
    )


def _dedupe_items(items: list[dict]) -> list[dict]:
    seen: set[tuple[str, str, str]] = set()
    out: list[dict] = []
    for it in items:
        k = _feed_item_key(it)
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def merge_feeds(ann_row: dict | None, news_row: dict | None) -> dict[str, Any]:
    merged: dict[str, Any] = {
        "公告": _dedupe_items(list((ann_row or {}).get("announcements") or [])),
        "资讯": _dedupe_items(list((news_row or {}).get("news") or [])),
        "观点": _dedupe_items(list((news_row or {}).get("opinions") or [])),
        "研报": _dedupe_items(list((news_row or {}).get("research") or [])),
        "行业资讯": _dedupe_items(list((news_row or {}).get("industry_news") or [])),
        "warnings": [],
        "warnings_struct": [],
    }
    warning = (ann_row or {}).get("warning")
    if isinstance(warning, dict) and warning.get("message"):
        merged["warnings"].append(str(warning["message"]))
        merged["warnings_struct"].append(
            {
                "code_key": str(warning.get("code") or "ANN_WARN"),
                "message": str(warning["message"]),
                "category": "公告",
                "code": str((ann_row or {}).get("code") or ""),
                "group": "",
            }
        )
    for msg in (news_row or {}).get("warnings") or []:
        if msg and msg not in merged["warnings"]:
            merged["warnings"].append(str(msg))
    for ws in (news_row or {}).get("warnings_struct") or []:
        if isinstance(ws, dict):
            merged["warnings_struct"].append(dict(ws))
    return merged


def new_titles(feeds_merged: dict[str, Any], *, limit: int = 5) -> list[str]:
    titles: list[str] = []
    for cat in ("公告", "资讯", "观点", "研报", "行业资讯"):
        for row in feeds_merged.get(cat) or []:
            t = str(row.get("title") or "").strip()
            if t:
                titles.append(f"{cat}:{t}")
    return titles[:limit]


__all__ = ["merge_feeds", "new_titles"]
