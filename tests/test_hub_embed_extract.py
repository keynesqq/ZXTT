"""hub_embed_extract 单元测试。"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "packages"))

from report.hub_embed_extract import extract_report_chunk


class TestHubEmbedExtract(unittest.TestCase):
    def test_extract_evening_report(self) -> None:
        path = ROOT / "reports" / "2026-06-12" / "daily_evening.html"
        if not path.is_file():
            self.skipTest("no sample evening report")
        chunk = extract_report_chunk(path)
        self.assertIsNotNone(chunk)
        assert chunk is not None
        self.assertTrue(chunk["rev"])
        html = chunk["html"]
        self.assertIn("report-chunk", html)
        self.assertIn("hero", html)
        self.assertNotIn("hub_embed_child", html)
        self.assertIn("<script", html)

    def test_extract_legacy_morning_html(self) -> None:
        for rel in (
            "reports/2026-06-10/daily_morning.html",
            "reports/2099-01-02/daily_morning.html",
        ):
            path = ROOT / rel
            if not path.is_file():
                continue
            chunk = extract_report_chunk(path)
            self.assertIsNotNone(chunk, rel)
            assert chunk is not None
            self.assertIn("report-chunk", chunk["html"])

    def test_missing_file(self) -> None:
        path = ROOT / "reports" / "2099-01-01" / "daily_evening.html"
        self.assertIsNone(extract_report_chunk(path))

    def test_wrap_class_variants(self) -> None:
        for sample in (
            '<html><body><div class="wrap report-root"><p>x</p></div><script>a()</script></body></html>',
            "<html><body><div class='wrap'><p>y</p></div><script>b()</script></body></html>",
        ):
            chunk = extract_report_chunk_from_html(sample)
            self.assertIsNotNone(chunk)
            assert chunk is not None
            self.assertIn("report-chunk", chunk["html"])


def extract_report_chunk_from_html(raw: str) -> dict[str, str] | None:
    import tempfile

    from report.hub_embed_extract import extract_report_chunk

    with tempfile.NamedTemporaryFile("w", suffix=".html", delete=False, encoding="utf-8") as f:
        f.write(raw)
        path = Path(f.name)
    try:
        return extract_report_chunk(path)
    finally:
        path.unlink(missing_ok=True)


if __name__ == "__main__":
    unittest.main()
