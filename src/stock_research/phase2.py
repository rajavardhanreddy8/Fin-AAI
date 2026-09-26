from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

from .collectors.company_ir import CompanyIRCollector
from .collectors.nse_filings import NSEFilingsCollector
from .collectors.price_csv import PriceCSVCollector
from .db import connect, initialize_database, transaction
from .governance.rules import (
    evaluate_documents,
    evaluate_financial_health,
    evaluate_ownership_history,
)
from .normalization.financial_results import normalize_financial_results
from .normalization.ownership import normalize_shareholding_xbrl


TCS_ISIN = "INE467B01029"
DEFAULT_REQUIRED_METRICS = ("revenue", "operating_income", "net_income", "eps_diluted")


@dataclass(frozen=True, slots=True)
class SourceProfile:
    source_id: str
    source_name: str
    evidence_tier: str
    base_url: str


@dataclass(frozen=True, slots=True)
class CompanyEvidenceProfile:
    isin: str
    company_name: str
    nse_symbol: str
    bse_code: str
    company_kind: str
    sources: tuple[SourceProfile, ...]
    price_source_id: str
    price_source_location: str
    required_metrics: tuple[str, ...] = DEFAULT_REQUIRED_METRICS

    @classmethod
    def load(cls, fixture_dir: str | Path) -> "CompanyEvidenceProfile":
        path = Path(fixture_dir) / "company.json"
        try:
            payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8-sig"))
            sources = tuple(
                SourceProfile(
                    source_id=str(row["source_id"]).strip(),
                    source_name=str(row["source_name"]).strip(),
                    evidence_tier=str(row["evidence_tier"]).strip(),
                    base_url=str(row["base_url"]).strip(),
                )
                for row in payload["sources"]
            )
            price = payload["price_source"]
            profile = cls(
                isin=str(payload["isin"]).strip().upper(),
                company_name=str(payload["company_name"]).strip(),
                nse_symbol=str(payload["nse_symbol"]).strip().upper(),
                bse_code=str(payload["bse_code"]).strip(),
                company_kind=str(payload.get("company_kind", "non_bank")).strip(),
                sources=sources,
                price_source_id=str(price["source_id"]).strip(),
                price_source_location=str(price["source_location"]).strip(),
                required_metrics=tuple(payload.get("required_metrics", DEFAULT_REQUIRED_METRICS)),
            )
        except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
            raise ValueError(f"Invalid company evidence profile {path}: {exc}") from exc
        if len(profile.isin) != 12 or not profile.isin.isalnum():
            raise ValueError(f"Invalid ISIN in company evidence profile: {profile.isin!r}")
        if profile.company_kind not in {"non_bank", "bank"}:
            raise ValueError(f"Unsupported company kind: {profile.company_kind!r}")
        if not sources or len({source.source_id for source in sources}) != len(sources):
            raise ValueError("Company evidence profile requires unique sources")
        if profile.price_source_id not in {source.source_id for source in sources}:
            raise ValueError("Price source must be registered in the company evidence profile")
        return profile


@dataclass(frozen=True, slots=True)
class PipelineResult:
    isin: str
    documents: int
    financial_facts: int
    ownership_facts: int
    price_rows: int
    governance_flags: int
    ready: bool
    blockers: tuple[str, ...]


def _trading_days_old(latest: date, as_of: date) -> int:
    if latest > as_of:
        raise ValueError("Latest price cannot be after the pipeline as-of date")
    cursor = latest
    days = 0
    while cursor < as_of:
        cursor = date.fromordinal(cursor.toordinal() + 1)
        if cursor.weekday() < 5:
            days += 1
    return days


