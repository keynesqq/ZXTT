"""大盘短线生态：涨停/炸板/昨涨停三池 + 汇总 + 池子参考分（AkShare 东财，不含 cls）。"""
from __future__ import annotations

import json
import time
from datetime import date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from collect.manifest import track_source
from core.io import atomic_write_text
from core.config import market_cfg
from core.paths import ROOT
from core.trading_calendar import market_data_date

_STORAGE = ROOT / "data" / "market_sentiment"

_ZT_COLS = [
    "序号",
    "代码",
    "名称",
    "涨跌幅",
    "最新价",
    "成交额",
    "流通市值",
    "总市值",
    "换手率",
    "封板资金",
    "首次封板时间",
    "最后封板时间",
    "炸板次数",
    "涨停统计",
    "连板数",
    "所属行业",
]
_PREV_COLS = [
    "序号",
    "代码",
    "名称",
    "涨跌幅",
    "涨停价",
    "最新价",
    "成交额",
    "流通市值",
    "总市值",
    "换手率",
    "振幅",
    "昨日封板时间",
    "连续涨停天数",
    "涨停统计",
    "所属行业",
]


def _norm_columns(df) -> dict[str, str]:
    """将 DataFrame 列映射为标准字段名。"""
    cols = list(df.columns)
    if len(cols) >= len(_ZT_COLS) and cols[0] == _ZT_COLS[0]:
        return dict(zip(_ZT_COLS[: len(cols)], cols))
    mapping: dict[str, str] = {}
    std = _ZT_COLS if len(cols) >= 14 else _PREV_COLS
    for i, key in enumerate(std):
        if i < len(cols):
            mapping[key] = cols[i]
    return mapping


def _row_val(row, mapping: dict[str, str], key: str, default=None):
    col = mapping.get(key)
    if not col:
        return default
    try:
        v = row[col]
        if v is None or (isinstance(v, float) and v != v):
            return default
        return v
    except (KeyError, TypeError):
        return default


def _fetch_pool(func, d: date) -> list[dict[str, Any]]:
    from feeds.eastmoney import call_akshare

    ds = d.strftime("%Y%m%d")
    df = call_akshare(func, date=ds)
    if df is None:
        df = call_akshare(func)
    if df is None or df.empty:
        return []
    mapping = _norm_columns(df)
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        code = str(_row_val(row, mapping, "代码", "") or "").strip().zfill(6)
        if not code or len(code) != 6:
            continue
        out.append(
            {
                "code": code,
                "name": str(_row_val(row, mapping, "名称", "") or "").strip(),
                "pct_chg": _to_float(_row_val(row, mapping, "涨跌幅")),
                "industry": str(_row_val(row, mapping, "所属行业", "") or "").strip(),
                "lb_count": _to_int(_row_val(row, mapping, "连板数")),
                "broken_count": _to_int(_row_val(row, mapping, "炸板次数")),
            }
        )
    return out


def _to_float(v) -> float | None:
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _to_int(v) -> int | None:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return None


def _prev_pool(d: date) -> list[dict[str, Any]]:
    import akshare as ak

    from feeds.eastmoney import call_akshare

    ds = d.strftime("%Y%m%d")
    df = call_akshare(ak.stock_zt_pool_previous_em, date=ds)
    if df is None or df.empty:
        return []
    mapping = _norm_columns(df)
    out: list[dict[str, Any]] = []
    for _, row in df.iterrows():
        code = str(_row_val(row, mapping, "代码", "") or "").strip().zfill(6)
        if not code:
            continue
        out.append(
            {
                "code": code,
                "name": str(_row_val(row, mapping, "名称", "") or "").strip(),
                "pct_chg": _to_float(_row_val(row, mapping, "涨跌幅")),
                "industry": str(_row_val(row, mapping, "所属行业", "") or "").strip(),
                "lb_count": _to_int(_row_val(row, mapping, "连续涨停天数")),
            }
        )
    return out


