#!/usr/bin/env python3
"""ZXTT — 已打包模块工具集（8 个基础模块）。"""
from __future__ import annotations

import argparse
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "packages"))


def _parse_date(raw: str | None) -> date | None:
    if not raw:
        return None
    return date.fromisoformat(raw)


def cmd_intraday(args: argparse.Namespace) -> int:
    from core.config import normalize_code

    if args.simulate:
        from intraday.simulate import run_intraday_simulate

        result = run_intraday_simulate(on_date=_parse_date(args.date))
        ok = result.get("outcome") == "ok"
    else:
        from intraday.stocks import resolve_intraday_stocks
        from intraday.watch import run_intraday_watch

        cli_codes = [normalize_code(c.strip()) for c in (args.codes or "").split(",") if c.strip()] or None
        stocks = resolve_intraday_stocks(cli_codes, on_date=_parse_date(args.date))
        if not stocks:
            print({
                "outcome": "error",
                "reason": "need_codes",
                "hint": "请配置 ths.account_dir（默认可读全自选），或传 --codes",
            })
            return 1
        result = run_intraday_watch(
            [s.code for s in stocks],
            force=args.force,
            on_date=_parse_date(args.date),
            session=args.session,
            resume=args.resume,
        )
        ok = result.get("outcome") in ("ok", "skip")
    print(result)
    return 0 if ok else 1


def cmd_auction(args: argparse.Namespace) -> int:
    from core.config import normalize_code

    if args.simulate:
        from auction.simulate import run_auction_simulate

        result = run_auction_simulate(on_date=_parse_date(args.date))
        ok = result.get("outcome") == "ok" and not result.get("shape_mismatches")
    else:
        from auction.stocks import resolve_auction_codes
        from auction.watch import run_auction_watch

        cli_codes = [normalize_code(c.strip()) for c in (args.codes or "").split(",") if c.strip()] or None
        codes = resolve_auction_codes(cli_codes, on_date=_parse_date(args.date))
        if not codes:
            print({"outcome": "error", "reason": "need_codes", "hint": "传 --codes，或先跑 quote query --all"})
            return 1
        result = run_auction_watch(
            codes,
            force=args.force,
            on_date=_parse_date(args.date),
            resume=args.resume,
        )
        ok = result.get("outcome") in ("ok", "skip")
    print(result)
    return 0 if ok else 1


def cmd_announcement_query(args: argparse.Namespace) -> int:
    from announcement.query import query_announcements, resolve_query_options
    from core.config import normalize_code

    codes = [normalize_code(c.strip()) for c in (args.codes or "").split(",") if c.strip()]
    if not codes:
        print({"outcome": "error", "reason": "need_codes"})
        return 1

    days = int(args.days) if args.days is not None else None
    max_count = int(args.max_count) if args.max_count is not None else None
    latest = int(args.latest) if args.latest is not None else None
    try:
        options = resolve_query_options(
            days=days,
            max_count=max_count,
            latest=latest,
            on_date=_parse_date(args.date),
        )
    except ValueError as e:
        print({"outcome": "error", "reason": "invalid_params", "message": str(e)})
        return 1

    items, path = query_announcements(codes, options=options)
    out: dict = {
        "outcome": "ok",
        "count": len(items),
        "query": {
            "lookback_days": options.lookback_days,
            "max_count": options.max_count,
            "fallback_latest_count": options.fallback_latest_count,
            "end_date": options.end_date.isoformat(),
        },
        "items": items,
    }
    if path is not None:
        out["path"] = str(path)
    print(out)
    return 0


def cmd_news_query(args: argparse.Namespace) -> int:
    from core.config import normalize_code
    from news.query import parse_categories, query_news, resolve_query_options

    codes = [normalize_code(c.strip()) for c in (args.codes or "").split(",") if c.strip()]
    if not codes:
        print({"outcome": "error", "reason": "need_codes"})
        return 1

    days = int(args.days) if args.days is not None else None
    max_count = int(args.max_count) if args.max_count is not None else None
    try:
        categories = None if not args.categories else parse_categories(args.categories)
        options = resolve_query_options(
            days=days,
            max_count=max_count,
            on_date=_parse_date(args.date),
            industry_enabled=False if args.no_industry else None,
            categories=categories,
            strict=True if args.strict else None,
        )
    except ValueError as e:
        print({"outcome": "error", "reason": "invalid_params", "message": str(e)})
        return 1

    items, path = query_news(codes, options=options)
    out: dict = {
        "outcome": "ok",
        "count": len(items),
        "query": {
            "lookback_days": options.lookback_days,
            "max_count": options.max_count,
            "end_date": options.end_date.isoformat(),
            "industry_enabled": options.industry_enabled,
            "categories": sorted(options.categories),
            "strict": options.strict,
        },
        "items": items,
    }
    if path is not None:
        out["path"] = str(path)
    print(out)
    return 0


