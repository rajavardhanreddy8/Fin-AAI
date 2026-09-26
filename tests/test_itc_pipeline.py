from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/itc"
ITC_ISIN = "INE154A01025"
AS_OF = date(2026, 7, 18)


class ITCPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_itc_is_research_ready_and_idempotent(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)

        self.assertTrue(first.ready, first.blockers)
        self.assertTrue(second.ready, second.blockers)
        self.assertEqual(first.isin, ITC_ISIN)
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (12, 33, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (ITC_ISIN,),
                )
            )
            identity = connection.execute(
                """
                SELECT raw_text
                FROM documents
                WHERE isin = ? AND document_type = 'financial_results_ixbrl'
                """,
                (ITC_ISIN,),
            ).fetchone()
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})
        self.assertIn("INE154A01025", identity["raw_text"])
        self.assertIn("ITC", identity["raw_text"])
        self.assertIn("500875", identity["raw_text"])

    def test_itc_q3_fy2025_preserves_company_reported_pat_and_eps(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            pat = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'profit_after_tax' AND period_end = '2024-12-31'
                """,
                (ITC_ISIN,),
            ).fetchone()
            eps = connection.execute(
                """
                SELECT value, source_value
                FROM financial_facts
                WHERE isin = ? AND metric = 'eps_diluted' AND period_end = '2024-12-31'
                """,
                (ITC_ISIN,),
            ).fetchone()
        self.assertEqual(pat["source_value"], "5,638")
        self.assertEqual(pat["value"], 56_380.0)
        self.assertIn("31st-December-2024", pat["source_location"])
        self.assertEqual(eps["source_value"], "4.51")
        self.assertEqual(eps["value"], 4.51)

    def test_itc_profile_declares_identity_and_required_metrics(self) -> None:
        profile = CompanyEvidenceProfile.load(FIXTURES)
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("ITC", "500875"))
        self.assertEqual(profile.required_metrics, ("revenue", "profit_after_tax", "eps_diluted"))


if __name__ == "__main__":
    unittest.main()
