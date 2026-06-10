"""财联社采集编排：A 层看盘 API + 可选 B 层五篇固定长文。"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from core.io import atomic_write_text
from core.paths import ROOT
from market.cls.daily_articles import collect_cls_daily_articles
from market.cls.finance import collect_cls_finance


def _cls_finance_path(for_date: date) -> Any:
    root = ROOT / "data" / "cls_finance"
    root.mkdir(parents=True, exist_ok=True)
    return root / f"{for_date.isoformat()}.json"


def collect_cls(
    for_date: date | None = None,
    *,
    include_articles: bool = False,
    force: bool = False,
    calendar_date: date | None = None,
    fetch_content: bool = True,
    save_layer_a: bool = True,
) -> dict[str, Any]:
    """采集财联社 A 层；`include_articles=True` 时追加 B 层五篇长文。"""
    d = for_date or date.today()
    cal = calendar_date or d

    layer_a = collect_cls_finance(for_date=d, calendar_date=cal)
    if save_layer_a:
        atomic_write_text(
            _cls_finance_path(d),
            json.dumps(layer_a, ensure_ascii=False, indent=2),
        )

    out: dict[str, Any] = {
        "source": "cls.cn",
        "trade_date": d.isoformat(),
        "layer_a": layer_a,
        "layer_a_ok": not layer_a.get("warnings"),
        "market_heat": layer_a.get("market_heat"),
        "wind_count": len(layer_a.get("wind_plates") or []),
        "mainline_count": len((layer_a.get("mainline") or {}).get("lines") or []),
    }

    if include_articles:
        layer_b = collect_cls_daily_articles(
            for_date=d,
            force=force,
            calendar_date=cal,
            fetch_content=fetch_content,
        )
        out["layer_b"] = layer_b
        out["articles_found"] = int(layer_b.get("found_count") or 0)
        out["articles_expected"] = int(layer_b.get("expected_count") or 0)
        out["articles_ok"] = out["articles_found"] >= out["articles_expected"] and not layer_b.get(
            "skipped"
        )

    warnings: list[str] = []
    warnings.extend(layer_a.get("warnings") or [])
    if include_articles:
        warnings.extend((out.get("layer_b") or {}).get("warnings") or [])
    if warnings:
        out["warnings"] = warnings

    return out
