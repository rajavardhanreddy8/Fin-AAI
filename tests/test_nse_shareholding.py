from __future__ import annotations

import unittest
from datetime import date
from unittest.mock import patch

from stock_research.collectors.base import CollectorError
from stock_research.collectors.nse_shareholding import NSEShareholdingCollector


class NSEShareholdingCollectorTest(unittest.TestCase):
    def test_selects_latest_filing_available_by_as_of_date(self) -> None:
        rows = [
            {
                "date": "30-JUN-2026",
                "submissionDate": "21-JUL-2026",
                "isin": "INE467B01029",
                "symbol": "TCS",
                "pr_and_prgrp": "71.77",
                "public_val": "28.23",
                "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/latest.xml",
            },
            {
                "date": "31-MAR-2026",
                "submissionDate": "21-APR-2026",
                "isin": "INE467B01029",
                "symbol": "TCS",
                "pr_and_prgrp": "71.77",
                "public_val": "28.23",
                "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/older.xml",
            },
        ]
        collector = NSEShareholdingCollector()
        with (
            patch.object(collector, "_fetch_rows", return_value=rows),
            patch(
                "stock_research.collectors.nse_shareholding.read_bytes",
                return_value=b"<xbrl>INE467B01029 promoter 71.77</xbrl>",
            ),
        ):
            document = collector.collect_latest(
                "INE467B01029", "TCS", date(2026, 9, 1)
            )

        self.assertEqual(document.period_end, "2026-06-30")
        self.assertEqual(document.published_at, "2026-07-21")
        self.assertEqual(document.source_tier, "official")
        self.assertEqual(document.source_location, rows[0]["xbrl"])
        self.assertIn("INE467B01029", document.raw_text)

    def test_identity_mismatch_fails_closed(self) -> None:
        rows = [
            {
                "date": "30-JUN-2026",
                "submissionDate": "21-JUL-2026",
                "isin": "INE009A01021",
                "symbol": "TCS",
                "xbrl": "https://nsearchives.nseindia.com/corporate/xbrl/wrong.xml",
            }
        ]
        collector = NSEShareholdingCollector()
        with (
            patch.object(collector, "_fetch_rows", return_value=rows),
            patch(
                "stock_research.collectors.nse_shareholding.read_bytes",
                return_value=b"<xbrl>INE009A01021</xbrl>",
            ),
            self.assertRaisesRegex(CollectorError, "XBRL identity mismatch"),
        ):
            collector.collect_latest("INE467B01029", "TCS", date(2026, 9, 1))


if __name__ == "__main__":
    unittest.main()
