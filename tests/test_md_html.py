from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.md_html import markdown_to_html, push_summary_to_html


class MdHtmlTest(unittest.TestCase):
    def test_stock_list_and_body(self) -> None:
        md = (
            "### 600010 包钢股份\n"
            "- **上午复盘**：收跌1.29%。\n"
            "- **午后研判**：午后情景预判：\n"
            "  - **偏弱开盘**：留意支撑。\n"
            "  - **基准或偏强开盘**：窄幅修复。\n"
            "- 下午以观察为主。"
        )
        out = markdown_to_html(md, stock_body=True)
        self.assertIn('<details class="stock-block">', out)
        self.assertIn('<summary class="stock-heading"', out)
        self.assertIn('id="stock-600010"', out)
        self.assertIn('<div class="stock-body">', out)
        self.assertIn('<ul class="prose-list">', out)
        self.assertIn("<strong>上午复盘</strong>", out)
        self.assertIn("<strong>偏弱开盘</strong>", out)
        self.assertLess(out.index("stock-body"), out.index("上午复盘"))

    def test_push_summary_sections(self) -> None:
        raw = (
            "【环境】沪指微跌，市场分化。\n"
            "【操作】下午观察承接。**分析时刻**：2026-06-11 16:20:50\n"
            "【我的】包钢股份 阴跌观望；巨化股份 阳线可跟踪\n"
            "【想买的】000021 深科技涨1.46%关注支撑；000066 中国长城跌3.28%观望"
        )
        out = push_summary_to_html(raw)
        self.assertIn("push-section-global", out)
        self.assertIn("push-section-portfolio", out)
        self.assertIn("push-stock-list", out)
        self.assertIn("push-code", out)
        self.assertIn("000021", out)
        self.assertIn("分析时刻", out)
        self.assertNotIn("push-row", out)

    def test_push_summary_operation_nested_brackets(self) -> None:
        raw = (
            "**【操作】**\n"
            "9:30后不宜追涨。对于【我的】持仓应减仓。对于【想买的】，等换手后再动。\n"
            "---"
        )
        out = push_summary_to_html(raw)
        self.assertEqual(out.count("push-section-label"), 1)
        self.assertIn("对于【我的】持仓应减仓", out)
        self.assertNotIn("---", out)

    def test_push_summary_morning_bullet_stocks(self) -> None:
        raw = (
            "**【我的】**\n"
            "- **600010 包钢股份**：高开不追，弱势震荡。\n"
            "- **603773 沃格光电**：低开走弱，考虑减仓。\n"
        )
        out = push_summary_to_html(raw)
        self.assertIn("push-code", out)
        self.assertIn("600010", out)
        self.assertNotIn("push-stock-link", out)
        self.assertNotIn("push-stock-text\"></span></li>", out)

    def test_push_summary_section_order_and_hide_material(self) -> None:
        raw = (
            "**【环境】**\n大盘高开。\n"
            "**【9:15素材】**\n- **600010 包钢股份**：事故调查。\n"
            "**【超预期】**\n- **超预期偏强**：中科曙光。\n"
            "**【我的】**\n- **600010 包钢股份**：观望。\n"
            "**【想买的】**\n- **000021 深科技**：不追。\n"
            "**【操作】**\n9:30后不宜追涨。\n"
        )
        out = push_summary_to_html(raw)
        self.assertNotIn("9:15素材", out)
        self.assertLess(out.index("超预期"), out.index("操作"))
        self.assertLess(out.index("操作"), out.index("我的"))
        self.assertLess(out.index("我的"), out.index("想买的"))

    def test_push_summary_analysis_time_in_footer(self) -> None:
        raw = "**分析时刻**：2026-06-12 09:25:06\n\n**【环境】**\n低开。"
        out = push_summary_to_html(raw)
        self.assertIn("push-meta", out)
        self.assertIn("2026-06-12 09:25:06", out)
        self.assertNotIn("push-lead", out)

    def test_push_summary_midday_position_alias(self) -> None:
        raw = "【环境】普涨。\n【仓位】维持不追高。\n【我的】600010 观望。"
        out = push_summary_to_html(raw, label_aliases={"仓位": "操作"})
        self.assertIn(">操作</span>", out)
        self.assertNotIn(">仓位</span>", out)
        self.assertIn("维持不追高", out)


if __name__ == "__main__":
    unittest.main()
