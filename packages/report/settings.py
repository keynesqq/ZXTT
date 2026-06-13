"""设置页：读取/保存 config.yaml（对照 ZXReport settings.py）。"""
from __future__ import annotations

from copy import deepcopy

from core.config import load_config, mutate_config, ths_cfg
from core.trading_calendar import trading_day_info
from watchlist.loader import watchlist_group_names, watchlist_source_summary
from watchlist.ths_blocks import ThsBlocksError, list_all_blocks, resolve_account_dir

SLOT_SCRIPTS = (
    "evening",
    "morning_pre",
    "morning_auction",
    "morning_open",
    "midday_snapshot",
    "midday",
)

DEFAULT_SLOTS = {
    "evening": {"enabled": False, "time": "22:00", "label": "晚间收盘卡"},
    "morning_pre": {"enabled": False, "time": "09:15", "label": "盘前·竞价前采集"},
    "morning_auction": {"enabled": False, "time": "09:15:05", "label": "盘前·竞价"},
    "morning_open": {"enabled": False, "time": "09:25", "label": "开盘核对卡"},
    "midday_snapshot": {"enabled": False, "time": "11:35", "label": "午间·上午快照"},
    "midday": {"enabled": False, "time": "12:50", "label": "午间作战卡"},
}

DEFAULT_ANNOUNCEMENT = {
    "lookback_days": 30,
    "fallback_latest_count": 5,
    "max_count": 0,
}

VALID_SCOPES = frozenset({"schedule", "announcement", "watchlist"})


def _announcement_settings(cfg: dict) -> dict:
    ann = (cfg.get("feeds") or {}).get("announcement") or {}
    return {
        "lookback_days": int(ann.get("lookback_days", DEFAULT_ANNOUNCEMENT["lookback_days"])),
        "fallback_latest_count": int(
            ann.get("fallback_latest_count", DEFAULT_ANNOUNCEMENT["fallback_latest_count"])
        ),
        "max_count": int(ann.get("max_count", DEFAULT_ANNOUNCEMENT["max_count"])),
    }


def _parse_announcement_settings(payload: dict) -> dict:
    raw = payload.get("announcement") or {}
    days = int(raw.get("lookback_days", DEFAULT_ANNOUNCEMENT["lookback_days"]))
    latest = int(raw.get("fallback_latest_count", DEFAULT_ANNOUNCEMENT["fallback_latest_count"]))
    max_count = int(raw.get("max_count", DEFAULT_ANNOUNCEMENT["max_count"]))
    if days < 1 or days > 365:
        raise ValueError("公告回溯天数须在 1–365 之间")
    if latest < 1 or latest > 50:
        raise ValueError("公告备用条数须在 1–50 之间")
    if max_count < 0 or max_count > 200:
        raise ValueError("公告最多展示条数须在 0–200 之间（0 表示不限制）")
    return {
        "lookback_days": days,
        "fallback_latest_count": latest,
        "max_count": max_count,
    }


def _selected_names(ab: dict | None) -> set[str]:
    if not ab:
        return set()
    return {str(x).strip() for x in (ab.get("by_name") or []) if str(x).strip()}


def _ordered_names(ab: dict | None) -> list[str]:
    if not ab:
        return []
    return [str(x).strip() for x in (ab.get("by_name") or []) if str(x).strip()]


def _sort_blocks_by_config_order(blocks: list[dict], preferred: list[str]) -> list[dict]:
    rank = {name: i for i, name in enumerate(preferred)}
    return sorted(
        blocks,
        key=lambda b: (rank.get(str(b.get("group_name") or ""), 10_000), str(b.get("group_name") or "")),
    )


def _apply_schedule(cfg: dict, payload: dict) -> None:
    schedule = cfg.setdefault("schedule", {})
    schedule["sync_windows_tasks"] = False

    slots_in = payload.get("slots") or {}
    slots_cfg = schedule.setdefault("slots", {})
    for slot_id in SLOT_SCRIPTS:
        s = slots_in.get(slot_id) or {}
        base = DEFAULT_SLOTS[slot_id]
        prev = slots_cfg.get(slot_id) or {}
        slots_cfg[slot_id] = {
            "enabled": bool(s.get("enabled", prev.get("enabled", base["enabled"]))),
            "time": str(s.get("time") or prev.get("time") or base["time"]).strip(),
            "label": str(prev.get("label") or base["label"]).strip(),
        }


