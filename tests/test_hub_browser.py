"""共用进度页 · 浏览器按报告档位只开一次。"""
from __future__ import annotations

import json
import sys
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report import hub as hub_mod


class TestHubBrowser(unittest.TestCase):
    def setUp(self) -> None:
        self._marker = hub_mod._BROWSER_MARKER
        if self._marker.is_file():
            self._marker.unlink()

    def tearDown(self) -> None:
        if self._marker.is_file():
            self._marker.unlink()

    @patch.object(hub_mod, "webbrowser")
    @patch.object(hub_mod, "publish_hub")
    def test_first_open_launches_browser(self, _pub, mock_wb) -> None:
        day = date(2026, 6, 11)
        url = hub_mod.open_hub(day, open_browser=True, slot="morning")
        self.assertIn("2026-06-11", url)
        mock_wb.open.assert_called_once()
        session = json.loads(self._marker.read_text(encoding="utf-8"))
        self.assertIn("morning", session["slots"])

    @patch.object(hub_mod, "webbrowser")
    @patch.object(hub_mod, "publish_hub")
    def test_same_slot_skips_second_open(self, _pub, mock_wb) -> None:
        day = date(2026, 6, 11)
        hub_mod.open_hub(day, open_browser=True, slot="midday")
        mock_wb.open.reset_mock()
        hub_mod.open_hub(day, open_browser=True, slot="midday")
        mock_wb.open.assert_not_called()

    @patch.object(hub_mod, "webbrowser")
    @patch.object(hub_mod, "publish_hub")
    def test_different_slot_opens_again(self, _pub, mock_wb) -> None:
        day = date(2026, 6, 11)
        hub_mod.open_hub(day, open_browser=True, slot="morning")
        mock_wb.open.reset_mock()
        hub_mod.open_hub(day, open_browser=True, slot="midday")
        mock_wb.open.assert_called_once()


if __name__ == "__main__":
    unittest.main()
