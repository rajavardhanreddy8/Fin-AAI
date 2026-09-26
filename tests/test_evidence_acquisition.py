from __future__ import annotations

from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import unittest

from stock_research.evidence_acquisition import plan_acquisition
from stock_research.nifty_store import initialize


class EvidenceAcquisitionTests(unittest.TestCase):
    def test_plans_attributable_sources_and_prioritizes_stale_profiles(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            db = Path(temp) / "finance.db"
            initialize(db)
            with closing(sqlite3.connect(db)) as connection:
                connection.execute(
                    "INSERT INTO universe_snapshots VALUES(?,?,?,?,?,?,?)",
                    ("snapshot-1", "2026-09-25", "2026-09-25T00:00:00+00:00", "https://www.nseindia.com", "hash", 2, "csv"),
                )
                for isin, symbol, name in (
                    ("INE000000001", "STALE", "Stale Co"),
                    ("INE000000002", "MISSING", "Missing Co"),
                ):
                    connection.execute("INSERT INTO securities VALUES(?,?,?,?,?,?,?,?,?)", (
                        isin, name, symbol, None, None, "watchlist", 1,
                        "2026-09-25T00:00:00+00:00", "2026-09-25T00:00:00+00:00",
                    ))
                    connection.execute("INSERT INTO universe_members VALUES(?,?,?,?,?,?,?)", (
                        "snapshot-1", isin, symbol, name, "Other", "non_financial", "retained",
                    ))
                    connection.execute("INSERT INTO evidence_snapshots VALUES(?,?,?,?,?,?)", (
                        f"evidence-{symbol}", isin, "2026-09-25T00:00:00+00:00",
                        "2026-09-25T00:00:00+00:00", "hash", "{}",
                    ))
                connection.execute(
                    "INSERT INTO research_runs(run_id,mode,started_at,status,membership_id) VALUES(?,?,?,?,?)",
                    ("run-1", "pre_market", "2026-09-25T00:00:00+00:00", "completed", "snapshot-1"),
                )
                connection.execute("INSERT INTO coverage VALUES(?,?,?,?,?,?,?)", (
                    "run-1", "INE000000001", "evidence-STALE", "stale",
                    '["Quarterly financial evidence is stale (over 150 days)."]', "2026-09-24", None,
                ))
                connection.execute("INSERT INTO coverage VALUES(?,?,?,?,?,?,?)", (
                    "run-1", "INE000000002", "evidence-MISSING", "missing",
                    '["Frozen evidence lacks 3 complete annual periods.","Shareholding disclosure is missing at cutoff."]',
                    "2026-09-24", None,
                ))
                connection.commit()

            result = plan_acquisition(db, "run-1", limit=2)

            self.assertEqual(result["planned"], 2)
            self.assertEqual(result["tasks"][0]["symbol"], "STALE")
            self.assertEqual(result["tasks"][0]["priority"], 1)
            missing = next(task for task in result["tasks"] if task["symbol"] == "MISSING")
            self.assertIn("official_nse_shareholding", missing["sourceRoutes"])
            self.assertIn("official_nse_financial_filing", missing["sourceRoutes"])
            self.assertNotIn("price_history", missing["sourceRoutes"])


if __name__ == "__main__":
    unittest.main()
