from __future__ import annotations

import hashlib
import tempfile
import unittest
from datetime import date
from pathlib import Path

from stock_research.collectors.base import CollectedDocument
from stock_research.db import connect, initialize_database
from stock_research.ingest import import_universe
from stock_research.normalization.ownership import normalize_shareholding_xbrl
from stock_research.phase2 import run_company_pipeline
from stock_research.supabase_sync import build_accepted_payload


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TCS_FIXTURES = PROJECT_ROOT / "tests/fixtures/tcs"


def _shareholding_document(*, pledged: bool = False) -> CollectedDocument:
    flag = str(pledged).lower()
    xml = f'''<?xml version="1.0"?>
    <xbrl>
      <NumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">2596558628</NumberOfShares>
      <ShareholdingAsAPercentageOfTotalNumberOfShares contextRef="ShareholdingOfPromoterAndPromoterGroup_ContextI">0.7177</ShareholdingAsAPercentageOfTotalNumberOfShares>
      <WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged contextRef="MainI">{flag}</WhetherAnySharesHeldByPromotersAreEncumberedUnderPledged>
    </xbrl>'''
    return CollectedDocument(
        document_key="nse_shareholding:INE467B01029:2026-06-30:ownership-test",
        isin="INE467B01029",
        source_id="nse_filings",
        source_tier="official",
        document_type="shareholding_pattern",
        title="TCS shareholding pattern",
        published_at="2026-07-21",
        retrieved_at="2026-09-01T00:00:00+00:00",
        source_location="https://nsearchives.nseindia.com/corporate/xbrl/test.xml",
        period_end="2026-06-30",
        reporting_scope="not_applicable",
        content_hash=hashlib.sha256(xml.encode()).hexdigest(),
        raw_text=xml,
        confidence=1.0,
    )


class OwnershipFactsTest(unittest.TestCase):
    def test_normalizes_promoter_holding_shares_and_pledge(self) -> None:
        facts = normalize_shareholding_xbrl(_shareholding_document())
        values = {fact.metric: fact.value for fact in facts}
        self.assertEqual(values["promoter_holding_pct"], 0.7177)
        self.assertEqual(values["promoter_shares"], 2596558628)
        self.assertEqual(values["promoter_pledged_flag"], 0)

    def test_pipeline_persists_facts_and_flags_disclosed_pledge(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            db_path = Path(directory) / "research.db"
            initialize_database(db_path)
            import_universe(db_path, PROJECT_ROOT / "config/test_universe.csv")
            result = run_company_pipeline(
                db_path,
                TCS_FIXTURES,
                date(2026, 7, 21),
                additional_documents=(_shareholding_document(pledged=True),),
            )

            self.assertEqual(result.ownership_facts, 3)
            payload = build_accepted_payload(db_path, "INE467B01029")
            self.assertEqual(len(payload["ownership_facts"]), 3)
            self.assertTrue(
                all(fact["_document_key"] for fact in payload["ownership_facts"])
            )
            with connect(db_path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM ownership_facts WHERE isin = ?",
                        ("INE467B01029",),
                    ).fetchone()[0],
                    3,
                )
                flag = connection.execute(
                    "SELECT severity FROM governance_flags WHERE isin = ? AND rule_id = 'promoter_pledge'",
                    ("INE467B01029",),
                ).fetchone()
            self.assertEqual(flag["severity"], "blocking")

            rerun = run_company_pipeline(
                db_path,
                TCS_FIXTURES,
                date(2026, 7, 21),
            )
            self.assertTrue(rerun.ready, rerun.blockers)
            with connect(db_path) as connection:
                self.assertEqual(
                    connection.execute(
                        "SELECT COUNT(*) FROM governance_flags WHERE isin = ? AND rule_id = 'promoter_pledge'",
                        ("INE467B01029",),
                    ).fetchone()[0],
                    1,
                )


if __name__ == "__main__":
    unittest.main()
