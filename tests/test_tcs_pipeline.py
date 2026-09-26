from __future__ import annotations

import shutil
import tempfile
import unittest
import csv
from datetime import date
from pathlib import Path

from stock_research.db import connect, initialize_database
from stock_research.change_detection import detect_weekly_material_changes
from stock_research.ingest import import_universe
from stock_research.phase2 import TCS_ISIN, run_tcs_pipeline
from stock_research.supabase_sync import build_accepted_payload, sync_accepted_records


PROJECT_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = PROJECT_ROOT / "tests/fixtures/tcs"


class _FakeQuery:
    def __init__(self, client: "_FakeClient", table: str) -> None:
        self.client = client
        self.table = table
        self.rows: list[dict] = []
        self.conflict = ""
        self.selected = ""
        self.filter_values: list[str] = []

    def upsert(self, rows: list[dict], on_conflict: str) -> "_FakeQuery":
        self.rows = rows
        self.conflict = on_conflict
        return self

    def select(self, columns: str) -> "_FakeQuery":
        self.selected = columns
        return self

    def in_(self, column: str, values: list[str]) -> "_FakeQuery":
        self.filter_values = values
        return self

    def execute(self) -> object:
        if self.selected:
            data = [
                {"document_key": key, "document_id": self.client.document_ids[key]}
                for key in self.filter_values
            ]
            return type("Response", (), {"data": data})()
        self.client.calls.append((self.table, self.rows, self.conflict))
        if self.table == "documents":
            for row in self.rows:
                self.client.document_ids.setdefault(
                    row["document_key"], len(self.client.document_ids) + 1000
                )
        return type("Response", (), {"data": self.rows})()


class _FakeClient:
    def __init__(self) -> None:
        self.calls: list[tuple[str, list[dict], str]] = []
        self.document_ids: dict[str, int] = {}

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(self, name)


class TCSPipelineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, PROJECT_ROOT / "config/test_universe.csv")

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_tcs_pipeline_is_research_ready_and_idempotent(self) -> None:
        first = run_tcs_pipeline(self.db_path, FIXTURES)
        second = run_tcs_pipeline(self.db_path, FIXTURES)
        self.assertTrue(first.ready, first.blockers)
        self.assertTrue(second.ready, second.blockers)
        self.assertEqual(first.documents, 16)
        self.assertEqual(first.financial_facts, 44)
        self.assertEqual(first.price_rows, 10)

        with connect(self.db_path) as connection:
            quarterly = connection.execute(
                "SELECT COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? AND period_type = 'quarterly'",
                (TCS_ISIN,),
            ).fetchone()[0]
            annual = connection.execute(
                "SELECT COUNT(DISTINCT period_end) FROM financial_facts WHERE isin = ? AND period_type = 'annual'",
                (TCS_ISIN,),
            ).fetchone()[0]
            counts = {
                row["document_type"]: row["count"]
                for row in connection.execute(
                    "SELECT document_type, COUNT(*) AS count FROM documents WHERE isin = ? GROUP BY document_type",
                    (TCS_ISIN,),
                )
            }
            self.assertEqual(quarterly, 8)
            self.assertEqual(annual, 3)
            self.assertEqual(counts["annual_report"], 1)
            self.assertEqual(counts["shareholding_pattern"], 1)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM documents WHERE isin = ?", (TCS_ISIN,)).fetchone()[0], 16)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM financial_facts WHERE isin = ?", (TCS_ISIN,)).fetchone()[0], 44)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM price_bars WHERE isin = ?", (TCS_ISIN,)).fetchone()[0], 10)

    def test_every_fact_is_attributable_and_latest_price_is_current(self) -> None:
        run_tcs_pipeline(self.db_path, FIXTURES)
        with connect(self.db_path) as connection:
            unattributed = connection.execute(
                """
                SELECT COUNT(*) FROM financial_facts f
                LEFT JOIN documents d ON d.document_id = f.document_id
                WHERE f.isin = ? AND (
                    d.document_id IS NULL OR f.source_location IS NULL OR
                    f.publication_date IS NULL OR f.currency IS NULL OR
                    f.evidence_label <> 'fact_source_reported'
                )
                """,
                (TCS_ISIN,),
            ).fetchone()[0]
            latest = connection.execute("SELECT MAX(trade_date) FROM price_bars WHERE isin = ?", (TCS_ISIN,)).fetchone()[0]
            self.assertEqual(unattributed, 0)
            self.assertEqual(latest, "2026-07-17")

    def test_failed_parsing_does_not_replace_accepted_facts(self) -> None:
        run_tcs_pipeline(self.db_path, FIXTURES)
        with connect(self.db_path) as connection:
            before = connection.execute(
                "SELECT value FROM financial_facts WHERE isin = ? AND metric = 'revenue' AND period_end = '2026-06-30' AND period_type = 'quarterly'",
                (TCS_ISIN,),
            ).fetchone()[0]

        bad_fixture_dir = Path(self.temp_dir.name) / "bad-fixtures"
        shutil.copytree(FIXTURES, bad_fixture_dir)
        facts_path = bad_fixture_dir / "financial_results.csv"
        content = facts_path.read_text(encoding="utf-8")
        facts_path.write_text(content.replace('"7,624",USD_million', 'not-a-number,USD_million', 1), encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Invalid financial fact row"):
            run_tcs_pipeline(self.db_path, bad_fixture_dir)

        with connect(self.db_path) as connection:
            after = connection.execute(
                "SELECT value FROM financial_facts WHERE isin = ? AND metric = 'revenue' AND period_end = '2026-06-30' AND period_type = 'quarterly'",
                (TCS_ISIN,),
            ).fetchone()[0]
        self.assertEqual(after, before)

    def test_standalone_fact_does_not_replace_consolidated_fact(self) -> None:
        mixed_fixture_dir = Path(self.temp_dir.name) / "mixed-scope-fixtures"
        shutil.copytree(FIXTURES, mixed_fixture_dir)
        facts_path = mixed_fixture_dir / "financial_results.csv"
        with facts_path.open(newline="", encoding="utf-8-sig") as handle:
            rows = list(csv.DictReader(handle))
            fieldnames = list(rows[0])

        standalone = dict(rows[0])
        standalone["reporting_scope"] = "standalone"
        standalone["source_value"] = "1"
        rows.append(standalone)
        with facts_path.open("w", newline="", encoding="utf-8") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)

        result = run_tcs_pipeline(self.db_path, mixed_fixture_dir)

        self.assertEqual(result.financial_facts, 45)
        with connect(self.db_path) as connection:
            stored = connection.execute(
                """
                SELECT statement_scope, value FROM financial_facts
                WHERE isin = ? AND metric = ? AND period_end = ? AND period_type = ?
                ORDER BY statement_scope
                """,
                (
                    TCS_ISIN,
                    standalone["metric"],
                    standalone["period_end"],
                    standalone["period_type"],
                ),
            ).fetchall()

        self.assertEqual([row["statement_scope"] for row in stored], ["consolidated", "standalone"])
        self.assertNotEqual(stored[0]["value"], stored[1]["value"])

    def test_governance_rules_are_deterministic(self) -> None:
        first = run_tcs_pipeline(self.db_path, FIXTURES)
        second = run_tcs_pipeline(self.db_path, FIXTURES)
        self.assertEqual(first.governance_flags, 1)
        self.assertEqual(second.governance_flags, 1)
        with connect(self.db_path) as connection:
            flag = connection.execute("SELECT * FROM governance_flags WHERE isin = ?", (TCS_ISIN,)).fetchone()
            self.assertEqual(flag["rule_id"], "management_change")
            self.assertEqual(flag["severity"], "info")
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM governance_flags WHERE isin = ?", (TCS_ISIN,)).fetchone()[0], 1)

    def test_supabase_sync_contains_only_accepted_attributable_records(self) -> None:
        run_tcs_pipeline(self.db_path, FIXTURES)
        detect_weekly_material_changes(
            self.db_path, TCS_ISIN, date(2026, 7, 7), date(2026, 7, 18)
        )
        payload = build_accepted_payload(self.db_path, TCS_ISIN)
        self.assertEqual(len(payload["financial_facts"]), 44)
        self.assertTrue(all(row["validation_status"] == "accepted" for row in payload["financial_facts"]))
        self.assertTrue(all(row["document_id"] is not None for row in payload["financial_facts"]))

        client = _FakeClient()
        counts = sync_accepted_records(self.db_path, client, TCS_ISIN)
        self.assertEqual(counts["financial_facts"], 44)
        self.assertEqual([call[0] for call in client.calls], [
            "securities",
            "sources",
            "documents",
            "financial_facts",
            "price_bars",
            "governance_flags",
            "material_changes",
        ])
        document_rows = next(call[1] for call in client.calls if call[0] == "documents")
        fact_rows = next(call[1] for call in client.calls if call[0] == "financial_facts")
        self.assertTrue(all("document_id" not in row for row in document_rows))
        self.assertTrue(all(row["document_id"] >= 1000 for row in fact_rows))
        self.assertTrue(all("fact_id" not in row for row in fact_rows))

    def test_weekly_material_changes_are_deduplicated_and_idempotent(self) -> None:
        run_tcs_pipeline(self.db_path, FIXTURES)
        first = detect_weekly_material_changes(
            self.db_path, TCS_ISIN, date(2026, 7, 7), date(2026, 7, 18)
        )
        second = detect_weekly_material_changes(
            self.db_path, TCS_ISIN, date(2026, 7, 7), date(2026, 7, 18)
        )
        self.assertEqual(first, second)
        self.assertEqual(len(first), 3)
        self.assertEqual(
            {change.change_type for change in first},
            {"financial_results_ixbrl", "governance", "price_move"},
        )
        with connect(self.db_path) as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM material_changes WHERE isin = ?", (TCS_ISIN,)
                ).fetchone()[0],
                3,
            )


if __name__ == "__main__":
    unittest.main()
