from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.md_html import markdown_to_html


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
        self.assertIn('id="stock-600010"', out)
        self.assertIn('<div class="stock-body">', out)
        self.assertIn('<ul class="prose-list">', out)
        self.assertIn("<strong>上午复盘</strong>", out)
        self.assertIn("<strong>偏弱开盘</strong>", out)
        self.assertLess(out.index("stock-body"), out.index("上午复盘"))


if __name__ == "__main__":
    unittest.main()
