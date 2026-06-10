"""行业名称本地缓存（避免每次快照重复请求 AkShare）。"""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from core.config import legacy_config_path
from core.io import atomic_write_text
from core.paths import DATA_DIR
from quote.eastmoney_industry import get_industry

_CACHE_PATH = DATA_DIR / "industry_cache.json"


def _legacy_cache_path():
    legacy = legacy_config_path()
    if not legacy:
        return None
    path = legacy.parent / "data" / "industry_cache.json"
    return path if path.is_file() else None


def _read_cache_file(path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(data, dict):
        return {}
    return {str(k): str(v).strip() for k, v in data.items() if str(v or "").strip()}


def _load_cache() -> dict[str, str]:
    merged: dict[str, str] = {}
    legacy = _legacy_cache_path()
    if legacy:
        merged.update(_read_cache_file(legacy))
    if _CACHE_PATH.is_file():
        merged.update(_read_cache_file(_CACHE_PATH))
    return merged


def _save_cache(cache: dict[str, str]) -> None:
    atomic_write_text(_CACHE_PATH, json.dumps(cache, ensure_ascii=False, indent=2))


def batch_industries(codes: list[str], *, fetch_missing: bool = True) -> dict[str, str]:
    """返回 code -> 行业；缺失项按需拉取并写入缓存。"""
    cache = _load_cache()
    unique = list(dict.fromkeys(codes))
    missing = [c for c in unique if not str(cache.get(c) or "").strip()]

    if missing and fetch_missing:

        def _one(code: str) -> tuple[str, str]:
            return code, get_industry(code)

        with ThreadPoolExecutor(max_workers=min(4, len(missing))) as pool:
            for code, industry in pool.map(_one, missing):
                if industry:
                    cache[code] = industry
        _save_cache(cache)

    return {c: str(cache.get(c) or "").strip() for c in unique}
