from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/icicibank"
ICICIBANK_ISIN = "INE090A01021"
AS_OF = date(2026, 7, 18)


class ICICIBankPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_icicibank_bank_profile_runs_and_remains_blocked_on_missing_coverage(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)

        self.assertFalse(first.ready)
        self.assertFalse(second.ready)
        self.assertEqual(first.isin, ICICIBANK_ISIN)
        self.assertEqual(first.blockers, ("The latest accepted annual period has no matching annual report.",))
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (10, 22, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (ICICIBANK_ISIN,),
                )
            )
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})

    def test_icicibank_q1_fy2026_preserves_reported_nii_and_pat(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            identity_doc = connection.execute(
                """
                SELECT raw_text
                FROM documents
                WHERE isin = ? AND document_type = 'financial_results_ixbrl'
                """,
                (ICICIBANK_ISIN,),
            ).fetchone()
            nii = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'net_interest_income' AND period_end = '2025-06-30'
                """,
                (ICICIBANK_ISIN,),
            ).fetchone()
            pat = connection.execute(
                """
                SELECT value, source_value
                FROM financial_facts
                WHERE isin = ? AND metric = 'profit_after_tax' AND period_end = '2025-06-30'
                """,
                (ICICIBANK_ISIN,),
            ).fetchone()
            annual = connection.execute(
                """
                SELECT period_end, metric, source_value
                FROM financial_facts
                WHERE isin = ? AND period_type = 'annual'
                ORDER BY period_end, metric
                """,
                (ICICIBANK_ISIN,),
            ).fetchall()
        self.assertIsNotNone(identity_doc)
        self.assertIn("ICICIBANK", identity_doc["raw_text"])
        self.assertIn("532174", identity_doc["raw_text"])
        self.assertIn(ICICIBANK_ISIN, identity_doc["raw_text"])
        self.assertEqual(
            [(row["period_end"], row["metric"], row["source_value"]) for row in annual],
            [
                ("2024-03-31", "net_interest_income", "74,306"),
                ("2024-03-31", "profit_after_tax", "40,888"),
                ("2025-03-31", "net_interest_income", "81,165"),
                ("2025-03-31", "profit_after_tax", "47,227"),
                ("2026-03-31", "net_interest_income", "88,075"),
                ("2026-03-31", "profit_after_tax", "50,147"),
            ],
        )
        self.assertEqual(nii["source_value"], "216,350")
        self.assertEqual(nii["value"], 216_350)
        self.assertIn("performance-review-quarter-ended-june-30-2025", nii["source_location"])
        self.assertEqual(pat["source_value"], "127,680")
        self.assertEqual(pat["value"], 127_680)

    def test_icicibank_profile_declares_bank_metrics(self) -> None:
        profile = CompanyEvidenceProfile.load(FIXTURES)
        self.assertEqual(profile.company_kind, "bank")
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("ICICIBANK", "532174"))
        self.assertEqual(profile.required_metrics, ("net_interest_income", "profit_after_tax"))


if __name__ == "__main__":
    unittest.main()
