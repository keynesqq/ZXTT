"""腾讯财经 qt.gtimg.cn 行情（辅源 / 校验）。"""
from __future__ import annotations

import re
from typing import Any

import httpx

from core.config import normalize_code

TENCENT_QUOTE_URL = "https://qt.gtimg.cn/q="
CHUNK_SIZE = 60
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.qq.com/",
}

_IDX_NAME = 1
_IDX_CODE = 2
_IDX_PRICE = 3
_IDX_PRE_CLOSE = 4
_IDX_OPEN = 5
_IDX_VOLUME = 6
_IDX_SNAPSHOT_TS = 30
_IDX_CHANGE = 31
_IDX_PCT = 32
_IDX_HIGH = 33
_IDX_LOW = 34
_IDX_AMOUNT_WAN = 37
_IDX_TURNOVER = 38
_IDX_AMPLITUDE = 43
_IDX_PCT_5D = 62
_IDX_PCT_20D = 63
_IDX_HIGH_52W = 67
_IDX_LOW_52W = 68
_IDX_PCT_YTD = 69
_IDX_PCT_60D = 70
_IDX_PCT_250D = 71

DEFAULT_INDEX_SYMBOLS: list[tuple[str, str]] = [
    ("sh000001", "上证指数"),
    ("sz399001", "深证成指"),
    ("sz399006", "创业板指"),
    ("sh000905", "中证500"),
]


def code_to_tencent_symbol(code: str) -> str:
    c = normalize_code(code)
    if c.startswith(("5", "6", "9")):
        return f"sh{c}"
    return f"sz{c}"


def _to_float(val) -> float | None:
    if val in (None, ""):
        return None
    try:
        return float(val)
    except (TypeError, ValueError):
        return None


def _parse_quote_line(line: str) -> dict | None:
    match = re.search(r'"([^"]*)"', line)
    if not match:
        return None
    parts = match.group(1).split("~")
    if len(parts) < 35:
        return None
    code = normalize_code(parts[2])
    if not code.isdigit():
        return None
    amount_wan = _to_float(parts[37]) if len(parts) > 37 else None
    return {
        "code": code,
        "name": parts[1] if len(parts) > 1 else code,
        "price": _to_float(parts[3]),
        "open": _to_float(parts[5]),
        "high": _to_float(parts[33]) if len(parts) > 33 else None,
        "low": _to_float(parts[34]) if len(parts) > 34 else None,
        "pre_close": _to_float(parts[4]),
        "pct_chg": _to_float(parts[32]),
        "turnover": _to_float(parts[38]) if len(parts) > 38 else None,
        "amplitude": _to_float(parts[43]) if len(parts) > 43 else None,
        "pe": _to_float(parts[39]) if len(parts) > 39 else None,
        "pb": _to_float(parts[46]) if len(parts) > 46 else None,
        "total_mv_yi": _to_float(parts[45]) if len(parts) > 45 else None,
        "float_mv_yi": _to_float(parts[44]) if len(parts) > 44 else None,
        "amount_yi": amount_wan / 10000 if amount_wan else None,
    }


def _parse_snapshot_ts(raw: Any) -> tuple[str | None, str | None]:
    s = str(raw or "").strip()
    if len(s) == 14 and s.isdigit():
        iso = f"{s[0:4]}-{s[4:6]}-{s[6:8]} {s[8:10]}:{s[10:12]}:{s[12:14]}"
        return s, iso
    return None, None


def _part_float(parts: list[str], idx: int) -> float | None:
    if idx >= len(parts):
        return None
    return _to_float(parts[idx])


def _split_tencent_symbol(symbol: str) -> tuple[str, str]:
    sym = str(symbol).strip().lower()
    if len(sym) >= 8 and sym[:2] in ("sh", "sz"):
        return sym[:2], sym[2:]
    return "", normalize_code(sym)


