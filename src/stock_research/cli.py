from __future__ import annotations

import argparse
import json
from datetime import date, time, timedelta
from pathlib import Path

from .db import initialize_database
from .change_detection import detect_weekly_material_changes
from .ingest import import_filings_feed, import_prices_csv, import_universe, register_source
from .models import EvidenceTier
from .phase2 import (
    TCS_ISIN,
    CompanyEvidenceProfile,
    run_company_pipeline,
    run_tcs_pipeline,
)
from .quality import run_quality_checks, save_quality_json
from .report import build_weekly_report, save_report
from .research_agent import OpenAICompatibleLLM, ResearchResult, _provider_required_report, build_evidence_packet, run_research_agent
from .supabase_adapter import SupabaseSettings, create_service_client, verify_connection
from .supabase_sync import sync_accepted_records
from .weekly_pipeline import run_weekly_universe_pipeline
from .intraday_pilot import compare_holdout, load_bars, load_verified_bars, pilot_status, record_run, replay, train_candidate, train_candidate_from_bars


def parser() -> argparse.ArgumentParser:
    root = argparse.ArgumentParser(prog="stock-research")
    root.add_argument("--db", default="research.db", help="SQLite database path")
    commands = root.add_subparsers(dest="command", required=True)

    commands.add_parser("init-db", help="Create or migrate the local database")

    universe = commands.add_parser("import-universe", help="Import the ISIN security master")
    universe.add_argument("csv_path")

    source = commands.add_parser("register-source", help="Register a source and evidence tier")
    source.add_argument("source_id")
    source.add_argument("source_name")
    source.add_argument("tier", choices=[tier.value for tier in EvidenceTier])
    source.add_argument("--base-url")

    prices = commands.add_parser("import-prices", help="Import price CSV from a file or public URL")
    prices.add_argument("location")
    prices.add_argument("--source-id", required=True)

    filings = commands.add_parser("import-filings", help="Import an RSS/Atom file or URL")
    filings.add_argument("location")
    filings.add_argument("--source-id", required=True)
    filings.add_argument("--isin", help="Attribute all feed entries to one ISIN")

    quality = commands.add_parser("quality", help="Run recommendation-blocking data checks")
    quality.add_argument("--policy", default="config/investment_policy.json")
    quality.add_argument("--as-of")
    quality.add_argument("--output")

    weekly = commands.add_parser("weekly-report", help="Generate the simple weekly report")
    weekly.add_argument("--policy", default="config/investment_policy.json")
    weekly.add_argument("--as-of")
    weekly.add_argument("--output", default="output/weekly_report.md")

    demo = commands.add_parser("demo", help="Load included fixture data and produce a report")
    demo.add_argument("--as-of", default="2026-07-18")

    tcs = commands.add_parser("tcs-pilot", help="Run the Phase 2 TCS evidence pipeline")
    tcs.add_argument("--fixtures", default="tests/fixtures/tcs")
    tcs.add_argument("--universe", default="config/test_universe.csv")
    tcs.add_argument("--as-of", default="2026-07-18")

    company = commands.add_parser(
        "company-pipeline", help="Run a manifest-driven company evidence pipeline"
    )
    company.add_argument("fixtures")
    company.add_argument("--universe", default="config/test_universe.csv")
    company.add_argument("--as-of", required=True)

    sync_tcs = commands.add_parser(
        "sync-tcs-supabase",
        help="Upload accepted TCS evidence using server-only Supabase settings",
    )
    sync_tcs.add_argument("--run-pilot", action="store_true")
    sync_tcs.add_argument("--fixtures", default="tests/fixtures/tcs")
    sync_tcs.add_argument("--universe", default="config/test_universe.csv")
    sync_tcs.add_argument("--as-of", default="2026-07-18")

    sync_company = commands.add_parser(
        "sync-company-supabase",
        help="Upload accepted company evidence using server-only Supabase settings",
    )
    sync_company.add_argument("fixtures")
    sync_company.add_argument("--run-pipeline", action="store_true")
    sync_company.add_argument("--universe", default="config/test_universe.csv")
    sync_company.add_argument("--as-of", required=True)

    commands.add_parser(
        "check-supabase",
        help="Verify the server-only Supabase connection without exposing secrets",
    )

    changes = commands.add_parser(
        "weekly-changes", help="Detect deterministic weekly evidence changes"
    )
    changes.add_argument("--isin", default=TCS_ISIN)
    changes.add_argument("--window-start", required=True)
    changes.add_argument("--as-of", required=True)
    changes.add_argument("--price-threshold", type=float, default=0.10)

    universe_weekly = commands.add_parser(
        "weekly-universe", help="Run, gate, and optionally sync the full Phase 2 universe"
    )
    universe_weekly.add_argument("--fixtures-root", default="tests/fixtures")
    universe_weekly.add_argument("--universe", default="config/test_universe.csv")
    universe_weekly.add_argument("--window-start", required=True)
    universe_weekly.add_argument("--as-of", required=True)
    universe_weekly.add_argument("--price-threshold", type=float, default=0.10)
    universe_weekly.add_argument("--sync-supabase", action="store_true")
    universe_weekly.add_argument(
        "--refresh-nse-eod",
        action="store_true",
        help="Fetch recent official NSE CM-UDiFF bhavcopies before readiness checks",
    )
    universe_weekly.add_argument(
        "--refresh-nse-shareholding",
        action="store_true",
        help="Fetch each company's latest official NSE shareholding-pattern filing",
    )
    universe_weekly.add_argument(
        "--refresh-company-annual-reports",
        action="store_true",
        help="Fetch configured latest company-primary annual-report PDFs",
    )
    universe_weekly.add_argument(
        "--refresh-nse-annual-financials",
        action="store_true",
        help="Fetch configured audited annual financial facts from official NSE iXBRL filings",
    )
    research = commands.add_parser(
        "research-recommendation",
        help="Generate one validated, cited research recommendation from accepted evidence",
    )
    research.add_argument("fixtures", help="Company fixture directory used for identity and readiness rules")
    research.add_argument("--as-of", required=True)
    research.add_argument("--output", required=True)
    research.add_argument("--run-pipeline", action="store_true", help="Load the company evidence manifest before analysis")
    research.add_argument("--universe", default="config/test_universe.csv")
    research.add_argument("--fixtures-root", default="tests/fixtures")
    research.add_argument("--window-start")
    research.add_argument(
        "--refresh-current-evidence",
        action="store_true",
        help="Refresh official EOD prices, ownership, annual reports, and annual financials before analysis",
    )
    pilot_status_command = commands.add_parser("pilot-status", help="Show the locked NIFTYBEES intraday pilot status")
    pilot_status_command.add_argument("--pilot-db", default="output/intraday-pilot.db")
    pilot_status_command.add_argument("--forward-db", help="Read-only forward-paper journal to audit for qualification")
    pilot_status_command.add_argument("--strategy-id", help="Frozen forward strategy identifier when auditing a journal")
    commands.add_parser("pilot-provider-status", help="Inspect API configuration gaps without invoking models")
    pilot_backtest = commands.add_parser("pilot-backtest", help="Replay completed five-minute bars in paper-safe backtest mode")
    pilot_backtest.add_argument("bars_csv")
    pilot_backtest.add_argument("--pilot-db", default="output/intraday-pilot.db")
    pilot_backtest.add_argument("--run-id", required=True)
    pilot_train = commands.add_parser("pilot-train", help="Train a candidate Q-policy from matched paper transitions")
    pilot_train.add_argument("--pilot-db", default="output/intraday-pilot.db")
    pilot_train.add_argument("--source-run", required=True)
    pilot_train.add_argument("--version", required=True)
    pilot_train_bars = commands.add_parser("pilot-train-bars", help="Train a seeded candidate from the first 60% of manifest-verified sessions")
    pilot_train_bars.add_argument("bars_csv")
    pilot_train_bars.add_argument("--pilot-db", default="output/intraday-pilot.db")
    pilot_train_bars.add_argument("--version", required=True)
    pilot_train_bars.add_argument("--seed", type=int, default=42)
    pilot_compare = commands.add_parser("pilot-compare", help="Compare frozen rules-only and RL-only holdout variants")
    pilot_compare.add_argument("bars_csv")
    pilot_compare.add_argument("--pilot-db", default="output/intraday-pilot.db")
    pilot_compare.add_argument("--version", required=True)
    return root