def cmd_quote_query(args: argparse.Namespace) -> int:
    from core.config import normalize_code
    from quote.query import query_quotes

    day = _parse_date(args.date) or date.today()
    if args.all and args.codes:
        print({"outcome": "error", "reason": "codes_and_all_mutually_exclusive"})
        return 1
    if args.all:
        rows, path, meta = query_quotes(all_watchlist=True, on_date=day)
        mode = "all"
    else:
        codes = [normalize_code(c.strip()) for c in (args.codes or "").split(",") if c.strip()]
        if not codes:
            print({"outcome": "error", "reason": "need_codes_or_all"})
            return 1
        rows, path, meta = query_quotes(codes, on_date=day)
        mode = "codes"

    structure = meta.get("structure") if isinstance(meta.get("structure"), dict) else {}
    groups = [
        str(g.get("name")).strip()
        for g in (structure.get("groups") or [])
        if isinstance(g, dict) and str(g.get("name") or "").strip()
    ]
    out: dict = {
        "outcome": "ok",
        "mode": mode,
        "count": len(rows),
        "code_count": meta.get("code_count", len(rows)),
        "row_count": meta.get("row_count", len(rows)),
        "groups": groups,
        "quotes": rows,
    }
    if path is not None:
        out["path"] = str(path)
    print(out)
    return 0


def cmd_cls_collect(args: argparse.Namespace) -> int:
    from core.config import market_cfg
    from core.paths import ROOT
    from core.trading_calendar import is_trading_day, market_data_date
    from market.cls import collect_cls

    if not market_cfg().get("cls_enabled", True):
        print({"outcome": "skip", "reason": "cls_disabled"})
        return 0

    day = _parse_date(args.date) or date.today()
    if not args.force and not is_trading_day(day):
        print({"outcome": "skip", "reason": "non_trading_day", "date": day.isoformat()})
        return 0

    trade = market_data_date(day)
    data = collect_cls(
        trade,
        include_articles=bool(args.articles),
        force=args.force,
        calendar_date=day,
    )
    layer_a_path = ROOT / "data" / "cls_finance" / f"{trade.isoformat()}.json"
    layer_b_path = ROOT / "data" / "cls_articles" / f"{trade.isoformat()}.json"
    print(
        {
            "outcome": "ok",
            "trade_date": trade.isoformat(),
            "layer_a_path": str(layer_a_path),
            "layer_a_ok": data.get("layer_a_ok"),
            "market_heat": data.get("market_heat"),
            "wind_count": data.get("wind_count"),
            "mainline_count": data.get("mainline_count"),
            "articles_path": str(layer_b_path) if args.articles else None,
            "articles_found": data.get("articles_found"),
            "articles_expected": data.get("articles_expected"),
            "articles_ok": data.get("articles_ok"),
            "warnings": data.get("warnings"),
        }
    )
    return 0


def cmd_market_collect(args: argparse.Namespace) -> int:
    from core.config import market_cfg
    from core.paths import ROOT
    from core.trading_calendar import is_trading_day, market_data_date
    from market.sentiment import collect_market_sentiment

    if not market_cfg().get("enabled", True):
        print({"outcome": "skip", "reason": "market_disabled"})
        return 0

    day = _parse_date(args.date) or date.today()
    if not args.force and not is_trading_day(day):
        print({"outcome": "skip", "reason": "non_trading_day", "date": day.isoformat()})
        return 0

    if getattr(args, "articles", False):
        print(
            {"warning": "market collect --articles 已废弃，请改用: python run.py cls collect --articles"},
            file=sys.stderr,
        )
        from market.cls import collect_cls

        trade = market_data_date(day)
        collect_cls(trade, include_articles=True, force=args.force, calendar_date=day)

    trade = market_data_date(day)
    data = collect_market_sentiment(trade, calendar_date=day)
    path = ROOT / "data" / "market_sentiment" / f"{trade.isoformat()}.json"
    print(
        {
            "outcome": "ok",
            "path": str(path),
            "trade_date": trade.isoformat(),
            "limit_up_count": data.get("limit_up_count"),
            "broken_limit_count": data.get("broken_limit_count"),
            "pool_signal": data.get("pool_signal"),
            "pool_score": data.get("pool_score"),
            "pool_hint": data.get("pool_hint"),
        }
    )
    return 0


