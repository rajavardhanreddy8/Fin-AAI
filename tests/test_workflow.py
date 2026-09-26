from __future__ import annotations

import json
import sqlite3
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_filings_feed, import_prices_csv, import_universe, register_source
from stock_research.models import EvidenceTier
from stock_research.quality import run_quality_checks
from stock_research.report import build_weekly_report


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class WorkflowTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def seed(self) -> None:
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")
        register_source(
            self.db_path,
            "sample_eod",
            "Sample EOD fixture",
            EvidenceTier.REPUTABLE_SECONDARY,
        )
        register_source(
            self.db_path,
            "sample_nse",
            "Sample NSE fixture",
            EvidenceTier.OFFICIAL,
        )
        import_prices_csv(self.db_path, PROJECT_ROOT / "sample_data/prices.csv", "sample_eod")

    def test_universe_and_prices_are_idempotent(self) -> None:
        self.seed()
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")
        import_prices_csv(self.db_path, PROJECT_ROOT / "sample_data/prices.csv", "sample_eod")
        with connect(self.db_path) as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM securities").fetchone()[0], 10)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0], 10)

    def test_official_feed_keeps_provenance_and_deduplicates(self) -> None:
        self.seed()
        fixture = PROJECT_ROOT / "sample_data/filings.xml"
        first = import_filings_feed(self.db_path, fixture, "sample_nse", "INE002A01018")
        second = import_filings_feed(self.db_path, fixture, "sample_nse", "INE002A01018")
        self.assertEqual(first, 1)
        self.assertEqual(second, 0)
        with connect(self.db_path) as connection:
            row = connection.execute("SELECT * FROM documents").fetchone()
            self.assertEqual(row["confidence"], 1.0)
            self.assertEqual(row["document_type"], "financial_results")
            self.assertEqual(len(row["content_hash"]), 64)

    def test_quality_gate_blocks_incomplete_official_coverage(self) -> None:
        self.seed()
        import_filings_feed(
            self.db_path,
            PROJECT_ROOT / "sample_data/filings.xml",
            "sample_nse",
            "INE002A01018",
        )
        result = run_quality_checks(
            self.db_path,
            PROJECT_ROOT / "config/investment_policy.json",
            date(2026, 7, 18),
        )
        self.assertEqual(result.securities_checked, 10)
        self.assertEqual(result.blocking, 9)
        self.assertFalse(result.safe_for_recommendations)
        report = build_weekly_report(self.db_path, result, date(2026, 7, 18))
        self.assertIn("No recommendation is given", report)
        self.assertIn("9 blocking", report)

    def test_recommendation_ledger_is_append_only(self) -> None:
        self.seed()
        with connect(self.db_path) as connection:
            cursor = connection.execute(
                """
                INSERT INTO recommendations(
                    isin, created_at, classification, action, score, confidence,
                    facts_json, assumptions_json, risks_json, opinion,
                    entry_zone_json, exit_triggers_json, thesis, policy_version
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "INE002A01018",
                    "2026-07-18T00:00:00+00:00",
                    "watchlist_only",
                    "wait",
                    None,
                    0.2,
                    json.dumps([]),
                    json.dumps(["test-only"]),
                    json.dumps(["missing real evidence"]),
                    "Synthetic test record",
                    None,
                    json.dumps(["Do not act on test data"]),
                    "Verify the ledger constraint",
                    "1.0.0",
                ),
            )
            recommendation_id = cursor.lastrowid
            connection.commit()
            with self.assertRaises(sqlite3.IntegrityError):
                connection.execute(
                    "UPDATE recommendations SET opinion = 'changed' WHERE recommendation_id = ?",
                    (recommendation_id,),
                )

    def test_connection_is_closed_after_context_exit(self) -> None:
        with connect(self.db_path) as connection:
            result = connection.execute("SELECT 1").fetchone()
            self.assertEqual(result[0], 1)

        with self.assertRaises(sqlite3.ProgrammingError):
            connection.execute("SELECT 1")


if __name__ == "__main__":
    unittest.main()
