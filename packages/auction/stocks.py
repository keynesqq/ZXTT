"""竞价模块：解析用户传入的个股列表（同股只保留一条）。"""
from __future__ import annotations

from datetime import date

from core.config import auction_cfg, normalize_code
from morning.codes import codes_from_quote
from watchlist.ths_blocks import StockItem


def resolve_auction_codes(
    cli_codes: list[str] | None = None,
    *,
    on_date: date | None = None,
) -> list[str]:
    """CLI --codes 优先；否则 quote_query/自选（31 只）；最后 config auction.codes。"""
    if cli_codes:
        out: list[str] = []
        seen: set[str] = set()
        for raw in cli_codes:
            code = normalize_code(str(raw).strip())
            if code and code not in seen:
                seen.add(code)
                out.append(code)
        return out
    cal = on_date or date.today()
    from_quote, _ = codes_from_quote(cal)
    if from_quote:
        return from_quote
    raw = auction_cfg().get("codes") or []
    out: list[str] = []
    seen: set[str] = set()
    for item in raw:
        code = normalize_code(str(item).strip())
        if code and code not in seen:
            seen.add(code)
            out.append(code)
    return out


def resolve_auction_stocks(codes: list[str]) -> list[StockItem]:
    """按用户提供的代码列表建 StockItem；不读自选板块。"""
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in codes:
        code = normalize_code(str(raw).strip())
        if not code or code in seen:
            continue
        seen.add(code)
        normalized.append(code)
    return [StockItem(code=c, name=c, group="", block_id="") for c in normalized]
