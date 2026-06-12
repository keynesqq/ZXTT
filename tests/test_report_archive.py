"""报告归档与复现。"""
from __future__ import annotations

import sys
import unittest
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.archive import (
    archive_path,
    build_report_archive,
    reproduce_report,
    save_report_archive,
    verify_report_archive,
)


class TestReportArchive(unittest.TestCase):
    def test_evening_archive_lists_layers(self) -> None:
        archive = build_report_archive("evening", date(2026, 6, 12))
        self.assertEqual(archive["slot"], "evening")
        self.assertIn("L0_raw", archive["layers"])
        self.assertIn("L2_ai", archive["layers"])
        roles = {f["role"] for f in archive["files"]}
        self.assertIn("evening_context", roles)
        self.assertIn("scheduled_ai", roles)

    def test_verify_evening_render_ready(self) -> None:
        result = verify_report_archive("evening", date(2026, 6, 12), min_layer="L2_ai")
        self.assertEqual(result["outcome"], "ok")
        self.assertEqual(result["missing"], [])

    def test_save_snapshot(self) -> None:
        path = save_report_archive("midday", date(2026, 6, 12))
        self.assertTrue(path.is_file())
        self.assertEqual(archive_path(date(2026, 6, 12), "midday"), path)

    def test_morning_has_paths_in_archive(self) -> None:
        archive = build_report_archive("morning", date(2026, 6, 12))
        roles = {f["role"] for f in archive["files"]}
        self.assertIn("auction_trend", roles)
        self.assertIn("morning_context", roles)

    def test_reproduce_verify_writes_archive(self) -> None:
        result = reproduce_report("evening", date(2026, 6, 12), phase="verify")
        self.assertEqual(result["outcome"], "ok")
        self.assertTrue(archive_path(date(2026, 6, 12), "evening").is_file())


if __name__ == "__main__":
    unittest.main()
