"""晚间 live 进度页单测。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.evening_live import build_evening_live_page, build_run_status_js


class TestEveningLive(unittest.TestCase):
    def test_live_page_has_progress(self) -> None:
        html = build_evening_live_page(
            {
                "trade_date": "2026-06-10",
                "status": "running",
                "started_at": "2026-06-10 22:00:00",
                "current_step": "ai",
                "current_label": "④ AI 研判合成",
                "detail": "分片完成：holding（4 只）",
                "progress_pct": 55,
                "steps_done": ["collect", "preprocess"],
            }
        )
        self.assertIn("applyRunStatus", html)
        self.assertIn("pollViaFetch", html)
        self.assertIn("run-steps", html)
        self.assertIn("switchToReport", html)
        js = build_run_status_js({"status": "running", "progress_pct": 55, "seq": 1})
        self.assertIn("applyRunStatus", js)


if __name__ == "__main__":
    unittest.main()
