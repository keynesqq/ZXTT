"""同花顺 d.10jqka.com.cn 行情（主源）。"""
from __future__ import annotations

import json
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import date

import httpx

from core.config import normalize_code

REALHEAD = "https://d.10jqka.com.cn/v2/realhead/hs_{code}/last.js"
KLINE = "https://d.10jqka.com.cn/v6/line/hs_{code}/01/last.js"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://stockpage.10jqka.com.cn/",
}

_client_lock = threading.Lock()
_http_client: httpx.Client | None = None


def _get_http_client() -> httpx.Client:
    global _http_client
    with _client_lock:
        if _http_client is None:
            _http_client = httpx.Client(timeout=15.0, headers=HEADERS)
        return _http_client


def _parse_js(text: str) -> dict | None:
    m = re.search(r"\((\{.*\})\)\s*;?\s*$", text.strip(), re.S)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def _f(val) -> float | None:
    if val in (None, "", "-1"):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _fetch_kline_rows(code: str, *, bars: int = 120) -> list[list[str]]:
    c = normalize_code(code)
    h = {**HEADERS, "Referer": f"https://stockpage.10jqka.com.cn/{c}/"}
    client = _get_http_client()
    r = client.get(KLINE.format(code=c), headers=h)
    r.raise_for_status()
    payload = _parse_js(r.text) or {}
    rows = [x.split(",") for x in (payload.get("data") or "").split(";") if x]
    if len(rows) > bars:
        rows = rows[-bars:]
    return rows


def fetch_quote(code: str) -> dict:
    c = normalize_code(code)
    h = {**HEADERS, "Referer": f"https://stockpage.10jqka.com.cn/{c}/"}
    client = _get_http_client()
    r = client.get(REALHEAD.format(code=c), headers=h)
    r.raise_for_status()
    payload = _parse_js(r.text) or {}
    items = payload.get("items") or {}
    amount = _f(items.get("19"))
    total_mv = _f(items.get("3475914"))
    return {
        "code": c,
        "name": str(items.get("name") or payload.get("name") or c),
        "price": _f(items.get("10")),
        "pct_chg": _f(items.get("199112")),
        "amplitude": _f(items.get("526792")),
        "turnover": _f(items.get("1968584")),
        "pe": _f(items.get("2034120")),
        "pb": _f(items.get("592920")),
        "pct_60d": _f(items.get("264648")),
        "pct_ytd": _f(items.get("134152")),
        "amount_yi": amount / 1e8 if amount else None,
        "total_mv_yi": total_mv / 1e8 if total_mv else None,
    }


def _kline_derived(rows: list[list[str]], price: float | None) -> dict:
    closes = [float(x[4]) for x in rows if len(x) > 4]
    if not closes:
        return {}
    last = closes[-1]
    out: dict = {}
    if len(closes) >= 2:
        out["pre_close"] = round(closes[-2], 3)

    amounts: list[float] = []
    for row in rows:
        if len(row) > 6:
            try:
                amounts.append(float(row[6]))
            except (TypeError, ValueError):
                pass
    if len(amounts) >= 6:
        prev5 = amounts[-6:-1]
        if prev5:
            avg5 = sum(prev5) / len(prev5)
            out["amount_avg_5d_yi"] = round(avg5 / 1e8, 3)
            if amounts[-1] > 0 and avg5 > 0:
                out["amount_ratio"] = round(amounts[-1] / avg5, 2)

    for key, n in [
        ("pct_5d", 5),
        ("pct_10d", 10),
        ("pct_20d", 20),
        ("pct_30d", 30),
        ("pct_60d", 60),
    ]:
        if len(closes) >= n:
            out[key] = round((last / closes[-n] - 1) * 100, 2)
    year_prefix = str(date.today().year)
    for row in rows:
        if row[0].startswith(year_prefix):
            out["pct_ytd"] = round((last / float(row[4]) - 1) * 100, 2)
            break
    if price is not None:
        for key, period in [("ma5", 5), ("ma20", 20), ("ma60", 60)]:
            if len(closes) >= period:
                ma = sum(closes[-period:]) / period
                out[key] = round(ma, 3)
                out[f"{key}_dist"] = round((price / ma - 1) * 100, 2)
    return out