def cmd_index_collect(args: argparse.Namespace) -> int:
    from core.config import index_cfg
    from core.paths import ROOT
    from core.trading_calendar import is_trading_day, market_data_date
    from market.index_snapshot import collect_market_index

    if not index_cfg().get("enabled", True):
        print({"outcome": "skip", "reason": "index_disabled"})
        return 0

    day = _parse_date(args.date) or date.today()
    if not args.force and not is_trading_day(day):
        print({"outcome": "skip", "reason": "non_trading_day", "date": day.isoformat()})
        return 0

    slot = (args.slot or "evening").strip().lower()
    trade = market_data_date(day)
    data = collect_market_index(calendar_date=day, slot=slot)
    path = ROOT / "data" / "market_index" / f"{trade.isoformat()}.json"
    indices = data.get("indices") or []
    summary = [{"name": row.get("name"), "pct_chg": row.get("pct_chg"), "price": row.get("price")} for row in indices]
    print(
        {
            "outcome": "ok" if indices else "warn",
            "path": str(path),
            "trade_date": trade.isoformat(),
            "slot": data.get("latest_slot"),
            "index_count": len(indices),
            "indices": summary,
            "warnings": data.get("warnings"),
        }
    )
    return 0 if indices else 1


def cmd_flow_collect(args: argparse.Namespace) -> int:
    from core.config import flow_cfg
    from core.paths import ROOT
    from core.trading_calendar import is_trading_day, market_data_date
    from market.flow_snapshot import collect_market_flow

    if not flow_cfg().get("enabled", True):
        print({"outcome": "skip", "reason": "flow_disabled"})
        return 0

    day = _parse_date(args.date) or date.today()
    if not args.force and not is_trading_day(day):
        print({"outcome": "skip", "reason": "non_trading_day", "date": day.isoformat()})
        return 0

    if args.no_watchlist and args.watchlist:
        print({"outcome": "error", "reason": "watchlist_flags_mutually_exclusive"})
        return 1

    cli_wl: bool | None = False if args.no_watchlist else (True if args.watchlist else None)
    slot = (args.slot or "evening").strip().lower()
    trade = market_data_date(day)
    data = collect_market_flow(calendar_date=day, slot=slot, watchlist_enabled=cli_wl)
    if data.get("outcome") == "skip":
        print(data)
        return 0

    north = data.get("northbound") or {}
    market_row = data.get("market") or {}
    watchlist = data.get("watchlist_flow") or []
    ok = north.get("net_yi") is not None or market_row.get("main_net_yi") is not None
    path = data.get("path") or str(ROOT / "data" / "market_flow" / f"{trade.isoformat()}.json")
    print(
        {
            "outcome": "ok" if ok else "warn",
            "path": path,
            "trade_date": trade.isoformat(),
            "slot": data.get("latest_slot"),
            "north_net_yi": north.get("net_yi"),
            "main_net_yi": market_row.get("main_net_yi"),
            "watchlist_enabled": data.get("watchlist_enabled"),
            "watchlist_count": len(watchlist),
            "sector_inflow_top": [r.get("name") for r in (data.get("sectors_inflow_top") or [])[:3]],
            "flow_signal": data.get("flow_signal"),
            "flow_hint": data.get("flow_hint"),
            "warnings": data.get("warnings"),
        }
    )
    return 0 if ok else 1


def cmd_collect(args: argparse.Namespace) -> int:
    slot = (args.slot or "evening").strip().lower()
    if slot == "midday":
        from midday.collect import run_collect_midday

        result = run_collect_midday(on_date=_parse_date(args.date), force=args.force)
    elif slot == "evening":
        from evening.collect import run_collect_evening

        result = run_collect_evening(on_date=_parse_date(args.date), force=args.force)
    else:
        print({"outcome": "error", "reason": "unsupported_slot", "slot": slot})
        return 1
    print(result)
    return 0 if result.get("overall") != "fail" else 1


