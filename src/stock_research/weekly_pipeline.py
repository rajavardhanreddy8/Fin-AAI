from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import date
from pathlib import Path
from typing import Any

from .change_detection import detect_weekly_material_changes
from .collectors.nse_eod import (
    NSEBhavcopyCollector,
    NSE_EOD_BASE_URL,
    NSE_EOD_SOURCE_ID,
    NSE_EOD_SOURCE_NAME,
)
from .collectors.nse_shareholding import NSEShareholdingCollector
from .collectors.nse_ixbrl_financials import (
    ANNUAL_IXBRL_SPECS,
    NSEIXBRLFinancialCollector,
)
from .collectors.company_annual_report import (
    ANNUAL_REPORT_SPECS,
    CompanyAnnualReportCollector,
)
from .db import initialize_database
from .db import transaction
from .ingest import import_universe, register_source
from .models import EvidenceTier
from .phase2 import CompanyEvidenceProfile, run_company_pipeline
from .supabase_sync import sync_accepted_records


@dataclass(frozen=True, slots=True)
class CompanyWeeklyResult:
    isin: str
    company_name: str
    ready: bool
    blockers: tuple[str, ...]
    material_changes: int
    synced: bool
    sync_counts: dict[str, int] | None


@dataclass(frozen=True, slots=True)
class WeeklyUniverseResult:
    as_of: str
    window_start: str
    companies: tuple[CompanyWeeklyResult, ...]

    @property
    def ready(self) -> bool:
        return all(company.ready for company in self.companies)

    def to_dict(self) -> dict[str, Any]:
        return {
            "as_of": self.as_of,
            "window_start": self.window_start,
            "ready": self.ready,
            "ready_companies": sum(company.ready for company in self.companies),
            "blocked_companies": sum(not company.ready for company in self.companies),
            "companies": [asdict(company) for company in self.companies],
        }


def run_weekly_universe_pipeline(
    db_path: str | Path,
    fixtures_root: str | Path,
    universe_path: str | Path,
    window_start: date,
    as_of: date,
    *,
    supabase_client: Any | None = None,
    price_move_threshold: float = 0.10,
    refresh_nse_eod: bool = False,
    refresh_nse_shareholding: bool = False,
    refresh_company_annual_reports: bool = False,
    refresh_nse_annual_financials: bool = False,
) -> WeeklyUniverseResult:
    """Run the local evidence pipeline for every fixture-backed security.

    Incomplete companies remain local and blocked. Only research-ready companies
    are eligible for server synchronization.
    """
    if window_start > as_of:
        raise ValueError("Weekly pipeline window start cannot be after its as-of date")

    initialize_database(db_path)
    import_universe(db_path, universe_path)
    fixture_dirs = sorted(
        path
        for path in Path(fixtures_root).iterdir()
        if path.is_dir() and (path / "company.json").is_file()
    )
    if not fixture_dirs:
        raise ValueError(f"No company fixture manifests found under {fixtures_root}")

    if refresh_nse_eod:
        profiles = [CompanyEvidenceProfile.load(path) for path in fixture_dirs]
        prices = NSEBhavcopyCollector().collect_recent(
            as_of, {profile.isin for profile in profiles}
        )
        register_source(
            db_path,
            NSE_EOD_SOURCE_ID,
            NSE_EOD_SOURCE_NAME,
            EvidenceTier.OFFICIAL,
            NSE_EOD_BASE_URL,
        )
        with transaction(db_path) as connection:
            for price in prices:
                connection.execute(
                    """
                    INSERT INTO price_bars(
                        isin, trade_date, close, volume, source_id, retrieved_at
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(isin, trade_date, source_id) DO UPDATE SET
                        close=excluded.close,
                        volume=excluded.volume,
                        retrieved_at=excluded.retrieved_at
                    """,
                    (
                        price.isin,
                        price.trade_date.isoformat(),
                        price.close,
                        price.volume,
                        price.source_id,
                        price.retrieved_at,
                    ),
                )

    companies: list[CompanyWeeklyResult] = []
    shareholding_collector = NSEShareholdingCollector() if refresh_nse_shareholding else None
    annual_report_collector = (
        CompanyAnnualReportCollector() if refresh_company_annual_reports else None
    )
    financial_collector = NSEIXBRLFinancialCollector() if refresh_nse_annual_financials else None
    for fixture_dir in fixture_dirs:
        profile = CompanyEvidenceProfile.load(fixture_dir)
        additional_documents = []
        additional_financial_facts = []
        if shareholding_collector is not None:
            additional_documents.append(
                shareholding_collector.collect_latest(
                    profile.isin, profile.nse_symbol, as_of
                )
            )
        report_spec = ANNUAL_REPORT_SPECS.get(profile.isin)
        if annual_report_collector is not None and report_spec is not None:
            additional_documents.append(annual_report_collector.collect(report_spec, as_of))
        financial_spec = ANNUAL_IXBRL_SPECS.get(profile.isin)
        if financial_collector is not None and financial_spec is not None:
            document, facts = financial_collector.collect_spec(financial_spec)
            additional_documents.append(document)
            additional_financial_facts.extend(facts)
        pipeline = run_company_pipeline(
            db_path,
            fixture_dir,
            as_of,
            additional_documents=tuple(additional_documents),
            additional_financial_facts=tuple(additional_financial_facts),
        )
        changes = ()
        sync_counts = None
        if pipeline.ready:
            changes = detect_weekly_material_changes(
                db_path,
                profile.isin,
                window_start,
                as_of,
                price_move_threshold,
            )
            if supabase_client is not None:
                sync_counts = sync_accepted_records(db_path, supabase_client, profile.isin)

        companies.append(
            CompanyWeeklyResult(
                isin=profile.isin,
                company_name=profile.company_name,
                ready=pipeline.ready,
                blockers=pipeline.blockers,
                material_changes=len(changes),
                synced=sync_counts is not None,
                sync_counts=sync_counts,
            )
        )

    return WeeklyUniverseResult(
        as_of=as_of.isoformat(),
        window_start=window_start.isoformat(),
        companies=tuple(companies),
    )