def fetch_metrics(code: str) -> dict:
    q = fetch_quote(code)
    price = q.get("price")
    try:
        rows = _fetch_kline_rows(code)
        derived = _kline_derived(rows, price)
        for key in ("pct_5d", "pct_10d", "pct_20d", "pct_30d", "pct_60d", "pct_ytd"):
            if q.get(key) is None and derived.get(key) is not None:
                q[key] = derived[key]
        for key in ("ma5", "ma20", "ma60", "ma5_dist", "ma20_dist", "ma60_dist"):
            if derived.get(key) is not None:
                q[key] = derived[key]
        for key in ("pre_close", "amount_avg_5d_yi", "amount_ratio"):
            if derived.get(key) is not None:
                q[key] = derived[key]
        if q.get("open") is None and rows and len(rows[-1]) > 1:
            try:
                q["open"] = float(rows[-1][1])
            except (TypeError, ValueError):
                pass
        if q.get("high") is None and rows and len(rows[-1]) > 2:
            try:
                q["high"] = float(rows[-1][2])
            except (TypeError, ValueError):
                pass
        if q.get("low") is None and rows and len(rows[-1]) > 3:
            try:
                q["low"] = float(rows[-1][3])
            except (TypeError, ValueError):
                pass
    except Exception:
        pass
    if q.get("pre_close") is None and q.get("price") is not None and q.get("pct_chg") is not None:
        pct = q["pct_chg"]
        if pct != -100:
            q["pre_close"] = round(q["price"] / (1 + pct / 100), 3)
    return q


def _merge_metrics(code: str, q: dict, rows: list[list[str]] | None) -> dict:
    out = dict(q)
    price = out.get("price")
    try:
        derived = _kline_derived(rows or [], price)
        for key in ("pct_5d", "pct_10d", "pct_20d", "pct_30d", "pct_60d", "pct_ytd"):
            if out.get(key) is None and derived.get(key) is not None:
                out[key] = derived[key]
        for key in ("ma5", "ma20", "ma60", "ma5_dist", "ma20_dist", "ma60_dist"):
            if derived.get(key) is not None:
                out[key] = derived[key]
        for key in ("pre_close", "amount_avg_5d_yi", "amount_ratio"):
            if derived.get(key) is not None:
                out[key] = derived[key]
        if rows:
            last = rows[-1]
            if out.get("open") is None and len(last) > 1:
                try:
                    out["open"] = float(last[1])
                except (TypeError, ValueError):
                    pass
            if out.get("high") is None and len(last) > 2:
                try:
                    out["high"] = float(last[2])
                except (TypeError, ValueError):
                    pass
            if out.get("low") is None and len(last) > 3:
                try:
                    out["low"] = float(last[3])
                except (TypeError, ValueError):
                    pass
    except Exception:
        pass
    if out.get("pre_close") is None and out.get("price") is not None and out.get("pct_chg") is not None:
        pct = out["pct_chg"]
        if pct != -100:
            out["pre_close"] = round(out["price"] / (1 + pct / 100), 3)
    out["code"] = code
    return out


def fetch_quote_batch(codes: list[str]) -> dict[str, dict]:
    """轻量批量：仅 realhead（竞价等场景），不拉 K 线。"""
    unique = list(dict.fromkeys(normalize_code(c) for c in codes if normalize_code(c)))
    if not unique:
        return {}

    workers = min(12, len(unique))

    def quote_one(code: str) -> tuple[str, dict | None]:
        try:
            row = fetch_quote(code)
            if row.get("pre_close") is None and row.get("price") is not None and row.get("pct_chg") is not None:
                pct = row["pct_chg"]
                if pct != -100:
                    row["pre_close"] = round(row["price"] / (1 + pct / 100), 3)
            return code, row
        except Exception:
            return code, None

    result: dict[str, dict] = {}
    pending = list(unique)
    for _ in range(2):
        if not pending:
            break
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for code, row in pool.map(quote_one, pending):
                if row:
                    result[code] = row
                else:
                    failed.append(code)
        pending = failed
    return result


def fetch_metrics_batch(codes: list[str]) -> dict[str, dict]:
    """批量拉取：先并行 realhead，再并行 K 线，比逐股串行快。"""
    unique = list(dict.fromkeys(normalize_code(c) for c in codes if normalize_code(c)))
    if not unique:
        return {}

    workers = min(12, len(unique))

    def quote_one(code: str) -> tuple[str, dict | None]:
        try:
            return code, fetch_quote(code)
        except Exception:
            return code, None

    def kline_one(code: str) -> tuple[str, list[list[str]] | None]:
        try:
            return code, _fetch_kline_rows(code)
        except Exception:
            return code, None

    quotes: dict[str, dict] = {}
    klines: dict[str, list[list[str]]] = {}
    pending = list(unique)
    for _ in range(2):
        if not pending:
            break
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for code, row in pool.map(quote_one, pending):
                if row:
                    quotes[code] = row
                else:
                    failed.append(code)
        pending = failed

    pending = list(quotes)
    for _ in range(2):
        if not pending:
            break
        failed: list[str] = []
        with ThreadPoolExecutor(max_workers=workers) as pool:
            for code, rows in pool.map(kline_one, pending):
                if rows is not None:
                    klines[code] = rows
                else:
                    failed.append(code)
        pending = failed

    return {code: _merge_metrics(code, quotes[code], klines.get(code)) for code in quotes}
