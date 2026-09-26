from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timezone
from pathlib import Path

from .db import connect, transaction


@dataclass(frozen=True, slots=True)
class MaterialChange:
    isin: str
    change_key: str
    change_type: str
    severity: str
    summary: str
    source_document_id: int | None
    effective_date: str


def _document_event_key(document_type: str, period_end: str | None, document_key: str) -> str:
    if document_type.startswith("financial_results"):
        return f"financial_results:{period_end}"
    if document_type in {"annual_results", "annual_report", "shareholding_pattern"}:
        return f"{document_type}:{period_end}"
    return f"document:{document_key}"


def detect_weekly_material_changes(
    db_path: str | Path,
    isin: str,
    window_start: date,
    as_of: date,
    price_move_threshold: float = 0.10,
) -> tuple[MaterialChange, ...]:
    """Detect and persist source-backed changes for a closed weekly window."""
    if window_start > as_of:
        raise ValueError("Material-change window start cannot be after its as-of date")
    if price_move_threshold <= 0:
        raise ValueError("Price-move threshold must be positive")

    with connect(db_path) as connection:
        governance_rows = list(
            connection.execute(
                """
                SELECT g.rule_id, g.severity, g.message, g.source_document_id,
                       d.document_key, d.published_at
                FROM governance_flags g
                JOIN documents d ON d.document_id = g.source_document_id
                WHERE g.isin = ? AND date(d.published_at) BETWEEN ? AND ?
                ORDER BY date(d.published_at), g.rule_id, d.document_key
                """,
                (isin, window_start.isoformat(), as_of.isoformat()),
            )
        )
        governance_document_ids = {row["source_document_id"] for row in governance_rows}
        document_rows = list(
            connection.execute(
                """
                SELECT d.*, s.evidence_tier
                FROM documents d
                JOIN sources s ON s.source_id = d.source_id
                WHERE d.isin = ? AND d.validation_status = 'accepted'
                  AND date(d.published_at) BETWEEN ? AND ?
                ORDER BY date(d.published_at), d.document_key
                """,
                (isin, window_start.isoformat(), as_of.isoformat()),
            )
        )
        previous_price = connection.execute(
            """
            SELECT trade_date, close FROM price_bars
            WHERE isin = ? AND trade_date < ?
            ORDER BY trade_date DESC LIMIT 1
            """,
            (isin, window_start.isoformat()),
        ).fetchone()
        latest_price = connection.execute(
            """
            SELECT trade_date, close FROM price_bars
            WHERE isin = ? AND trade_date <= ?
            ORDER BY trade_date DESC LIMIT 1
            """,
            (isin, as_of.isoformat()),
        ).fetchone()
        latest_documents = {
            row["document_type"]: row["period_end"]
            for row in connection.execute(
                """
                SELECT document_type, MAX(period_end) AS period_end
                FROM documents
                WHERE isin = ? AND validation_status = 'accepted'
                  AND document_type IN ('annual_report', 'shareholding_pattern')
                GROUP BY document_type
                """,
                (isin,),
            )
        }
        trend_rows = list(
            connection.execute(
                """
                WITH candidates AS (
                    SELECT f.metric, f.period_end, f.value, f.publication_date,
                           f.document_id, d.document_key,
                           ROW_NUMBER() OVER (
                               PARTITION BY f.metric, f.period_end
                               ORDER BY CASE f.statement_scope WHEN 'consolidated' THEN 0 ELSE 1 END,
                                        f.retrieved_at DESC, f.fact_id DESC
                           ) AS period_rank
                    FROM financial_facts f
                    JOIN documents d ON d.document_id = f.document_id
                    WHERE f.isin = ? AND f.period_type = 'annual'
                      AND f.validation_status = 'accepted'
                      AND f.metric IN ('operating_cash_flow', 'total_debt', 'cash_and_equivalents')
                )
                SELECT *, ROW_NUMBER() OVER (PARTITION BY metric ORDER BY period_end DESC) AS rank
                FROM candidates WHERE period_rank = 1
                """,
                (isin,),
            )
        )

    changes: list[MaterialChange] = []
    for row in governance_rows:
        changes.append(
            MaterialChange(
                isin=isin,
                change_key=f"governance:{row['rule_id']}:{row['document_key']}",
                change_type="governance",
                severity=row["severity"],
                summary=row["message"],
                source_document_id=row["source_document_id"],
                effective_date=str(row["published_at"])[:10],
            )
        )

    tier_priority = {"official": 3, "company_primary": 2, "reputable_secondary": 1}
    evidence_events: dict[str, object] = {}
    for row in document_rows:
        if row["document_id"] in governance_document_ids:
            continue
        event_key = _document_event_key(row["document_type"], row["period_end"], row["document_key"])
        current = evidence_events.get(event_key)
        if current is None or tier_priority.get(row["evidence_tier"], 0) > tier_priority.get(current["evidence_tier"], 0):
            evidence_events[event_key] = row

    for event_key in sorted(evidence_events):
        row = evidence_events[event_key]
        severity = "warning" if row["document_type"] == "legal_update" else "info"
        changes.append(
            MaterialChange(
                isin=isin,
                change_key=event_key,
                change_type=row["document_type"],
                severity=severity,
                summary=f"New accepted evidence: {row['title']}",
                source_document_id=row["document_id"],
                effective_date=str(row["published_at"])[:10],
            )
        )

    if previous_price is not None and latest_price is not None:
        move = (float(latest_price["close"]) / float(previous_price["close"])) - 1.0
        if abs(move) >= price_move_threshold:
            changes.append(
                MaterialChange(
                    isin=isin,
                    change_key=f"price_move:{window_start.isoformat()}:{as_of.isoformat()}",
                    change_type="price_move",
                    severity="warning",
                    summary=f"Close moved {move:+.1%} from {previous_price['trade_date']} to {latest_price['trade_date']}.",
                    source_document_id=None,
                    effective_date=latest_price["trade_date"],
                )
            )

    by_metric: dict[str, list[object]] = {}
    for row in trend_rows:
        if row["rank"] <= 2:
            by_metric.setdefault(row["metric"], []).append(row)
    deterioration_rules = {
        "operating_cash_flow": (0.20, "cash_flow_deterioration", "Operating cash flow declined"),
        "cash_and_equivalents": (0.25, "cash_deterioration", "Cash and equivalents declined"),
    }
    for metric, (threshold, change_type, label) in deterioration_rules.items():
        metric_rows = by_metric.get(metric, [])
        if len(metric_rows) == 2 and metric_rows[1]["value"] not in (None, 0):
            newest, previous = metric_rows
            publication_date = newest["publication_date"]
            decline = 1 - float(newest["value"]) / float(previous["value"])
            if (
                publication_date
                and window_start.isoformat() <= publication_date <= as_of.isoformat()
                and decline >= threshold
            ):
                changes.append(
                    MaterialChange(
                        isin=isin,
                        change_key=f"{change_type}:{newest['period_end']}",
                        change_type=change_type,
                        severity="warning",
                        summary=f"{label} {decline:.1%} year over year.",
                        source_document_id=newest["document_id"],
                        effective_date=publication_date,
                    )
                )
    debt_rows = by_metric.get("total_debt", [])
    if len(debt_rows) == 2 and debt_rows[1]["value"] not in (None, 0):
        newest, previous = debt_rows
        publication_date = newest["publication_date"]
        increase = float(newest["value"]) / float(previous["value"]) - 1
        if (
            publication_date
            and window_start.isoformat() <= publication_date <= as_of.isoformat()
            and increase >= 0.25
        ):
            changes.append(
                MaterialChange(
                    isin=isin,
                    change_key=f"debt_deterioration:{newest['period_end']}",
                    change_type="debt_deterioration",
                    severity="warning",
                    summary=f"Total debt increased {increase:.1%} year over year.",
                    source_document_id=newest["document_id"],
                    effective_date=publication_date,
                )
            )

    if latest_price is None:
        changes.append(MaterialChange(isin, f"missing_price:{as_of}", "missing_information", "blocking", "No accepted EOD price is available.", None, as_of.isoformat()))
    elif (as_of - date.fromisoformat(latest_price["trade_date"])).days > 5:
        changes.append(MaterialChange(isin, f"stale_price:{as_of}", "stale_information", "blocking", f"Latest EOD price is stale ({latest_price['trade_date']}).", None, as_of.isoformat()))
    for document_type, label in (("annual_report", "annual report"), ("shareholding_pattern", "shareholding pattern")):
        if not latest_documents.get(document_type):
            changes.append(MaterialChange(isin, f"missing_{document_type}:{as_of}", "missing_information", "blocking", f"Latest {label} is missing.", None, as_of.isoformat()))

    detected_at = datetime.combine(as_of, time.max, tzinfo=timezone.utc).isoformat()
    with transaction(db_path) as connection:
        for change in changes:
            connection.execute(
                """
                INSERT INTO material_changes(
                    isin, change_key, change_type, severity, summary,
                    source_document_id, effective_date, detected_at, status
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'new')
                ON CONFLICT(isin, change_key) DO UPDATE SET
                    change_type=excluded.change_type,
                    severity=excluded.severity,
                    summary=excluded.summary,
                    source_document_id=excluded.source_document_id,
                    effective_date=excluded.effective_date,
                    detected_at=excluded.detected_at
                """,
                (
                    change.isin,
                    change.change_key,
                    change.change_type,
                    change.severity,
                    change.summary,
                    change.source_document_id,
                    change.effective_date,
                    detected_at,
                ),
            )
    return tuple(sorted(changes, key=lambda item: (item.effective_date, item.change_key)))
