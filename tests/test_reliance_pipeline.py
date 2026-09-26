from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import run_company_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/reliance"
RELIANCE_ISIN = "INE002A01018"
AS_OF = date(2026, 7, 18)


class ReliancePipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reliance_is_research_ready_and_idempotent(self) -> None:
        first = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        self.assertTrue(first.ready, first.blockers)
        self.assertTrue(second.ready, second.blockers)
        self.assertEqual((first.documents, first.financial_facts, first.price_rows), (10, 33, 10))

        with connect(self.db_path) as connection:
            periods = dict(
                connection.execute(
                    "SELECT period_type, COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? GROUP BY period_type",
                    (RELIANCE_ISIN,),
                )
            )
            current = connection.execute(
                "SELECT value, source_value FROM financial_facts WHERE isin = ? AND metric = 'gross_revenue' AND period_end = '2026-06-30'",
                (RELIANCE_ISIN,),
            ).fetchone()
        self.assertEqual(periods, {"annual": 3, "quarterly": 8})
        self.assertEqual(current["value"], 3_402_570.0)
        self.assertEqual(current["source_value"], "340,257")

    def test_original_q1_fy2026_reported_ebitda_is_not_replaced_by_adjusted_comparative(self) -> None:
        run_company_pipeline(self.db_path, FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            fact = connection.execute(
                """
                SELECT value, source_value, source_location
                FROM financial_facts
                WHERE isin = ? AND metric = 'ebitda' AND period_end = '2025-06-30'
                """,
                (RELIANCE_ISIN,),
            ).fetchone()
        self.assertEqual(fact["source_value"], "58,024")
        self.assertEqual(fact["value"], 580_240.0)
        self.assertIn("MediaRelease-RILQ1FY2025-26", fact["source_location"])


if __name__ == "__main__":
    unittest.main()
