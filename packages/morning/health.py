"""早盘数据健康：仅评估本报告实际使用的数据源。"""
from __future__ import annotations

from datetime import date
from typing import Any

from morning.evening_ref import evening_recap_text

_TIER0 = frozenset({"holding", "candidate"})


def _has_evening_expectation_content(exp_stock: dict[str, Any]) -> bool:
    if evening_recap_text(exp_stock):
        return True
    return bool(exp_stock.get("critical"))


def _ann_empty_count(morning_pre: dict[str, Any], rows: list[dict[str, Any]]) -> int:
    pre_by = morning_pre.get("by_code") or {}
    n = 0
    for row in rows:
        code = str(row.get("code") or "")
        if row.get("primary_stance") not in _TIER0:
            continue
        counts = (pre_by.get(code) or {}).get("item_counts") or {}
        if int(counts.get("公告") or 0) == 0:
            n += 1
    return n


def _expectation_missing(rows: list[dict[str, Any]], exp_stocks: dict[str, Any]) -> int:
    n = 0
    for row in rows:
        if row.get("primary_stance") not in _TIER0:
            continue
        if str(row.get("expected_open") or "").strip():
            continue
        code = str(row.get("code") or "")
        if _has_evening_expectation_content(exp_stocks.get(code) or {}):
            continue
        n += 1
    return n


def _auction_missing_codes(morning_pre: dict[str, Any], auction_trend: dict[str, Any]) -> int:
    pre_codes = set((morning_pre.get("by_code") or {}).keys())
    auction_codes = {
        str(st.get("code") or "")
        for st in (auction_trend.get("stocks") or [])
        if st.get("code")
    }
    return len(pre_codes - auction_codes)


def _trust_flags(
    *,
    auction_trend: dict[str, Any],
    morning_pre: dict[str, Any],
    checks: dict[str, Any],
    open_market: dict[str, Any] | None,
    evening_summary: str,
    prev_trade_date: str,
    exp_stocks: dict[str, Any],
) -> dict[str, bool]:
    rows = checks.get("rows") or []
    pre_summary = morning_pre.get("summary") or {}
    open_m = open_market or {}
    point_count = int(auction_trend.get("point_count") or 0)
    return {
        "auction_ok": point_count >= 2 and bool(auction_trend.get("stocks")),
        "auction_complete": _auction_missing_codes(morning_pre, auction_trend) == 0,
        "pre_collect_ok": int(pre_summary.get("failed") or 0) == 0,
        "open_market_ok": not (open_m.get("warnings") or []),
        "prev_limit_ok": open_m.get("prev_limit_count") is not None,
        "evening_summary_ok": bool(evening_summary.strip()) or not prev_trade_date,
        "expectations_ok": _expectation_missing(rows, exp_stocks) == 0,
    }


def _health_brief(trust: dict[str, bool], summary: dict[str, Any]) -> str:
    parts: list[str] = []
    if not trust.get("evening_summary_ok"):
        parts.append("昨晚推送摘要缺失")
    if not trust.get("expectations_ok"):
        n = int(summary.get("expectation_missing") or 0)
        parts.append(f"{n} 只开盘预期缺失" if n else "开盘预期缺失")
    if not trust.get("auction_ok"):
        parts.append("竞价序列不完整")
    if not trust.get("auction_complete"):
        n = int(summary.get("auction_missing_codes") or 0)
        parts.append(f"竞价缺 {n} 只" if n else "竞价缺股")
    if not trust.get("pre_collect_ok"):
        failed = int(summary.get("pre_failed") or 0)
        parts.append(f"9:15素材采集失败 {failed} 只" if failed else "9:15素材采集异常")
    if not trust.get("open_market_ok"):
        parts.append("9:25开盘环境采集异常")
    elif not trust.get("prev_limit_ok"):
        parts.append("昨涨停溢价不可用")
    ann_empty = int(summary.get("ann_empty_codes") or 0)
    if ann_empty:
        parts.append(f"{ann_empty} 只近3日无公告")
    return "；".join(parts) + "。" if parts else "数据整体可用。"


def build_health(
    *,
    calendar_date: date,
    auction_trend: dict[str, Any],
    morning_pre: dict[str, Any],
    checks: dict[str, Any],
    open_market: dict[str, Any] | None = None,
    evening_summary: str = "",
    prev_trade_date: str = "",
    evening_expectations: dict[str, Any] | None = None,
) -> dict[str, Any]:
    del calendar_date
    rows = checks.get("rows") or []
    exp_stocks = (evening_expectations or {}).get("stocks") or {}
    pre_summary = morning_pre.get("summary") or {}
    trust = _trust_flags(
        auction_trend=auction_trend,
        morning_pre=morning_pre,
        checks=checks,
        open_market=open_market,
        evening_summary=evening_summary,
        prev_trade_date=prev_trade_date,
        exp_stocks=exp_stocks,
    )
    summary = {
        "ann_empty_codes": _ann_empty_count(morning_pre, rows),
        "pre_failed": int(pre_summary.get("failed") or 0),
        "auction_missing_codes": _auction_missing_codes(morning_pre, auction_trend),
        "expectation_missing": _expectation_missing(rows, exp_stocks),
    }
    return {
        "slot": "morning",
        "health_brief": _health_brief(trust, summary),
        "trust_flags": trust,
        "summary": summary,
    }


__all__ = ["build_health"]
