"""全量行情快照：同花顺主源 + 腾讯辅源 + 校验黄标。"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from zoneinfo import ZoneInfo

from collect.manifest import track_source
from core.config import normalize_code, quote_cfg
from core.trading_calendar import is_trading_day, market_data_date
from quote.industry_cache import batch_industries
from quote.stock_meta import (
    infer_intraday_shape,
    infer_limit_status,
    is_st_stock,
    limit_pct_for,
    open_gap_pct,
    stock_board,
)
from quote.stock_names import pick_name
from quote.tencent import fetch_quotes as fetch_tencent_quotes
from quote.ths import fetch_metrics_batch
from watchlist.ths_blocks import StockItem
from watchlist.loader import load_stocks

_CN_TZ = ZoneInfo("Asia/Shanghai")


@dataclass
class SnapshotRow:
    code: str
    name: str
    group: str
    block_id: str
    price: float | None = None
    pre_close: float | None = None
    open: float | None = None
    high: float | None = None
    low: float | None = None
    open_gap_pct: float | None = None
    pct_chg: float | None = None
    amplitude: float | None = None
    turnover: float | None = None
    amount_yi: float | None = None
    amount_avg_5d_yi: float | None = None
    amount_ratio: float | None = None
    pe: float | None = None
    pb: float | None = None
    total_mv_yi: float | None = None
    float_mv_yi: float | None = None
    pct_5d: float | None = None
    pct_20d: float | None = None
    pct_60d: float | None = None
    pct_ytd: float | None = None
    ma5: float | None = None
    ma20: float | None = None
    ma60: float | None = None
    ma5_dist: float | None = None
    ma20_dist: float | None = None
    ma60_dist: float | None = None
    industry: str = ""
    board: str = ""
    is_st: bool = False
    limit_pct: float | None = None
    limit_status: str = ""
    consecutive_boards: int | None = None
    intraday_shape: str = ""
    snapshot_at: str = ""
    quote_fetched_at: str = ""
    warnings: list[str] = field(default_factory=list)
    data_missing: bool = False


def _verify_tolerance() -> tuple[float, float]:
    tol = quote_cfg().get("verify_tolerance") or {}
    price_pct = float(tol.get("price_pct", 0.005))
    pct_chg = float(tol.get("pct_chg", 0.05))
    return price_pct, pct_chg


def _infer_trading_session(now: datetime) -> str:
    if now.tzinfo is None:
        now = now.replace(tzinfo=_CN_TZ)
    else:
        now = now.astimezone(_CN_TZ)
    if now.weekday() >= 5:
        return "非交易时段（周末）"
    t = now.hour * 60 + now.minute
    if t < 9 * 60 + 15:
        return "盘前（竞价前）"
    if t < 9 * 60 + 30:
        return "盘前（竞价）"
    if t < 11 * 60 + 30:
        return "上午盘中"
    if t < 13 * 60:
        return "午间休市"
    if t < 15 * 60:
        return "下午盘中"
    return "盘后"


def _verify_mode(now: datetime | None = None) -> str:
    """strict=双源数值校验；auxiliary=连续竞价盘中次源仅辅（不比现价/涨跌幅）。"""
    dt = now or datetime.now(_CN_TZ)
    if is_trading_day(dt.date()) and _infer_trading_session(dt) in ("上午盘中", "下午盘中"):
        return "auxiliary"
    return "strict"


def _field(ths: dict | None, tx: dict | None, key: str):
    if ths and ths.get(key) is not None:
        return ths.get(key)
    if tx and tx.get(key) is not None:
        return tx.get(key)
    return None


def _verify_row(ths: dict | None, tx: dict | None, verify: bool) -> list[str]:
    warnings: list[str] = []
    if not verify:
        return warnings
    if not ths and not tx:
        return warnings
    if _verify_mode() == "auxiliary":
        if not ths and tx:
            warnings.append("同花顺不可用，展示数据来自腾讯")
        return warnings
    if not ths and tx:
        warnings.append("同花顺不可用，展示数据来自腾讯")
        return warnings
    if ths and not tx:
        warnings.append("腾讯校验不可用，仅展示同花顺数据")
        return warnings

    price_pct_tol, pct_tol = _verify_tolerance()
    t_name = str(ths.get("name") or "").strip()
    x_name = str(tx.get("name") or "").strip()
    if t_name and x_name and t_name != x_name:
        warnings.append(f"名称不一致：同花顺「{t_name}」/ 腾讯「{x_name}」")

    t_price = ths.get("price")
    x_price = tx.get("price")
    if t_price is not None and x_price is not None and t_price > 0:
        diff = abs(t_price - x_price) / t_price
        if diff > price_pct_tol:
            warnings.append(f"现价偏差 {diff * 100:.2f}%：同花顺 {t_price} / 腾讯 {x_price}")

    t_pct = ths.get("pct_chg")
    x_pct = tx.get("pct_chg")
    if t_pct is not None and x_pct is not None:
        if abs(t_pct - x_pct) > pct_tol:
            warnings.append(f"涨跌幅不一致：同花顺 {t_pct:+.2f}% / 腾讯 {x_pct:+.2f}%")
    return warnings


def _enrich_row(
    row: SnapshotRow,
    *,
    limit_meta: dict[str, dict] | None = None,
    industry_map: dict[str, str] | None = None,
) -> SnapshotRow:
    code = normalize_code(row.code)
    meta = (limit_meta or {}).get(code) or {}
    name = row.name or code

    row.board = stock_board(code)
    row.is_st = is_st_stock(name)
    row.limit_pct = limit_pct_for(board=row.board, is_st=row.is_st)

    if not row.pre_close and row.price is not None and row.pct_chg is not None and row.pct_chg != -100:
        row.pre_close = round(row.price / (1 + row.pct_chg / 100), 3)

    if row.open_gap_pct is None:
        row.open_gap_pct = open_gap_pct(row.open, row.pre_close)

    in_pool = bool(meta.get("in_limit_up_pool"))
    broken = int(meta.get("broken_count") or 0)
    row.limit_status = infer_limit_status(
        row.pct_chg,
        row.limit_pct or 10.0,
        in_limit_up_pool=in_pool,
        broken_count=broken,
    )
    lb = meta.get("consecutive_boards")
    if lb is not None:
        try:
            row.consecutive_boards = int(lb)
        except (TypeError, ValueError):
            row.consecutive_boards = None
    elif row.limit_status == "涨停" and in_pool:
        row.consecutive_boards = 1

    ind = (industry_map or {}).get(code) or meta.get("industry") or ""
    row.industry = str(ind).strip()

    row.intraday_shape = infer_intraday_shape(row.open, row.high, row.low, row.price, row.pre_close)
    if row.snapshot_at and not row.quote_fetched_at:
        row.quote_fetched_at = row.snapshot_at
    return row


def _merge_one(stock: StockItem, ths: dict | None, tx: dict | None) -> SnapshotRow:
    verify = quote_cfg().get("verify", True)
    warnings = _verify_row(ths, tx, verify)

    if not ths and not tx:
        return SnapshotRow(
            code=stock.code,
            name=stock.name,
            group=stock.group,
            block_id=stock.block_id,
            data_missing=True,
            warnings=["行情双源均不可用"],
        )

    row = SnapshotRow(
        code=stock.code,
        name=pick_name(
            stock.code,
            (ths or {}).get("name"),
            (tx or {}).get("name"),
            fallback=stock.name,
        ),
        group=stock.group,
        block_id=stock.block_id,
        price=_field(ths, tx, "price"),
        pre_close=_field(ths, tx, "pre_close"),
        open=_field(ths, tx, "open"),
        high=_field(ths, tx, "high"),
        low=_field(ths, tx, "low"),
        pct_chg=_field(ths, tx, "pct_chg"),
        amplitude=_field(ths, tx, "amplitude"),
        turnover=_field(ths, tx, "turnover"),
        amount_yi=_field(ths, tx, "amount_yi"),
        amount_avg_5d_yi=(ths or {}).get("amount_avg_5d_yi"),
        amount_ratio=(ths or {}).get("amount_ratio"),
        pe=_field(ths, tx, "pe"),
        pb=_field(ths, tx, "pb"),
        total_mv_yi=_field(ths, tx, "total_mv_yi"),
        float_mv_yi=_field(ths, tx, "float_mv_yi"),
        pct_5d=(ths or {}).get("pct_5d"),
        pct_20d=(ths or {}).get("pct_20d"),
        pct_60d=(ths or {}).get("pct_60d"),
        pct_ytd=(ths or {}).get("pct_ytd"),
        ma5=(ths or {}).get("ma5"),
        ma20=(ths or {}).get("ma20"),
        ma60=(ths or {}).get("ma60"),
        ma5_dist=(ths or {}).get("ma5_dist"),
        ma20_dist=(ths or {}).get("ma20_dist"),
        ma60_dist=(ths or {}).get("ma60_dist"),
        warnings=warnings,
    )
    return row


def build_placeholder_snapshots(stocks: list[StockItem]) -> list[SnapshotRow]:
    return [
        SnapshotRow(code=s.code, name=s.name or s.code, group=s.group, block_id=s.block_id)
        for s in stocks
    ]


def _build_snapshot_rows(
    stocks: list[StockItem],
    *,
    on_date: date,
    fetch_industry: bool,
    rec: dict | None = None,
) -> list[SnapshotRow]:
    trade = market_data_date(on_date)
    unique_codes = list({normalize_code(s.code) for s in stocks})
    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=2) as pool:
        fut_ths = pool.submit(fetch_metrics_batch, unique_codes)
        fut_tx = pool.submit(fetch_tencent_quotes, unique_codes)
        ths_map = fut_ths.result()
        tx_map = fut_tx.result()

    try:
        from market.sentiment import load_limit_meta_map

        limit_meta = load_limit_meta_map(trade)
    except Exception:
        limit_meta = {}

    try:
        industry_map = batch_industries(unique_codes, fetch_missing=fetch_industry)
    except Exception:
        industry_map = {}

    rows = [
        _enrich_row(
            _merge_one(s, ths_map.get(normalize_code(s.code)), tx_map.get(normalize_code(s.code))),
            limit_meta=limit_meta,
            industry_map=industry_map,
        )
        for s in stocks
    ]
    batch_ts = datetime.now(_CN_TZ).strftime("%Y-%m-%d %H:%M:%S")
    for row in rows:
        row.snapshot_at = batch_ts
        row.quote_fetched_at = batch_ts
    if rec is not None:
        rec["row_count"] = len(rows)
        rec["code_count"] = len(unique_codes)
        rec["verify_warn_rows"] = sum(1 for r in rows if r.warnings)
        rec["both_down_rows"] = sum(1 for r in rows if any("双源均不可用" in w for w in r.warnings))
    return rows


def build_snapshots(
    stocks: list[StockItem] | None = None,
    *,
    on_date: date | None = None,
    fetch_industry: bool = True,
    record_manifest: bool = True,
) -> list[SnapshotRow]:
    stocks = stocks or load_stocks()
    if not stocks:
        return []
    cal = on_date or date.today()
    if not record_manifest:
        return _build_snapshot_rows(stocks, on_date=cal, fetch_industry=fetch_industry)
    with track_source(market_data_date(cal), "snapshot", calendar_date=cal) as rec:
        return _build_snapshot_rows(stocks, on_date=cal, fetch_industry=fetch_industry, rec=rec)


def snapshot_row_dict(r: SnapshotRow, *, quotes_pending: bool = False, pre_open: bool = False) -> dict:
    out = {
        "group": r.group,
        "code": r.code,
        "name": r.name,
        "industry": r.industry,
        "board": r.board,
        "is_st": r.is_st,
        "price": r.price,
        "pre_close": r.pre_close,
        "open": r.open,
        "high": r.high,
        "low": r.low,
        "open_gap_pct": r.open_gap_pct,
        "pct_chg": r.pct_chg,
        "limit_pct": r.limit_pct,
        "limit_status": r.limit_status,
        "consecutive_boards": r.consecutive_boards,
        "amplitude": r.amplitude,
        "turnover": r.turnover,
        "amount_yi": r.amount_yi,
        "amount_avg_5d_yi": r.amount_avg_5d_yi,
        "amount_ratio": r.amount_ratio,
        "pct_5d": r.pct_5d,
        "pct_20d": r.pct_20d,
        "pct_60d": r.pct_60d,
        "pct_ytd": r.pct_ytd,
        "ma5": r.ma5,
        "ma20": r.ma20,
        "ma60": r.ma60,
        "ma5_dist": r.ma5_dist,
        "ma20_dist": r.ma20_dist,
        "ma60_dist": r.ma60_dist,
        "intraday_shape": r.intraday_shape,
        "pe": r.pe,
        "pb": r.pb,
        "total_mv_yi": r.total_mv_yi,
        "float_mv_yi": r.float_mv_yi,
        "snapshot_at": r.snapshot_at,
        "quote_fetched_at": r.quote_fetched_at,
        "warnings": r.warnings,
        "data_missing": r.data_missing,
    }
    if pre_open:
        out["pre_open"] = True
        if out.get("amount_ratio") is not None:
            out["amount_ratio_stale"] = True
    if quotes_pending:
        out["quotes_pending"] = True
    return out