def cmd_generate(args: argparse.Namespace) -> int:
    slot = (args.slot or "evening").strip().lower()
    phase = (args.phase or "all").strip().lower()
    if phase not in ("all", "ai", "render"):
        print({"outcome": "error", "reason": "unsupported_phase", "phase": phase})
        return 1
    if slot == "midday":
        from midday.pipeline import run_midday_generate

        result = run_midday_generate(on_date=_parse_date(args.date), phase=phase, force=args.force)
    elif slot == "evening":
        from evening.pipeline import run_evening_generate

        result = run_evening_generate(on_date=_parse_date(args.date), phase=phase, force=args.force)
    else:
        print({"outcome": "error", "reason": "unsupported_slot", "slot": slot})
        return 1
    print(result)
    return 0 if result.get("outcome") != "fail" else 1


def cmd_evening(args: argparse.Namespace) -> int:
    from evening.run_full import run_evening_pipeline

    result = run_evening_pipeline(
        on_date=_parse_date(args.date),
        force=args.force,
        open_browser=not args.no_open,
    )
    print(result)
    return 0 if result.get("outcome") in ("ok", "skip") else 1


def cmd_eve_news(args: argparse.Namespace) -> int:
    from evening.eve_news import run_eve_news_pipeline

    result = run_eve_news_pipeline(on_date=_parse_date(args.date), force=args.force)
    print(result)
    return 0 if result.get("outcome") in ("ok", "skip") else 1


def cmd_preprocess(args: argparse.Namespace) -> int:
    slot = (args.slot or "evening").strip().lower()
    if slot == "midday":
        from midday.preprocess import run_preprocess_midday

        result = run_preprocess_midday(on_date=_parse_date(args.date), force=args.force)
    elif slot == "evening":
        from evening.preprocess import run_preprocess_evening

        result = run_preprocess_evening(on_date=_parse_date(args.date), force=args.force)
    else:
        print({"outcome": "error", "reason": "unsupported_slot", "slot": slot})
        return 1
    print(result)
    return 0 if result.get("outcome") != "fail" else 1


def cmd_midday(args: argparse.Namespace) -> int:
    from midday.run_full import run_midday_pipeline

    result = run_midday_pipeline(
        on_date=_parse_date(args.date),
        force=args.force,
        open_browser=not args.no_open,
    )
    print(result)
    return 0 if result.get("outcome") == "ok" else 1


def cmd_hub(args: argparse.Namespace) -> int:
    from report.hub import open_hub

    url = open_hub(_parse_date(args.date), open_browser=not args.no_open)
    print({"outcome": "ok", "url": url})
    return 0


def cmd_open(args: argparse.Namespace) -> int:
    from report.app_server import DEFAULT_PORT, ensure_server, open_in_browser, run_app_server
    from report.hub import open_hub

    port = int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT)
    start_path = "/settings" if getattr(args, "settings", False) else "/reports/index.html"
    if args.date:
        start_path = f"{start_path}?date={args.date}"

    if getattr(args, "foreground", False):
        run_app_server(port=port, open_browser=not args.no_browser, start_path=start_path)
        return 0

    open_hub(_parse_date(args.date), open_browser=False)
    status = ensure_server(port)
    if not getattr(args, "no_browser", False):
        if getattr(args, "settings", False):
            url = open_in_browser(port, "/settings")
        else:
            url = open_in_browser(port, start_path)
    else:
        from report.app_server import server_url

        url = server_url(port, start_path if not getattr(args, "settings", False) else "/settings")
    print({"outcome": "ok", "server": status, "url": url})
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from report.app_server import (
        DEFAULT_PORT,
        ensure_server,
        is_server_running,
        run_app_server,
        stop_server,
    )

    port = int(getattr(args, "port", DEFAULT_PORT) or DEFAULT_PORT)
    if getattr(args, "stop", False):
        if stop_server(port):
            print(f"已停止端口 {port} 上的 ZXTT 服务")
        elif is_server_running(port):
            print(f"端口 {port} 有服务在运行，但无 PID 记录。")
            return 1
        else:
            print("服务未在运行")
        return 0

    if getattr(args, "foreground", False):
        try:
            run_app_server(port=port, open_browser=not args.no_browser)
        except OSError as e:
            print({"outcome": "error", "reason": str(e)})
            return 1
        return 0

    status = ensure_server(port)
    print({"outcome": "ok", "server": status, "url": f"http://127.0.0.1:{port}/"})
    return 0


