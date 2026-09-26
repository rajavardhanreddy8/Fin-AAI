from __future__ import annotations

import shutil
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import CompanyEvidenceProfile, run_company_pipeline, run_tcs_pipeline


PROJECT_ROOT = Path(__file__).resolve().parents[1]
INFOSYS_FIXTURES = PROJECT_ROOT / "tests/fixtures/infosys"
TCS_FIXTURES = PROJECT_ROOT / "tests/fixtures/tcs"
INFOSYS_ISIN = "INE009A01021"
AS_OF = date(2026, 7, 18)


class InfosysPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_infosys_pipeline_is_research_ready_and_idempotent(self) -> None:
        first = run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)
        second = run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)

        self.assertTrue(first.ready, first.blockers)
        self.assertTrue(second.ready, second.blockers)
        self.assertEqual(first.isin, INFOSYS_ISIN)
        self.assertEqual(first.documents, 9)
        self.assertEqual(first.financial_facts, 44)
        self.assertEqual(first.price_rows, 10)

        with connect(self.db_path) as connection:
            quarterly = connection.execute(
                "SELECT COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? AND period_type = 'quarterly'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
            annual = connection.execute(
                "SELECT COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? AND period_type = 'annual'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
            self.assertEqual(quarterly, 8)
            self.assertEqual(annual, 3)
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM documents WHERE isin = ?", (INFOSYS_ISIN,)).fetchone()[0],
                9,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM financial_facts WHERE isin = ?", (INFOSYS_ISIN,)).fetchone()[0],
                44,
            )
            self.assertEqual(
                connection.execute("SELECT COUNT(*) FROM price_bars WHERE isin = ?", (INFOSYS_ISIN,)).fetchone()[0],
                10,
            )

    def test_as_of_cutoff_excludes_scheduled_q1_fy2027_results(self) -> None:
        run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            latest_quarter = connection.execute(
                "SELECT MAX(period_end) FROM financial_facts WHERE isin = ? AND period_type = 'quarterly'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
            scheduled = connection.execute(
                "SELECT COUNT(*) FROM documents WHERE isin = ? AND document_type = 'result_schedule' AND period_end = '2026-06-30'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
            q1_facts = connection.execute(
                "SELECT COUNT(*) FROM financial_facts WHERE isin = ? AND period_end = '2026-06-30'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
        self.assertEqual(latest_quarter, "2026-03-31")
        self.assertEqual(scheduled, 1)
        self.assertEqual(q1_facts, 0)

    def test_official_filing_verifies_exchange_identity(self) -> None:
        profile = CompanyEvidenceProfile.load(INFOSYS_FIXTURES)
        self.assertEqual((profile.nse_symbol, profile.bse_code), ("INFY", "500209"))
        run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            filing = connection.execute(
                """
                SELECT d.raw_text, s.evidence_tier
                FROM documents d JOIN sources s ON s.source_id = d.source_id
                WHERE d.isin = ? AND d.document_type = 'financial_results_ixbrl'
                """,
                (INFOSYS_ISIN,),
            ).fetchone()
        self.assertEqual(filing["evidence_tier"], "official")
        self.assertIn("INE009A01021", filing["raw_text"])
        self.assertIn("INFY", filing["raw_text"])
        self.assertIn("500209", filing["raw_text"])

    def test_failed_infosys_parse_preserves_accepted_facts(self) -> None:
        run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)
        with connect(self.db_path) as connection:
            before = connection.execute(
                "SELECT value FROM financial_facts WHERE isin = ? AND metric = 'revenue' AND period_end = '2026-03-31' AND period_type = 'quarterly'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]

        bad_fixture_dir = Path(self.temp_dir.name) / "bad-infosys-fixtures"
        shutil.copytree(INFOSYS_FIXTURES, bad_fixture_dir)
        facts_path = bad_fixture_dir / "financial_results.csv"
        content = facts_path.read_text(encoding="utf-8")
        facts_path.write_text(
            content.replace('"5,040",USD_million', "not-a-number,USD_million", 1),
            encoding="utf-8",
        )
        with self.assertRaisesRegex(ValueError, "Invalid financial fact row"):
            run_company_pipeline(self.db_path, bad_fixture_dir, AS_OF)

        with connect(self.db_path) as connection:
            after = connection.execute(
                "SELECT value FROM financial_facts WHERE isin = ? AND metric = 'revenue' AND period_end = '2026-03-31' AND period_type = 'quarterly'",
                (INFOSYS_ISIN,),
            ).fetchone()[0]
        self.assertEqual(after, before)

    def test_tcs_and_infosys_coexist_in_one_evidence_store(self) -> None:
        tcs = run_tcs_pipeline(self.db_path, TCS_FIXTURES, AS_OF)
        infosys = run_company_pipeline(self.db_path, INFOSYS_FIXTURES, AS_OF)
        self.assertTrue(tcs.ready, tcs.blockers)
        self.assertTrue(infosys.ready, infosys.blockers)

        with connect(self.db_path) as connection:
            accepted = dict(
                connection.execute(
                    """
                    SELECT isin, COUNT(*) AS count
                    FROM financial_facts
                    WHERE isin IN (?, ?) AND validation_status = 'accepted'
                    GROUP BY isin
                    """,
                    (tcs.isin, infosys.isin),
                )
            )
        self.assertEqual(accepted, {tcs.isin: 44, infosys.isin: 44})


if __name__ == "__main__":
    unittest.main()
