"""第 5 步 · HTML 触达编排。"""

from __future__ import annotations



import json

from datetime import date

from pathlib import Path

from typing import Any



from core.context_as_of import now_iso

from core.io import atomic_write_text

from core.paths import DATA_DIR, ROOT

from report.evening_html import build_evening_page

from report.push import push_wechat_summary

from report.render import build_evening_render_context



_REPORTS = ROOT / "reports"

_LAST = DATA_DIR / "last_report.json"





def run_evening_render(*, on_date: date | None = None) -> dict[str, Any]:

    cal = on_date or date.today()

    rc = build_evening_render_context(on_date=cal)

    html_text = build_evening_page(rc)

    out_dir = _REPORTS / cal.isoformat()

    out_dir.mkdir(parents=True, exist_ok=True)

    main_path = out_dir / "daily_evening.html"

    atomic_write_text(main_path, html_text)

    atomic_write_text(out_dir / "index.html", html_text)



    push_result: dict[str, Any] = {"outcome": "skip"}

    if rc.get("ai_ok"):

        push_result = push_wechat_summary(rc.get("ai_summary_raw") or "", trade_date=str(rc.get("trade_date")))



    last = {

        "path": str(main_path.relative_to(ROOT)).replace("\\", "/"),

        "slot": "evening",

        "generated_at_iso": now_iso(),

        "context_as_of": rc.get("context_as_of"),

        "ai_ok": rc.get("ai_ok"),

        "push_ok": push_result.get("outcome") == "ok",

    }

    atomic_write_text(_LAST, json.dumps(last, ensure_ascii=False, indent=2))

    from report.archive import save_report_archive

    save_report_archive("evening", cal, report_path=str(main_path))

    return {

        "outcome": "ok",

        "path": str(main_path),

        "index_path": str(out_dir / "index.html"),

        "snapshot_rows": len(rc.get("snapshot_rows") or []),

        "ai_ok": rc.get("ai_ok"),

        "push": push_result,

        "last_report": str(_LAST),

    }





__all__ = ["run_evening_render"]

