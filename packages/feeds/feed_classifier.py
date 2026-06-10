"""资讯标题/来源分类为 资讯 或 观点。"""
from __future__ import annotations

import re

from core.config import feeds_cfg

DEFAULT_OPINION_SOURCES = ["证券", "研究所", "期货", "基金", "智库", "研究院", "资本"]
DEFAULT_OPINION_TITLES = [
    "策略", "周报", "观点", "点评", "深度", "金股", "看好", "建议",
    "维持", "评级", "目标价", "首推", "推荐", "行业研究",
]


def classify_news(title: str, source: str, *, opinion_cfg: dict | None = None) -> str:
    if opinion_cfg is None:
        from core.config import news_cfg

        cfg = news_cfg().get("opinion") or feeds_cfg().get("opinion") or {}
    else:
        cfg = opinion_cfg
    source_keys = cfg.get("source_keywords") or DEFAULT_OPINION_SOURCES
    title_keys = cfg.get("title_keywords") or DEFAULT_OPINION_TITLES
    src, ttl = source or "", title or ""
    for kw in source_keys:
        if kw in src:
            return "观点"
    for kw in title_keys:
        if kw in ttl:
            return "观点"
    if re.search(r"(买入|增持|减持|卖出|中性).*评级", ttl):
        return "观点"
    return "资讯"