def _collect_cls_articles_resolved(
    trade_date: date,
    *,
    force: bool = False,
    calendar_date: date | None = None,
) -> dict[str, Any]:
    """采集财联社固定栏目；未齐且已过通常发布时间时 force 补采一次。"""
    from market.cls.daily_articles import before_typical_article_publish, collect_cls_daily_articles

    daily = collect_cls_daily_articles(
        for_date=trade_date, force=force, calendar_date=calendar_date
    )
    if not before_typical_article_publish(trade_date) and not _cls_articles_payload_ok(daily) and not force:
        daily = collect_cls_daily_articles(
            for_date=trade_date, force=True, calendar_date=calendar_date
        )
    return daily


def _disabled_payload(*, date_str: str, calendar_date: date, message: str) -> dict[str, Any]:
    row = {
        "date": date_str,
        "calendar_date": calendar_date.isoformat(),
        "warnings": [message],
        "pool_score": 0,
        "pool_signal": "不明",
        "pool_hint": "大盘生态采集已关闭",
        "emotion_score": 0,
        "emotion_label": "不明",
        "position_hint": "大盘生态采集已关闭",
    }
    return row


def _pool_score_fields(score: int, signal: str, hint: str) -> dict[str, Any]:
    return {
        "pool_score": score,
        "pool_signal": signal,
        "pool_hint": hint,
        "emotion_score": score,
        "emotion_label": signal,
        "position_hint": hint,
    }


def collect_market_sentiment(
    for_date: date | None = None,
    *,
    include_cls_articles: bool = False,
    calendar_date: date | None = None,
) -> dict[str, Any]:
    """采集当日短线生态（三池 + 汇总 + pool 参考分）并持久化；不含财联社。"""
    import akshare as ak

    if include_cls_articles:
        import warnings

        warnings.warn(
            "collect_market_sentiment(include_cls_articles=True) 已废弃，请改用 cls collect --articles",
            DeprecationWarning,
            stacklevel=2,
        )

    cal = calendar_date or for_date or date.today()
    d = market_data_date(cal)
    ds = d.isoformat()
    cfg = market_cfg()
    if not cfg.get("enabled", True):
        return _disabled_payload(
            date_str=ds,
            calendar_date=cal,
            message="market.enabled=false，跳过大盘短线生态采集",
        )

    with track_source(d, "akshare_zt_pool", calendar_date=cal) as pool_rec:
        zt = _fetch_pool(ak.stock_zt_pool_em, d)
        broken = _fetch_pool(ak.stock_zt_pool_zbgc_em, d)
        prev = _prev_pool(d)
        pool_rec["limit_up_count"] = len(zt)
        pool_rec["broken_limit_count"] = len(broken)
        pool_rec["prev_limit_count"] = len(prev)
        if not zt and not broken and not prev:
            pool_rec["ok"] = False
            pool_rec["empty_all_pools"] = True

    prev_pcts = [x["pct_chg"] for x in prev if x.get("pct_chg") is not None]
    prev_avg = sum(prev_pcts) / len(prev_pcts) if prev_pcts else None
    prev_up = sum(1 for p in prev_pcts if p > 0)
    prev_down = sum(1 for p in prev_pcts if p < 0)
    prev_flat = len(prev_pcts) - prev_up - prev_down
    prev_green_high = sum(1 for p in prev_pcts if p >= 3.0) if prev_pcts else 0

    broken_pcts = [x["pct_chg"] for x in broken if x.get("pct_chg") is not None]
    broken_avg = sum(broken_pcts) / len(broken_pcts) if broken_pcts else None
    broken_repair = sum(1 for p in broken_pcts if p > 0) if broken_pcts else 0

    max_lb = max((x.get("lb_count") or 0 for x in zt), default=0)
    lb2_plus = sum(1 for x in zt if (x.get("lb_count") or 0) >= 2)

    industry_counts: dict[str, int] = {}
    for x in zt:
        ind = x.get("industry") or "未知"
        industry_counts[ind] = industry_counts.get(ind, 0) + 1
    hot_industries = sorted(industry_counts.items(), key=lambda kv: -kv[1])[:8]

    pool_score, pool_signal, pool_hint = _score_pool(
        zt_count=len(zt),
        broken_count=len(broken),
        prev_avg=prev_avg,
        prev_up_ratio=(prev_up / len(prev_pcts)) if prev_pcts else None,
        prev_green_high_ratio=(prev_green_high / len(prev_pcts)) if prev_pcts else None,
        broken_repair_ratio=(broken_repair / len(broken_pcts)) if broken_pcts else None,
    )

    payload: dict[str, Any] = {
        "date": ds,
        "calendar_date": cal.isoformat(),
        "collected_at": time.time(),
        "collected_at_iso": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        "warnings": [],
        "limit_up_count": len(zt),
        "broken_limit_count": len(broken),
        "prev_limit_count": len(prev),
        "prev_limit_avg_pct": round(prev_avg, 2) if prev_avg is not None else None,
        "prev_limit_up": prev_up,
        "prev_limit_down": prev_down,
        "prev_limit_flat": prev_flat,
        "prev_limit_premium_3pct": prev_green_high,
        "broken_limit_avg_pct": round(broken_avg, 2) if broken_avg is not None else None,
        "broken_limit_repair_count": broken_repair,
        "max_consecutive_boards": max_lb,
        "boards_2plus": lb2_plus,
        "hot_industries": [{"name": n, "limit_up_count": c} for n, c in hot_industries],
        "limit_up_leaders": sorted(zt, key=lambda x: -(x.get("lb_count") or 0))[:10],
        "prev_limit_sample": prev[:12],
        "limit_up_index": {
            x["code"]: {
                "lb_count": x.get("lb_count"),
                "broken_count": x.get("broken_count"),
                "industry": x.get("industry") or "",
            }
            for x in zt
            if x.get("code")
        },
        "broken_limit_index": {
            x["code"]: {
                "broken_count": x.get("broken_count") or 1,
                "pct_chg": x.get("pct_chg"),
                "industry": x.get("industry") or "",
            }
            for x in broken
            if x.get("code")
        },
    }
    payload.update(_pool_score_fields(pool_score, pool_signal, pool_hint))

    _save_market_sentiment(d, payload)
    return payload


