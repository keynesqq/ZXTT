"""财联社 HTTP 请求公共参数（含时间戳，避免缓存/错日数据）。"""
from __future__ import annotations

import hashlib
import time
from datetime import date, datetime
from typing import Any

import httpx

_WEB_UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)
_APP_UA = "okhttp/4.9.0"

_APP_BASE: dict[str, str] = {
    "app": "cailianpress",
    "sv": "8.7.4",
    "os": "android",
    "mb": "Xiaomi-2206123SC",
    "ov": "32",
    "channel": "8",
    "motif": "0",
    "net": "",
    "province_code": "3205",
    "token": "",
    "uid": "",
}

_WEB_BASE: dict[str, str] = {
    "app": "CailianpressWeb",
    "os": "web",
    "sv": "8.4.6",
    "sign": "9f8797a1f4de66c2370f7a03990d2737",
}


def now_ts() -> int:
    return int(time.time())


def now_ms() -> int:
    return int(time.time() * 1000)


def day_end_ts(for_date: date | None = None) -> int:
    d = for_date or date.today()
    return int(datetime(d.year, d.month, d.day, 23, 59, 59).timestamp())


def day_start_ts(for_date: date | None = None) -> int:
    d = for_date or date.today()
    return int(datetime(d.year, d.month, d.day, 0, 0, 0).timestamp())


def ts_iso(ts: float | int | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts)).strftime("%Y-%m-%d %H:%M:%S")
    except (OSError, OverflowError, ValueError):
        return None


def app_sign(params: dict[str, str]) -> str:
    s = "&".join(f"{k}={v}" for k, v in sorted(params.items()))
    sha1 = hashlib.sha1(s.encode()).hexdigest()
    return hashlib.md5(sha1.encode()).hexdigest()


def web_sign_params(**extra: str | int) -> dict[str, str]:
    """网页 JSON API 签名参数（Subject 栏目列表等）。"""
    p = {"app": "CailianpressWeb", "os": "web", "sv": "8.7.9", **{k: str(v) for k, v in extra.items()}}
    p["sign"] = app_sign(p)
    return p


def web_params(**extra: str | int) -> dict[str, str]:
    """网页端请求参数，附带毫秒时间戳。"""
    p = {**_WEB_BASE, **{k: str(v) for k, v in extra.items()}}
    p["_t"] = str(now_ms())
    return p


def app_params(*, for_date: date | None = None, **extra: str | int) -> dict[str, str]:
    """App 端签名请求参数，附带 last_time（日末）与 _t。"""
    p = {**_APP_BASE, **{k: str(v) for k, v in extra.items() if k != "last_time"}}
    p["last_time"] = str(extra.get("last_time", day_end_ts(for_date)))
    p["_t"] = str(now_ms())
    p["sign"] = app_sign({k: v for k, v in p.items() if k != "sign"})
    return p


def web_headers(*, referer: str = "https://www.cls.cn/finance") -> dict[str, str]:
    return {"User-Agent": _WEB_UA, "Referer": referer, "Cache-Control": "no-cache"}


def app_headers(*, host: str = "api3.cls.cn") -> dict[str, str]:
    return {"User-Agent": _APP_UA, "Accept-Encoding": "gzip", "Host": host, "Cache-Control": "no-cache"}


def get_signed_json(
    url: str,
    *,
    params: dict[str, str],
    referer: str,
    timeout: float = 12.0,
) -> Any:
    """GET 带 sign 的 JSON API（不附加 _t）。"""
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, params=params, headers=web_headers(referer=referer))
        resp.raise_for_status()
        return resp.json()


def get_json(
    url: str,
    *,
    params: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 15.0,
    referer: str = "https://www.cls.cn/",
) -> Any:
    """GET JSON/HTML；query 自动补 _t 毫秒时间戳。"""
    q = dict(params or {})
    if "_t" not in q:
        q["_t"] = str(now_ms())
    h = headers or web_headers(referer=referer)
    with httpx.Client(timeout=timeout, follow_redirects=True) as client:
        resp = client.get(url, params=q, headers=h)
        resp.raise_for_status()
        if "json" in (resp.headers.get("content-type") or ""):
            return resp.json()
        return resp.text
