from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from html.parser import HTMLParser

from .base import CollectedDocument, CollectorError, read_bytes
from ..normalization.financial_results import METRICS, NormalizedFact
from ..normalization.units import normalize_value


_SPACE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AnnualIXBRLSpec:
    isin: str
    symbol: str
    bse_code: str
    url: str
    published_at: date
    period_end: date
    reporting_scope: str


ANNUAL_IXBRL_SPECS = {
    "INE467B01029": AnnualIXBRLSpec(
        isin="INE467B01029",
        symbol="TCS",
        bse_code="532540",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_150311_09042026234134_iXBRL_WEB.html"
        ),
        published_at=date(2026, 4, 9),
        period_end=date(2026, 3, 31),
        reporting_scope="standalone",
    ),
    "INE009A01021": AnnualIXBRLSpec(
        isin="INE009A01021",
        symbol="INFY",
        bse_code="500209",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_152465_23042026210154_iXBRL_WEB.html"
        ),
        published_at=date(2026, 4, 23),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    ),
    "INE154A01025": AnnualIXBRLSpec(
        isin="INE154A01025",
        symbol="ITC",
        bse_code="500875",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_159756_21052026183229_iXBRL_WEB.html"
        ),
        published_at=date(2026, 5, 21),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    ),
    "INE018A01030": AnnualIXBRLSpec(
        isin="INE018A01030",
        symbol="LT",
        bse_code="500510",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_155661_05052026193236_iXBRL_WEB.html"
        ),
        published_at=date(2026, 5, 5),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    ),
    "INE585B01010": AnnualIXBRLSpec(
        isin="INE585B01010",
        symbol="MARUTI",
        bse_code="532500",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_153870_28042026212750_iXBRL_WEB.html"
        ),
        published_at=date(2026, 4, 28),
        period_end=date(2026, 3, 31),
        reporting_scope="standalone",
    ),
    "INE733E01010": AnnualIXBRLSpec(
        isin="INE733E01010",
        symbol="NTPC",
        bse_code="532555",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_160541_23052026160706_iXBRL_WEB.html"
        ),
        published_at=date(2026, 5, 23),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    ),
    "INE002A01018": AnnualIXBRLSpec(
        isin="INE002A01018",
        symbol="RELIANCE",
        bse_code="500325",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_152826_24042026225714_iXBRL_WEB.html"
        ),
        published_at=date(2026, 4, 24),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    ),
    "INE044A01036": AnnualIXBRLSpec(
        isin="INE044A01036",
        symbol="SUNPHARMA",
        bse_code="524715",
        url=(
            "https://nsearchives.nseindia.com/corporate/ixbrl/"
            "INTEGRATED_FILING_INDAS_160266_22052026183920_iXBRL_WEB.html"
        ),
        published_at=date(2026, 5, 22),
        period_end=date(2026, 3, 31),
        reporting_scope="consolidated",
    )
}


