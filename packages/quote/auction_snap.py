from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from core.config import normalize_code, quote_cfg
from quote.tencent import fetch_quotes
from quote.ths import fetch_quote_batch
from watchlist.loader import StockItem

_CN_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class AuctionSnap:
    code: str
    name: str
    group: str
    price: float | None = None
    pre_close: float | None = None
    open: float | None = None
    open_gap_pct: float | None = None
    pct_chg: float | None = None
    amount_yi: float | None = None
    snapshot_at: str = ""
    warnings: list[str] = field(default_factory=list)


def open_gap_pct(open_px: float | None, pre_close: float | None) -> float | None:
    if open_px is None or pre_close is None or pre_close <= 0:
        return None
    return round((open_px / pre_close - 1) * 100, 2)


def _field(ths: dict | None, tx: dict | None, key: str):
    if ths and ths.get(key) is not None:
        return ths.get(key)
    if tx and tx.get(key) is not None:
        return tx.get(key)
    return None


def _pick_name(code: str, ths_name, tx_name, *, fallback: str) -> str:
    for n in (ths_name, tx_name, fallback, code):
        s = str(n or "").strip()
        if s:
            return s
    return code


def _merge_one(stock: StockItem, ths: dict | None, tx: dict | None) -> AuctionSnap:
    if not ths and not tx:
        return AuctionSnap(
            code=stock.code,
            name=stock.name,
            group=stock.group,
            warnings=["行情双源均不可用"],
        )
    row = AuctionSnap(
        code=stock.code,
        name=_pick_name(stock.code, (ths or {}).get("name"), (tx or {}).get("name"), fallback=stock.name),
        group=stock.group,
        price=_field(ths, tx, "price"),
        pre_close=_field(ths, tx, "pre_close"),
        open=_field(ths, tx, "open"),
        pct_chg=_field(ths, tx, "pct_chg"),
        amount_yi=_field(ths, tx, "amount_yi"),
        snapshot_at=datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S"),
    )
    if row.pre_close is None and row.price is not None and row.pct_chg is not None and row.pct_chg != -100:
        row.pre_close = round(row.price / (1 + row.pct_chg / 100), 3)
    gap_px = row.open if row.open is not None else row.price
    row.open_gap_pct = open_gap_pct(gap_px, row.pre_close)
    return row


def build_auction_snapshots(stocks: list[StockItem]) -> list[AuctionSnap]:
    if not stocks:
        return []
    codes = list({normalize_code(s.code) for s in stocks})
    ths_map = fetch_quote_batch(codes) if quote_cfg().get("primary", "ths") != "tencent" else {}
    tx_map = fetch_quotes(codes) if quote_cfg().get("secondary", "tencent") else {}
    if quote_cfg().get("primary") == "tencent":
        ths_map, tx_map = tx_map, {}
    return [_merge_one(s, ths_map.get(normalize_code(s.code)), tx_map.get(normalize_code(s.code))) for s in stocks]


def snap_to_dict(s: AuctionSnap, *, is_final: bool = False) -> dict:
    trade_px = s.open if (is_final and s.open is not None) else (s.price if s.price is not None else s.open)
    gap = open_gap_pct(trade_px, s.pre_close) if trade_px is not None else s.open_gap_pct
    return {
        "code": s.code,
        "name": s.name,
        "group": s.group,
        "price": s.price,
        "pre_close": s.pre_close,
        "open": s.open,
        "trade_px": trade_px,
        "open_gap_pct": gap,
        "pct_chg": s.pct_chg,
        "amount_yi": s.amount_yi,
        "snapshot_at": s.snapshot_at,
        "warnings": list(s.warnings),
    }