def assess_company_readiness(
    db_path: str | Path,
    profile: CompanyEvidenceProfile,
    as_of: date,
) -> tuple[bool, tuple[str, ...]]:
    blockers: list[str] = []
    with connect(db_path) as connection:
        identity = connection.execute(
            "SELECT isin, company_name, nse_symbol, bse_code FROM securities WHERE isin = ?",
            (profile.isin,),
        ).fetchone()
        if (
            identity is None
            or identity["nse_symbol"] != profile.nse_symbol
            or identity["bse_code"] != profile.bse_code
        ):
            blockers.append(f"{profile.company_name} exchange identity is missing or mismatched.")

        identity_evidence = connection.execute(
            """
            SELECT COUNT(*)
            FROM documents d JOIN sources s ON s.source_id = d.source_id
            WHERE d.isin = ? AND d.validation_status = 'accepted'
              AND s.evidence_tier = 'official'
              AND instr(upper(d.raw_text), ?) > 0
              AND instr(upper(d.raw_text), ?) > 0
              AND instr(upper(d.raw_text), ?) > 0
            """,
            (profile.isin, profile.isin, profile.nse_symbol, profile.bse_code),
        ).fetchone()[0]
        if not identity_evidence:
            blockers.append("No accepted official document verifies the ISIN, NSE symbol, and BSE code.")

        for period_type, required_periods in (("quarterly", 8), ("annual", 3)):
            rows = list(
                connection.execute(
                    """
                    SELECT period_end, COUNT(DISTINCT metric) AS metric_count
                    FROM financial_facts
                    WHERE isin = ? AND period_type = ? AND validation_status = 'accepted'
                      AND metric IN ({})
                    GROUP BY period_end
                    HAVING COUNT(DISTINCT metric) = ?
                    """.format(",".join("?" for _ in profile.required_metrics)),
                    (
                        profile.isin,
                        period_type,
                        *profile.required_metrics,
                        len(profile.required_metrics),
                    ),
                )
            )
            if len(rows) < required_periods:
                blockers.append(
                    f"Only {len(rows)} complete {period_type} periods are accepted; "
                    f"{required_periods} are required."
                )

        latest_annual_period = connection.execute(
            """
            SELECT MAX(period_end) FROM financial_facts
            WHERE isin = ? AND period_type = 'annual' AND validation_status = 'accepted'
            """,
            (profile.isin,),
        ).fetchone()[0]
        annual_report_period = connection.execute(
            """
            SELECT MAX(period_end) FROM documents
            WHERE isin = ? AND document_type = 'annual_report'
              AND validation_status = 'accepted'
            """,
            (profile.isin,),
        ).fetchone()[0]
        if latest_annual_period is None or annual_report_period != latest_annual_period:
            blockers.append("The latest accepted annual period has no matching annual report.")

        shareholding_period = connection.execute(
            """
            SELECT MAX(period_end) FROM documents
            WHERE isin = ? AND document_type = 'shareholding_pattern'
              AND validation_status = 'accepted'
            """,
            (profile.isin,),
        ).fetchone()[0]
        if shareholding_period is None:
            blockers.append("Latest shareholding pattern is missing.")
        elif _trading_days_old(date.fromisoformat(shareholding_period), as_of) > 100:
            blockers.append(f"Shareholding pattern ({shareholding_period}) is stale.")

        latest_price = connection.execute(
            "SELECT MAX(trade_date) FROM price_bars WHERE isin = ?", (profile.isin,)
        ).fetchone()[0]
        if latest_price is None:
            blockers.append(f"Recent {profile.nse_symbol} EOD prices are missing.")
        elif _trading_days_old(date.fromisoformat(latest_price), as_of) > 3:
            blockers.append(f"Latest price ({latest_price}) is more than three trading days old.")

        bad_facts = connection.execute(
            """
            SELECT COUNT(*)
            FROM financial_facts f
            LEFT JOIN documents d ON d.document_id = f.document_id
            WHERE f.isin = ? AND (
                f.validation_status <> 'accepted' OR d.document_id IS NULL
                OR d.validation_status <> 'accepted' OR d.isin <> f.isin
                OR f.publication_date IS NULL OR f.source_location IS NULL
                OR f.currency IS NULL OR f.source_value IS NULL
            )
            """,
            (profile.isin,),
        ).fetchone()[0]
        if bad_facts:
            blockers.append(f"{bad_facts} facts lack complete accepted source-document provenance.")
    return not blockers, tuple(blockers)