def _score_pool(
    *,
    zt_count: int,
    broken_count: int,
    prev_avg: float | None,
    prev_up_ratio: float | None,
    prev_green_high_ratio: float | None,
    broken_repair_ratio: float | None,
) -> tuple[int, str, str]:
    """0-100 池子参考分 + 档位 + 仓位提示（仅 AkShare 三池，非最终大盘情绪）。"""
    score = 50
    if prev_avg is not None:
        if prev_avg >= 2.0:
            score += 18
        elif prev_avg >= 0.5:
            score += 10
        elif prev_avg <= -1.5:
            score -= 18
        elif prev_avg <= -0.3:
            score -= 8
    if prev_up_ratio is not None:
        if prev_up_ratio >= 0.7:
            score += 12
        elif prev_up_ratio <= 0.35:
            score -= 12
    if prev_green_high_ratio is not None and prev_green_high_ratio >= 0.4:
        score += 8
    if broken_repair_ratio is not None:
        if broken_repair_ratio >= 0.5:
            score += 6
        elif broken_repair_ratio <= 0.2:
            score -= 6
    if zt_count >= 60:
        score += 5
    elif zt_count <= 25:
        score -= 5
    if broken_count >= 25:
        score -= 8

    score = max(0, min(100, score))
    if score >= 72:
        label, pos = "强", "可维持或试探进攻（仅限主线与预期符合）"
    elif score >= 55:
        label, pos = "中", "维持仓位，「想买的」只做主线龙头"
    elif score >= 40:
        label, pos = "弱", "减仓提高胜率，暂停非主线新开"
    else:
        label, pos = "防守", "以减/空仓为主，只做「我的」风控"
    return score, label, pos