def cmd_settings(args: argparse.Namespace) -> int:
    args.settings = True
    return cmd_open(args)


def cmd_reproduce(args: argparse.Namespace) -> int:
    from report.archive import reproduce_report

    cal = _parse_date(args.date) or date.today()
    result = reproduce_report(
        args.slot,
        cal,
        phase=args.phase,
        force=args.force,
    )
    print(result)
    return 0 if result.get("outcome") in ("ok", "warn", "skip") else 1


def cmd_calendar(args: argparse.Namespace) -> int:
    from core.trading_calendar import trading_day_info, verify_exchange_calendar

    if args.calendar_cmd == "info":
        d = _parse_date(args.date) or date.today()
        print(trading_day_info(d))
        return 0
    year = int(args.year)
    result = verify_exchange_calendar(year=year)
    print(result)
    return 0 if result.get("ok") else 1


def cmd_morning(args: argparse.Namespace) -> int:
    phase = (args.phase or "report").strip().lower()
    if phase == "pre":
        from morning.run_full import run_morning_pre_pipeline

        result = run_morning_pre_pipeline(on_date=_parse_date(args.date), force=args.force)
        ok = result.get("outcome") in ("ok", "skip")
    else:
        from morning.run_full import run_morning_pipeline

        result = run_morning_pipeline(
            on_date=_parse_date(args.date),
            force=args.force,
            open_browser=not args.no_open,
        )
        ok = result.get("outcome") in ("ok", "skip")
    print(result)
    return 0 if ok else 1