class _TableRows(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag.lower() == "tr":
            self._row = []
        elif tag.lower() in {"th", "td"} and self._row is not None:
            self._cell = []

    def handle_data(self, data: str) -> None:
        if self._cell is not None:
            self._cell.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in {"th", "td"} and self._row is not None and self._cell is not None:
            self._row.append(_SPACE.sub(" ", "".join(self._cell)).strip())
            self._cell = None
        elif tag.lower() == "tr" and self._row is not None:
            if any(self._row):
                self.rows.append(self._row)
            self._row = None
            self._cell = None


def _number(value: str) -> Decimal:
    text = value.strip().replace(",", "")
    if text.startswith("(") and text.endswith(")"):
        text = f"-{text[1:-1]}"
    try:
        return Decimal(text)
    except InvalidOperation as exc:
        raise CollectorError(f"Invalid NSE iXBRL numeric value: {value!r}") from exc


class NSEIXBRLFinancialCollector:
    """Collect audited annual facts from an official NSE integrated filing.

    The exchange's rendered iXBRL pages expose deterministic statement rows even
    when a company's annual-report PDF is protected by a download gateway.
    """

    def collect_annual(
        self,
        url: str,
        expected_isin: str,
        expected_symbol: str,
        expected_bse_code: str,
        published_at: date,
        period_end: date,
        reporting_scope: str = "standalone",
    ) -> tuple[CollectedDocument, list[NormalizedFact]]:
        body = read_bytes(url)
        html = body.decode("utf-8-sig", errors="replace")
        parser = _TableRows()
        parser.feed(html)
        rows = parser.rows

        row_values: dict[str, list[str]] = {}
        for row in rows:
            populated = [cell for cell in row if cell]
            if len(populated) >= 2:
                labels = [cell for cell in populated[:-1] if any(ch.isalpha() for ch in cell)]
                label = max(labels, key=len) if labels else None
                if label is not None:
                    row_values.setdefault(label.casefold(), []).append(populated[-1])

        identity = {
            "isin": expected_isin.upper(),
            "nse symbol": expected_symbol.upper(),
            "scrip code": expected_bse_code,
        }
        if any(
            not row_values.get(label) or row_values[label][-1].strip().upper() != expected
            for label, expected in identity.items()
        ):
            raise CollectorError("NSE iXBRL identity mismatch")
        scopes = row_values.get("nature of report standalone or consolidated", [])
        if not scopes or reporting_scope.casefold() not in {scope.casefold() for scope in scopes}:
            raise CollectorError("NSE iXBRL reporting-scope mismatch")

        def last(label: str) -> str:
            matches = row_values.get(label.casefold(), [])
            if not matches:
                raise CollectorError(f"NSE iXBRL is missing required row: {label}")
            return matches[-1]

        direct = {
            "revenue": last("Revenue from operations"),
            "profit_after_tax": last("Total profit (loss) for period"),
            "operating_cash_flow": last("Net cash flows from (used in) operating activities"),
            "cash_and_equivalents": last("Cash and cash equivalents"),
            "interest_expense": last("Finance costs"),
        }
        profit_before_tax = last("Total profit before tax")
        depreciation = last("Depreciation, depletion and amortisation expense")
        total_equity = last("Total equity")
        total_assets = last("Total assets")
        current_liabilities = last("Total current liabilities")
        ppe = last("Purchase of property, plant and equipment")
        intangibles = last("Purchase of intangible assets")
        debt_noncurrent = last("Borrowings, non-current")
        debt_current = last("Borrowings, current")
        paid_up_capital = last("Paid-up equity share capital")
        face_value = last("Face value of equity share capital")

        direct_values = {
            metric: normalize_value(value, "INR_lakh")[0]
            for metric, value in direct.items()
        }
        capex = normalize_value(str(_number(ppe) + _number(intangibles)), "INR_lakh")[0]
        total_debt = normalize_value(
            str(_number(debt_noncurrent) + _number(debt_current)), "INR_lakh"
        )[0]
        free_cash_flow = direct_values["operating_cash_flow"] - capex
        profit_before_tax_value = normalize_value(profit_before_tax, "INR_lakh")[0]
        depreciation_value = normalize_value(depreciation, "INR_lakh")[0]
        ebitda = profit_before_tax_value + direct_values["interest_expense"] + depreciation_value
        net_debt = total_debt - direct_values["cash_and_equivalents"]
        revenue = direct_values["revenue"]
        profit = direct_values["profit_after_tax"]
        equity = normalize_value(total_equity, "INR_lakh")[0]
        capital_employed = normalize_value(
            str(_number(total_assets) - _number(current_liabilities)), "INR_lakh"
        )[0]
        ebit = profit_before_tax_value + direct_values["interest_expense"]
        shares = (_number(paid_up_capital) * Decimal("100000")) / _number(face_value)

        document_key = (
            f"nse_ixbrl:{expected_isin.upper()}:{period_end.isoformat()}:{reporting_scope}"
        )
        retrieved_at = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        document = CollectedDocument(
            document_key=document_key,
            isin=expected_isin.upper(),
            source_id="nse_filings",
            source_tier="official",
            document_type="financial_results_ixbrl",
            title=f"NSE audited integrated filing for {expected_symbol.upper()} year ended {period_end.isoformat()}",
            published_at=published_at.isoformat(),
            retrieved_at=retrieved_at,
            source_location=url,
            period_end=period_end.isoformat(),
            reporting_scope=reporting_scope,
            content_hash=hashlib.sha256(body).hexdigest(),
            raw_text=html,
            confidence=1.0,
        )

        fact_specs = [
            (metric, direct[metric], value, "fact_source_reported")
            for metric, value in direct_values.items()
        ] + [
            ("capital_expenditure", f"{ppe} + {intangibles}", capex, "fact_derived"),
            ("free_cash_flow", f"operating cash flow - capital expenditure", free_cash_flow, "fact_derived"),
            ("total_debt", f"{debt_noncurrent} + {debt_current}", total_debt, "fact_derived"),
            ("net_debt", "total debt - cash and cash equivalents", net_debt, "fact_derived"),
            ("ebitda", "profit before tax + finance costs + depreciation and amortisation", ebitda, "fact_derived"),
            ("shares_outstanding", f"{paid_up_capital} lakh INR / INR {face_value}", shares, "fact_derived"),
            ("interest_coverage", "(profit before tax + finance costs) / finance costs", ebit / direct_values["interest_expense"], "fact_derived"),
            ("roe", "profit after tax / closing total equity", profit / equity * 100, "fact_derived"),
            ("roce", "EBIT / (closing total assets - closing current liabilities)", ebit / capital_employed * 100, "fact_derived"),
            ("ebitda_margin", "EBITDA / revenue from operations", ebitda / revenue * 100, "fact_derived"),
            ("net_margin", "profit after tax / revenue from operations", profit / revenue * 100, "fact_derived"),
        ]
        facts = [
            NormalizedFact(
                isin=expected_isin.upper(),
                document_key=document_key,
                source_id="nse_filings",
                metric=metric,
                metric_label=METRICS[metric],
                source_value=source_value,
                value=value,
                currency=(
                    "COUNT" if metric == "shares_outstanding"
                    else "RATIO" if metric == "interest_coverage"
                    else "PCT" if metric in {"roe", "roce", "ebitda_margin", "net_margin"}
                    else "INR"
                ),
                unit=(
                    "shares" if metric == "shares_outstanding"
                    else "multiple" if metric == "interest_coverage"
                    else "percent" if metric in {"roe", "roce", "ebitda_margin", "net_margin"}
                    else "million"
                ),
                period_label=f"FY{period_end.year}",
                period_end=period_end.isoformat(),
                period_type="annual",
                reporting_scope=reporting_scope,
                publication_date=published_at.isoformat(),
                source_location=url,
                evidence_label=evidence_label,
                confidence_label="high",
            )
            for metric, source_value, value, evidence_label in fact_specs
        ]
        return document, facts

    def collect_spec(self, spec: AnnualIXBRLSpec) -> tuple[CollectedDocument, list[NormalizedFact]]:
        return self.collect_annual(
            spec.url,
            spec.isin,
            spec.symbol,
            spec.bse_code,
            spec.published_at,
            spec.period_end,
            spec.reporting_scope,
        )
