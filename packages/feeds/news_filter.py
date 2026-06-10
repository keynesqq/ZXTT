"""资讯标题与股票代码/名称的相关性校验。"""
from __future__ import annotations

import re

from core.config import normalize_code

_SUFFIXES = ("股份有限公司", "有限公司", "股份")


def _name_variants(name: str) -> list[str]:
    nm = (name or "").strip().replace(" ", "")
    if not nm:
        return []
    out = [nm]
    for suffix in _SUFFIXES:
        if nm.endswith(suffix) and len(nm) > len(suffix) + 1:
            short = nm[: -len(suffix)]
            if len(short) >= 2:
                out.append(short)
    seen: set[str] = set()
    ordered: list[str] = []
    for v in sorted(out, key=len, reverse=True):
        if v not in seen:
            seen.add(v)
            ordered.append(v)
    return ordered


def news_matches_stock(title: str, code: str, name: str = "") -> bool:
    """标题是否明确指向该股票（过滤全市场快讯误挂）。"""
    text = (title or "").replace(" ", "")
    if not text:
        return False

    c = normalize_code(code)
    code_patterns = (
        c,
        f"{c}.SZ",
        f"{c}.SH",
        f"{c}.BJ",
        f"({c}",
        f"（{c}",
        f"{c}）",
        f"{c})",
    )
    if any(p in text for p in code_patterns):
        return True

    for variant in _name_variants(name):
        if variant in text:
            return True

    return False


def filter_news_rows(rows: list[dict], code: str, name: str) -> list[dict]:
    return [r for r in rows if news_matches_stock(r.get("title", ""), code, name)]
