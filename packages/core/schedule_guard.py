"""时段守卫：段首等待、段尾报错、段内/续跑只采剩余时刻。"""
from __future__ import annotations

from datetime import date, datetime
from zoneinfo import ZoneInfo

from core.trading_calendar import today_cn

_CN_TZ = ZoneInfo("Asia/Shanghai")

_PHASE_LABEL = {
    "auction": "竞价",
    "morning": "上午",
    "afternoon": "下午",
}


def phase_label(phase: str) -> str:
    return _PHASE_LABEL.get(phase, phase)


def sleep_until(target: datetime) -> None:
    now = datetime.now(_CN_TZ)
    sec = (target - now).total_seconds()
    if sec > 0:
        import time

        time.sleep(sec)


_sleep_until = sleep_until


def _point_time_key(point: dict) -> str | None:
    raw = str(point.get("captured_at") or "")
    if len(raw) >= 19:
        return raw[11:19]
    return None


def _collected_time_keys(points: list[dict]) -> set[str]:
    keys: set[str] = set()
    for point in points:
        key = _point_time_key(point)
        if key:
            keys.add(key)
    return keys


def _pending_after_existing(
    schedule: list[datetime],
    existing_points: list[dict],
    live: list[datetime],
) -> list[datetime]:
    collected = _collected_time_keys(existing_points)
    if collected:
        pending = [t for t in schedule if t.strftime("%H:%M:%S") not in collected]
    else:
        pending = schedule[len(existing_points) :] if existing_points else list(schedule)
    if not pending:
        return []
    live_at = {t.strftime("%H:%M:%S") for t in live}
    merged = [t for t in pending if t.strftime("%H:%M:%S") in live_at]
    if merged:
        return merged
    now = datetime.now(_CN_TZ)
    return [t for t in pending if t >= now]


def prepare_live_schedule(
    schedule: list[datetime],
    *,
    phase: str,
    force: bool,
    on_date: date | None = None,
) -> list[datetime]:
    if force or not schedule:
        return schedule
    day = on_date or schedule[0].date()
    if day != today_cn():
        return schedule
    label = phase_label(phase)
    start, end = schedule[0], schedule[-1]
    now = datetime.now(_CN_TZ)
    if now > end:
        raise RuntimeError(
            f"{label}时段已结束（{end.strftime('%H:%M:%S')}），请用 --force 验通路或次日再跑"
        )
    _sleep_until(start)
    now = datetime.now(_CN_TZ)
    remaining = [t for t in schedule if t >= now]
    if not remaining:
        raise RuntimeError(f"{label}时段内无剩余采样点，请用 --force 验通路")
    return remaining


def resolve_collect_schedule(
    schedule: list[datetime],
    *,
    phase: str,
    force: bool,
    on_date: date | None = None,
    resume: bool = False,
    existing_points: list[dict] | None = None,
) -> list[datetime]:
    """段首/段内守卫；续跑时按已采时刻（非纯计数）跳过计划点。"""
    if force or not schedule:
        return schedule
    live = prepare_live_schedule(schedule, phase=phase, force=False, on_date=on_date)
    points = existing_points or []
    if not resume or not points:
        return live
    return _pending_after_existing(schedule, points, live)


def require_collect_schedule(
    schedule: list[datetime],
    *,
    phase: str,
    force: bool,
    on_date: date | None = None,
    resume: bool = False,
    existing_points: list[dict] | None = None,
    incomplete: bool = False,
) -> list[datetime]:
    live = resolve_collect_schedule(
        schedule,
        phase=phase,
        force=force,
        on_date=on_date,
        resume=resume,
        existing_points=existing_points,
    )
    if not live and incomplete and resume and not force:
        label = phase_label(phase)
        raise RuntimeError(f"{label}段尚有未完成数据且无剩余采样点，请用 --force 验通路")
    return live
