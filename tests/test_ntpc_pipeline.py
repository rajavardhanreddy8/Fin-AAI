from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/ntpc"
NTPC_ISIN = "INE733E01010"
AS_OF = date(2026, 7, 18)


class NTPCPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_ntpc_remains_blocked_until_latest_fy2026_annual_report_is_listed(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)

        self.assertFalse(first.ready)
        self.assertFalse(second.ready)
        self.assertEqual(first.isin, NTPC_ISIN)
        self.assertEqual(first.blockers, ("The latest accepted annual period has no matching annual report.",))
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (9, 33, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (NTPC_ISIN,),
                )
            )
            identity = connection.execute(
                """
                SELECT raw_text
                FROM documents
                WHERE isin = ? AND source_id = 'nse_filings'
                ORDER BY published_at DESC
                LIMIT 1
                """,
                (NTPC_ISIN,),
            ).fetchone()
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})
        self.assertIn("INE733E01010", identity["raw_text"])
        self.assertIn("NTPC", identity["raw_text"])
        self.assertIn("532555", identity["raw_text"])

    def test_ntpc_q2_fy2026_preserves_official_revenue_and_pat(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            revenue = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'revenue' AND period_end = '2025-09-30'
                """,
                (NTPC_ISIN,),
            ).fetchone()
            pat = connection.execute(
                """
                SELECT value, source_value
                FROM financial_facts
                WHERE isin = ? AND metric = 'profit_after_tax' AND period_end = '2025-09-30'
                """,
                (NTPC_ISIN,),
            ).fetchone()
        self.assertEqual(revenue["source_value"], "39,166.59")
        self.assertEqual(revenue["value"], 39_166.59)
        self.assertIn("NTPCQ2FY26", revenue["source_location"])
        self.assertEqual(pat["source_value"], "4,653.33")
        self.assertEqual(pat["value"], 4_653.33)

    def test_ntpc_profile_declares_identity_and_required_metrics(self) -> None:
        profile = CompanyEvidenceProfile.load(FIXTURES)
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("NTPC", "532555"))
        self.assertEqual(profile.required_metrics, ("revenue", "profit_after_tax", "eps_diluted"))


if __name__ == "__main__":
    unittest.main()
