"""晚间 generate 编排：ai → render。"""
from __future__ import annotations

from datetime import date
from typing import Any

from evening.generate import run_evening_ai
from evening.render import run_evening_render


def run_evening_generate(
    *,
    on_date: date | None = None,
    phase: str = "all",
    force: bool = False,
) -> dict[str, Any]:
    phase = (phase or "all").strip().lower()
    out: dict[str, Any] = {"phases": {}}
    if phase in ("all", "ai"):
        out["phases"]["ai"] = run_evening_ai(on_date=on_date, force=force)
        if phase == "ai":
            out["outcome"] = out["phases"]["ai"].get("outcome", "fail")
            return out
        if out["phases"]["ai"].get("outcome") == "fail":
            out["outcome"] = "fail"
            return out
    if phase in ("all", "render"):
        out["phases"]["render"] = run_evening_render(on_date=on_date)
        out["outcome"] = out["phases"]["render"].get("outcome", "fail")
    return out


__all__ = ["run_evening_generate"]
