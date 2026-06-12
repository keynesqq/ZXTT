"""从 intraday 分钟序列生成午/晚报告用摘要。"""
from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

from auction.trajectory import classify_value_path
from core.config import normalize_code
from core.io import atomic_write_text
from core.paths import DATA_DIR
from core.trading_calendar import today_cn
from intraday.series import load_intraday_segment, load_intraday_series
from quote.stock_meta import infer_limit_status, is_st_stock, limit_pct_for, stock_board

SCHEMA_VERSION = 1
SEGMENTS = ("morning", "afternoon", "full")
EXPECTED_MORNING_POINTS = 121
EXPECTED_AFTERNOON_POINTS = 121


def digest_segment_complete(points: list[dict], *, segment: str) -> bool:
    if segment == "morning":
        expected = EXPECTED_MORNING_POINTS
    elif segment == "afternoon":
        expected = EXPECTED_AFTERNOON_POINTS
    else:
        return False
    if len(points) < expected:
        return False
    return bool(points[-1].get("is_final"))


def digest_path(on_date: date, segment: str) -> Path:
    if segment == "full":
        return DATA_DIR / f"intraday_digest_{on_date.isoformat()}_full.json"
    if segment in ("morning", "afternoon"):
        return DATA_DIR / f"intraday_digest_{on_date.isoformat()}_{segment}.json"
    raise ValueError(f"invalid segment: {segment}")


def load_intraday_digest(*, on_date: date | None = None, segment: str = "morning") -> dict[str, Any] | None:
    day = on_date or today_cn()
    path = digest_path(day, segment)
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(data, dict):
        return None
    if str(data.get("calendar_date") or "") != day.isoformat():
        return None
    if str(data.get("segment") or "") != segment:
        return None
    return data


def digest_payload_ok(payload: dict[str, Any] | None, *, segment: str) -> bool:
    if not payload:
        return False
    if str(payload.get("segment") or "") != segment:
        return False
    if not payload.get("is_complete"):
        return False
    point_count = int(payload.get("point_count") or 0)
    if segment == "morning":
        return point_count >= EXPECTED_MORNING_POINTS
    if segment == "afternoon":
        return point_count >= EXPECTED_AFTERNOON_POINTS
    if segment == "full":
        return point_count >= EXPECTED_MORNING_POINTS + EXPECTED_AFTERNOON_POINTS
    return False


def _load_auction_end_gaps(day: date) -> dict[str, float]:
    path = DATA_DIR / f"auction_trend_{day.isoformat()}.json"
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, float] = {}
    for row in data.get("stocks") or []:
        if not isinstance(row, dict):
            continue
        code = normalize_code(str(row.get("code") or ""))
        if not code:
            continue
        try:
            out[code] = float(row.get("end_gap"))
        except (TypeError, ValueError):
            continue
    return out


def _samples_by_code(points: list[dict]) -> dict[str, list[tuple[str, float | None, dict]]]:
    keyed: dict[str, list[tuple[str, float | None, dict]]] = {}
    for point in points:
        ts = str(point.get("captured_at") or "")
        for row in point.get("rows") or []:
            if not isinstance(row, dict):
                continue
            code = normalize_code(str(row.get("code") or ""))
            if not code:
                continue
            pct = row.get("pct_chg")
            try:
                pct_f = float(pct) if pct is not None else None
            except (TypeError, ValueError):
                pct_f = None
            keyed.setdefault(code, []).append((ts, pct_f, row))
    return keyed


def _limit_status(row: dict) -> str:
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


def _shape_detail(samples: list[tuple[str, float | None, dict]]) -> str:
    valid = [(ts, pct) for ts, pct, _ in samples if pct is not None]
    if len(valid) < 2:
        return ""
    peak_ts, peak_pct = max(valid, key=lambda item: item[1])
    end = valid[-1][1]
    peak_t = peak_ts[11:16] if len(peak_ts) >= 16 else peak_ts[-5:]
    return f"{peak_t}见顶{peak_pct:+.1f}%→收{end:+.1f}%"


