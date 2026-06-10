"""股票名称解析：避免将代码误当作名称。"""
from __future__ import annotations

from core.config import normalize_code


def is_resolved_name(code: str, name: str | None) -> bool:
    c = normalize_code(code)
    n = str(name or "").strip()
    return bool(n) and n != c


def pick_name(code: str, *candidates: str | None, fallback: str | None = None) -> str:
    c = normalize_code(code)
    for cand in candidates:
        if is_resolved_name(c, cand):
            return str(cand).strip()
    fb = str(fallback or "").strip()
    if is_resolved_name(c, fb):
        return fb
    return c
