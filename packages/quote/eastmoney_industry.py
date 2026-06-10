"""东方财富行业查询（AkShare，供 industry_cache 使用）。"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FuturesTimeoutError
from typing import Any, Callable, TypeVar

from core.config import feeds_cfg, normalize_code

T = TypeVar("T")
_DEFAULT_AKSHARE_TIMEOUT_SEC = 45.0


def _akshare_timeout_sec() -> float:
    cfg = feeds_cfg()
    try:
        return max(5.0, float(cfg.get("akshare_timeout_sec") or _DEFAULT_AKSHARE_TIMEOUT_SEC))
    except (TypeError, ValueError):
        return _DEFAULT_AKSHARE_TIMEOUT_SEC


def call_akshare(fn: Callable[..., T], /, *args: Any, **kwargs: Any) -> T | None:
    timeout = _akshare_timeout_sec()
    with ThreadPoolExecutor(max_workers=1) as pool:
        fut = pool.submit(fn, *args, **kwargs)
        try:
            return fut.result(timeout=timeout)
        except FuturesTimeoutError:
            return None


def get_industry(code: str) -> str:
    c = normalize_code(code)
    try:
        import akshare as ak

        df = call_akshare(ak.stock_individual_info_em, symbol=c)
        if df is None or df.empty:
            return ""
        item_col = "item" if "item" in df.columns else df.columns[0]
        val_col = "value" if "value" in df.columns else df.columns[1]
        row = df[df[item_col].astype(str) == "行业"]
        if not row.empty:
            return str(row.iloc[0][val_col]).strip()
    except Exception:
        pass
    return ""
