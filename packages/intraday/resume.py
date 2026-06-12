"""分段完成检测与 --resume 续跑。"""
from __future__ import annotations

from datetime import date

from core.phase_complete import auction_phase_complete
from intraday.digest import digest_segment_complete
from intraday.series import load_intraday_segment

PHASES = ("auction", "morning", "afternoon")


def intraday_segment_complete(on_date: date, segment: str) -> bool:
    points = load_intraday_segment(on_date=on_date, segment=segment)
    return digest_segment_complete(points, segment=segment)


def phase_complete(phase: str, on_date: date) -> bool:
    if phase == "auction":
        return auction_phase_complete(on_date)
    if phase in ("morning", "afternoon"):
        return intraday_segment_complete(on_date, phase)
    return False


def phase_status(on_date: date) -> dict[str, bool]:
    return {p: phase_complete(p, on_date) for p in PHASES}


def resolve_phases(*, session: str, resume: bool, on_date: date) -> list[str]:
    if session != "all":
        if resume and phase_complete(session, on_date):
            return []
        return [session]
    if not resume:
        return list(PHASES)
    status = phase_status(on_date)
    return [p for p in PHASES if not status.get(p)]
