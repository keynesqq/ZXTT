"""财联社看盘数据（情绪/封板率/风口），补充东财 AkShare。

固定采集 v1 层 A：emotion + todayTuyere + mainline，见 SPEC.md §7。
"""
from __future__ import annotations

import json
from datetime import date
from typing import Any

from collect.manifest import record_source, track_source
from core.paths import ROOT
from market.cls.request import app_headers, app_params, get_json, now_ts, ts_iso, web_headers, web_params

_EMOTION_URL = "https://x-quote.cls.cn/v2/quote/a/stock/emotion"
_WIND_URL = "https://api3.cls.cn/v2/todayTuyere"
_MAINLINE_URL = "https://api3.cls.cn/v2/dingPan/mainline"


def _parse_pct(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip().replace("%", "")
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_num(raw: Any) -> float | None:
    if raw is None:
        return None
    s = str(raw).strip()
    if not s or s == "-":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def _parse_limit_board(raw: dict[str, Any] | None) -> dict[str, dict[str, str]]:
    if not raw:
        return {}
    row1 = raw.get("row1") or []
    row2 = raw.get("row2") or []
    row3 = raw.get("row3") or []
    out: dict[str, dict[str, str]] = {}
    for i, name in enumerate(row1):
        if not name:
            continue
        out[str(name)] = {
            "count": str(row2[i]) if i < len(row2) else "-",
            "continuous_rate": str(row3[i + 1]) if i + 1 < len(row3) else "-",
        }
    return out


def _normalize_emotion(body: dict[str, Any]) -> dict[str, Any]:
    dis = body.get("up_down_dis") or {}
    return {
        "market_heat": _parse_num(body.get("market_degree")),
        "turnover": str(body.get("shsz_balance") or "-"),
        "turnover_change": str(body.get("shsz_balance_change_px") or "-"),
        "seal_rate": _parse_pct(body.get("up_ratio")),
        "sealed_count": _parse_num(body.get("up_ratio_num")),
        "touched_count": _parse_num(body.get("up_open_num")),
        "prev_zt_performance": _parse_pct(body.get("performance")),
        "high_open_rate": _parse_pct(body.get("up_open_ratio")),
        "profit_rate": _parse_pct(body.get("profit_ratio")),
        "limit_up_count": _parse_num(dis.get("up_num")),
        "limit_down_count": _parse_num(dis.get("down_num")),
        "rise_count": _parse_num(dis.get("rise_num")),
        "fall_count": _parse_num(dis.get("fall_num")),
        "flat_count": _parse_num(dis.get("flat_num")),
        "suspend_count": _parse_num(dis.get("suspend_num")),
        "limit_up_board": _parse_limit_board(body.get("limit_up_board")),
    }


def _normalize_wind(items: list[dict[str, Any]]) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for item in items:
        name = str(item.get("title") or item.get("plate_name") or "").strip()
        if not name:
            continue
        out.append(
            {
                "plate_code": str(item.get("plate_code") or ""),
                "name": name,
                "catalyst": str(item.get("interpret") or item.get("catalyst") or "").strip(),
            }
        )
    return out


def _normalize_mainline(data: dict[str, Any]) -> dict[str, Any]:
    chances = data.get("chances") or []
    lines: list[dict[str, Any]] = []
    for ch in chances[:5]:
        plates = []
        for p in (ch.get("plates") or [])[:4]:
            plates.append(
                {
                    "code": str(p.get("code") or ""),
                    "name": str(p.get("name") or ""),
                }
            )
        lines.append(
            {
                "desc": str(ch.get("mainLine_desc") or ch.get("mainline_desc") or "").strip(),
                "hot": ch.get("hot"),
                "continued": ch.get("continued"),
                "plates": plates,
            }
        )
    return {
        "chance_desc": str(data.get("chance_desc") or "").strip(),
        "lines": lines,
    }


def fetch_cls_emotion(*, for_date: date | None = None, timeout: float = 15.0) -> dict[str, Any]:
    data = get_json(
        _EMOTION_URL,
        params=web_params(),
        headers=web_headers(referer="https://www.cls.cn/finance"),
        timeout=timeout,
    )
    if data.get("code") != 200:
        raise RuntimeError(f"CLS emotion code={data.get('code')} msg={data.get('msg')}")
    return _normalize_emotion(data.get("data") or {})


def fetch_cls_wind(*, for_date: date | None = None, timeout: float = 15.0) -> list[dict[str, str]]:
    data = get_json(
        _WIND_URL,
        params=app_params(for_date=for_date),
        headers=app_headers(),
        timeout=timeout,
    )
    if data.get("errno") != 0:
        raise RuntimeError(f"CLS wind errno={data.get('errno')} msg={data.get('msg')}")
    items = (data.get("data") or {}).get("today_tuyere") or []
    return _normalize_wind(items)


def fetch_cls_mainline(*, for_date: date | None = None, timeout: float = 15.0) -> dict[str, Any]:
    data = get_json(
        _MAINLINE_URL,
        params=app_params(for_date=for_date),
        headers=app_headers(),
        timeout=timeout,
    )
    if data.get("errno") != 0:
        raise RuntimeError(f"CLS mainline errno={data.get('errno')} msg={data.get('msg')}")
    return _normalize_mainline(data.get("data") or {})


def collect_cls_finance(
    *,
    for_date: date | None = None,
    calendar_date: date | None = None,
    include_wind: bool = True,
    include_mainline: bool = True,
) -> dict[str, Any]:
    """采集财联社看盘核心指标；所有请求带时间戳。"""
    d = for_date or date.today()
    cal = calendar_date or d
    collected_at = now_ts()
    payload: dict[str, Any] = {
        "source": "cls.cn",
        "trade_date": d.isoformat(),
        "collected_at": collected_at,
        "collected_at_iso": ts_iso(collected_at),
        "request_ts": collected_at,
    }
    warnings: list[str] = []

    try:
        with track_source(d, "cls_emotion", calendar_date=cal) as rec:
            emotion = fetch_cls_emotion(for_date=d)
            payload.update(emotion)
            rec["market_heat"] = emotion.get("market_heat")
    except Exception as e:
        warnings.append(f"财联社emotion: {e}")
        record_source(d, "cls_emotion", {"ok": False, "error": str(e)}, calendar_date=cal)

    if include_wind:
        try:
            with track_source(d, "cls_wind", calendar_date=cal) as rec:
                payload["wind_plates"] = fetch_cls_wind(for_date=d)
                rec["count"] = len(payload["wind_plates"])
        except Exception as e:
            payload["wind_plates"] = []
            warnings.append(f"财联社风口: {e}")

    if include_mainline:
        try:
            with track_source(d, "cls_mainline", calendar_date=cal) as rec:
                payload["mainline"] = fetch_cls_mainline(for_date=d)
                rec["line_count"] = len((payload["mainline"] or {}).get("lines") or [])
        except Exception as e:
            payload["mainline"] = {"chance_desc": "", "lines": []}
            warnings.append(f"财联社主线: {e}")

    if warnings:
        payload["warnings"] = warnings
    record_source(
        d,
        "cls_api",
        {
            "ok": not warnings,
            "warning_count": len(warnings),
            "has_emotion": payload.get("market_heat") is not None,
        },
        calendar_date=cal,
    )
    return payload


def load_cls_finance(for_date: date | None = None) -> dict[str, Any] | None:
    """读 `data/cls_finance/{trade_date}.json`（health / 解读层用）。"""
    d = for_date or date.today()
    path = ROOT / "data" / "cls_finance" / f"{d.isoformat()}.json"
    if not path.is_file():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def format_cls_prompt(cls: dict[str, Any] | None) -> list[str]:
    if not cls:
        return []
    lines = [
        "",
        "## [财联社看盘] L1 补充（cls.cn）",
        f"- 交易日: {cls.get('trade_date', '—')} · 采集: {cls.get('collected_at_iso', '—')}",
    ]
    heat = cls.get("market_heat")
    if heat is not None:
        lines.append(f"- 市场热度: {heat}°")
    if cls.get("turnover") and cls.get("turnover") != "-":
        chg = cls.get("turnover_change") or "—"
        lines.append(f"- 两市成交额: {cls['turnover']} · 较上日 {chg}")
    if cls.get("limit_up_count") is not None:
        ld = cls.get("limit_down_count")
        lines.append(f"- 涨停 {cls.get('limit_up_count')} vs 跌停 {ld if ld is not None else '—'}")
    if cls.get("seal_rate") is not None:
        lines.append(
            f"- 封板率 {cls['seal_rate']}% · 封板 {cls.get('sealed_count', '—')} / "
            f"触及 {cls.get('touched_count', '—')}"
        )
    perf = cls.get("prev_zt_performance")
    if perf is not None:
        lines.append(
            f"- 昨涨停今表现 {perf}% · 高开率 {cls.get('high_open_rate', '—')}% · "
            f"获利率 {cls.get('profit_rate', '—')}%"
        )
    rise = cls.get("rise_count")
    fall = cls.get("fall_count")
    if rise is not None and fall is not None:
        lines.append(f"- 涨跌家数: 涨 {int(rise)} / 跌 {int(fall)}")

    board = cls.get("limit_up_board") or {}
    if board:
        parts = []
        for name, rec in list(board.items())[:4]:
            parts.append(f"{name}{rec.get('count', '-')}({rec.get('continuous_rate', '-')})")
        if parts:
            lines.append("- 连板梯队: " + " · ".join(parts))

    wind = cls.get("wind_plates") or []
    if wind:
        lines.append("- 今日风口: " + " · ".join(w["name"] for w in wind[:5] if w.get("name")))

    mainline = cls.get("mainline") or {}
    if mainline.get("chance_desc"):
        lines.append(f"- 主线机会: {mainline['chance_desc']}")
    for ln in (mainline.get("lines") or [])[:2]:
        plates = " · ".join(p["name"] for p in (ln.get("plates") or []) if p.get("name"))
        desc = (ln.get("desc") or "")[:80]
        if plates or desc:
            lines.append(f"  · {plates or '—'}: {desc}")

    daily = cls.get("daily_articles")
    if daily:
        from market.cls.daily_articles import format_cls_articles_prompt

        lines.extend(format_cls_articles_prompt(daily))

    for w in cls.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    return lines
