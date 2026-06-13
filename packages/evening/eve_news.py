"""交易日前夜 · 休市期间资讯更新报告（管线待实现）。"""
from __future__ import annotations

from datetime import date
from typing import Any

from core.trading_calendar import should_run_eve_news


def run_eve_news_pipeline(
    *,
    on_date: date | None = None,
    force: bool = False,
) -> dict[str, Any]:
    cal = on_date or date.today()
    if not force and not should_run_eve_news(cal):
        return {"outcome": "skip", "reason": "not_eve_news_day", "calendar_date": cal.isoformat()}

    from report.hub import open_hub_for_scheduled_task

    open_hub_for_scheduled_task(cal, slot="eve_news")

    return {
        "outcome": "skip",
        "reason": "pipeline_not_implemented",
        "calendar_date": cal.isoformat(),
        "hint": "交易日前夜资讯更新报告：采集闭市增量、合并上一版晚间产出，待下一迭代实现",
    }


__all__ = ["run_eve_news_pipeline"]
