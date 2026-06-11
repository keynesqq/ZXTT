"""第 5 步渲染冒烟（可无 AI）。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from evening.render import run_evening_render

_DAY = date(2026, 6, 10)


class TestEveningRender(unittest.TestCase):
    def test_render_without_ai(self) -> None:
        result = run_evening_render(on_date=_DAY)
        self.assertEqual(result.get("outcome"), "ok")
        self.assertEqual(result.get("snapshot_rows"), 35)
        path = Path(result["path"])
        self.assertTrue(path.is_file())
        text = path.read_text(encoding="utf-8")
        self.assertIn("明日作战卡", text)
        self.assertIn("env-strip", text)
        self.assertNotIn("panel-snapshot", text)
        self.assertNotIn("预消化资料", text)
        self.assertIn("高度关注", text)
        self.assertNotIn('data-prose-group="观察"', text)


if __name__ == "__main__":
    unittest.main()