def _parse_index_line(line: str, fallback_symbol: str, fallback_name: str) -> dict | None:
    match = re.search(r'"([^"]*)"', line)
    if not match:
        return None
    parts = match.group(1).split("~")
    if len(parts) < 6:
        return None
    raw_symbol = str(parts[_IDX_CODE] if len(parts) > _IDX_CODE else "").strip().lower()
    market, code = _split_tencent_symbol(raw_symbol)
    if not market:
        market, code = _split_tencent_symbol(fallback_symbol)
    if not market or not code:
        return None
    symbol = f"{market}{code}"
    pre_close = _to_float(parts[_IDX_PRE_CLOSE])
    open_px = _to_float(parts[_IDX_OPEN])
    price = _to_float(parts[_IDX_PRICE])
    volume = _part_float(parts, _IDX_VOLUME)
    amount_wan = _part_float(parts, _IDX_AMOUNT_WAN) if len(parts) > _IDX_AMOUNT_WAN else None
    turnover = _part_float(parts, _IDX_TURNOVER) if len(parts) > _IDX_TURNOVER else None
    amplitude = _part_float(parts, _IDX_AMPLITUDE) if len(parts) > _IDX_AMPLITUDE else None

    snapshot_raw: str | None = None
    snapshot_at: str | None = None
    change: float | None = None
    pct: float | None = None
    high: float | None = None
    low: float | None = None
    for i, raw in enumerate(parts):
        s = str(raw).strip()
        if len(s) == 14 and s.isdigit():
            snapshot_raw, snapshot_at = _parse_snapshot_ts(s)
            change = _part_float(parts, i + 1)
            pct = _part_float(parts, i + 2)
            high = _part_float(parts, i + 3)
            low = _part_float(parts, i + 4)
            break

    open_gap = None
    if open_px is not None and pre_close is not None and pre_close > 0:
        open_gap = round((open_px / pre_close - 1) * 100, 2)
    if change is None and price is not None and pre_close is not None:
        change = round(price - pre_close, 2)

    stage: dict[str, float | None] = {}
    if len(parts) > _IDX_HIGH_52W:
        stage = {
            "pct_5d": _part_float(parts, _IDX_PCT_5D),
            "pct_20d": _part_float(parts, _IDX_PCT_20D),
            "high_52w": _part_float(parts, _IDX_HIGH_52W),
            "low_52w": _part_float(parts, _IDX_LOW_52W),
            "pct_ytd": _part_float(parts, _IDX_PCT_YTD),
            "pct_60d": _part_float(parts, _IDX_PCT_60D),
            "pct_250d": _part_float(parts, _IDX_PCT_250D),
        }

    return {
        "symbol": symbol,
        "market": market,
        "code": code,
        "name": parts[_IDX_NAME] if len(parts) > _IDX_NAME else fallback_name,
        "price": price,
        "open": open_px,
        "high": high,
        "low": low,
        "pre_close": pre_close,
        "change": change,
        "pct_chg": pct,
        "open_gap_pct": open_gap,
        "volume": volume,
        "turnover": turnover,
        "amplitude": amplitude,
        "amount_yi": amount_wan / 10000 if amount_wan else None,
        "snapshot_ts": snapshot_raw,
        "snapshot_at": snapshot_at,
        **stage,
    }


def fetch_index_snapshots(
    symbols: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """拉主要指数快照（腾讯 qt）。"""
    pairs = symbols or list(DEFAULT_INDEX_SYMBOLS)
    if not pairs:
        return []
    symbol_list = [s for s, _ in pairs]
    name_by_sym = {s: n for s, n in pairs}
    out: list[dict] = []
    with httpx.Client(timeout=15.0, headers=HEADERS) as client:
        try:
            resp = client.get(f"{TENCENT_QUOTE_URL}{','.join(symbol_list)}")
            resp.raise_for_status()
            text = resp.content.decode("gbk", errors="replace")
        except Exception:
            return []
        for line in text.strip().split(";"):
            line = line.strip()
            if not line or "=" not in line:
                continue
            sym = next((s for s in symbol_list if s in line), "")
            if not sym:
                continue
            parsed = _parse_index_line(line, sym, name_by_sym.get(sym, sym))
            if parsed:
                out.append(parsed)
    order = {s: i for i, s in enumerate(symbol_list)}
    out.sort(key=lambda row: order.get(row.get("symbol", ""), 999))
    return out


_OPEN_GAP_FIELDS = (
    "symbol",
    "name",
    "price",
    "open",
    "high",
    "low",
    "pre_close",
    "change",
    "pct_chg",
    "open_gap_pct",
    "volume",
    "amount_yi",
    "amplitude",
    "snapshot_at",
)


def fetch_index_open_gaps(
    symbols: list[tuple[str, str]] | None = None,
) -> list[dict]:
    """主要指数开盘缺口（兼容开盘环境输入）。"""
    out: list[dict] = []
    for row in fetch_index_snapshots(symbols):
        out.append({k: row.get(k) for k in _OPEN_GAP_FIELDS})
    return out


def fetch_quotes(codes: list[str]) -> dict[str, dict]:
    if not codes:
        return {}
    symbols = [code_to_tencent_symbol(c) for c in codes]
    result: dict[str, dict] = {}
    with httpx.Client(timeout=15.0, headers=HEADERS) as client:
        for i in range(0, len(symbols), CHUNK_SIZE):
            chunk = symbols[i : i + CHUNK_SIZE]
            try:
                resp = client.get(f"{TENCENT_QUOTE_URL}{','.join(chunk)}")
                resp.raise_for_status()
                text = resp.content.decode("gbk", errors="replace")
            except Exception:
                continue
            for line in text.strip().split(";"):
                line = line.strip()
                if not line or "=" not in line:
                    continue
                parsed = _parse_quote_line(line)
                if parsed:
                    result[parsed["code"]] = parsed
    return result
