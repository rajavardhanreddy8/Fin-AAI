from __future__ import annotations

import json
import uuid
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from .db import transaction


@dataclass(frozen=True, slots=True)
class QualityIssue:
    run_id: str
    isin: str | None
    check_name: str
    severity: str
    message: str
    detected_at: str


@dataclass(frozen=True, slots=True)
class QualityResult:
    run_id: str
    checked_at: str
    securities_checked: int
    blocking: int
    warnings: int
    info: int
    issues: tuple[QualityIssue, ...]

    @property
    def safe_for_recommendations(self) -> bool:
        return self.blocking == 0

    def to_dict(self) -> dict:
        result = asdict(self)
        result["safe_for_recommendations"] = self.safe_for_recommendations
        return result


def load_policy(path: str | Path) -> dict:
    with Path(path).open(encoding="utf-8") as handle:
        return json.load(handle)


def run_quality_checks(
    db_path: str | Path,
    policy_path: str | Path,
    as_of_date: date | None = None,
) -> QualityResult:
    policy = load_policy(policy_path)
    settings = policy["data_quality"]
    as_of = as_of_date or date.today()
    detected = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
    run_id = f"dq-{as_of.isoformat()}-{uuid.uuid4().hex[:8]}"
    issues: list[QualityIssue] = []

    def add(isin: str | None, check: str, severity: str, message: str) -> None:
        issues.append(QualityIssue(run_id, isin, check, severity, message, detected))

    with transaction(db_path) as connection:
        securities = connection.execute(
            "SELECT * FROM securities WHERE active = 1 ORDER BY isin"
        ).fetchall()
        if not securities:
            add(None, "universe_present", "blocking", "No active securities are loaded.")

        duplicate_symbols = connection.execute(
            """
            SELECT nse_symbol, COUNT(*) AS count
            FROM securities
            WHERE nse_symbol IS NOT NULL
            GROUP BY nse_symbol HAVING COUNT(*) > 1
            """
        ).fetchall()
        for row in duplicate_symbols:
            add(None, "unique_exchange_identity", "blocking", f"Duplicate NSE symbol {row['nse_symbol']}.")

        price_cutoff = as_of - timedelta(days=int(settings["maximum_price_age_days"]))
        filing_cutoff = as_of - timedelta(days=int(settings["maximum_filing_age_days"]))
        minimum_docs = int(settings["minimum_official_documents_per_security"])

        for security in securities:
            isin = security["isin"]
            latest_price = connection.execute(
                "SELECT MAX(trade_date) AS latest FROM price_bars WHERE isin = ?", (isin,)
            ).fetchone()["latest"]
            if latest_price is None:
                add(isin, "price_available", "blocking", "No price data is available.")
            elif date.fromisoformat(latest_price) < price_cutoff:
                add(
                    isin,
                    "price_freshness",
                    "blocking",
                    f"Latest price {latest_price} is older than cutoff {price_cutoff.isoformat()}.",
                )

            official_docs = connection.execute(
                """
                SELECT COUNT(*) AS count, MAX(d.published_at) AS latest
                FROM documents d
                JOIN sources s ON s.source_id = d.source_id
                WHERE d.isin = ? AND s.evidence_tier IN ('official', 'company_primary')
                """,
                (isin,),
            ).fetchone()
            if official_docs["count"] < minimum_docs:
                add(
                    isin,
                    "official_evidence_coverage",
                    "blocking",
                    f"Only {official_docs['count']} official/primary documents; minimum is {minimum_docs}.",
                )
            elif official_docs["latest"]:
                try:
                    published_date = parse_date(official_docs["latest"])
                    if published_date < filing_cutoff:
                        add(
                            isin,
                            "filing_freshness",
                            "warning",
                            f"Latest attributable official filing is dated {published_date.isoformat()}.",
                        )
                except ValueError:
                    add(
                        isin,
                        "filing_date_parse",
                        "warning",
                        "Latest filing date is present but could not be parsed reliably.",
                    )

        orphan_docs = connection.execute(
            "SELECT COUNT(*) AS count FROM documents WHERE isin IS NULL"
        ).fetchone()["count"]
        if orphan_docs:
            add(
                None,
                "document_attribution",
                "warning",
                f"{orphan_docs} documents are not yet mapped to an ISIN.",
            )

        for issue in issues:
            connection.execute(
                """
                INSERT INTO quality_issues(
                    run_id, isin, check_name, severity, message, detected_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    issue.run_id,
                    issue.isin,
                    issue.check_name,
                    issue.severity,
                    issue.message,
                    issue.detected_at,
                ),
            )

    counts = {severity: sum(i.severity == severity for i in issues) for severity in ("blocking", "warning", "info")}
    return QualityResult(
        run_id=run_id,
        checked_at=detected,
        securities_checked=len(securities),
        blocking=counts["blocking"],
        warnings=counts["warning"],
        info=counts["info"],
        issues=tuple(issues),
    )


def parse_date(value: str) -> date:
    value = value.strip()
    parsers = (
        lambda: datetime.fromisoformat(value.replace("Z", "+00:00")).date(),
        lambda: datetime.strptime(value[:16], "%a, %d %b %Y").date(),
        lambda: datetime.strptime(value[:10], "%Y-%m-%d").date(),
    )
    for parser in parsers:
        try:
            return parser()
        except ValueError:
            continue
    raise ValueError(f"Unparseable date: {value!r}")


def save_quality_json(result: QualityResult, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(result.to_dict(), indent=2), encoding="utf-8")