_score_emotion = _score_pool


def load_market_sentiment(for_date: date | None = None, *, strict: bool = False) -> dict[str, Any] | None:
    d = for_date or date.today()
    path = _STORAGE / f"{d.isoformat()}.json"
    if not path.is_file():
        if strict:
            return None
        for offset in range(1, 4):
            alt = _STORAGE / f"{(d - timedelta(days=offset)).isoformat()}.json"
            if alt.is_file():
                path = alt
                break
        else:
            return None
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


def load_limit_meta_map(for_date: date | None = None) -> dict[str, dict[str, Any]]:
    """合并涨停池/炸板池元数据，供快照 enrich 使用。"""
    d = for_date or date.today()
    data = load_market_sentiment(d) or {}
    out: dict[str, dict[str, Any]] = {}
    for code, meta in (data.get("limit_up_index") or {}).items():
        c = str(code).zfill(6)
        out[c] = {
            "in_limit_up_pool": True,
            "consecutive_boards": meta.get("lb_count"),
            "broken_count": meta.get("broken_count") or 0,
            "industry": meta.get("industry") or "",
        }
    for code, meta in (data.get("broken_limit_index") or {}).items():
        c = str(code).zfill(6)
        row = out.setdefault(c, {})
        row["broken_count"] = max(int(row.get("broken_count") or 0), int(meta.get("broken_count") or 1))
        if not row.get("industry"):
            row["industry"] = meta.get("industry") or ""
    return out


def _should_collect_cls_articles(include_cls_articles: bool, cls_cfg: dict[str, Any]) -> bool:
    return bool(include_cls_articles) and bool(cls_cfg.get("cls_articles_enabled", True))


def _cls_articles_payload_ok(data: dict[str, Any] | None) -> bool:
    from market.cls.daily_articles import ARTICLE_SLOTS

    if not data or data.get("skipped"):
        return False
    return int(data.get("found_count") or 0) >= len(ARTICLE_SLOTS)


def _cls_articles_satisfied(trade_date: date, cached: dict[str, Any] | None) -> bool:
    from market.cls.daily_articles import load_cls_daily_articles

    if cached:
        embedded = (cached.get("cls") or {}).get("daily_articles")
        if _cls_articles_payload_ok(embedded):
            return True
    return _cls_articles_payload_ok(load_cls_daily_articles(trade_date))


def _embed_cls_articles(cached: dict[str, Any], trade_date: date) -> dict[str, Any]:
    from market.cls.daily_articles import load_cls_daily_articles

    daily = (cached.get("cls") or {}).get("daily_articles")
    if _cls_articles_payload_ok(daily):
        return cached
    standalone = load_cls_daily_articles(trade_date)
    if not _cls_articles_payload_ok(standalone):
        return cached
    cls = dict(cached.get("cls") or {})
    cls["daily_articles"] = standalone
    cached["cls"] = cls
    return cached


def _save_market_sentiment(trade_date: date, payload: dict[str, Any]) -> None:
    path = _STORAGE / f"{trade_date.isoformat()}.json"
    atomic_write_text(path, json.dumps(payload, ensure_ascii=False, indent=2))


def _patch_cls_articles(cached: dict[str, Any], trade_date: date) -> dict[str, Any]:
    cls = dict(cached.get("cls") or {})
    cls["daily_articles"] = _collect_cls_articles_resolved(trade_date, force=True)
    daily = cls["daily_articles"]
    if daily.get("warnings"):
        warnings = list(cached.get("warnings") or [])
        for w in daily["warnings"]:
            if w not in warnings:
                warnings.append(w)
        cached["warnings"] = warnings
    cached["cls"] = cls
    _save_market_sentiment(trade_date, cached)
    return cached


