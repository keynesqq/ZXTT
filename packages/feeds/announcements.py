"""公告拉取（巨潮主源 + AkShare 兜底），供 feeds 采集与 announcement 查询共用。"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Any

from core.config import feeds_cfg
from feeds.cninfo import fetch_announcements as fetch_cninfo_ann
from feeds.cninfo import fetch_latest_announcements as fetch_cninfo_latest
from feeds.eastmoney import (
    fetch_announcements_akshare,
    fetch_latest_announcements_akshare,
)
from feeds.feed_warnings import ANN_EMPTY, ANN_LATEST_FALLBACK


@dataclass(frozen=True)
class AnnouncementFetchResult:
    rows: list[dict]
    warning_code: str | None = None
    warning_message: str | None = None


def akshare_fallback_enabled() -> bool:
    ann_cfg = feeds_cfg().get("announcement") or {}
    return str(ann_cfg.get("fallback", "akshare")).lower() == "akshare"


def fetch_announcement_rows(
    code: str,
    *,
    start: date,
    end: date,
    lookback_days: int,
    fallback_latest_count: int = 0,
    max_count: int = 0,
    use_akshare_fallback: bool | None = None,
) -> AnnouncementFetchResult:
    """拉取公告。fallback_latest_count=0 时不拉历史最新条，仅返回时间范围内结果。"""
    latest_n = fallback_latest_count
    use_akshare = akshare_fallback_enabled() if use_akshare_fallback is None else use_akshare_fallback
    use_latest_fallback = latest_n > 0

    rows = fetch_cninfo_ann(code, start, end)
    if not rows and use_akshare:
        rows = fetch_announcements_akshare(code, start, end)

    used_latest = False
    if not rows and use_latest_fallback:
        rows = fetch_cninfo_latest(code, latest_n)
        if not rows and use_akshare:
            rows = fetch_latest_announcements_akshare(code, latest_n)
        used_latest = bool(rows)

    if max_count > 0 and len(rows) > max_count:
        rows = rows[:max_count]

    warning_code: str | None = None
    warning_message: str | None = None
    if not rows:
        warning_code = ANN_EMPTY
        if use_latest_fallback:
            warning_message = f"公告：近{lookback_days}日无数据，且无法获取最新{latest_n}条"
        else:
            warning_message = f"公告：近{lookback_days}日内无公告"
    elif used_latest:
        warning_code = ANN_LATEST_FALLBACK
        warning_message = f"公告：近{lookback_days}日内无公告，已展示最新{len(rows)}条"

    return AnnouncementFetchResult(
        rows=rows,
        warning_code=warning_code,
        warning_message=warning_message,
    )


def warning_dict(result: AnnouncementFetchResult) -> dict[str, Any] | None:
    if not result.warning_code:
        return None
    return {"code": result.warning_code, "message": result.warning_message or ""}
