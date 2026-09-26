from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from stock_research.db import initialize_database, transaction
from stock_research.governance.rules import evaluate_financial_health


class QuantitativeGovernanceTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        with transaction(self.db_path) as connection:
            connection.execute(
                "INSERT INTO securities(isin, company_name, created_at, updated_at) VALUES (?, ?, ?, ?)",
                ("INE467B01029", "TCS", "2026-01-01", "2026-01-01"),
            )
            connection.execute(
                "INSERT INTO sources(source_id, source_name, evidence_tier, created_at) VALUES (?, ?, ?, ?)",
                ("official", "Official filing", "official", "2026-01-01"),
            )
            connection.execute(
                """
                INSERT INTO documents(
                    isin, source_id, document_type, title, published_at, retrieved_at,
                    source_location, content_hash, confidence, document_key, period_end
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    "INE467B01029",
                    "official",
                    "annual_report",
                    "Annual report",
                    "2026-06-01",
                    "2026-06-01",
                    "https://example.test/annual.pdf",
                    "hash",
                    1.0,
                    "annual-2026",
                    "2026-03-31",
                ),
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def _facts(self, rows: list[tuple[str, float, str]]) -> None:
        with transaction(self.db_path) as connection:
            document_id = connection.execute(
                "SELECT document_id FROM documents WHERE document_key = 'annual-2026'"
            ).fetchone()[0]
            for metric, value, period_end in rows:
                connection.execute(
                    """
                    INSERT INTO financial_facts(
                        isin, metric, value, unit, period_end, period_type, source_id,
                        document_id, retrieved_at, publication_date, currency,
                        source_value, source_location, evidence_label, statement_scope
                    ) VALUES (?, ?, ?, ?, ?, 'annual', ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        "INE467B01029",
                        metric,
                        value,
                        "million",
                        period_end,
                        "official",
                        document_id,
                        "2026-06-01",
                        "2026-06-01",
                        "INR",
                        str(value),
                        "https://example.test/annual.pdf",
                        "fact_source_reported",
                        "consolidated",
                    ),
                )

    def test_flags_weak_cash_conversion_and_debt_stress(self) -> None:
        self._facts(
            [
                ("profit_after_tax", 100, "2026-03-31"),
                ("operating_cash_flow", 60, "2026-03-31"),
                ("interest_coverage", 1.5, "2026-03-31"),
            ]
        )
        with transaction(self.db_path) as connection:
            flags = evaluate_financial_health(connection, "INE467B01029")
        self.assertEqual(
            {(flag.rule_id, flag.severity) for flag in flags},
            {("weak_cash_conversion", "warning"), ("debt_stress", "blocking")},
        )

    def test_flags_repeated_share_dilution(self) -> None:
        self._facts(
            [
                ("shares_outstanding", 100, "2024-03-31"),
                ("shares_outstanding", 103, "2025-03-31"),
                ("shares_outstanding", 107, "2026-03-31"),
            ]
        )
        with transaction(self.db_path) as connection:
            flags = evaluate_financial_health(connection, "INE467B01029")
        self.assertEqual([flag.rule_id for flag in flags], ["frequent_dilution"])


if __name__ == "__main__":
    unittest.main()
