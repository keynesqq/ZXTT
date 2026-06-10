"""快照 JSON 落盘与加载（ZXModular 路径：data/snapshot_{date}.json）。"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from core.config import normalize_code
from core.io import atomic_write_text
from core.paths import DATA_DIR
from quote.snapshot.build import SnapshotRow, snapshot_row_dict
from watchlist.loader import load_stocks, watchlist_group_names
from watchlist.ths_blocks import StockItem

SNAPSHOT_SCHEMA_VERSION = 2

SNAPSHOT_ROW_DEFAULTS: dict = {
    "group": "",
    "code": "",
    "name": "",
    "industry": "",
    "board": "",
    "is_st": False,
    "price": None,
    "pre_close": None,
    "open": None,
    "high": None,
    "low": None,
    "open_gap_pct": None,
    "pct_chg": None,
    "limit_pct": None,
    "limit_status": "",
    "consecutive_boards": None,
    "amplitude": None,
    "turnover": None,
    "amount_yi": None,
    "amount_avg_5d_yi": None,
    "amount_ratio": None,
    "pct_5d": None,
    "pct_20d": None,
    "pct_60d": None,
    "pct_ytd": None,
    "ma5": None,
    "ma20": None,
    "ma60": None,
    "ma5_dist": None,
    "ma20_dist": None,
    "ma60_dist": None,
    "intraday_shape": "",
    "pe": None,
    "pb": None,
    "total_mv_yi": None,
    "float_mv_yi": None,
    "snapshot_at": "",
    "warnings": [],
    "data_missing": False,
}


def snapshot_cache_path(on_date: date | None = None) -> Path:
    d = on_date or date.today()
    return DATA_DIR / f"snapshot_{d.isoformat()}.json"


def normalize_snapshot_row(row: dict) -> dict:
    out = dict(SNAPSHOT_ROW_DEFAULTS)
    for key, val in row.items():
        if key in SNAPSHOT_ROW_DEFAULTS:
            out[key] = val
        elif key == "quotes_pending":
            out[key] = bool(val)
    if not isinstance(out.get("warnings"), list):
        out["warnings"] = []
    return out


def normalize_snapshot_rows(rows: list[dict]) -> list[dict]:
    return [normalize_snapshot_row(r) for r in rows if isinstance(r, dict)]


def structure_from_stocks(stocks: list[StockItem]) -> dict:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for s in stocks:
        if s.group not in groups:
            groups[s.group] = []
            order.append(s.group)
        groups[s.group].append({"code": s.code, "name": s.name or s.code})
    return structure_from_group_map(groups, order)


def structure_from_row_dicts(rows: list[dict], *, group_order: list[str] | None = None) -> dict:
    groups: dict[str, list[dict]] = {}
    order: list[str] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        g = str(row.get("group") or "").strip()
        code = str(row.get("code") or "").strip()
        if not g or not code:
            continue
        if g not in groups:
            groups[g] = []
            order.append(g)
        groups[g].append({"code": code, "name": str(row.get("name") or code).strip() or code})
    preferred = group_order if group_order is not None else watchlist_group_names()
    return structure_from_group_map(groups, order, preferred_order=preferred)


def structure_from_group_map(
    groups: dict[str, list[dict]],
    discovery_order: list[str],
    *,
    preferred_order: list[str] | None = None,
) -> dict:
    preferred = preferred_order if preferred_order is not None else watchlist_group_names()
    ordered: list[str] = [g for g in preferred if g in groups]
    for g in discovery_order:
        if g in groups and g not in ordered:
            ordered.append(g)
    for g in groups:
        if g not in ordered:
            ordered.append(g)
    return {"groups": [{"name": name, "stocks": groups[name]} for name in ordered]}


def _read_snapshot_cache_path(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(data, dict):
        return None
    if int(data.get("schema_version") or 0) != SNAPSHOT_SCHEMA_VERSION:
        return None
    rows = data.get("rows")
    if not isinstance(rows, list) or not rows:
        return None
    return data


def load_snapshot_cache_file(*, on_date: date | None = None) -> dict | None:
    return _read_snapshot_cache_path(snapshot_cache_path(on_date))


def load_cached_snapshot_rows(*, on_date: date | None = None) -> list[dict] | None:
    data = load_snapshot_cache_file(on_date=on_date)
    if data is None:
        return None
    rows = data.get("rows")
    if not isinstance(rows, list):
        return None
    return normalize_snapshot_rows(rows)


def _row_merge_key(row: dict) -> tuple[str, str]:
    return (normalize_code(str(row.get("code") or "")), str(row.get("group") or ""))


def expand_stocks_by_codes(codes: list[str]) -> list[StockItem]:
    code_set = {normalize_code(c) for c in codes if normalize_code(c)}
    if not code_set:
        return []
    return [s for s in load_stocks() if normalize_code(s.code) in code_set]


def merge_snapshot_row_dicts(base: list[dict], updates: list[dict]) -> list[dict]:
    out = [normalize_snapshot_row(r) for r in base]
    index = {_row_merge_key(r): i for i, r in enumerate(out)}
    for raw in updates:
        u = normalize_snapshot_row(raw)
        key = _row_merge_key(u)
        u.pop("quotes_pending", None)
        if key in index:
            merged = dict(out[index[key]])
            for k, v in u.items():
                if k in SNAPSHOT_ROW_DEFAULTS:
                    merged[k] = v
            out[index[key]] = normalize_snapshot_row(merged)
        else:
            out.append(u)
    return out


def snapshot_rows_from_dicts(rows: list[dict]) -> list[SnapshotRow]:
    stock_map = {(normalize_code(s.code), s.group): s for s in load_stocks()}
    out: list[SnapshotRow] = []
    for d in normalize_snapshot_rows(rows):
        key = (normalize_code(str(d.get("code") or "")), str(d.get("group") or ""))
        stock = stock_map.get(key)
        out.append(
            SnapshotRow(
                code=key[0],
                name=str(d.get("name") or (stock.name if stock else key[0])),
                group=key[1],
                block_id=stock.block_id if stock else "",
                price=d.get("price"),
                pre_close=d.get("pre_close"),
                open=d.get("open"),
                high=d.get("high"),
                low=d.get("low"),
                open_gap_pct=d.get("open_gap_pct"),
                pct_chg=d.get("pct_chg"),
                amplitude=d.get("amplitude"),
                turnover=d.get("turnover"),
                amount_yi=d.get("amount_yi"),
                amount_avg_5d_yi=d.get("amount_avg_5d_yi"),
                amount_ratio=d.get("amount_ratio"),
                pe=d.get("pe"),
                pb=d.get("pb"),
                total_mv_yi=d.get("total_mv_yi"),
                float_mv_yi=d.get("float_mv_yi"),
                pct_5d=d.get("pct_5d"),
                pct_20d=d.get("pct_20d"),
                pct_60d=d.get("pct_60d"),
                pct_ytd=d.get("pct_ytd"),
                ma5=d.get("ma5"),
                ma20=d.get("ma20"),
                ma60=d.get("ma60"),
                ma5_dist=d.get("ma5_dist"),
                ma20_dist=d.get("ma20_dist"),
                ma60_dist=d.get("ma60_dist"),
                industry=str(d.get("industry") or ""),
                board=str(d.get("board") or ""),
                is_st=bool(d.get("is_st")),
                limit_pct=d.get("limit_pct"),
                limit_status=str(d.get("limit_status") or ""),
                consecutive_boards=d.get("consecutive_boards"),
                intraday_shape=str(d.get("intraday_shape") or ""),
                snapshot_at=str(d.get("snapshot_at") or ""),
                warnings=list(d.get("warnings") or []),
                data_missing=bool(d.get("data_missing")),
            )
        )
    return out


def write_snapshot_cache(
    rows: list[SnapshotRow],
    *,
    on_date: date | None = None,
    quotes_pending: bool = False,
    generated_at: str | None = None,
) -> Path:
    path = snapshot_cache_path(on_date)
    path.parent.mkdir(parents=True, exist_ok=True)
    if not generated_at:
        generated_at = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S")
    payload = {
        "schema_version": SNAPSHOT_SCHEMA_VERSION,
        "generated_at": generated_at,
        "quotes_pending": bool(quotes_pending),
        "rows": [snapshot_row_dict(r, quotes_pending=quotes_pending) for r in rows],
    }
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path
