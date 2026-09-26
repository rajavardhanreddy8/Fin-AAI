from __future__ import annotations

import csv
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from .periods import parse_period
from .units import normalize_value


METRICS = {
    "revenue": "Revenue",
    "net_revenue": "Net revenue",
    "net_interest_income": "Net interest income",
    "gross_revenue": "Gross revenue",
    "ebitda": "EBITDA",
    "operating_income": "Operating income",
    "net_income": "Net income",
    "profit_after_tax": "Profit after tax including associates and joint ventures",
    "eps_diluted": "EPS diluted",
    "operating_cash_flow": "Operating cash flow",
    "capital_expenditure": "Capital expenditure",
    "free_cash_flow": "Free cash flow",
    "total_debt": "Total debt",
    "cash_and_equivalents": "Cash and equivalents",
    "net_debt": "Net debt",
    "interest_expense": "Interest expense",
    "interest_coverage": "Interest coverage",
    "roe": "Return on equity",
    "roce": "Return on capital employed",
    "ebitda_margin": "EBITDA margin",
    "net_margin": "Net margin",
    "shares_outstanding": "Shares outstanding",
}


@dataclass(frozen=True, slots=True)
class NormalizedFact:
    isin: str
    document_key: str
    source_id: str
    metric: str
    metric_label: str
    source_value: str
    value: Decimal
    currency: str
    unit: str
    period_label: str
    period_end: str
    period_type: str
    reporting_scope: str
    publication_date: str
    source_location: str
    evidence_label: str = "fact_source_reported"
    confidence_label: str = "high"


def normalize_financial_results(path: str | Path, expected_isin: str) -> list[NormalizedFact]:
    facts: list[NormalizedFact] = []
    seen: set[tuple[str, str, str, str, str]] = set()
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        for row_number, row in enumerate(csv.DictReader(handle), start=2):
            try:
                isin = row["isin"].strip().upper()
                metric = row["metric"].strip()
                period = parse_period(row["period_label"], row["period_end"], row["period_type"])
                value, currency, unit = normalize_value(row["source_value"], row["source_unit"])
                document_key = row["document_key"].strip()
                source_id = row["source_id"].strip()
                source_location = row["source_location"].strip()
                publication_date = row["publication_date"].strip()
                reporting_scope = row.get("reporting_scope", "consolidated").strip().lower()
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(f"Invalid financial fact row {row_number}: {exc}") from exc
            if isin != expected_isin.upper():
                raise ValueError(f"Unexpected ISIN in financial fact row {row_number}: {isin}")
            if metric not in METRICS:
                raise ValueError(f"Unsupported metric in row {row_number}: {metric!r}")
            if not all((document_key, source_id, source_location, publication_date)):
                raise ValueError(f"Missing provenance in financial fact row {row_number}")
            key = (isin, metric, period.period_end.isoformat(), period.period_type, reporting_scope)
            if key in seen:
                raise ValueError(f"Duplicate normalized fact in row {row_number}: {key}")
            seen.add(key)
            facts.append(
                NormalizedFact(
                    isin=isin,
                    document_key=document_key,
                    source_id=source_id,
                    metric=metric,
                    metric_label=METRICS[metric],
                    source_value=row["source_value"].strip(),
                    value=value,
                    currency=currency,
                    unit=unit,
                    period_label=period.label,
                    period_end=period.period_end.isoformat(),
                    period_type=period.period_type,
                    reporting_scope=reporting_scope,
                    publication_date=publication_date,
                    source_location=source_location,
                )
            )
    if not facts:
        raise ValueError("Financial result file contains no facts")
    return facts
