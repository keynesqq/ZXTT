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


if __name__ == "__main__":
    unittest.main()