def _add_ecosystem_collect_parser(sub) -> None:
    p = sub.add_parser("collect", help="采集涨停/炸板/昨涨停三池 + pool 参考分")
    p.add_argument("--force", action="store_true", help="忽略交易日检查")
    p.add_argument("--date", default=None, help="日历日 YYYY-MM-DD（落盘文件名）")
    p.add_argument(
        "--articles",
        action="store_true",
        help="已废弃：转发 cls collect --articles 后仍采三池",
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="ZXTT — 已打包 8 模块工具集")
    sub = parser.add_subparsers(dest="cmd", required=True)

    market = sub.add_parser("market", help="大盘短线生态（别名见 ecosystem）")
    market_sub = market.add_subparsers(dest="market_cmd", required=True)
    _add_ecosystem_collect_parser(market_sub)

    ecosystem = sub.add_parser("ecosystem", help="大盘短线生态：东财涨停/炸板/昨涨停三池")
    ecosystem_sub = ecosystem.add_subparsers(dest="ecosystem_cmd", required=True)
    _add_ecosystem_collect_parser(ecosystem_sub)

    index_mod = sub.add_parser("index", help="主要指数快照")
    index_sub = index_mod.add_subparsers(dest="index_cmd", required=True)
    index_collect = index_sub.add_parser("collect", help="采集主要指数涨跌与量能")
    index_collect.add_argument("--force", action="store_true")
    index_collect.add_argument("--date", default=None)
    index_collect.add_argument(
        "--slot",
        default="evening",
        choices=("open", "morning", "midday", "evening", "manual"),
    )

    flow_mod = sub.add_parser("flow", help="大盘资金流")
    flow_sub = flow_mod.add_subparsers(dest="flow_cmd", required=True)
    flow_collect = flow_sub.add_parser("collect", help="采集结构化资金流")
    flow_collect.add_argument("--force", action="store_true")
    flow_collect.add_argument("--date", default=None)
    flow_collect.add_argument(
        "--slot",
        default="evening",
        choices=("open", "morning", "midday", "evening", "manual"),
    )
    flow_collect.add_argument("--no-watchlist", action="store_true")
    flow_collect.add_argument("--watchlist", action="store_true")

    cls_mod = sub.add_parser("cls", help="财联社采集")
    cls_sub = cls_mod.add_subparsers(dest="cls_cmd", required=True)
    cls_collect = cls_sub.add_parser("collect", help="采集财联社 A/B 层")
    cls_collect.add_argument("--force", action="store_true")
    cls_collect.add_argument("--date", default=None)
    cls_collect.add_argument("--articles", action="store_true")

    announcement = sub.add_parser("announcement", help="个股公告查询")
    announcement_sub = announcement.add_subparsers(dest="announcement_cmd", required=True)
    ann_q = announcement_sub.add_parser("query", help="查公告")
    ann_q.add_argument("--codes", required=True)
    ann_q.add_argument("--days", default=None)
    ann_q.add_argument("--max-count", default=None)
    ann_q.add_argument("--latest", default=None)
    ann_q.add_argument("--date", default=None)

    news = sub.add_parser("news", help="个股非公告资讯查询")
    news_sub = news.add_subparsers(dest="news_cmd", required=True)
    news_q = news_sub.add_parser("query", help="查资讯/观点/研报/行业")
    news_q.add_argument("--codes", required=True)
    news_q.add_argument("--days", default=None)
    news_q.add_argument("--max-count", default=None)
    news_q.add_argument("--no-industry", action="store_true")
    news_q.add_argument("--categories", default=None)
    news_q.add_argument("--date", default=None)
    news_q.add_argument("--strict", action="store_true")

    quote = sub.add_parser("quote", help="行情查询")
    quote_sub = quote.add_subparsers(dest="quote_cmd", required=True)
    q = quote_sub.add_parser("query", help="查行情并落盘")
    q.add_argument("--codes", default="")
    q.add_argument("--all", action="store_true")
    q.add_argument("--date", default=None)

    evening_mod = sub.add_parser("evening", help="晚间管线 · 一键跑通并打开进度页")
    evening_mod.add_argument("--force", action="store_true")
    evening_mod.add_argument("--date", default=None)
    evening_mod.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    eve_news_mod = sub.add_parser("eve-news", help="交易日前夜 · 休市期间资讯更新（管线待实现）")
    eve_news_mod.add_argument("--force", action="store_true")
    eve_news_mod.add_argument("--date", default=None)

    midday_mod = sub.add_parser("midday", help="午间管线 · 一键跑通并打开进度页")
    midday_mod.add_argument("--force", action="store_true")
    midday_mod.add_argument("--date", default=None)
    midday_mod.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    hub_mod = sub.add_parser("hub", help="三报告共用进度页 · 状态与计时")
    hub_mod.add_argument("--date", default=None)
    hub_mod.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    open_mod = sub.add_parser("open", help="启动本地 Web 并打开作战卡（对照老项目 open）")
    open_mod.add_argument("--date", default=None)
    open_mod.add_argument("--no-browser", action="store_true")
    open_mod.add_argument("--settings", action="store_true", help="打开后直接切到设置页")
    open_mod.add_argument("--foreground", action="store_true", help="前台运行服务（Ctrl+C 停止）")
    open_mod.add_argument("--port", type=int, default=8765)

    serve_mod = sub.add_parser("serve", help="本地 Web 服务（作战卡/快照/设置 API）")
    serve_mod.add_argument("--foreground", action="store_true")
    serve_mod.add_argument("--no-browser", action="store_true")
    serve_mod.add_argument("--stop", action="store_true", help="停止后台服务")
    serve_mod.add_argument("--port", type=int, default=8765)

    set_mod = sub.add_parser("settings", help="等同 open --settings")
    set_mod.add_argument("--date", default=None)
    set_mod.add_argument("--no-browser", action="store_true")
    set_mod.add_argument("--foreground", action="store_true")
    set_mod.add_argument("--port", type=int, default=8765)

    reproduce_mod = sub.add_parser("reproduce", help="报告复现 · 校验归档或按层重跑")
    reproduce_mod.add_argument("--slot", required=True, choices=("morning", "midday", "evening"))
    reproduce_mod.add_argument(
        "--phase",
        default="verify",
        choices=("verify", "snapshot", "render", "preprocess", "ai", "full"),
        help="verify=校验缺失; snapshot=写归档清单; render=仅重渲染; preprocess/ai/full=逐层重跑",
    )
    reproduce_mod.add_argument("--force", action="store_true")
    reproduce_mod.add_argument("--date", default=None)

    morning_mod = sub.add_parser("morning", help="早盘集合竞价报告 · pre=9:15采集 / 默认=报告档")
    morning_mod.add_argument("--phase", default="report", choices=("pre", "report"))
    morning_mod.add_argument("--force", action="store_true")
    morning_mod.add_argument("--date", default=None)
    morning_mod.add_argument("--no-open", action="store_true", help="不自动打开浏览器")

    collect_mod = sub.add_parser("collect", help="报告管线 · 第 2 步采集编排")
    collect_mod.add_argument("--slot", default="evening", choices=("evening", "midday"))
    collect_mod.add_argument("--force", action="store_true")
    collect_mod.add_argument("--date", default=None)

    preprocess_mod = sub.add_parser("preprocess", help="报告管线 · 第 3 步本地预处理")
    preprocess_mod.add_argument("--slot", default="evening", choices=("evening", "midday"))
    preprocess_mod.add_argument("--force", action="store_true")
    preprocess_mod.add_argument("--date", default=None)

    generate_mod = sub.add_parser("generate", help="报告管线 · 第 4/5 步 AI+报告")
    generate_mod.add_argument("--slot", default="evening", choices=("evening", "midday"))
    generate_mod.add_argument("--phase", default="all", choices=("all", "ai", "render"))
    generate_mod.add_argument("--force", action="store_true")
    generate_mod.add_argument("--date", default=None)

    auction = sub.add_parser("auction", help="集合竞价走势")
    auction.add_argument("--codes", default="")
    auction.add_argument("--force", action="store_true")
    auction.add_argument("--date", default=None)
    auction.add_argument("--resume", action="store_true", help="保留已采竞价点，续跑剩余时刻")
    auction.add_argument("--simulate", action="store_true")

    intraday = sub.add_parser("intraday", help="全天监控：竞价+正式交易（分段保存，竞价独立文件）")
    intraday.add_argument("--codes", default="")
    intraday.add_argument("--force", action="store_true")
    intraday.add_argument("--date", default=None)
    intraday.add_argument("--simulate", action="store_true")
    intraday.add_argument("--resume", action="store_true", help="跳过已完成分段，续跑未完成段")
    intraday.add_argument("--session", default="all", choices=("all", "auction", "morning", "afternoon"))

    calendar_mod = sub.add_parser("calendar", help="A 股交易日历 · 对照沪深北交易所休市标准")
    calendar_sub = calendar_mod.add_subparsers(dest="calendar_cmd", required=True)
    cal_info = calendar_sub.add_parser("info", help="今日是否交易日、下一交易日")
    cal_info.add_argument("--date", default=None)
    cal_verify = calendar_sub.add_parser("verify", help="对照 akshare 与交易所 2026 休市安排")
    cal_verify.add_argument("--year", default="2026")

    args = parser.parse_args()
    if args.cmd == "cls" and args.cls_cmd == "collect":
        raise SystemExit(cmd_cls_collect(args))
    if args.cmd == "market" and args.market_cmd == "collect":
        raise SystemExit(cmd_market_collect(args))
    if args.cmd == "ecosystem" and args.ecosystem_cmd == "collect":
        raise SystemExit(cmd_market_collect(args))
    if args.cmd == "index" and args.index_cmd == "collect":
        raise SystemExit(cmd_index_collect(args))
    if args.cmd == "flow" and args.flow_cmd == "collect":
        raise SystemExit(cmd_flow_collect(args))
    if args.cmd == "announcement" and args.announcement_cmd == "query":
        raise SystemExit(cmd_announcement_query(args))
    if args.cmd == "news" and args.news_cmd == "query":
        raise SystemExit(cmd_news_query(args))
    if args.cmd == "quote" and args.quote_cmd == "query":
        raise SystemExit(cmd_quote_query(args))
    if args.cmd == "evening":
        raise SystemExit(cmd_evening(args))
    if args.cmd == "eve-news":
        raise SystemExit(cmd_eve_news(args))
    if args.cmd == "midday":
        raise SystemExit(cmd_midday(args))
    if args.cmd == "hub":
        raise SystemExit(cmd_hub(args))
    if args.cmd == "open":
        raise SystemExit(cmd_open(args))
    if args.cmd == "serve":
        raise SystemExit(cmd_serve(args))
    if args.cmd == "settings":
        raise SystemExit(cmd_settings(args))
    if args.cmd == "reproduce":
        raise SystemExit(cmd_reproduce(args))
    if args.cmd == "morning":
        raise SystemExit(cmd_morning(args))
    if args.cmd == "collect":
        raise SystemExit(cmd_collect(args))
    if args.cmd == "preprocess":
        raise SystemExit(cmd_preprocess(args))
    if args.cmd == "generate":
        raise SystemExit(cmd_generate(args))
    if args.cmd == "auction":
        raise SystemExit(cmd_auction(args))
    if args.cmd == "intraday":
        raise SystemExit(cmd_intraday(args))
    if args.cmd == "calendar":
        raise SystemExit(cmd_calendar(args))
    raise SystemExit(2)


if __name__ == "__main__":
    main()