def _apply_announcement(cfg: dict, payload: dict) -> dict:
    ann = _parse_announcement_settings(payload)
    feeds = cfg.setdefault("feeds", {})
    ann_cfg = feeds.setdefault("announcement", {})
    ann_cfg["lookback_days"] = ann["lookback_days"]
    ann_cfg["fallback_latest_count"] = ann["fallback_latest_count"]
    ann_cfg["max_count"] = ann["max_count"]
    if not ann_cfg.get("fallback"):
        ann_cfg["fallback"] = "akshare"
    return ann


def _apply_watchlist(cfg: dict, payload: dict) -> tuple[list[str], list[str]]:
    ths = cfg.setdefault("ths", {})
    schedule = cfg.setdefault("schedule", {})

    watchlist = [str(x).strip() for x in (payload.get("watchlist_blocks") or []) if str(x).strip()]
    if not watchlist:
        raise ValueError("请至少勾选一个自选板块")

    ths["analyze_blocks"] = {"by_name": watchlist}
    schedule["analyze_blocks"] = {"by_name": list(watchlist)}
    return watchlist, list(watchlist)


def get_announcement_settings(cfg: dict | None = None) -> dict:
    return _announcement_settings(cfg or load_config())


def build_settings_view() -> dict:
    cfg = load_config()
    ths = ths_cfg()
    schedule = cfg.get("schedule") or {}
    wl_names_set = _selected_names(ths.get("analyze_blocks"))
    auto_names_set = _selected_names(schedule.get("analyze_blocks")) or wl_names_set
    wl_order = watchlist_group_names()
    auto_order = _ordered_names(schedule.get("analyze_blocks")) or wl_order

    blocks: list[dict] = []
    account_dir = ""
    blocks_error = ""
    try:
        account_dir = str(resolve_account_dir())
        for p in list_all_blocks():
            blocks.append(
                {
                    "block_id": p.block_id,
                    "group_name": p.group_name,
                    "count": len(p.codes),
                    "mtime": p.mtime,
                    "watchlist": p.group_name in wl_names_set,
                    "auto_analyze": p.group_name in auto_names_set,
                }
            )
        blocks = _sort_blocks_by_config_order(blocks, wl_order)
    except ThsBlocksError as e:
        blocks_error = str(e)

    slots = []
    merged = deepcopy(DEFAULT_SLOTS)
    merged.update(schedule.get("slots") or {})
    for slot_id in SLOT_SCRIPTS:
        s = merged.get(slot_id) or DEFAULT_SLOTS[slot_id]
        slots.append(
            {
                "id": slot_id,
                "label": s.get("label") or DEFAULT_SLOTS[slot_id]["label"],
                "time": s.get("time") or DEFAULT_SLOTS[slot_id]["time"],
                "enabled": bool(s.get("enabled", False)),
            }
        )

    return {
        "account_dir": account_dir,
        "blocks": blocks,
        "blocks_error": blocks_error,
        "slots": slots,
        "sync_windows_tasks": False,
        "watchlist_names": wl_order,
        "auto_names": [n for n in auto_order if n in auto_names_set],
        "announcement": get_announcement_settings(cfg),
        "trading_calendar": trading_day_info(),
        "watchlist_source": watchlist_source_summary(),
    }


def apply_settings(payload: dict) -> dict:
    scope = str(payload.get("scope") or "").strip()
    if scope not in VALID_SCOPES:
        raise ValueError("无效的保存范围，请使用 schedule / announcement / watchlist")

    result: dict = {"ok": True, "scope": scope}
    ann: dict | None = None
    watchlist: list[str] | None = None
    auto_analyze: list[str] | None = None

    def _mut(cfg: dict) -> None:
        nonlocal ann, watchlist, auto_analyze
        cfg.setdefault("ths", {})
        cfg.setdefault("schedule", {})
        if scope == "schedule":
            _apply_schedule(cfg, payload)
        elif scope == "announcement":
            ann = _apply_announcement(cfg, payload)
        elif scope == "watchlist":
            watchlist, auto_analyze = _apply_watchlist(cfg, payload)

    mutate_config(_mut)

    if watchlist is not None:
        result["watchlist_blocks"] = watchlist
        result["auto_analyze_blocks"] = auto_analyze
        from watchlist.refresh import refresh_watchlist_pages

        refresh_info = refresh_watchlist_pages(fetch_quotes=True)
        result["refresh"] = refresh_info
        if refresh_info.get("quote_error"):
            result["quote_warning"] = refresh_info["quote_error"]

    if ann is not None:
        result["announcement"] = ann

    from report.hub import publish_settings

    publish_settings()
    return result


__all__ = [
    "SLOT_SCRIPTS",
    "apply_settings",
    "build_settings_view",
    "get_announcement_settings",
]