def get_or_collect(
    for_date: date | None = None,
    *,
    calendar_date: date | None = None,
    refresh: bool = False,
    include_cls_articles: bool = False,
) -> dict[str, Any]:
    cal = calendar_date or for_date or date.today()
    trade = market_data_date(cal)
    if not market_cfg().get("enabled", True):
        cached = load_market_sentiment(trade)
        if cached:
            return cached
        return _disabled_payload(
            date_str=trade.isoformat(),
            calendar_date=cal,
            message="market.enabled=false，跳过大盘短线生态采集",
        )

    if include_cls_articles:
        import warnings

        warnings.warn(
            "get_or_collect(include_cls_articles=True) 已废弃，请改用 cls collect --articles",
            DeprecationWarning,
            stacklevel=2,
        )

    if not refresh:
        cached = load_market_sentiment(trade)
        if cached:
            return cached
    try:
        return collect_market_sentiment(trade, calendar_date=cal)
    except Exception as e:
        row = _disabled_payload(
            date_str=trade.isoformat(),
            calendar_date=cal,
            message=f"短线生态采集失败: {e}",
        )
        row["pool_hint"] = "数据不足，偏防守，以个股预期为准"
        row["position_hint"] = row["pool_hint"]
        return row


def collect_open_market_context(*, calendar_date: date | None = None) -> dict[str, Any]:
    """9:25 轻量大盘：昨涨停今开溢价 + 指数缺口（不采当日涨停池）。"""
    cal = calendar_date or date.today()
    d = market_data_date(cal)
    warnings: list[str] = []

    prev = _prev_pool(d)
    prev_pcts = [x["pct_chg"] for x in prev if x.get("pct_chg") is not None]
    prev_avg = sum(prev_pcts) / len(prev_pcts) if prev_pcts else None
    prev_up = sum(1 for p in prev_pcts if p > 0)
    prev_down = sum(1 for p in prev_pcts if p < 0)
    prev_green_high = sum(1 for p in prev_pcts if p >= 3.0) if prev_pcts else 0

    index_gaps: list[dict[str, Any]] = []
    try:
        from quote.tencent import fetch_index_open_gaps

        index_gaps = fetch_index_open_gaps()
    except Exception as e:
        warnings.append(f"指数开盘: {e}")

    cached = load_market_sentiment(d) or {}
    pool_signal = cached.get("pool_signal") or cached.get("emotion_label") or "待定"
    pool_score = cached.get("pool_score", cached.get("emotion_score"))
    pool_hint = cached.get("pool_hint") or cached.get("position_hint")

    return {
        "date": d.isoformat(),
        "calendar_date": cal.isoformat(),
        "context": "open_925",
        "collected_at": time.time(),
        "collected_at_iso": datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y-%m-%d %H:%M:%S"),
        "warnings": warnings,
        "prev_limit_count": len(prev),
        "prev_limit_avg_pct": round(prev_avg, 2) if prev_avg is not None else None,
        "prev_limit_up": prev_up,
        "prev_limit_down": prev_down,
        "prev_limit_premium_3pct": prev_green_high,
        "index_open_gaps": index_gaps,
        "limit_up_count": None,
        "broken_limit_count": None,
        "pool_signal": pool_signal,
        "pool_score": pool_score,
        "pool_hint": pool_hint or "9:25 仅参考昨涨停溢价与指数缺口；盘中后再更新 L1",
        "emotion_label": pool_signal,
        "emotion_score": pool_score,
        "position_hint": pool_hint
        or "9:25 仅参考昨涨停溢价与指数缺口；盘中后再更新 L1",
    }


