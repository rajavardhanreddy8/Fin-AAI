from __future__ import annotations

import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.change_detection import detect_weekly_material_changes
from stock_research.collectors.base import CollectedDocument
from stock_research.db import initialize_database, transaction
from stock_research.governance.rules import evaluate_documents


class HealthChangeDetectorTest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        with transaction(self.db_path) as connection:
            connection.execute(
                "insert into sources(source_id,source_name,evidence_tier,enabled,created_at) values('official','Official','official',1,'2026-01-01T00:00:00+00:00')"
            )
            connection.execute(
                "insert into securities(isin,company_name,nse_symbol,bse_code,sector,style_bucket,active,created_at,updated_at) values('INE000A01000','Example','EXAMPLE','500000','Test','watchlist',1,'2026-01-01T00:00:00+00:00','2026-01-01T00:00:00+00:00')"
            )
            for key, kind, period, published in (
                ("annual-report", "annual_report", "2026-03-31", "2026-08-30"),
                ("shareholding", "shareholding_pattern", "2026-06-30", "2026-07-20"),
                ("cash-2025", "financial_results_ixbrl", "2025-03-31", "2025-04-20"),
                ("cash-2026", "financial_results_ixbrl", "2026-03-31", "2026-08-30"),
            ):
                connection.execute(
                    """insert into documents(isin,source_id,document_type,title,published_at,retrieved_at,source_location,content_hash,confidence,raw_text,document_key,period_end,reporting_scope,validation_status)
                    values('INE000A01000','official',?,?,?,?,?,'hash',1,'evidence',?,?, 'consolidated','accepted')""",
                    (kind, key, published, published + "T00:00:00+00:00", f"https://example.com/{key}", key, period),
                )
            docs = {row[1]: row[0] for row in connection.execute("select document_id,document_key from documents")}
            for period, value, key, publication in (
                ("2025-03-31", 1000, "cash-2025", "2025-04-20"),
                ("2026-03-31", 600, "cash-2026", "2026-08-30"),
            ):
                connection.execute(
                    """insert into financial_facts(isin,metric,value,unit,period_end,period_type,source_id,document_id,retrieved_at,publication_date,currency,source_value,source_location,evidence_label,confidence_label,statement_scope,validation_status)
                    values('INE000A01000','operating_cash_flow',?,'million',?,'annual','official',?,'2026-08-30T00:00:00+00:00',?,'INR',?,'https://example.com','fact_source_reported','high','consolidated','accepted')""",
                    (value, period, docs[key], publication, str(value)),
                )
            connection.execute(
                "insert into price_bars values('INE000A01000','2026-09-01',100,1000,'official','2026-09-01T00:00:00+00:00')"
            )

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_reports_material_cash_flow_deterioration(self) -> None:
        changes = detect_weekly_material_changes(
            self.db_path, "INE000A01000", date(2026, 8, 25), date(2026, 9, 1)
        )
        match = next(change for change in changes if change.change_type == "cash_flow_deterioration")
        self.assertEqual(match.severity, "warning")
        self.assertIn("40.0%", match.summary)

    def test_flags_suspicious_announcement_without_llm(self) -> None:
        document = CollectedDocument.from_mapping(
            {
                "document_key": "rumour",
                "isin": "INE000A01000",
                "source_id": "official",
                "source_tier": "official",
                "document_type": "announcement",
                "title": "Clarification on news reports",
                "published_at": "2026-09-01",
                "source_location": "https://example.com/rumour",
            }
        )
        flags = evaluate_documents([document])
        self.assertIn("suspicious_announcement", {flag.rule_id for flag in flags})


if __name__ == "__main__":
    unittest.main()
