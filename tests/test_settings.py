"""设置页逻辑冒烟。"""
from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from core.paths import CONFIG_PATH


class SettingsTests(unittest.TestCase):
    def test_apply_schedule_writes_config(self) -> None:
        from report.settings import apply_settings

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            cfg_path.write_text(
                "schedule:\n  slots:\n    evening:\n      enabled: false\n      time: '22:00'\n",
                encoding="utf-8",
            )
            with patch("core.config.CONFIG_PATH", cfg_path):
                result = apply_settings(
                    {
                        "scope": "schedule",
                        "slots": {"evening": {"enabled": True, "time": "21:30"}},
                    }
                )
            self.assertTrue(result["ok"])
            text = cfg_path.read_text(encoding="utf-8")
            self.assertIn("enabled: true", text.lower())
            self.assertIn("21:30", text)

    def test_apply_announcement_validates_range(self) -> None:
        from report.settings import apply_settings

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            cfg_path.write_text("feeds:\n  announcement:\n    lookback_days: 3\n", encoding="utf-8")
            with patch("core.config.CONFIG_PATH", cfg_path):
                with self.assertRaises(ValueError):
                    apply_settings({"scope": "announcement", "announcement": {"lookback_days": 0}})

    def test_apply_watchlist_requires_selection(self) -> None:
        from report.settings import apply_settings

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.yaml"
            cfg_path.write_text("ths:\n  analyze_blocks:\n    by_name:\n    - 我的\n", encoding="utf-8")
            with patch("core.config.CONFIG_PATH", cfg_path):
                with self.assertRaises(ValueError):
                    apply_settings({"scope": "watchlist", "watchlist_blocks": [], "auto_analyze_blocks": []})

    def test_build_settings_view_uses_legacy_ths(self) -> None:
        from report.settings import build_settings_view

        legacy_ths = {"account_dir": "D:\\ths\\mo_test", "analyze_blocks": {"by_name": ["我的"]}}
        with patch("core.config.load_config", return_value={"legacy": {"zxreport_config": "x"}}):
            with patch("core.config.ths_cfg", return_value=legacy_ths):
                with patch("report.settings.list_all_blocks", return_value=[]):
                    with patch("report.settings.resolve_account_dir", return_value=Path("D:/ths/mo_test")):
                        view = build_settings_view()
        self.assertEqual(view["account_dir"], "D:\\ths\\mo_test")
        self.assertEqual(view["blocks_error"], "")

    def test_build_settings_page_contains_tabs(self) -> None:
        from report.settings_html import build_settings_page

        html = build_settings_page(
            {
                "account_dir": "",
                "blocks": [],
                "blocks_error": "",
                "slots": [{"id": "evening", "label": "晚间", "time": "22:00", "enabled": False}],
                "announcement": {"lookback_days": 30, "fallback_latest_count": 5, "max_count": 0},
                "watchlist_names": [],
                "auto_names": [],
                "sync_windows_tasks": False,
                "trading_calendar": {},
            }
        )
        self.assertIn("settings-panel-schedule", html)
        self.assertIn("settings-panel-watchlist", html)
        self.assertIn("保存报告时间点", html)

    @unittest.skipUnless(CONFIG_PATH.is_file(), "需要本地 config.yaml")
    def test_mutate_config_roundtrip(self) -> None:
        from core.config import load_config, mutate_config

        before = load_config()
        key = "_zxtt_settings_test"
        try:

            def _mut(cfg: dict) -> None:
                cfg[key] = True

            mutate_config(_mut)
            self.assertTrue(load_config().get(key))

            def _clear(cfg: dict) -> None:
                cfg.pop(key, None)

            mutate_config(_clear)
        finally:
            if before.get(key) is None:

                def _cleanup(cfg: dict) -> None:
                    cfg.pop(key, None)

                mutate_config(_cleanup)


if __name__ == "__main__":
    unittest.main()
