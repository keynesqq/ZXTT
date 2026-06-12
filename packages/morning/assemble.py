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
from morning.checks import build_checks, load_evening_ai, load_evening_expectations, save_checks
from morning.evening_ref import merge_evening_into_row, stock_tier
from morning.health import build_health
from morning.pre_format import format_stock_prompt_line

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
    evening_expectations = load_evening_expectations(calendar_date)
    exp_stocks = evening_expectations.get("stocks") or {}

    stocks_prompt: list[dict[str, Any]] = []
    for row in checks.get("rows") or []:
        code = str(row.get("code") or "")
        merged = merge_evening_into_row(row, exp_stocks.get(code) or {})
        tier = stock_tier(merged)
        line = format_stock_prompt_line(merged)
        stocks_prompt.append(
            {
                "code": merged.get("code"),
                "name": merged.get("name"),
                "stance_hint": merged.get("primary_stance"),
                "tier": tier,
                "prompt_line": line,
                "highlight": merged.get("highlight"),
            }
        )
        # 回写 enriched 字段供 prompt_build 核对表使用
        row.update(
            {
                "discipline": merged.get("discipline") or "",
                "check_925": merged.get("check_925") or "",
                "evening_recap": merged.get("evening_recap") or "",
            }
        )

    health = build_health(
        calendar_date=calendar_date,
        auction_trend=auction,
        morning_pre=morning_pre,
        checks=checks,
        open_market=open_market,
        evening_summary=evening_summary,
        prev_trade_date=prev_td.isoformat() if prev_td else "",
        evening_expectations=evening_expectations,
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
            "evening_summary": evening_summary,
        },
        "evening_expectations": evening_expectations,
        "morning_pre": morning_pre,
        "auction_trend": auction,
        "checks": checks,
        "open_market": open_market,
        "health": health,
        "prompt": {
            "priority_instructions": (
                "【报告类型】开盘核对卡 | 【数据】昨晚结构化预期(expectations)+推送摘要+9:15素材+竞价 | "
                "【目标】9:30起前30分钟纪律；对照 [昨晚结构化预期] 核对，无 9:15 新证据勿推翻昨晚结论\n"
                "【我的】【想买的】推送块须逐只覆盖 tier0 列表每一只，不可遗漏。\n"
                "素材=refresh 且列有新素材标题时，正文须引用该标题，禁止写「无新公告/资讯」。\n"
                "我的/想买的：短评2-4句；highlight升格短评；其余默认一句。\n"
                "正文禁止（我的）（想买的）等分组前缀；禁止 verdict 行。"
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
