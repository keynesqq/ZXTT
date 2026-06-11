from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.stock_fact_strip import (
    inject_stock_events_footer,
    inject_stock_fact_strips,
    snapshot_rows_by_code,
    stock_events_footer_html,
    stock_fact_strip_html,
)


class StockFactStripTest(unittest.TestCase):
    def test_strip_fields(self) -> None:
        html_out = stock_fact_strip_html(
            {
                "code": "600519",
                "pct_chg": 2.35,
                "pct_5d": -1.2,
                "main_net_yi": 1.23,
                "tags": ["放量", "趋势"],
            }
        )
        self.assertIn("今+2.35%", html_out)
        self.assertIn("5日-1.20%", html_out)
        self.assertIn("主力+1.23亿", html_out)
        self.assertIn("放量", html_out)

    def test_inject_after_h3(self) -> None:
        prose = (
            '<h3 class="stock-heading" id="stock-002594">'
            '<span class="code">002594</span> 比亚迪</h3>'
            "<p>正文</p>"
        )
        by_code = snapshot_rows_by_code(
            [{"code": "002594", "pct_chg": 0.5, "pct_5d": 3.0, "main_net_yi": -0.5, "tags": ["观察"]}]
        )
        out = inject_stock_fact_strips(prose, by_code)
        self.assertIn("stock-fact-inline", out)
        self.assertIn("今+0.50%", out)
        self.assertLess(out.index("stock-fact-inline"), out.index("</h3>"))


    def test_events_footer(self) -> None:
        html_out = stock_events_footer_html(
            {
                "events_display": [
                    {"label": "利空", "title": "解除质押公告", "pub_date": "2026-06-10"},
                ]
            }
        )
        self.assertIn("stock-events-foot", html_out)
        self.assertIn("解除质押公告", html_out)

    def test_inject_events_in_body(self) -> None:
        prose = (
            '<h3 class="stock-heading" id="stock-000066"><span class="code">000066</span> 中国长城</h3>'
            '<div class="stock-body"><p>正文</p></div>'
        )
        by_code = snapshot_rows_by_code(
            [
                {
                    "code": "000066",
                    "events_label": "大利空·待核实 审查调查",
                    "events_display": [
                        {
                            "label": "大利空·待核实",
                            "title": "审查调查",
                            "unverified": True,
                        }
                    ],
                }
            ]
        )
        out = inject_stock_events_footer(prose, by_code)
        self.assertIn("stock-events-foot", out)
        self.assertLess(out.index("正文"), out.index("stock-events-foot"))


if __name__ == "__main__":
    unittest.main()
