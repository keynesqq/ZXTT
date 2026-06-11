"""核对表：预期双轨、verdict、highlight、分组。"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from typing import Any

from core.config import normalize_code
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import previous_trading_day
from quote.query_cache import load_quote_query_cache

_EXP_DIR = DATA_DIR / "expectations"
_AI_DIR = DATA_DIR / "scheduled_ai"
_CHECKS_DIR = DATA_DIR / "morning_checks"

_GROUP_HOLDING = frozenset({"我的"})
_GROUP_CANDIDATE = frozenset({"想买的"})

_STRONG_SHAPES = frozenset(
    {"一路抬升", "一路走弱", "冲高回落", "探底回升"}
)

_OPEN_PATTERNS = [
    (re.compile(r"偏高开|略偏强|高开"), "偏高开"),
    (re.compile(r"偏低开|略偏弱|低开"), "偏低开"),
    (re.compile(r"不确定"), "不确定"),
    (re.compile(r"震荡|中性"), "震荡/中性"),
]


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def extract_open_from_text(text: str) -> str:
    for pat, label in _OPEN_PATTERNS:
        if pat.search(text or ""):
            return label
    m = re.search(r"开盘情景[为是：:]\s*([^\s，。；;]+)", text or "")
    if m:
        return m.group(1).strip()
    return ""


def load_evening_expectations(day: date) -> dict[str, Any]:
    return _load_json(_EXP_DIR / f"{day.isoformat()}.json") or {}


def load_evening_ai(prev_day: date) -> dict[str, Any]:
    return _load_json(_AI_DIR / f"evening_{prev_day.isoformat()}.json") or {}


def expected_open_for_code(
    code: str,
    *,
    expectations: dict[str, Any],
    evening_ai: dict[str, Any],
) -> tuple[str, str]:
    stocks = expectations.get("stocks") or {}
    rec = stocks.get(code) or {}
    exp = str(rec.get("expected_open") or "").strip()
    if exp:
        return exp, "expectations"
    body = evening_ai.get("body") or ""
    block_m = re.search(
        rf"###\s+{code}\s+[^\n]*\n([\s\S]*?)(?=###\s+\d{{6}}|\Z)",
        body,
    )
    snippet = block_m.group(1) if block_m else body
    parsed = extract_open_from_text(snippet)
    if parsed:
        return parsed, "evening_body"
    return "", ""


def _surprise_verdict(metric: float) -> str:
    return "超预期偏强" if metric >= 0 else "超预期偏弱"


def match_verdict(expected: str, end_gap: float | None) -> str:
    if end_gap is None:
        return "数据缺失"
    metric = end_gap
    if "高开" in expected or "偏强" in expected:
        if metric >= 1.5:
            return _surprise_verdict(metric)
        if metric >= 0.3:
            return "符合"
        if metric <= -0.5:
            return "不符合"
        return "部分符合"
    if "低开" in expected or "偏弱" in expected:
        if metric <= -1.5:
            return _surprise_verdict(metric)
        if metric <= -0.3:
            return "符合"
        if metric >= 0.5:
            return "不符合"
        return "部分符合"
    if metric >= 1.2:
        return _surprise_verdict(metric)
    if metric <= -1.2:
        return _surprise_verdict(metric)
    if abs(metric) <= 0.5:
        return "符合"
    return "部分符合"


def primary_stance_for_groups(groups: list[str]) -> str:
    if any(g in _GROUP_HOLDING for g in groups):
        return "holding"
    if any(g in _GROUP_CANDIDATE for g in groups):
        return "candidate"
    return "theme_other"


def groups_for_code(code: str, memberships: list[dict]) -> list[str]:
    groups: list[str] = []
    for row in memberships:
        if normalize_code(str(row.get("code") or "")) != code:
            continue
        g = str(row.get("group") or "").strip()
        if g and g not in groups:
            groups.append(g)
    return groups


def compute_highlight(
    *,
    verdict: str,
    end_gap: float | None,
    limit_status: str,
    shape_after_920: str,
    pre_status: str,
) -> bool:
    if verdict in ("超预期", "超预期偏强", "超预期偏弱", "不符合"):
        return True
    if end_gap is not None and abs(end_gap) >= 2.0:
        return True
    if limit_status and limit_status != "正常":
        return True
    if shape_after_920 in _STRONG_SHAPES:
        return True
    if pre_status == "refresh":
        return True
    return False


def build_checks(
    *,
    calendar_date: date,
    auction_trend: dict[str, Any],
    morning_pre: dict[str, Any],
    open_market: dict[str, Any] | None = None,
) -> dict[str, Any]:
    prev_td = previous_trading_day(calendar_date)
    expectations = load_evening_expectations(calendar_date)
    evening_ai = load_evening_ai(prev_td) if prev_td else {}
    quote = load_quote_query_cache(on_date=calendar_date) or {}
    if not quote.get("quotes") and prev_td:
        quote = load_quote_query_cache(on_date=prev_td) or quote
    memberships = quote.get("memberships") or []

    pre_by = morning_pre.get("by_code") or {}
    stocks_trend = auction_trend.get("stocks") or []
    rows: list[dict[str, Any]] = []

    for st in stocks_trend:
        code = normalize_code(str(st.get("code") or ""))
        if not code:
            continue
        groups = groups_for_code(code, memberships)
        stance = primary_stance_for_groups(groups)
        pre_rec = pre_by.get(code) or {}
        pre_status = str(pre_rec.get("status") or "")
        expected, exp_src = expected_open_for_code(
            code, expectations=expectations, evening_ai=evening_ai
        )
        exp_stock = (expectations.get("stocks") or {}).get(code) or {}
        end_gap = st.get("end_gap")
        try:
            end_gap_f = float(end_gap) if end_gap is not None else None
        except (TypeError, ValueError):
            end_gap_f = None
        verdict = match_verdict(expected, end_gap_f)
        highlight = compute_highlight(
            verdict=verdict,
            end_gap=end_gap_f,
            limit_status=str(st.get("limit_status") or "正常"),
            shape_after_920=str(st.get("shape_after_920") or ""),
            pre_status=pre_status,
        )
        rows.append(
            {
                "code": code,
                "name": st.get("name") or code,
                "groups": groups,
                "primary_stance": stance,
                "expected_open": expected,
                "expected_source": exp_src,
                "discipline": exp_stock.get("discipline") or "",
                "check_925": exp_stock.get("check_925") or "",
                "end_gap": end_gap_f,
                "shape": st.get("shape"),
                "shape_after_920": st.get("shape_after_920"),
                "limit_status": st.get("limit_status"),
                "amount_delta_total": st.get("amount_delta_total"),
                "verdict": verdict,
                "highlight": highlight,
                "pre_status": pre_status,
                "pre_titles": pre_rec.get("new_titles") or [],
            }
        )

    rows.sort(key=lambda r: r.get("code") or "")
    payload = {
        "schema_version": 1,
        "slot": "morning",
        "calendar_date": calendar_date.isoformat(),
        "prev_trade_date": prev_td.isoformat() if prev_td else "",
        "point_count": auction_trend.get("point_count"),
        "open_market": open_market,
        "rows": rows,
        "summary": {
            "超预期偏强": sum(1 for r in rows if r.get("verdict") == "超预期偏强"),
            "超预期偏弱": sum(1 for r in rows if r.get("verdict") == "超预期偏弱"),
            "不符合": sum(1 for r in rows if r.get("verdict") == "不符合"),
            "highlight": sum(1 for r in rows if r.get("highlight")),
        },
    }
    return payload


def save_checks(payload: dict[str, Any], day: date) -> Path:
    _CHECKS_DIR.mkdir(parents=True, exist_ok=True)
    path = _CHECKS_DIR / f"{day.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


__all__ = [
    "build_checks",
    "save_checks",
    "expected_open_for_code",
    "match_verdict",
]
