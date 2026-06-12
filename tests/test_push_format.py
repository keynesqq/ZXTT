"""微信推送摘要排版单测。"""
from __future__ import annotations

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.push_format import format_wechat_push_html


class PushFormatTests(unittest.TestCase):
    def test_morning_order_and_surprise(self) -> None:
        raw = (
            "**【环境】**\n大盘高开。\n"
            "**【9:15素材】**\n- **600010 包钢股份**：事故调查。\n"
            "**【超预期】**\n- **超预期偏强**：中科曙光。\n"
            "**【我的】**\n- **600010 包钢股份**：观望。\n"
            "**【想买的】**\n- **000021 深科技**：不追。\n"
            "**【操作】**\n9:30后不宜追涨。\n"
        )
        out = format_wechat_push_html(raw, slot="morning")
        self.assertNotIn("9:15素材", out)
        self.assertIn("超 预 期", out)
        self.assertIn("中科曙光", out)
        self.assertLess(out.index("操 作"), out.index("我 的"))
        self.assertNotIn("包钢股份**", out)

    def test_midday_merge_position_into_operation(self) -> None:
        raw = "【环境】普涨。\n【仓位】维持不追高。\n【操作】下午去弱留强。\n【我的】600010 观望。"
        out = format_wechat_push_html(raw, slot="midday")
        self.assertNotIn("仓 位", out)
        self.assertIn("维持不追高", out)
        self.assertIn("去弱留强", out)

    def test_evening_compact_stock_lines(self) -> None:
        raw = (
            "【环境】涨停89只。\n【仓位】中性。\n【操作】去弱留强。\n"
            "【我的】\n大利空 600010·包钢 | 减\n"
            "【想买的】\n轻多 000762·西藏矿业 | 试 | 逆势放量"
        )
        out = format_wechat_push_html(raw, slot="evening")
        self.assertIn("600010", out)
        self.assertIn("000762", out)
        self.assertLess(out.index("仓 位"), out.index("操 作"))
        self.assertLess(out.index("操 作"), out.index("我 的"))

    def test_midday_operation_multiline(self) -> None:
        raw = (
            "【环境】普涨。\n【仓位】第一行仓位\n第二行仓位\n"
            "【操作】第一行操作\n第二行操作\n【我的】600010 观望"
        )
        out = format_wechat_push_html(raw, slot="midday")
        self.assertIn("white-space:pre-wrap", out)
        self.assertIn("第一行仓位", out)
        self.assertIn("第二行操作", out)

    def test_line_kind_no_false_positive(self) -> None:
        raw = "【我的】\n600021 上海电力 等待企稳\n600160 巨化股份 持股观察"
        out = format_wechat_push_html(raw, slot="evening")
        self.assertNotIn("#fff5f5", out)
        self.assertNotIn("#f0faf4", out)

    def test_line_kind_pipe_action(self) -> None:
        raw = "【我的】\n600010 包钢 | 减\n600160 巨化 | 守"
        out = format_wechat_push_html(raw, slot="evening")
        self.assertIn("#fff5f5", out)
        self.assertIn("#f0faf4", out)

    def test_live_morning_summary(self) -> None:
        path = ROOT / "data" / "scheduled_ai" / "morning_2026-06-12.json"
        if not path.is_file():
            self.skipTest("no morning fixture")
        summary = json.loads(path.read_text(encoding="utf-8"))["summary"]
        out = format_wechat_push_html(summary, slot="morning")
        self.assertIn("超 预 期", out)
        self.assertNotIn("9:15素材", out)
        self.assertNotIn("**", out)
        self.assertLess(out.index("操 作"), out.index("我 的"))


if __name__ == "__main__":
    unittest.main()