def run_company_pipeline(
    db_path: str | Path,
    fixture_dir: str | Path,
    as_of: date,
    additional_documents: tuple[Any, ...] = (),
    additional_financial_facts: tuple[Any, ...] = (),
) -> PipelineResult:
    fixture_path = Path(fixture_dir)
    profile = CompanyEvidenceProfile.load(fixture_path)
    initialize_database(db_path)
    documents = (
        CompanyIRCollector(profile.isin).collect(fixture_path / "documents.json")
        + NSEFilingsCollector(profile.isin).collect(fixture_path / "documents.json")
        + list(additional_documents)
    )
    facts = normalize_financial_results(fixture_path / "financial_results.csv", profile.isin)
    facts.extend(additional_financial_facts)
    prices = PriceCSVCollector(
        profile.isin,
        profile.price_source_id,
        profile.price_source_location,
    ).collect(fixture_path / "prices.csv")
    flags = evaluate_documents(documents)
    ownership_facts = [
        fact
        for document in documents
        if document.document_type == "shareholding_pattern"
        and document.raw_text.lstrip().startswith("<?xml")
        for fact in normalize_shareholding_xbrl(document)
    ]

    source_ids = {source.source_id for source in profile.sources}
    referenced_sources = (
        {document.source_id for document in documents}
        | {fact.source_id for fact in facts}
        | {price.source_id for price in prices}
    )
    missing_sources = sorted(referenced_sources - source_ids)
    if missing_sources:
        raise ValueError(f"Evidence references unregistered sources: {', '.join(missing_sources)}")
    document_keys = {document.document_key for document in documents}
    missing_documents = sorted({fact.document_key for fact in facts} - document_keys)
    if missing_documents:
        raise ValueError(f"Financial facts reference missing documents: {', '.join(missing_documents)}")

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    with transaction(db_path) as connection:
        for source in profile.sources:
            connection.execute(
                """
                INSERT INTO sources(source_id, source_name, base_url, evidence_tier, created_at)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(source_id) DO UPDATE SET
                    source_name=excluded.source_name,
                    base_url=excluded.base_url,
                    evidence_tier=excluded.evidence_tier
                """,
                (
                    source.source_id,
                    source.source_name,
                    source.base_url,
                    source.evidence_tier,
                    now,
                ),
            )

        document_ids: dict[str, int] = {}
        for document in documents:
            connection.execute(
                """
                INSERT INTO documents(
                    isin, source_id, document_type, title, published_at, retrieved_at,
                    source_location, content_hash, confidence, raw_text, document_key,
                    period_end, reporting_scope, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')
                ON CONFLICT(source_id, source_location, content_hash) DO UPDATE SET
                    title=excluded.title,
                    published_at=excluded.published_at,
                    retrieved_at=excluded.retrieved_at,
                    raw_text=excluded.raw_text,
                    document_key=excluded.document_key,
                    period_end=excluded.period_end,
                    reporting_scope=excluded.reporting_scope,
                    validation_status='accepted'
                """,
                (
                    document.isin,
                    document.source_id,
                    document.document_type,
                    document.title,
                    document.published_at,
                    document.retrieved_at,
                    document.source_location,
                    document.content_hash,
                    document.confidence,
                    document.raw_text,
                    document.document_key,
                    document.period_end,
                    document.reporting_scope,
                ),
            )
            row = connection.execute(
                """
                SELECT document_id FROM documents
                WHERE source_id = ? AND source_location = ? AND content_hash = ?
                """,
                (document.source_id, document.source_location, document.content_hash),
            ).fetchone()
            document_ids[document.document_key] = row["document_id"]

        for fact in facts:
            connection.execute(
                """
                INSERT INTO financial_facts(
                    isin, metric, value, unit, period_end, period_type, source_id,
                    document_id, retrieved_at, publication_date, currency, source_value,
                    source_location, evidence_label, confidence_label, statement_scope,
                    validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')
                ON CONFLICT(
                    isin, metric, period_end, period_type, source_id, statement_scope
                ) DO UPDATE SET
                    value=excluded.value,
                    unit=excluded.unit,
                    document_id=excluded.document_id,
                    retrieved_at=excluded.retrieved_at,
                    publication_date=excluded.publication_date,
                    currency=excluded.currency,
                    source_value=excluded.source_value,
                    source_location=excluded.source_location,
                    evidence_label=excluded.evidence_label,
                    confidence_label=excluded.confidence_label,
                    statement_scope=excluded.statement_scope,
                    validation_status='accepted'
                """,
                (
                    fact.isin,
                    fact.metric,
                    float(fact.value),
                    fact.unit,
                    fact.period_end,
                    fact.period_type,
                    fact.source_id,
                    document_ids[fact.document_key],
                    now,
                    fact.publication_date,
                    fact.currency,
                    fact.source_value,
                    fact.source_location,
                    fact.evidence_label,
                    fact.confidence_label,
                    fact.reporting_scope,
                ),
            )

        for fact in ownership_facts:
            connection.execute(
                """
                INSERT INTO ownership_facts(
                    isin, metric, value, unit, period_end, source_id, document_id,
                    retrieved_at, source_location, evidence_label, validation_status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'accepted')
                ON CONFLICT(isin, metric, period_end, source_id) DO UPDATE SET
                    value=excluded.value,
                    unit=excluded.unit,
                    document_id=excluded.document_id,
                    retrieved_at=excluded.retrieved_at,
                    source_location=excluded.source_location,
                    evidence_label=excluded.evidence_label,
                    validation_status='accepted'
                """,
                (
                    fact.isin,
                    fact.metric,
                    fact.value,
                    fact.unit,
                    fact.period_end,
                    fact.source_id,
                    document_ids[fact.document_key],
                    now,
                    fact.source_location,
                    fact.evidence_label,
                ),
            )

        flags.extend(evaluate_ownership_history(connection, profile.isin))
        flags.extend(evaluate_financial_health(connection, profile.isin))

        for price in prices:
            connection.execute(
                """
                INSERT INTO price_bars(isin, trade_date, close, volume, source_id, retrieved_at)
                VALUES (?, ?, ?, ?, ?, ?)
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

        for flag in flags:
            source_document_id = document_ids.get(flag.document_key)
            if source_document_id is None:
                row = connection.execute(
                    "SELECT document_id FROM documents WHERE document_key = ?",
                    (flag.document_key,),
                ).fetchone()
                if row is None:
                    raise ValueError(
                        f"Governance flag references missing document: {flag.document_key}"
                    )
                source_document_id = row["document_id"]
            connection.execute(
                """
                INSERT INTO governance_flags(
                    isin, rule_id, event_key, severity, message,
                    source_document_id, detected_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, 'open')
                ON CONFLICT(isin, rule_id, event_key) DO UPDATE SET
                    severity=excluded.severity,
                    message=excluded.message,
                    source_document_id=excluded.source_document_id,
                    detected_at=excluded.detected_at
                """,
                (
                    flag.isin,
                    flag.rule_id,
                    flag.event_key,
                    flag.severity,
                    flag.message,
                    source_document_id,
                    now,
                ),
            )

    ready, blockers = assess_company_readiness(db_path, profile, as_of)
    return PipelineResult(
        isin=profile.isin,
        documents=len(documents),
        financial_facts=len(facts),
        ownership_facts=len(ownership_facts),
        price_rows=len(prices),
        governance_flags=len(flags),
        ready=ready,
        blockers=blockers,
    )


def assess_tcs_readiness(db_path: str | Path, as_of: date) -> tuple[bool, tuple[str, ...]]:
    fixture_dir = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "tcs"
    return assess_company_readiness(db_path, CompanyEvidenceProfile.load(fixture_dir), as_of)


def run_tcs_pipeline(
    db_path: str | Path,
    fixture_dir: str | Path,
    as_of: date = date(2026, 7, 18),
) -> PipelineResult:
    return run_company_pipeline(db_path, fixture_dir, as_of)
