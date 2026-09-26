from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import date
from pathlib import Path
from unittest.mock import Mock, patch

from stock_research.cli import main
from stock_research.db import initialize_database
from stock_research.ingest import import_universe
from stock_research.phase2 import run_tcs_pipeline
from stock_research.collectors.nse_eod import NSE_EOD_SOURCE_ID
from stock_research.collectors.price_csv import CollectedPrice


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TCS_FIXTURES = PROJECT_ROOT / "tests/fixtures/tcs"
NTPC_FIXTURES = PROJECT_ROOT / "tests/fixtures/ntpc"
UNIVERSE = PROJECT_ROOT / "config/test_universe.csv"


class Phase2CLITest(unittest.TestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.db_path = Path(self.temp_dir.name) / "research.db"
        initialize_database(self.db_path)
        import_universe(self.db_path, UNIVERSE)

    def tearDown(self) -> None:
        self.temp_dir.cleanup()

    def test_weekly_changes_cli_runs_locally_and_returns_material_changes(self) -> None:
        run_tcs_pipeline(self.db_path, TCS_FIXTURES)

        output = io.StringIO()
        with redirect_stdout(output):
            code = main(
                [
                    "--db",
                    str(self.db_path),
                    "weekly-changes",
                    "--isin",
                    "INE467B01029",
                    "--window-start",
                    "2026-07-07",
                    "--as-of",
                    "2026-07-18",
                ]
            )

        self.assertEqual(code, 0)
        payload = json.loads(output.getvalue())
        self.assertEqual(len(payload), 3)
        self.assertEqual(
            {row["change_type"] for row in payload},
            {"financial_results_ixbrl", "governance", "price_move"},
        )

    def test_sync_company_supabase_cli_runs_pipeline_and_syncs_ready_company(self) -> None:
        fake_client = object()
        output = io.StringIO()
        with (
            patch("stock_research.cli.SupabaseSettings.from_env", return_value=object()) as from_env,
            patch("stock_research.cli.create_service_client", return_value=fake_client) as create_client,
            patch(
                "stock_research.cli.sync_accepted_records",
                return_value={"financial_facts": 44, "documents": 16, "price_bars": 10},
            ) as sync_records,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--db",
                    str(self.db_path),
                    "sync-company-supabase",
                    str(TCS_FIXTURES),
                    "--run-pipeline",
                    "--universe",
                    str(UNIVERSE),
                    "--as-of",
                    "2026-07-18",
                ]
            )

        self.assertEqual(code, 0)
        from_env.assert_called_once_with()
        create_client.assert_called_once()
        sync_records.assert_called_once_with(self.db_path, fake_client, "INE467B01029")
        self.assertEqual(json.loads(output.getvalue())["financial_facts"], 44)

    def test_sync_company_supabase_cli_refuses_blocked_company_before_sync(self) -> None:
        output = io.StringIO()
        with (
            patch("stock_research.cli.create_service_client") as create_client,
            patch("stock_research.cli.sync_accepted_records") as sync_records,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--db",
                    str(self.db_path),
                    "sync-company-supabase",
                    str(NTPC_FIXTURES),
                    "--run-pipeline",
                    "--universe",
                    str(UNIVERSE),
                    "--as-of",
                    "2026-07-18",
                ]
            )

        self.assertEqual(code, 2)
        create_client.assert_not_called()
        sync_records.assert_not_called()
        payload = json.loads(output.getvalue())
        self.assertFalse(payload["ready"])
        self.assertEqual(
            payload["blockers"],
            ["The latest accepted annual period has no matching annual report."],
        )

    def test_weekly_universe_syncs_only_ready_companies(self) -> None:
        output = io.StringIO()
        fake_client = object()
        with (
            patch("stock_research.cli.SupabaseSettings.from_env", return_value=object()),
            patch("stock_research.cli.create_service_client", return_value=fake_client),
            patch(
                "stock_research.weekly_pipeline.sync_accepted_records",
                return_value={"financial_facts": 1},
            ) as sync_records,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--db",
                    str(self.db_path),
                    "weekly-universe",
                    "--fixtures-root",
                    str(PROJECT_ROOT / "tests/fixtures"),
                    "--universe",
                    str(UNIVERSE),
                    "--window-start",
                    "2026-07-07",
                    "--as-of",
                    "2026-07-18",
                    "--sync-supabase",
                ]
            )

        payload = json.loads(output.getvalue())
        self.assertEqual(code, 2)
        self.assertEqual(payload["ready_companies"], 8)
        self.assertEqual(payload["blocked_companies"], 2)
        self.assertEqual(sync_records.call_count, 8)
        synced_isins = {call.args[2] for call in sync_records.call_args_list}
        self.assertNotIn("INE733E01010", synced_isins)
        self.assertNotIn("INE090A01021", synced_isins)

    def test_weekly_universe_refreshes_prices_from_official_nse_bhavcopy(self) -> None:
        profiles = []
        for fixture_dir in (PROJECT_ROOT / "tests/fixtures").iterdir():
            company_path = fixture_dir / "company.json"
            if company_path.is_file():
                profiles.append(json.loads(company_path.read_text(encoding="utf-8")))
        refreshed = [
            CollectedPrice(
                isin=profile["isin"],
                trade_date=date(2026, 8, 31),
                close=100.0,
                volume=1000,
                source_id=NSE_EOD_SOURCE_ID,
                source_location="https://nsearchives.nseindia.com/example.zip",
                retrieved_at="2026-09-01T00:00:00+00:00",
            )
            for profile in profiles
        ]
        output = io.StringIO()
        with (
            patch(
                "stock_research.weekly_pipeline.NSEBhavcopyCollector.collect_recent",
                return_value=refreshed,
            ) as collect_recent,
            redirect_stdout(output),
        ):
            code = main(
                [
                    "--db",
                    str(self.db_path),
                    "weekly-universe",
                    "--fixtures-root",
                    str(PROJECT_ROOT / "tests/fixtures"),
                    "--universe",
                    str(UNIVERSE),
                    "--window-start",
                    "2026-08-25",
                    "--as-of",
                    "2026-09-01",
                    "--refresh-nse-eod",
                ]
            )

        self.assertEqual(code, 2)
        collect_recent.assert_called_once()
        payload = json.loads(output.getvalue())
        blockers = [blocker for company in payload["companies"] for blocker in company["blockers"]]
        self.assertFalse(any("Latest price" in blocker for blocker in blockers))


    def test_research_recommendation_refreshes_before_analysis(self) -> None:
        output = io.StringIO()
        report_path = Path(self.temp_dir.name) / "report.md"
        fake_refresh = Mock()
        fake_refresh.to_dict.return_value = {"ready": True}
        fake_research = Mock(status="insufficient_evidence", isin="INE467B01029", as_of="2026-09-06", recommendation_id=None, blockers=("stale",), report="# report\n")
        with (
            patch("stock_research.cli.run_weekly_universe_pipeline", return_value=fake_refresh) as refresh,
            patch("stock_research.cli.run_research_agent", return_value=fake_research) as research,
            redirect_stdout(output),
        ):
            code = main(["--db", str(self.db_path), "research-recommendation", str(TCS_FIXTURES), "--as-of", "2026-09-06", "--output", str(report_path), "--universe", str(UNIVERSE), "--fixtures-root", str(PROJECT_ROOT / "tests/fixtures"), "--refresh-current-evidence"])
        self.assertEqual(code, 2)
        self.assertEqual(refresh.call_args.args[3:], (date(2026, 8, 30), date(2026, 9, 6)))
        self.assertTrue(all(refresh.call_args.kwargs.values()))
        research.assert_called_once()
        self.assertEqual(json.loads(output.getvalue())["refresh"], {"ready": True})

if __name__ == "__main__":
    unittest.main()


