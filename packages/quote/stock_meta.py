"""A 股代码属性：板块、涨跌幅限制、涨跌停状态、日内形态。"""
from __future__ import annotations

from core.config import normalize_code


def stock_board(code: str) -> str:
    c = normalize_code(code)
    if c.startswith("688"):
        return "科创"
    if c.startswith("300"):
        return "创业"
    if c.startswith(("8", "4")):
        return "北交"
    return "主板"


def is_st_stock(name: str) -> bool:
    n = (name or "").upper().replace(" ", "")
    return "ST" in n


def limit_pct_for(*, board: str, is_st: bool) -> float:
    if is_st:
        return 5.0
    if board in ("创业", "科创"):
        return 20.0
    if board == "北交":
        return 30.0
    return 10.0


def open_gap_pct(open_px: float | None, pre_close: float | None) -> float | None:
    if open_px is None or pre_close is None or pre_close <= 0:
        return None
    return round((open_px / pre_close - 1) * 100, 2)


def infer_limit_status(
    pct_chg: float | None,
    limit_pct: float,
    *,
    in_limit_up_pool: bool = False,
    broken_count: int | None = None,
) -> str:
    if pct_chg is None:
        return "—"
    threshold = limit_pct * 0.98
    if pct_chg >= threshold:
        return "涨停"
    if pct_chg <= -threshold:
        return "跌停"
    if broken_count and broken_count > 0:
        return "炸板"
    if in_limit_up_pool:
        return "曾涨停"
    return "正常"


def infer_intraday_shape(
    open_px: float | None,
    high: float | None,
    low: float | None,
    close: float | None,
    pre_close: float | None,
) -> str:
    if open_px is None or high is None or low is None or close is None:
        return ""
    rng = high - low
    if rng <= 0:
        return "一字"
    tags: list[str] = []
    if pre_close and pre_close > 0:
        gap = (open_px / pre_close - 1) * 100
        if gap >= 1.0:
            tags.append("高开")
        elif gap <= -1.0:
            tags.append("低开")
    body = close - open_px
    if body > rng * 0.15:
        tags.append("阳")
    elif body < -rng * 0.15:
        tags.append("阴")
    else:
        tags.append("十字")
    upper = high - max(open_px, close)
    lower = min(open_px, close) - low
    if upper / rng >= 0.45:
        tags.append("长上影")
    elif lower / rng >= 0.45:
        tags.append("长下影")
    if close >= high - rng * 0.05 and open_px <= low + rng * 0.05:
        if close > open_px:
            tags.append("光头阳")
        elif close < open_px:
            tags.append("光脚阴")
    return "/".join(tags[:4])