def _stock_digest(
    code: str,
    samples: list[tuple[str, float | None, dict]],
    *,
    auction_end_gap: float | None,
) -> dict[str, Any]:
    pcts = [p for _, p, _ in samples if p is not None]
    meta_row = samples[-1][2] if samples else {}
    session_pct = pcts[-1] if pcts else None
    vs_gap = None
    if session_pct is not None and auction_end_gap is not None:
        vs_gap = round(session_pct - auction_end_gap, 2)
    high = max(pcts) if pcts else None
    low = min(pcts) if pcts else None
    return {
        "code": code,
        "name": meta_row.get("name") or code,
        "session_shape": classify_value_path(pcts) if len(pcts) >= 2 else "数据不足",
        "session_pct_chg": session_pct,
        "session_high_pct": high,
        "session_low_pct": low,
        "vs_auction_end_gap": vs_gap,
        "limit_status": _limit_status(meta_row),
        "shape_detail": _shape_detail(samples),
        "minute_point_count": len(samples),
    }


def _digest_from_points(
    points: list[dict],
    *,
    day: date,
    segment: str,
    is_complete: bool,
) -> dict[str, Any]:
    auction_gaps = _load_auction_end_gaps(day)
    keyed = _samples_by_code(points)
    stocks = [
        _stock_digest(code, samples, auction_end_gap=auction_gaps.get(code))
        for code, samples in sorted(keyed.items())
    ]
    return {
        "schema_version": SCHEMA_VERSION,
        "calendar_date": day.isoformat(),
        "segment": segment,
        "source": "intraday_watch",
        "point_count": len(points),
        "is_complete": is_complete,
        "stock_count": len(stocks),
        "stocks": stocks,
        "stocks_by_code": {s["code"]: s for s in stocks},
    }


def build_intraday_digest(*, on_date: date, segment: str) -> dict[str, Any]:
    day = on_date
    if segment == "morning":
        points = load_intraday_segment(on_date=day, segment="morning")
        complete = digest_segment_complete(points, segment="morning")
        return _digest_from_points(points, day=day, segment=segment, is_complete=complete)
    if segment == "afternoon":
        points = load_intraday_segment(on_date=day, segment="afternoon")
        complete = digest_segment_complete(points, segment="afternoon")
        return _digest_from_points(points, day=day, segment=segment, is_complete=complete)
    if segment == "full":
        morning = load_intraday_segment(on_date=day, segment="morning")
        afternoon = load_intraday_segment(on_date=day, segment="afternoon")
        merged = load_intraday_series(on_date=day)
        m_complete = digest_segment_complete(morning, segment="morning")
        a_complete = digest_segment_complete(afternoon, segment="afternoon")
        payload = _digest_from_points(
            merged,
            day=day,
            segment="full",
            is_complete=m_complete and a_complete,
        )
        m_keyed = _samples_by_code(morning)
        a_keyed = _samples_by_code(afternoon)
        auction_gaps = _load_auction_end_gaps(day)
        for stock in payload.get("stocks") or []:
            code = stock.get("code")
            if not code:
                continue
            m_samples = m_keyed.get(code) or []
            a_samples = a_keyed.get(code) or []
            m_pcts = [p for _, p, _ in m_samples if p is not None]
            a_pcts = [p for _, p, _ in a_samples if p is not None]
            if len(m_pcts) >= 2:
                stock["morning_shape"] = classify_value_path(m_pcts)
                stock["morning_pct_chg"] = m_pcts[-1]
                eg = auction_gaps.get(code)
                if eg is not None:
                    stock["vs_auction_end_gap"] = round(m_pcts[-1] - eg, 2)
            if len(a_pcts) >= 2:
                stock["afternoon_shape"] = classify_value_path(a_pcts)
                stock["afternoon_pct_chg"] = a_pcts[-1]
            close_pct = stock.get("session_pct_chg")
            eg = auction_gaps.get(code)
            if close_pct is not None and eg is not None:
                stock["vs_auction_end_gap_close"] = round(close_pct - eg, 2)
        payload["stocks_by_code"] = {s["code"]: s for s in payload.get("stocks") or []}
        return payload
    raise ValueError(f"invalid segment: {segment}")


