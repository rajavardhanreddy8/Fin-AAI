from __future__ import annotations

import io
import unittest
import zipfile
from datetime import date
from unittest.mock import patch

from stock_research.collectors.base import CollectorError
from stock_research.collectors.nse_eod import NSEBhavcopyCollector, bhavcopy_url


def _archive(csv_text: str) -> bytes:
    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("BhavCopy.csv", csv_text)
    return payload.getvalue()


class NSEBhavcopyCollectorTest(unittest.TestCase):
    def test_collects_official_eq_close_and_volume_by_isin(self) -> None:
        csv_text = (
            "TradDt,ISIN,TckrSymb,SctySrs,ClsPric,TtlTradgVol\n"
            "2026-08-31,INE467B01029,TCS,EQ,3210.50,1234567\n"
            "2026-08-31,INE467B01029,TCS,BE,3200.00,10\n"
            "2026-08-31,INE009A01021,INFY,EQ,1550.25,7654321\n"
        )
        with patch(
            "stock_research.collectors.nse_eod.read_bytes",
            return_value=_archive(csv_text),
        ):
            rows = NSEBhavcopyCollector().collect(
                date(2026, 8, 31), {"INE467B01029", "INE009A01021"}
            )

        self.assertEqual([row.isin for row in rows], ["INE009A01021", "INE467B01029"])
        self.assertEqual(rows[0].close, 1550.25)
        self.assertEqual(rows[1].volume, 1234567)
        self.assertEqual(rows[1].source_location, bhavcopy_url(date(2026, 8, 31)))

    def test_missing_expected_security_fails_closed(self) -> None:
        csv_text = (
            "TradDt,ISIN,TckrSymb,SctySrs,ClsPric,TtlTradgVol\n"
            "2026-08-31,INE467B01029,TCS,EQ,3210.50,1234567\n"
        )
        with (
            patch(
                "stock_research.collectors.nse_eod.read_bytes",
                return_value=_archive(csv_text),
            ),
            self.assertRaisesRegex(CollectorError, "INE009A01021"),
        ):
            NSEBhavcopyCollector().collect(
                date(2026, 8, 31), {"INE467B01029", "INE009A01021"}
            )


if __name__ == "__main__":
    unittest.main()