def _format_open_sentiment_prompt(data: dict[str, Any]) -> str:
    lines = [
        "## [开盘环境输入] 9:25（昨涨停今开 + 指数缺口）",
        f"- 日期: {data.get('date', '—')}",
        f"- 说明: 连续竞价未开始，**不使用**当日涨停/炸板池与全天成交额结论。",
    ]
    if data.get("prev_limit_count"):
        lines.append(
            f"- 昨涨停今开: 均涨 {data.get('prev_limit_avg_pct', '—')}% · "
            f"上涨 {data.get('prev_limit_up', '—')} / 下跌 {data.get('prev_limit_down', '—')} · "
            f"溢价≥3% {data.get('prev_limit_premium_3pct', '—')} 只"
        )
    else:
        lines.append("- 昨涨停今开: 未采集")
    for idx in data.get("index_open_gaps") or []:
        name = idx.get("name") or idx.get("symbol") or "—"
        gap = idx.get("open_gap_pct")
        pct = idx.get("pct_chg")
        chg = idx.get("change")
        gap_s = f"{gap:+.2f}%" if gap is not None else "—"
        pct_s = f"{pct:+.2f}%" if pct is not None else "—"
        chg_s = f"{chg:+.2f} 点" if chg is not None else None
        parts = [f"开盘缺口 {gap_s}", f"今 {pct_s}"]
        if chg_s:
            parts.append(chg_s)
        lines.append(f"- {name}: " + " · ".join(parts))
    if not (data.get("index_open_gaps") or []):
        lines.append("- 指数开盘: 未采集")
    for w in data.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    lines.append("- 解读要求: 仅引用上述开盘口径；禁止编造今日涨停家数或主力流向。")
    return "\n".join(lines)


def format_sentiment_prompt(data: dict[str, Any] | None, *, phase: str | None = None) -> str:
    if not data:
        return "## [市场情绪输入]\n（未采集到全市场短线数据，不作全市场结论，仅基于自选分析。）"
    if phase == "open" or data.get("context") == "open_925":
        return _format_open_sentiment_prompt(data)
    signal = data.get("pool_signal") or data.get("emotion_label", "不明")
    score = data.get("pool_score", data.get("emotion_score", "—"))
    hint = data.get("pool_hint") or data.get("position_hint", "—")
    lines = [
        "## [短线生态输入] L1 东财三池（非最终大盘情绪）",
        f"- 日期: {data.get('date', '—')}",
        f"- 池子参考档: {signal}（pool_score {score}/100）",
        f"- 仓位参考: {hint}",
        f"- 今日涨停家数: {data.get('limit_up_count', '—')}",
        f"- 今日炸板家数: {data.get('broken_limit_count', '—')}",
        f"- 最高连板: {data.get('max_consecutive_boards', '—')} · 2板+ {data.get('boards_2plus', '—')} 只",
    ]
    if data.get("prev_limit_count"):
        lines.append(
            f"- 昨涨停今表现: 均涨 {data.get('prev_limit_avg_pct', '—')}% · "
            f"上涨 {data.get('prev_limit_up', '—')} / 下跌 {data.get('prev_limit_down', '—')} · "
            f"溢价≥3% {data.get('prev_limit_premium_3pct', '—')} 只"
        )
    if data.get("broken_limit_count"):
        lines.append(
            f"- 今炸板今修复: 均涨 {data.get('broken_limit_avg_pct', '—')}% · "
            f"收红 {data.get('broken_limit_repair_count', '—')}/{data.get('broken_limit_count')} 只"
        )
    hot = data.get("hot_industries") or []
    if hot:
        lines.append("- 涨停行业集中度 TOP: " + " · ".join(f"{h['name']}({h['limit_up_count']})" for h in hot[:5]))
    leaders = data.get("limit_up_leaders") or []
    if leaders:
        top = leaders[:5]
        lines.append(
            "- 连板龙头: "
            + " · ".join(
                f"{x.get('code')} {x.get('name')} {x.get('lb_count')}板" for x in top if x.get("name")
            )
        )
    for w in data.get("warnings") or []:
        lines.append(f"- ⚠ {w}")
    lines.append(
        "- 解读要求: 缩量普涨→偏兑现；昨涨停溢价高→短线流动性好；封板率低/炸板修复弱→降仓。"
        "最终大盘情绪需与财联社 cls 相互印证；无上述数据项时不编造涨跌家数/全市场成交额。"
    )
    return "\n".join(lines)
