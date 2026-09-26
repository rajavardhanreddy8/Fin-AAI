from __future__ import annotations

from dataclasses import dataclass
import sqlite3

from stock_research.collectors.base import CollectedDocument


@dataclass(frozen=True, slots=True)
class GovernanceFlag:
    isin: str
    rule_id: str
    event_key: str
    severity: str
    message: str
    document_key: str


KEYWORD_RULES: tuple[tuple[str, str, str, tuple[str, ...]], ...] = (
    ("auditor_resignation", "blocking", "Auditor resignation requires review.", ("auditor resignation", "resignation of auditor")),
    ("auditor_qualification", "blocking", "Auditor qualification requires review.", ("qualified opinion", "adverse opinion", "disclaimer of opinion")),
    ("promoter_pledge", "blocking", "Promoter pledge disclosure requires review.", ("promoter pledge", "encumbrance of shares")),
    ("promoter_selling", "warning", "Material promoter selling requires review.", ("promoter sale", "promoter selling", "sale of shares by promoter")),
    ("regulatory_action", "blocking", "Regulatory action requires review.", ("regulatory action", "sebi order", "penalty imposed", "show cause notice")),
    ("share_dilution", "warning", "Potential share dilution requires review.", ("preferential allotment", "qualified institutional placement", "issue of equity shares")),
    ("related_party", "warning", "Related-party disclosure requires review.", ("related party transaction", "material related party")),
    ("management_change", "info", "Management change detected.", ("change in management", "resignation of director", "appointment of director")),
    (
        "suspicious_announcement",
        "warning",
        "Announcement requires review for unusual or potentially adverse activity.",
        (
            "forensic audit",
            "fraud or default",
            "unusual movement in price",
            "rumour verification",
            "clarification on news reports",
        ),
    ),
)


def evaluate_documents(documents: list[CollectedDocument]) -> list[GovernanceFlag]:
    flags: list[GovernanceFlag] = []
    for document in documents:
        haystack = f"{document.title}\n{document.raw_text}".lower()
        for rule_id, severity, message, terms in KEYWORD_RULES:
            if any(term in haystack for term in terms):
                flags.append(
                    GovernanceFlag(
                        isin=document.isin,
                        rule_id=rule_id,
                        event_key=document.document_key,
                        severity=severity,
                        message=message,
                        document_key=document.document_key,
                    )
                )
    return flags


def evaluate_ownership_history(
    connection: sqlite3.Connection, isin: str
) -> list[GovernanceFlag]:
    flags: list[GovernanceFlag] = []
    pledge = connection.execute(
        """
        SELECT o.value, d.document_key FROM ownership_facts o
        JOIN documents d ON d.document_id = o.document_id
        WHERE o.isin = ? AND o.metric = 'promoter_pledged_flag'
          AND o.validation_status = 'accepted'
        ORDER BY o.period_end DESC LIMIT 1
        """,
        (isin,),
    ).fetchone()
    if pledge is not None and float(pledge["value"]) > 0:
        flags.append(
            GovernanceFlag(
                isin=isin,
                rule_id="promoter_pledge",
                event_key=pledge["document_key"],
                severity="blocking",
                message="Promoter pledge or encumbrance is disclosed in the latest filing.",
                document_key=pledge["document_key"],
            )
        )

    holdings = connection.execute(
        """
        SELECT o.period_end, o.value, d.document_key FROM ownership_facts o
        JOIN documents d ON d.document_id = o.document_id
        WHERE o.isin = ? AND o.metric = 'promoter_holding_pct'
          AND o.validation_status = 'accepted'
        ORDER BY o.period_end DESC LIMIT 2
        """,
        (isin,),
    ).fetchall()
    if len(holdings) == 2 and float(holdings[1]["value"]) - float(holdings[0]["value"]) >= 0.02:
        flags.append(
            GovernanceFlag(
                isin=isin,
                rule_id="promoter_selling",
                event_key=holdings[0]["document_key"],
                severity="warning",
                message=(
                    "Promoter holding declined by at least 2 percentage points "
                    f"since {holdings[1]['period_end']}."
                ),
                document_key=holdings[0]["document_key"],
            )
        )
    return flags