def _date(value: str | None) -> date | None:
    return date.fromisoformat(value) if value else None


def main(argv: list[str] | None = None) -> int:
    args = parser().parse_args(argv)
    db_path = Path(args.db)

    if args.command == "init-db":
        initialize_database(db_path)
        print(f"Initialized {db_path}")
    elif args.command == "pilot-status":
        print(json.dumps(pilot_status(args.pilot_db, forward_db_path=args.forward_db, strategy_id=args.strategy_id), indent=2))
    elif args.command == "pilot-provider-status":
        from .pilot_agents import provider_readiness
        print(json.dumps(provider_readiness(), indent=2))
    elif args.command == "pilot-backtest":
        bars = load_verified_bars(args.bars_csv)
        dataset = json.loads(Path(args.bars_csv).with_name("dataset-manifest.json").read_text(encoding="utf-8"))
        special = dataset.get("calendar", {}).get("reconciliation", {}).get("known_special_sessions_without_cached_bars", {})
        session_schedules = {day: tuple((time.fromisoformat(opening), time.fromisoformat(closing)) for opening, closing in evidence.get("segments", []))
                             for day, evidence in special.items() if evidence.get("segments")}
        observations = replay(bars, session_schedules=session_schedules)
        summary = record_run(args.pilot_db, args.run_id, "backtest", None, observations)
        print(json.dumps(summary, indent=2))
    elif args.command == "pilot-train":
        policy = train_candidate(args.pilot_db, args.source_run, args.version)
        print(json.dumps({"version": args.version, "states": len(policy.values), "status": "candidate"}, indent=2))
    elif args.command == "pilot-train-bars":
        policy = train_candidate_from_bars(args.pilot_db, args.bars_csv, args.version, seed=args.seed)
        print(json.dumps({"version": args.version, "states": len(policy.values), "status": "candidate", "seed": args.seed}, indent=2))
    elif args.command == "pilot-compare":
        print(json.dumps(compare_holdout(args.pilot_db, args.bars_csv, args.version), indent=2))
    elif args.command == "import-universe":
        initialize_database(db_path)
        print(f"Imported {import_universe(db_path, args.csv_path)} securities")
    elif args.command == "register-source":
        initialize_database(db_path)
        register_source(db_path, args.source_id, args.source_name, args.tier, args.base_url)
        print(f"Registered source {args.source_id}")
    elif args.command == "import-prices":
        initialize_database(db_path)
        print(f"Imported {import_prices_csv(db_path, args.location, args.source_id)} price rows")
    elif args.command == "import-filings":
        initialize_database(db_path)
        print(
            f"Imported {import_filings_feed(db_path, args.location, args.source_id, args.isin)} documents"
        )
    elif args.command == "quality":
        initialize_database(db_path)
        result = run_quality_checks(db_path, args.policy, _date(args.as_of))
        if args.output:
            save_quality_json(result, args.output)
        print(json.dumps(result.to_dict(), indent=2))
        return 2 if result.blocking else 0
    elif args.command == "weekly-report":
        initialize_database(db_path)
        as_of = _date(args.as_of)
        result = run_quality_checks(db_path, args.policy, as_of)
        save_report(build_weekly_report(db_path, result, as_of), args.output)
        print(f"Saved {args.output}; blocking issues: {result.blocking}")
    elif args.command == "demo":
        project_root = Path(__file__).resolve().parents[2]
        initialize_database(db_path)
        import_universe(db_path, project_root / "config/test_universe.csv")
        register_source(db_path, "sample_eod", "Sample EOD fixture", EvidenceTier.REPUTABLE_SECONDARY)
        register_source(db_path, "sample_nse", "Sample NSE filing fixture", EvidenceTier.OFFICIAL)
        import_prices_csv(db_path, project_root / "sample_data/prices.csv", "sample_eod")
        import_filings_feed(
            db_path,
            project_root / "sample_data/filings.xml",
            "sample_nse",
            "INE002A01018",
        )
        as_of = _date(args.as_of)
        result = run_quality_checks(db_path, project_root / "config/investment_policy.json", as_of)
        save_quality_json(result, project_root / "output/data_quality.json")
        save_report(
            build_weekly_report(db_path, result, as_of),
            project_root / "output/weekly_report.md",
        )
        print(f"Demo complete; blocking issues: {result.blocking}")
    elif args.command == "tcs-pilot":
        initialize_database(db_path)
        import_universe(db_path, args.universe)
        result = run_tcs_pipeline(db_path, args.fixtures, _date(args.as_of))
        print(json.dumps({
            "isin": TCS_ISIN,
            "documents": result.documents,
            "financial_facts": result.financial_facts,
            "ownership_facts": result.ownership_facts,
            "price_rows": result.price_rows,
            "governance_flags": result.governance_flags,
            "ready": result.ready,
            "blockers": result.blockers,
        }, indent=2))
        return 2 if not result.ready else 0
    elif args.command == "company-pipeline":
        initialize_database(db_path)
        import_universe(db_path, args.universe)
        result = run_company_pipeline(db_path, args.fixtures, _date(args.as_of))
        print(json.dumps({
            "isin": result.isin,
            "documents": result.documents,
            "financial_facts": result.financial_facts,
            "ownership_facts": result.ownership_facts,
            "price_rows": result.price_rows,
            "governance_flags": result.governance_flags,
            "ready": result.ready,
            "blockers": result.blockers,
        }, indent=2))
        return 2 if not result.ready else 0
    elif args.command == "sync-tcs-supabase":
        if args.run_pilot:
            initialize_database(db_path)
            import_universe(db_path, args.universe)
            result = run_tcs_pipeline(db_path, args.fixtures, _date(args.as_of))
            if not result.ready:
                print(json.dumps({"ready": False, "blockers": result.blockers}, indent=2))
                return 2
        client = create_service_client(SupabaseSettings.from_env())
        print(json.dumps(sync_accepted_records(db_path, client, TCS_ISIN), indent=2))
    elif args.command == "sync-company-supabase":
        profile = CompanyEvidenceProfile.load(args.fixtures)
        if args.run_pipeline:
            initialize_database(db_path)
            import_universe(db_path, args.universe)
            result = run_company_pipeline(db_path, args.fixtures, _date(args.as_of))
            if not result.ready:
                print(json.dumps({"ready": False, "blockers": result.blockers}, indent=2))
                return 2
        client = create_service_client(SupabaseSettings.from_env())
        print(json.dumps(sync_accepted_records(db_path, client, profile.isin), indent=2))
    elif args.command == "check-supabase":
        client = create_service_client(SupabaseSettings.from_env())
        print(json.dumps({"securities_visible": verify_connection(client)}, indent=2))
    elif args.command == "weekly-changes":
        initialize_database(db_path)
        changes = detect_weekly_material_changes(
            db_path,
            args.isin,
            date.fromisoformat(args.window_start),
            date.fromisoformat(args.as_of),
            args.price_threshold,
        )
        print(json.dumps([
            {
                "change_key": change.change_key,
                "change_type": change.change_type,
                "severity": change.severity,
                "summary": change.summary,
                "effective_date": change.effective_date,
            }
            for change in changes
        ], indent=2))
    elif args.command == "weekly-universe":
        client = None
        if args.sync_supabase:
            client = create_service_client(SupabaseSettings.from_env())
        result = run_weekly_universe_pipeline(
            db_path,
            args.fixtures_root,
            args.universe,
            date.fromisoformat(args.window_start),
            date.fromisoformat(args.as_of),
            supabase_client=client,
            price_move_threshold=args.price_threshold,
            refresh_nse_eod=args.refresh_nse_eod,
            refresh_nse_shareholding=args.refresh_nse_shareholding,
            refresh_company_annual_reports=args.refresh_company_annual_reports,
            refresh_nse_annual_financials=args.refresh_nse_annual_financials,
        )
        print(json.dumps(result.to_dict(), indent=2))
        return 0 if result.ready else 2
    elif args.command == "research-recommendation":
        initialize_database(db_path)
        as_of = _date(args.as_of)
        refresh_result = None
        if args.refresh_current_evidence:
            window_start = _date(args.window_start) or (as_of - timedelta(days=7))
            refresh_result = run_weekly_universe_pipeline(
                db_path, args.fixtures_root, args.universe, window_start, as_of,
                refresh_nse_eod=True, refresh_nse_shareholding=True,
                refresh_company_annual_reports=True,
                refresh_nse_annual_financials=True,
            )
        elif args.run_pipeline:
            import_universe(db_path, args.universe)
            run_company_pipeline(db_path, args.fixtures, as_of)
        model: OpenAICompatibleLLM | None = None

        def call_llm(system: str, user: str) -> dict:
            nonlocal model
            model = model or OpenAICompatibleLLM.from_env()
            return model(system, user)

        try:
            result = run_research_agent(db_path, args.fixtures, as_of, call_llm)
        except ValueError as exc:
            message = str(exc)
            if not message.startswith("Missing server-only LLM setting(s):"):
                raise
            packet, blockers = build_evidence_packet(db_path, args.fixtures, as_of)
            result = ResearchResult("provider_required", packet["security"]["isin"], packet["as_of"], _provider_required_report(packet, message), blockers=blockers + (message,))
        save_report(result.report, args.output)
        print(json.dumps({
            "status": result.status,
            "isin": result.isin,
            "as_of": result.as_of,
            "recommendation_id": result.recommendation_id,
            "blockers": result.blockers,
            "output": str(Path(args.output)),
            "refresh": refresh_result.to_dict() if refresh_result else None,
        }, indent=2))
        return 0 if result.status == "completed" else 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())





