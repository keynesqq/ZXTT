"""全链路数据时效：context_as_of 聚合与 ISO 时间工具。"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from zoneinfo import ZoneInfo

_CN_TZ = ZoneInfo("Asia/Shanghai")
_FMT = "%Y-%m-%d %H:%M:%S"


def now_iso() -> str:
    return datetime.now(_CN_TZ).strftime(_FMT)


def from_unix_iso(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=_CN_TZ).strftime(_FMT)


def parse_ts_iso(text: str | None) -> datetime | None:
    s = (text or "").strip()
    if not s:
        return None
    for fmt in (_FMT, "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=_CN_TZ)
        except ValueError:
            continue
    return None


def max_ts_iso(*candidates: str | None) -> str:
    best: datetime | None = None
    best_s = ""
    for raw in candidates:
        dt = parse_ts_iso(raw)
        if dt is None:
            continue
        if best is None or dt > best:
            best = dt
            best_s = dt.strftime(_FMT)
    return best_s


def _row_ts(row: Any, attr: str) -> str:
    if isinstance(row, dict):
        return str(row.get(attr) or "")
    return str(getattr(row, attr, "") or "")


def snapshots_as_of(snapshots: list[Any] | None) -> str:
    parts = []
    for row in snapshots or []:
        parts.append(_row_ts(row, "snapshot_at"))
        parts.append(_row_ts(row, "quote_fetched_at"))
    return max_ts_iso(*parts)


def feeds_collected_iso(feeds_list: list[Any] | None) -> str:
    parts: list[str] = []
    for sf in feeds_list or []:
        parts.append(str(getattr(sf, "collected_at", "") or ""))
        feeds = getattr(sf, "feeds", None) or {}
        for items in feeds.values():
            for it in items:
                parts.append(str(getattr(it, "fetched_at", "") or ""))
    return max_ts_iso(*parts)


def market_sentiment_collected_iso(market_sentiment: dict[str, Any] | None) -> str:
    if not market_sentiment:
        return ""
    iso = market_sentiment.get("collected_at_iso")
    if iso:
        return str(iso)
    raw = market_sentiment.get("collected_at")
    if raw is not None:
        try:
            return datetime.fromtimestamp(float(raw), tz=_CN_TZ).strftime(_FMT)
        except (TypeError, ValueError, OSError):
            pass
    return ""


def digests_as_of(digests: dict[str, dict[str, Any]] | None) -> str:
    parts = [str(rec.get("digested_at") or "") for rec in (digests or {}).values()]
    return max_ts_iso(*parts)


def compute_context_as_of(
    *,
    snapshots: list[Any] | None = None,
    feeds_list: list[Any] | None = None,
    market_sentiment: dict[str, Any] | None = None,
    digests: dict[str, dict[str, Any]] | None = None,
    extra: list[str] | None = None,
) -> str:
    parts = [
        snapshots_as_of(snapshots),
        feeds_collected_iso(feeds_list),
        market_sentiment_collected_iso(market_sentiment),
        digests_as_of(digests),
    ]
    if extra:
        parts.extend(extra)
    return max_ts_iso(*parts)
