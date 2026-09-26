from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/hdfcbank"
HDFCBANK_ISIN = "INE040A01034"
AS_OF = date(2026, 7, 18)


class HDFCBankPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_hdfcbank_bank_profile_runs_and_is_research_ready(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)

        self.assertTrue(first.ready)
        self.assertTrue(second.ready)
        self.assertEqual(first.isin, HDFCBANK_ISIN)
        self.assertEqual(first.blockers, ())
        self.assertEqual(second.blockers, ())
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (11, 22, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (HDFCBANK_ISIN,),
                )
            )
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})

    def test_hdfcbank_q1_fy2026_preserves_reported_nii_and_pat(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            identity_doc = connection.execute(
                """
                SELECT raw_text
                FROM documents
                WHERE isin = ? AND document_type = 'financial_results_ixbrl'
                """,
                (HDFCBANK_ISIN,),
            ).fetchone()
            nii = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'net_interest_income' AND period_end = '2025-06-30'
                """,
                (HDFCBANK_ISIN,),
            ).fetchone()
            pat = connection.execute(
                """
                SELECT value, source_value
                FROM financial_facts
                WHERE isin = ? AND metric = 'profit_after_tax' AND period_end = '2025-06-30'
                """,
                (HDFCBANK_ISIN,),
            ).fetchone()
            shareholding = connection.execute(
                """
                SELECT period_end, source_location
                FROM documents
                WHERE isin = ? AND document_type = 'shareholding_pattern'
                """,
                (HDFCBANK_ISIN,),
            ).fetchone()
            q4 = connection.execute(
                """
                SELECT metric, value, source_value
                FROM financial_facts
                WHERE isin = ? AND period_end = '2026-03-31'
                  AND period_type = 'quarterly'
                ORDER BY metric
                """,
                (HDFCBANK_ISIN,),
            ).fetchall()
            annual = connection.execute(
                """
                SELECT period_end, metric, source_value, value
                FROM financial_facts
                WHERE isin = ? AND period_type = 'annual'
                ORDER BY period_end, metric
                """,
                (HDFCBANK_ISIN,),
            ).fetchall()
            quarterly = connection.execute(
                """
                SELECT period_end, metric, source_value
                FROM financial_facts
                WHERE isin = ? AND period_type = 'quarterly'
                ORDER BY period_end, metric
                """,
                (HDFCBANK_ISIN,),
            ).fetchall()
        self.assertIsNotNone(identity_doc)
        self.assertIn("HDFCBANK", identity_doc["raw_text"])
        self.assertIn("500180", identity_doc["raw_text"])
        self.assertIn(HDFCBANK_ISIN, identity_doc["raw_text"])
        self.assertIsNotNone(shareholding)
        self.assertEqual(shareholding["period_end"], "2026-03-31")
        self.assertIn("Shareholding_Pattern_Website.pdf", shareholding["source_location"])
        self.assertEqual([(row["metric"], row["source_value"], row["value"]) for row in q4], [
            ("net_interest_income", "330,800", 330_800),
            ("profit_after_tax", "192,200", 192_200),
        ])
        self.assertEqual(
            [(row["period_end"], row["metric"], row["source_value"]) for row in annual],
            [
                ("2024-03-31", "net_interest_income", "108,532.46"),
                ("2024-03-31", "profit_after_tax", "60,812.27"),
                ("2025-03-31", "net_interest_income", "122,670.09"),
                ("2025-03-31", "profit_after_tax", "67,347.36"),
                ("2026-03-31", "net_interest_income", "163,123.92"),
                ("2026-03-31", "profit_after_tax", "74,670"),
            ],
        )
        self.assertEqual(len(quarterly), 16)
        self.assertEqual(nii["source_value"], "314,400")
        self.assertEqual(nii["value"], 314_400)
        self.assertIn("june-30-2025", nii["source_location"])
        self.assertEqual(pat["source_value"], "177,100")
        self.assertEqual(pat["value"], 177_100)

    def test_hdfcbank_profile_declares_bank_metrics(self) -> None:
        profile = CompanyEvidenceProfile.load(FIXTURES)
        self.assertEqual(profile.company_kind, "bank")
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("HDFCBANK", "500180"))
        self.assertEqual(profile.required_metrics, ("net_interest_income", "profit_after_tax"))


if __name__ == "__main__":
    unittest.main()
