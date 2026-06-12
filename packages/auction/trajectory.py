from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from auction.series import load_auction_series
from core.paths import DATA_DIR
from core.trading_calendar import today_cn
from quote.auction_snap import open_gap_pct
from quote.stock_meta import infer_limit_status, is_st_stock, limit_pct_for, stock_board

SHAPE_LABELS = (
    "数据不足",
    "震荡",
    "一路抬升",
    "一路走弱",
    "尾盘上翘",
    "尾盘下压",
    "冲高回落",
    "探底回升",
    "偏强上行",
    "偏弱下行",
)

_AFTER_920 = "09:20:00"


def _trend_path(on_date: date) -> Path:
    return DATA_DIR / f"auction_trend_{on_date.isoformat()}.json"


def _time_part(captured_at: str) -> str:
    s = str(captured_at or "").strip()
    if " " in s:
        return s.split(" ", 1)[1]
    return s


def _is_after_920(captured_at: str) -> bool:
    return _time_part(captured_at) >= _AFTER_920


def _trade_px(row: dict, *, is_final: bool) -> float | None:
    if is_final:
        open_px = row.get("open")
        if open_px is not None:
            return float(open_px)
    for key in ("trade_px", "price", "open"):
        val = row.get(key)
        if val is not None:
            return float(val)
    return None


def _gap_at(row: dict, *, is_final: bool) -> float | None:
    g = row.get("open_gap_pct")
    if g is not None:
        return float(g)
    return open_gap_pct(_trade_px(row, is_final=is_final), row.get("pre_close"))


def _classify_shape(gaps: list[float]) -> str:
    if len(gaps) < 2:
        return "数据不足"
    start, end = gaps[0], gaps[-1]
    delta = round(end - start, 2)
    high = max(gaps)
    low = min(gaps)
    span = round(high - low, 2)
    if span < 0.3:
        return "震荡"
    if len(gaps) >= 3:
        late = gaps[-1] - gaps[-2]
        if late >= 0.3 and delta > 0:
            return "尾盘上翘"
        if late <= -0.3 and delta < 0:
            return "尾盘下压"
    if all(gaps[i] <= gaps[i + 1] + 0.05 for i in range(len(gaps) - 1)) and delta >= 0.3:
        return "一路抬升"
    if all(gaps[i] + 0.05 >= gaps[i + 1] for i in range(len(gaps) - 1)) and delta <= -0.3:
        return "一路走弱"
    peak_idx = max(i for i, g in enumerate(gaps) if g == high)
    if 0 < peak_idx < len(gaps) - 1 and end < high - 0.5:
        return "冲高回落"
    trough_idx = max(i for i, g in enumerate(gaps) if g == low)
    if 0 < trough_idx < len(gaps) - 1 and end > low + 0.5:
        return "探底回升"
    if delta >= 0.3:
        return "偏强上行"
    if delta <= -0.3:
        return "偏弱下行"
    return "震荡"


def classify_value_path(values: list[float]) -> str:
    """对涨跌幅/缺口序列做形态分类（规则同竞价 gap_path）。"""
    return _classify_shape(values)


def _amount_deltas(amounts: list[float]) -> list[float]:
    if len(amounts) < 2:
        return []
    return [round(amounts[i] - amounts[i - 1], 4) for i in range(1, len(amounts))]


def _limit_status_for_row(row: dict) -> str:
    name = str(row.get("name") or "")
    code = str(row.get("code") or "")
    board = stock_board(code)
    limit_pct = limit_pct_for(board=board, is_st=is_st_stock(name))
    pct = row.get("pct_chg")
    try:
        pct_f = float(pct) if pct is not None else None
    except (TypeError, ValueError):
        pct_f = None
    return infer_limit_status(pct_f, limit_pct)


def build_auction_trends(series_points: list[dict]) -> list[dict]:
    if not series_points:
        return []
    keyed: dict[str, list[tuple[str, float | None, float | None, bool, dict]]] = {}
    amounts_keyed: dict[str, list[float]] = {}
    meta: dict[str, dict] = {}
    for point in series_points:
        point_ts = str(point.get("captured_at") or "")
        is_final = bool(point.get("is_final"))
        rows = point.get("rows") or []
        if not isinstance(rows, list):
            continue
        for row in rows:
            if not isinstance(row, dict):
                continue
            code = str(row.get("code") or "")
            if not code:
                continue
            captured_at = str(row.get("snapshot_at") or point_ts)
            if code not in meta:
                meta[code] = {
                    "code": code,
                    "name": row.get("name") or code,
                    "group": str(row.get("group") or ""),
                }
            keyed.setdefault(code, []).append(
                (
                    captured_at,
                    _trade_px(row, is_final=is_final),
                    _gap_at(row, is_final=is_final),
                    is_final,
                    row,
                )
            )
            if row.get("amount_yi") is not None:
                amounts_keyed.setdefault(code, []).append(float(row["amount_yi"]))
    trends: list[dict] = []
    for key, samples in keyed.items():
        gaps = [g for _, _, g, _, _ in samples if g is not None]
        gaps_after = [g for ts, _, g, _, _ in samples if g is not None and _is_after_920(ts)]
        prices = [p for _, p, _, _, _ in samples if p is not None]
        amounts = amounts_keyed.get(key, [])
        deltas = _amount_deltas(amounts)
        start_gap = gaps[0] if gaps else None
        end_gap = gaps[-1] if gaps else None
        gap_delta = round(end_gap - start_gap, 2) if start_gap is not None and end_gap is not None else None
        final_row = samples[-1][4] if samples else {}
        trends.append(
            {
                **meta[key],
                "point_count": len(samples),
                "captured_start": samples[0][0] if samples else "",
                "captured_end": samples[-1][0] if samples else "",
                "price_path": prices,
                "gap_path": gaps,
                "start_gap": start_gap,
                "end_gap": end_gap,
                "gap_delta": gap_delta,
                "high_gap": max(gaps) if gaps else None,
                "low_gap": min(gaps) if gaps else None,
                "amount_start": amounts[0] if amounts else None,
                "amount_end": amounts[-1] if amounts else None,
                "amount_delta_path": deltas,
                "amount_delta_total": round(amounts[-1] - amounts[0], 4) if len(amounts) >= 2 else None,
                "shape": _classify_shape(gaps),
                "shape_after_920": _classify_shape(gaps_after),
                "limit_status": _limit_status_for_row(final_row),
            }
        )
    trends.sort(key=lambda r: r.get("code") or "")
    return trends


def write_auction_trend(*, on_date: date | None = None, series_points: list[dict] | None = None) -> Path:
    day = on_date or today_cn()
    points = series_points if series_points is not None else load_auction_series(on_date=day)
    trends = build_auction_trends(points)
    path = _trend_path(day)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 2,
        "calendar_date": day.isoformat(),
        "point_count": len(points),
        "stocks": trends,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path
