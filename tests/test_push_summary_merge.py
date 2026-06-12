"""推送摘要合并单测。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.push_format import format_wechat_push_html
from report.push_summary_merge import merge_push_summary_parts


class PushSummaryMergeTests(unittest.TestCase):
    def test_merge_duplicate_group(self) -> None:
        a = "【想买的】\n603773 沃格光电 | 观望 | 跌停\n000021 深科技 | 等 | 小阳"
        b = "【想买的】\n002273 水晶光电 | 观望 | 偏弱"
        out = merge_push_summary_parts(a, b)
        self.assertEqual(out.count("【想买的】"), 1)
        self.assertIn("603773", out)
        self.assertIn("002273", out)

    def test_normalize_bare_section_title(self) -> None:
        raw = "【高度关注】\n600021 上海电力 | 减 | 弱势\n跌幅达到预期重点关注\n600010 包钢 | 观望 | 待核实"
        out = merge_push_summary_parts(raw)
        self.assertIn("【跌幅达到预期重点关注】", out)
        self.assertIn("600010", out)

    def test_wechat_dynamic_group(self) -> None:
        raw = merge_push_summary_parts(
            "【环境】指数分化。\n【仓位】控仓。\n【操作】聚焦主线。",
            "【高度关注】\n600021 上海电力 | 减 | 弱势",
        )
        html_out = format_wechat_push_html(raw)
        self.assertIn("高度关注", html_out)
        self.assertIn("600021", html_out)


if __name__ == "__main__":
    unittest.main()
