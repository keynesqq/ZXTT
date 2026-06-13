from __future__ import annotations

import copy
import threading
from collections.abc import Callable
from pathlib import Path

import yaml
from dotenv import load_dotenv

from core.io import atomic_write_text
from core.paths import CONFIG_PATH, ROOT

_config_lock = threading.Lock()


def load_config() -> dict:
    load_dotenv(ROOT / ".env")
    if not CONFIG_PATH.is_file():
        return {}
    with CONFIG_PATH.open(encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


def load_config_cached() -> dict:
    return copy.deepcopy(load_config())


def save_config(cfg: dict) -> None:
    text = yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False, default_flow_style=False)
    atomic_write_text(CONFIG_PATH, text)


def mutate_config(mutator: Callable[[dict], None]) -> dict:
    """在进程内串行 load → mutator → save，避免并发写 config 互相覆盖。"""
    with _config_lock:
        cfg = load_config()
        mutator(cfg)
        save_config(cfg)
        return cfg


def normalize_code(code: str) -> str:
    return str(code).zfill(6)


def auction_cfg() -> dict:
    return load_config().get("auction") or {}


def intraday_cfg() -> dict:
    return load_config().get("intraday") or {}


def quote_cfg() -> dict:
    return load_config().get("quote") or {}


def _merge_section_dict(base: dict, override: dict) -> dict:
    out = dict(base)
    for key, val in override.items():
        if isinstance(val, dict) and isinstance(out.get(key), dict):
            out[key] = {**out[key], **val}
        else:
            out[key] = val
    return out


def index_cfg() -> dict:
    local = load_config().get("index") or {}
    market = load_config().get("market") or {}
    fallback: dict = {
        "enabled": bool(market.get("index_enabled", True)),
        "symbols": market.get("index_symbols"),
    }
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def flow_cfg() -> dict:
    local = load_config().get("flow") or {}
    fallback: dict = {
        "enabled": True,
        "primary": "eastmoney_direct",
        "fallback": "eastmoney_akshare",
        "watchlist_enabled": True,
        "sector_top_n": 10,
        "sector_max_pages": 3,
        "stock_rank_max_pages": 80,
        "watchlist_workers": 4,
        "watchlist_missing_warn": True,
    }
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def market_cfg() -> dict:
    local = load_config().get("market") or {}
    legacy = legacy_config_path()
    if not legacy:
        return local
    try:
        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
    except OSError:
        return local
    ext_market = ext.get("market") or {}
    if not ext_market:
        return local
    if not local:
        return ext_market
    return _merge_section_dict(ext_market, local)


def feeds_cfg() -> dict:
    local = load_config().get("feeds") or {}
    legacy = legacy_config_path()
    if not legacy:
        return local
    try:
        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
    except OSError:
        return local
    ext_feeds = ext.get("feeds") or {}
    if not ext_feeds:
        return local
    if not local:
        return ext_feeds
    return _merge_section_dict(ext_feeds, local)


def news_cfg() -> dict:
    """资讯 query 配置；本地 news 段覆盖，缺省只读继承 feeds 对应键。"""
    local = load_config().get("news") or {}
    feeds = feeds_cfg()
    news_block = feeds.get("news") or {}
    research_block = feeds.get("research") or {}
    industry_block = feeds.get("industry_news") or {}
    fallback: dict = {
        "lookback_days": int(news_block.get("lookback_days", research_block.get("lookback_days", 7))),
        "max_count": 0,
        "industry_enabled": True,
        "ths_f10": dict(feeds.get("ths_f10") or {"enabled": True, "trigger": "on_empty"}),
        "max_workers": int(feeds.get("max_workers", 4)),
        "akshare_timeout_sec": feeds.get("akshare_timeout_sec", 45),
        "opinion": dict(feeds.get("opinion") or {}),
        "research": {"lookback_days": int(research_block.get("lookback_days", 7))},
        "news": {"lookback_days": int(news_block.get("lookback_days", 7))},
        "industry_news": {"lookback_days": int(industry_block.get("lookback_days", 7))},
    }
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def health_cfg() -> dict:
    local = load_config().get("health") or {}
    legacy = legacy_config_path()
    if not legacy:
        return local
    try:
        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
    except OSError:
        return local
    ext_health = ext.get("health") or {}
    if not ext_health:
        return local
    if not local:
        return ext_health
    return _merge_section_dict(ext_health, local)


def probe_cfg() -> dict:
    local = load_config().get("probe") or {}
    legacy = legacy_config_path()
    if not legacy:
        return local
    try:
        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
    except OSError:
        return local
    ext_probe = ext.get("probe") or {}
    if not ext_probe:
        return local
    if not local:
        return ext_probe
    return _merge_section_dict(ext_probe, local)


def ths_cfg() -> dict:
    cfg = load_config()
    local = cfg.get("ths") or {}
    if (local.get("account_dir") or "").strip():
        return local
    legacy = legacy_config_path()
    if not legacy:
        return local
    try:
        with legacy.open(encoding="utf-8") as f:
            ext = yaml.safe_load(f) or {}
    except OSError:
        return local
    ext_ths = ext.get("ths") or {}
    return {**ext_ths, **local} if ext_ths else local


def midday_cfg() -> dict:
    fallback: dict = {
        "feeds_digest_workers": 8,
        "feeds_digest_content_max": 280,
        "on_digest_fail": "degrade",
        "verify_enabled": True,
        "write_bundle_full": False,
        "preprocess_cls_recollect": False,
        "synthesize_mode": "sharded",
        "synthesize_workers": 4,
        "synthesize_fallback_monolithic": True,
    }
    local = load_config().get("midday") or {}
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def morning_cfg() -> dict:
    fallback: dict = {
        "sla_sec": 120,
        "llm_timeout_sec": 110,
        "wait_auction_max_sec": 15,
        "llm_max_tokens": 4000,
        "on_ai_fail": "error",
    }
    local = load_config().get("morning") or {}
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def evening_cfg() -> dict:
    fallback: dict = {
        "feeds_digest_workers": 8,
        "feeds_digest_content_max": 280,
        "on_digest_fail": "degrade",
        "cls_digest_workers": 3,
        "cls_short_local_threshold": 200,
        "cls_digest_max_tokens": 2500,
        "verify_enabled": True,
        "write_bundle_full": False,
        "preprocess_cls_recollect": False,
        "synthesize_mode": "sharded",
        "synthesize_workers": 4,
        "synthesize_fallback_monolithic": True,
    }
    local = load_config().get("evening") or {}
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def events_cfg() -> dict:
    fallback: dict = {
        "enable_medium": True,
        "display_max": 3,
        "lookback_days": 3,
    }
    local = load_config().get("events") or {}
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def tags_cfg() -> dict:
    fallback: dict = {
        "pct_drop_heavy": -7,
        "pct_drop_mild": -5,
        "pct_rise_heavy": 7,
        "main_net_ratio_heavy": 0.15,
        "main_net_ratio_mild": 0.05,
        "amount_ratio_shrink": 0.7,
        "amount_ratio_expand": 1.3,
        "max_display_tags": 5,
    }
    local = load_config().get("tags") or {}
    if not local:
        return fallback
    return _merge_section_dict(fallback, local)


def legacy_config_path() -> Path | None:
    """可选：只读老项目 ZXReport config.yaml（不修改其源码）。"""
    raw = (load_config().get("legacy") or {}).get("zxreport_config")
    if not raw:
        return None
    path = Path(str(raw)).expanduser()
    return path if path.is_file() else None
