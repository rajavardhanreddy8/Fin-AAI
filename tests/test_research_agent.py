from __future__ import annotations

import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import run_company_pipeline
from stock_research.research_agent import run_research_agent


ROOT = Path(__file__).resolve().parents[1]


class ResearchAgentTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_validated_model_result_is_cited_and_appended(self) -> None:
        fixtures = ROOT / "tests/fixtures/tcs"
        run_company_pipeline(self.db_path, fixtures, date(2026, 7, 18))

        def model(system: str, user: str) -> dict:
            packet = json.loads(user)
            self.assertIn("target prices", system)
            return {
                "action": "watch",
                "classification": "watchlist_only",
                "confidence": 0.7,
                "opinion": "Evidence supports continued monitoring.",
                "thesis": "Operating performance remains attributable to company filings.",
                "risks": ["Demand can weaken."],
                "assumptions": ["Reported results remain comparable."],
                "exit_triggers": ["Review after the next quarterly filing."],
                "evidence_claims": [
                    {
                        "evidence_key": packet["evidence_index"][0]["evidence_key"],
                        "document_id": packet["evidence_index"][0]["document_id"],
                        "claim": "Latest filing reviewed.",
                    }
                ],
            }

        result = run_research_agent(self.db_path, fixtures, date(2026, 7, 18), model)
        self.assertEqual(result.status, "completed")
        self.assertIn("Latest filing reviewed", result.report)
        self.assertIn("https://", result.report)
        with connect(self.db_path) as connection:
            self.assertEqual(connection.execute("select count(*) from recommendations").fetchone()[0], 1)
            self.assertEqual(connection.execute("select count(*) from recommendation_evidence").fetchone()[0], 1)

    def test_incomplete_company_returns_without_calling_model(self) -> None:
        fixtures = ROOT / "tests/fixtures/ntpc"
        run_company_pipeline(self.db_path, fixtures, date(2026, 7, 18))
        called = False

        def model(system: str, user: str) -> dict:
            nonlocal called
            called = True
            return {}

        result = run_research_agent(self.db_path, fixtures, date(2026, 7, 18), model)
        self.assertEqual(result.status, "insufficient_evidence")
        self.assertFalse(called)
        self.assertIn("No LLM recommendation was requested", result.report)

    def test_positive_action_is_rejected_without_deterministic_valuation(self) -> None:
        fixtures = ROOT / "tests/fixtures/tcs"
        run_company_pipeline(self.db_path, fixtures, date(2026, 7, 18))

        def model(system: str, user: str) -> dict:
            packet = json.loads(user)
            return {
                "action": "buy",
                "classification": "core_investment",
                "confidence": 0.8,
                "opinion": "Buy.",
                "thesis": "Claimed upside.",
                "risks": ["Execution risk."],
                "assumptions": ["Growth continues."],
                "exit_triggers": ["Review next result."],
                "evidence_claims": [
                    {
                        "evidence_key": packet["evidence_index"][0]["evidence_key"],
                        "document_id": packet["evidence_index"][0]["document_id"],
                        "claim": "Filing reviewed.",
                    }
                ],
            }

        with self.assertRaisesRegex(ValueError, "deterministic evidence gates"):
            run_research_agent(self.db_path, fixtures, date(2026, 7, 18), model)
        with connect(self.db_path) as connection:
            self.assertEqual(connection.execute("select count(*) from recommendations").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