def evaluate_financial_health(
    connection: sqlite3.Connection, isin: str
) -> list[GovernanceFlag]:
    """Evaluate quantitative rules only when accepted attributable facts exist."""
    latest_period = connection.execute(
        """
        SELECT MAX(period_end) FROM financial_facts
        WHERE isin = ? AND period_type = 'annual' AND validation_status = 'accepted'
        """,
        (isin,),
    ).fetchone()[0]
    if latest_period is None:
        return []
    rows = connection.execute(
        """
        SELECT f.metric, f.value, d.document_key
        FROM financial_facts f JOIN documents d ON d.document_id = f.document_id
        WHERE f.isin = ? AND f.period_type = 'annual' AND f.period_end = ?
          AND f.validation_status = 'accepted'
        """,
        (isin, latest_period),
    ).fetchall()
    values = {row["metric"]: float(row["value"]) for row in rows if row["value"] is not None}
    documents = {row["metric"]: row["document_key"] for row in rows}
    flags: list[GovernanceFlag] = []

    profit_metric = "profit_after_tax" if "profit_after_tax" in values else "net_income"
    if "operating_cash_flow" in values and profit_metric in values and values[profit_metric] > 0:
        conversion = values["operating_cash_flow"] / values[profit_metric]
        if conversion < 0.70:
            document_key = documents["operating_cash_flow"]
            flags.append(
                GovernanceFlag(
                    isin=isin,
                    rule_id="weak_cash_conversion",
                    event_key=f"{document_key}:{latest_period}",
                    severity="warning",
                    message=f"Operating cash flow was only {conversion:.0%} of profit after tax.",
                    document_key=document_key,
                )
            )

    debt_stressed = False
    debt_message = ""
    debt_document = None
    if "interest_coverage" in values and values["interest_coverage"] < 2:
        debt_stressed = True
        debt_message = f"Interest coverage was {values['interest_coverage']:.2f}x, below 2.0x."
        debt_document = documents["interest_coverage"]
    elif (
        "net_debt" in values
        and "ebitda" in values
        and values["ebitda"] > 0
        and values["net_debt"] / values["ebitda"] > 3
    ):
        leverage = values["net_debt"] / values["ebitda"]
        debt_stressed = True
        debt_message = f"Net debt was {leverage:.2f}x EBITDA, above 3.0x."
        debt_document = documents["net_debt"]
    if debt_stressed and debt_document:
        flags.append(
            GovernanceFlag(
                isin=isin,
                rule_id="debt_stress",
                event_key=f"{debt_document}:{latest_period}",
                severity="blocking",
                message=debt_message,
                document_key=debt_document,
            )
        )

    dilution = connection.execute(
        """
        SELECT f.period_end, f.value, d.document_key
        FROM financial_facts f JOIN documents d ON d.document_id = f.document_id
        WHERE f.isin = ? AND f.metric = 'shares_outstanding'
          AND f.period_type = 'annual' AND f.validation_status = 'accepted'
        ORDER BY f.period_end DESC LIMIT 3
        """,
        (isin,),
    ).fetchall()
    if len(dilution) == 3:
        newest, middle, oldest = dilution
        first_growth = float(middle["value"]) / float(oldest["value"]) - 1
        second_growth = float(newest["value"]) / float(middle["value"]) - 1
        if first_growth >= 0.02 and second_growth >= 0.02:
            flags.append(
                GovernanceFlag(
                    isin=isin,
                    rule_id="frequent_dilution",
                    event_key=f"{newest['document_key']}:{newest['period_end']}",
                    severity="warning",
                    message="Shares outstanding increased by at least 2% in each of two consecutive years.",
                    document_key=newest["document_key"],
                )
            )
    return flags
