"""同花顺 F10 资讯辅助（on_empty 时启用）。"""
from __future__ import annotations

from datetime import date, datetime

import httpx

from core.config import normalize_code
from feeds.news_filter import filter_news_rows

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://stockpage.10jqka.com.cn/",
}

NEWS_URL = "https://news.10jqka.com.cn/tapp/news/push/stock/?code={code}&tag=&track=website&pagesize=30"
REPORT_URL = "https://basic.10jqka.com.cn/api/stockph/report/list?code={code}&page=1&size=20"


def _parse_date(text: str) -> date | None:
    text = (text or "").strip()
    if not text:
        return None
    if text.isdigit() and len(text) >= 10:
        try:
            ts = int(text[:10])
            return datetime.fromtimestamp(ts).date()
        except (ValueError, OSError):
            pass
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%Y/%m/%d"):
        try:
            size = 19 if " " in fmt else 10
            return datetime.strptime(text[:size], fmt).date()
        except ValueError:
            continue
    return None


def fetch_stock_news(code: str, start: date, end: date, *, name: str = "") -> list[dict]:
    c = normalize_code(code)
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS) as client:
            r = client.get(NEWS_URL.format(code=c))
            r.raise_for_status()
            data = r.json()
        for item in data.get("data", {}).get("list", []) or data.get("list", []) or []:
            title = str(item.get("title") or item.get("digest") or "").strip()
            if not title:
                continue
            pub_d = _parse_date(str(item.get("ctime") or item.get("rtime") or item.get("date") or ""))
            if pub_d and (pub_d < start or pub_d > end):
                continue
            url = str(item.get("url") or item.get("weburl") or "")
            if url and not url.startswith("http"):
                url = "https://news.10jqka.com.cn" + url
            rows.append(
                {
                    "pub_date": (pub_d or date.today()).isoformat(),
                    "pub_time": "",
                    "title": title[:500],
                    "source": str(item.get("source") or "同花顺"),
                    "url": url,
                    "provider": "同花顺",
                }
            )
    except Exception:
        pass
    return filter_news_rows(rows, c, name)


def fetch_research(code: str, start: date, end: date) -> list[dict]:
    c = normalize_code(code)
    rows: list[dict] = []
    try:
        with httpx.Client(timeout=15.0, headers=HEADERS) as client:
            r = client.get(REPORT_URL.format(code=c))
            r.raise_for_status()
            data = r.json()
        for item in data.get("data", []) or []:
            title = str(item.get("title") or item.get("reportTitle") or "").strip()
            if not title:
                continue
            pub_d = _parse_date(str(item.get("date") or item.get("publishDate") or ""))
            if pub_d and (pub_d < start or pub_d > end):
                continue
            rows.append(
                {
                    "pub_date": (pub_d or date.today()).isoformat(),
                    "pub_time": "",
                    "title": title[:500],
                    "source": str(item.get("org") or item.get("organ") or "同花顺"),
                    "url": str(item.get("url") or ""),
                    "extra": str(item.get("rating") or ""),
                    "provider": "同花顺",
                }
            )
    except Exception:
        pass
    return rows
