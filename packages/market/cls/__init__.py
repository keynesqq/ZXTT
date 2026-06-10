"""财联社采集模块：A 层看盘 API + B 层五篇固定长文。"""
from __future__ import annotations

from market.cls.collect import collect_cls
from market.cls.daily_articles import (
    ARTICLE_SLOTS,
    articles_publish_ready,
    collect_cls_daily_articles,
    format_cls_articles_prompt,
    load_cls_daily_articles,
)
from market.cls.finance import (
    collect_cls_finance,
    fetch_cls_emotion,
    fetch_cls_mainline,
    fetch_cls_wind,
    format_cls_prompt,
    load_cls_finance,
)

__all__ = [
    "ARTICLE_SLOTS",
    "articles_publish_ready",
    "collect_cls",
    "collect_cls_daily_articles",
    "collect_cls_finance",
    "fetch_cls_emotion",
    "fetch_cls_mainline",
    "fetch_cls_wind",
    "format_cls_articles_prompt",
    "format_cls_prompt",
    "load_cls_finance",
    "load_cls_daily_articles",
]
