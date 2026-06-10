"""午间渲染冒烟（离线，无 AI 也可出页）。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from midday.render import run_midday_render

_DAY = date(2026, 6, 10)


class TestMiddayRender(unittest.TestCase):
    def test_render_page_title(self) -> None:
        result = run_midday_render(on_date=_DAY)
        self.assertEqual(result.get("outcome"), "ok")
        html = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("午间作战卡", html)
        self.assertNotIn("明日作战卡", html)


if __name__ == "__main__":
    unittest.main()
