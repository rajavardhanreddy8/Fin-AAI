import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from scripts.normalize_powergrid_history import normalize


def provider_fixture():
    bar = {"date": "2023-10-25", "datetime": "2023-10-25T03:45:00Z",
           "timestamp_ms": 1698205500000, "open": 10, "high": 12, "low": 9, "close": 11,
           "adj_close": 10, "volume": 100, "split_factor": 1,
           "unadjusted_open": 10, "unadjusted_high": 12, "unadjusted_low": 9,
           "unadjusted_close": 11}
    return {"symbol": "POWERGRID.NS", "name": "Power Grid Corporation of India Limited",
            "currency": "INR", "exchange_name": "NSE", "exchange_timezone": "Asia/Kolkata",
            "interval": "1d", "instrument_type": "EQUITY", "start": "2023-10-25",
            "end": "2026-10-25", "count": 1, "source_url": "https://finance.yahoo.com/quote/POWERGRID.NS/history/",
            "observed_at_ms": int(datetime.now(timezone.utc).timestamp() * 1000),
            "dividends": [], "splits": [], "latest_trade": None, "bars": [bar]}


class PowergridPriceNormalizationTests(unittest.TestCase):
    def write_input(self, directory, data):
        path = Path(directory) / "provider-data.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_normalizes_valid_fixture_and_marks_review_pending(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_input(root, provider_fixture())
            result = normalize(source, root / "normalized")
            self.assertEqual(result["rows"], 1)
            self.assertEqual(result["independent_validation"]["status"], "pending")
            self.assertEqual(result["coverage"]["status"], "unknown")
            self.assertIsNotNone(result["retrieved_at_utc"])
            self.assertIn("not the network receipt time", result["retrieved_at_semantics"])

    def test_rejects_invalid_ohlc_and_timestamp_mismatch(self):
        for mutation in ("ohlc", "timestamp"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as tmp:
                data = provider_fixture()
                if mutation == "ohlc":
                    data["bars"][0]["high"] = 8
                else:
                    data["bars"][0]["timestamp_ms"] += 1000
                source = self.write_input(tmp, data)
                with self.assertRaises(ValueError):
                    normalize(source, Path(tmp) / "normalized")

    def test_refuses_to_overwrite_existing_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = self.write_input(root, provider_fixture())
            out = root / "normalized"
            normalize(source, out)
            with self.assertRaises(FileExistsError):
                normalize(source, out)


if __name__ == "__main__":
    unittest.main()
