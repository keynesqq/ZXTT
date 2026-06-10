"""拼装 morning_context。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from core.context_as_of import now_iso
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import previous_trading_day
from morning.checks import build_checks, load_evening_ai, save_checks

_CTX_DIR = DATA_DIR / "morning_context"
_TREND = DATA_DIR / "auction_trend_{d}.json"
_PRE = DATA_DIR / "morning_pre"


def _load_json(path: Path) -> dict[str, Any] | None:
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_auction_trend(day: date) -> dict[str, Any] | None:
    return _load_json(DATA_DIR / f"auction_trend_{day.isoformat()}.json")


def load_morning_pre(day: date) -> dict[str, Any] | None:
    return _load_json(_PRE / f"{day.isoformat()}.json")


def build_morning_context(
    *,
    calendar_date: date,
    open_market: dict[str, Any] | None = None,
) -> dict[str, Any]:
    auction = load_auction_trend(calendar_date)
    if not auction:
        raise FileNotFoundError(f"auction_trend missing for {calendar_date}")
    morning_pre = load_morning_pre(calendar_date) or {"by_code": {}, "summary": {}}
    checks = build_checks(
        calendar_date=calendar_date,
        auction_trend=auction,
        morning_pre=morning_pre,
        open_market=open_market,
    )
    save_checks(checks, calendar_date)

    prev_td = previous_trading_day(calendar_date)
    evening_ai = load_evening_ai(prev_td) if prev_td else {}
    evening_summary = (evening_ai.get("summary") or "").strip()

    stocks_prompt: list[dict[str, Any]] = []
    for row in checks.get("rows") or []:
        tier = "tier0" if row.get("primary_stance") in ("holding", "candidate") else (
            "tier1_star" if row.get("highlight") else "tier1"
        )
        line = (
            f"预期={row.get('expected_open') or '—'} | 终缺口={row.get('end_gap')}% | "
            f"9:20后={row.get('shape_after_920')} | 判定={row.get('verdict')} | "
            f"素材={row.get('pre_status')}"
        )
        stocks_prompt.append(
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "stance_hint": row.get("primary_stance"),
                "tier": tier,
                "prompt_line": line,
                "highlight": row.get("highlight"),
            }
        )

    ctx = {
        "schema_version": 1,
        "slot": "morning",
        "session_label": "集合竞价结束",
        "meta": {
            "calendar_date": calendar_date.isoformat(),
            "context_as_of": now_iso(),
            "code_count": len(stocks_prompt),
            "point_count": auction.get("point_count"),
            "evening_summary": evening_summary[:800],
        },
        "morning_pre": morning_pre,
        "auction_trend": auction,
        "checks": checks,
        "open_market": open_market,
        "prompt": {
            "priority_instructions": (
                "【报告类型】开盘核对卡 | 【数据】昨晚预期+9:15素材+竞价走势 | "
                "【目标】9:30起前30分钟纪律\n"
                "我的/想买的：短评2-4句；其余默认一句；highlight升格短评。"
            ),
            "stocks": stocks_prompt,
        },
    }
    return ctx


def save_context(ctx: dict[str, Any], day: date) -> Path:
    _CTX_DIR.mkdir(parents=True, exist_ok=True)
    path = _CTX_DIR / f"{day.isoformat()}.json"
    atomic_write_text(path, json.dumps(ctx, ensure_ascii=False, indent=2))
    return path


__all__ = ["build_morning_context", "save_context", "load_auction_trend", "load_morning_pre"]
