"""巨潮资讯 CNINFO 公告。"""
from __future__ import annotations

import math
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

import httpx

from core.config import normalize_code

CNINFO_STOCK_JSON = "http://www.cninfo.com.cn/new/data/szse_stock.json"
CNINFO_QUERY_URL = "http://www.cninfo.com.cn/new/hisAnnouncement/query"
CNINFO_STATIC_BASE = "http://static.cninfo.com.cn/"
CNINFO_DETAIL_BASE = "http://www.cninfo.com.cn/new/disclosure/detail"
PAGE_SIZE = 30
MAX_PAGES = 5
TZ = ZoneInfo("Asia/Shanghai")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "http://www.cninfo.com.cn/new/disclosure",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
}


@lru_cache(maxsize=1)
def _org_id_map() -> dict[str, str]:
    with httpx.Client(timeout=20.0) as client:
        resp = client.get(CNINFO_STOCK_JSON)
        resp.raise_for_status()
        data = resp.json()
    return {str(item["code"]).zfill(6): str(item["orgId"]) for item in data.get("stockList", [])}


def _ms_to_datetime(value) -> datetime | None:
    try:
        ms = int(value)
        return datetime.fromtimestamp(ms / 1000, tz=TZ).replace(tzinfo=None)
    except (TypeError, ValueError, OSError):
        return None


def _build_url(code: str, title: str, ann_id: str, org_id: str, pub_dt: datetime, adjunct_url) -> str:
    if adjunct_url:
        return f"{CNINFO_STATIC_BASE}{str(adjunct_url).lstrip('/')}"
    time_str = pub_dt.strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"{CNINFO_DETAIL_BASE}?stockCode={code}&announcementId={ann_id}"
        f"&orgId={org_id}&announcementTime={time_str}"
    )


def fetch_announcements(code: str, start: date, end: date) -> list[dict]:
    c = normalize_code(code)
    org_id = _org_id_map().get(c)
    if not org_id:
        return []

    payload = {
        "pageNum": "1",
        "pageSize": str(PAGE_SIZE),
        "column": "szse",
        "tabName": "fulltext",
        "plate": "",
        "stock": f"{c},{org_id}",
        "searchkey": "",
        "secid": "",
        "category": "",
        "trade": "",
        "seDate": f"{start.isoformat()}~{end.isoformat()}",
        "sortName": "",
        "sortType": "",
        "isHLtitle": "true",
    }
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=20.0, headers=HEADERS) as client:
            first_resp = client.post(CNINFO_QUERY_URL, data=payload)
            first_resp.raise_for_status()
            first = first_resp.json()
            total = int(first.get("totalAnnouncement") or 0)
            rows.extend(_parse_ann_items(first.get("announcements") or [], c))
            pages = min(math.ceil(total / PAGE_SIZE), MAX_PAGES)
            for page in range(2, pages + 1):
                payload["pageNum"] = str(page)
                r = client.post(CNINFO_QUERY_URL, data=payload)
                r.raise_for_status()
                rows.extend(_parse_ann_items(r.json().get("announcements") or [], c))
    except Exception:
        return rows
    return rows


def fetch_latest_announcements(code: str, limit: int = 5) -> list[dict]:
    """无近期公告时，拉取历史最新若干条（按日期降序）。"""
    end = date.today()
    start = end - timedelta(days=3650)
    rows = fetch_announcements(code, start, end)
    rows.sort(key=lambda r: (r.get("pub_date", ""), r.get("pub_time", "")), reverse=True)
    return rows[: max(1, limit)]


def _parse_ann_items(items: list[dict], code: str) -> list[dict]:
    rows: list[dict] = []
    for item in items:
        if normalize_code(str(item.get("secCode", ""))) != code:
            continue
        pub_dt = _ms_to_datetime(item.get("announcementTime"))
        if not pub_dt:
            continue
        title = str(item.get("announcementTitle", "")).strip()
        if not title:
            continue
        ann_type = item.get("announcementTypeName") or "公告"
        rows.append(
            {
                "pub_date": pub_dt.date().isoformat(),
                "pub_time": pub_dt.strftime("%H:%M"),
                "title": title[:500],
                "source": str(ann_type),
                "url": _build_url(
                    code,
                    title,
                    str(item.get("announcementId", "")),
                    str(item.get("orgId", "")),
                    pub_dt,
                    item.get("adjunctUrl"),
                ),
                "provider": "巨潮",
            }
        )
    return rows
