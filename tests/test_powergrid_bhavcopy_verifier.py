import csv
import io
import json
import tempfile
import unittest
import zipfile
from pathlib import Path

from scripts.verify_powergrid_bhavcopy import verify


class PowergridBhavcopyVerifierTests(unittest.TestCase):
    def test_compares_identity_date_unadjusted_ohlcv_offline(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            archive_path = root / "nse.zip"
            content = ("TradDt,ISIN,TckrSymb,SctySrs,OpnPric,HghPric,LwPric,ClsPric,TtlTradgVol\n"
                       "2026-10-23,INE752E01010,POWERGRID,EQ,248.05,248.60,242.30,247.40,5917098\n")
            with zipfile.ZipFile(archive_path, "w") as z:
                z.writestr("BhavCopy.csv", content)
            provider_path = root / "provider.json"
            provider_path.write_text(json.dumps({"symbol": "POWERGRID.NS", "exchange_name": "NSE",
                "currency": "INR", "bars": [{"date": "2026-10-23", "unadjusted_open": 248.05,
                "unadjusted_high": 248.6, "unadjusted_low": 242.3, "unadjusted_close": 247.4,
                "adj_close": 246.0, "volume": 5917098}]}), encoding="utf-8")
            result = verify(archive_path, provider_path, "2026-10-23")
            self.assertEqual(result["status"], "match")
            self.assertFalse(result["adjusted_close_compared"])

    def test_rejects_wrong_series(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            zpath = root / "nse.zip"
            with zipfile.ZipFile(zpath, "w") as z:
                z.writestr("b.csv", "TradDt,ISIN,TckrSymb,SctySrs\n2026-10-23,INE752E01010,POWERGRID,BE\n")
            p = root / "provider.json"
            p.write_text("{}", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "Expected one"):
                verify(zpath, p, "2026-10-23")


if __name__ == "__main__":
    unittest.main()
