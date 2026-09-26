from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/sunpharma"
SUNPHARMA_ISIN = "INE044A01036"
AS_OF = date(2026, 7, 18)


class SunPharmaPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_sunpharma_is_research_ready_and_idempotent(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)

        self.assertTrue(first.ready, first.blockers)
        self.assertTrue(second.ready, second.blockers)
        self.assertEqual(first.isin, SUNPHARMA_ISIN)
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (11, 33, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (SUNPHARMA_ISIN,),
                )
            )
            identity = connection.execute(
                """
                SELECT raw_text
                FROM documents
                WHERE isin = ? AND source_id = 'nse_filings'
                """,
                (SUNPHARMA_ISIN,),
            ).fetchone()
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})
        self.assertIn("INE044A01036", identity["raw_text"])
        self.assertIn("SUNPHARMA", identity["raw_text"])
        self.assertIn("524715", identity["raw_text"])

    def test_sunpharma_q3_fy2026_preserves_company_reported_revenue_and_pat(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            revenue = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'revenue' AND period_end = '2025-12-31'
                """,
                (SUNPHARMA_ISIN,),
            ).fetchone()
            pat = connection.execute(
                """
                SELECT value, source_value
                FROM financial_facts
                WHERE isin = ? AND metric = 'profit_after_tax' AND period_end = '2025-12-31'
                """,
                (SUNPHARMA_ISIN,),
            ).fetchone()
        self.assertEqual(revenue["source_value"], "155,205.4")
        self.assertEqual(revenue["value"], 155_205.4)
        self.assertIn("SPIL-Q3FY26-Financial-Results.pdf", revenue["source_location"])
        self.assertEqual(pat["source_value"], "33,688.1")
        self.assertEqual(pat["value"], 33_688.1)

    def test_sunpharma_profile_declares_identity_and_required_metrics(self) -> None:
        profile = CompanyEvidenceProfile.load(FIXTURES)
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("SUNPHARMA", "524715"))
        self.assertEqual(profile.required_metrics, ("revenue", "profit_after_tax", "eps_diluted"))


if __name__ == "__main__":
    unittest.main()