def write_intraday_digest(*, on_date: date, segment: str) -> Path | None:
    if segment not in SEGMENTS:
        raise ValueError(f"invalid segment: {segment}")
    path = digest_path(on_date, segment)
    payload = build_intraday_digest(on_date=on_date, segment=segment)
    if not payload.get("stocks") or not payload.get("is_complete"):
        if path.is_file():
            path.unlink()
        return None
    path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))
    return path


def format_digest_prompt_line(digest: dict | None, *, slot: str = "morning") -> str:
    if not digest:
        return ""
    parts: list[str] = []
    if slot == "morning":
        shape = digest.get("session_shape") or ""
        if shape:
            parts.append(f"上午形态={shape}")
        vs = digest.get("vs_auction_end_gap")
        if vs is not None:
            parts.append(f"较竞价{vs:+.1f}pct")
        pct = digest.get("session_pct_chg")
        if pct is not None:
            parts.append(f"上午收{pct:+.1f}%")
        detail = digest.get("shape_detail") or ""
        if detail:
            parts.append(detail)
        return " | ".join(parts)
    shape = digest.get("session_shape") or ""
    if shape:
        parts.append(f"全天形态={shape}")
    ms = digest.get("morning_shape")
    if ms:
        parts.append(f"上午={ms}")
    af = digest.get("afternoon_shape")
    if af:
        parts.append(f"下午={af}")
    vs_close = digest.get("vs_auction_end_gap_close")
    if vs_close is not None:
        parts.append(f"竞价→收{vs_close:+.1f}pct")
    pct = digest.get("session_pct_chg")
    if pct is not None:
        parts.append(f"收{pct:+.1f}%")
    detail = digest.get("shape_detail") or ""
    if detail:
        parts.append(detail)
    return " | ".join(parts)


def intraday_missing_label(*, slot: str = "morning", digest_ok: bool) -> str:
    if digest_ok:
        return "该股未纳入监控"
    return "全天监控未采集" if slot == "full" else "上午监控未采集"


def intraday_monitor_global_line(meta: dict[str, Any] | None) -> str:
    meta = meta or {}
    if meta.get("intraday_digest_ok"):
        return f"intraday_monitor={int(meta.get('intraday_point_count') or 0)}点"
    return "intraday_monitor=不可用"


def build_quote_line_with_intraday(
    quote: dict,
    flow: dict,
    tags: dict,
    *,
    intraday: dict | None = None,
    slot: str = "morning",
    digest_ok: bool = False,
) -> str:
    price = quote.get("price", "—")
    pct = quote.get("pct_chg")
    pct5 = quote.get("pct_5d")
    net = flow.get("main_net_yi")
    ts = tags.get("trend_short", "")
    tm = tags.get("trend_mid", "")
    pct_s = f"{pct:+.2f}%" if pct is not None else "—"
    p5 = f"5日{pct5:+.1f}%" if pct5 is not None else ""
    net_s = f"主力{net:+.2f}亿" if net is not None else "主力—"
    base = f"{price} {pct_s} | {p5} | {net_s} | 短{ts}/中{tm}".strip(" |")
    extra = format_digest_prompt_line(intraday, slot=slot)
    if extra:
        return f"{base} | {extra}"
    if not (intraday or {}).get("session_shape"):
        return f"{base} | {intraday_missing_label(slot=slot, digest_ok=digest_ok)}"
    return base


def digest_stock_map(payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not payload:
        return {}
    by_code = payload.get("stocks_by_code")
    if isinstance(by_code, dict):
        return by_code
    out: dict[str, dict[str, Any]] = {}
    for row in payload.get("stocks") or []:
        if isinstance(row, dict) and row.get("code"):
            out[str(row["code"])] = row
    return out
