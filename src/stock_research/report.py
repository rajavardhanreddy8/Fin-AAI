from __future__ import annotations

from datetime import date
from pathlib import Path

from .db import connect
from .quality import QualityResult


def build_weekly_report(db_path: str | Path, quality: QualityResult, as_of: date | None = None) -> str:
    report_date = as_of or date.today()
    with connect(db_path) as connection:
        universe_count = connection.execute(
            "SELECT COUNT(*) FROM securities WHERE active = 1"
        ).fetchone()[0]
        price_count = connection.execute("SELECT COUNT(*) FROM price_bars").fetchone()[0]
        document_count = connection.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        recommendation_count = connection.execute("SELECT COUNT(*) FROM recommendations").fetchone()[0]
        holdings_count = connection.execute("SELECT COUNT(*) FROM portfolio_holdings").fetchone()[0]

    blocking_lines = [
        f"- `{issue.isin or 'SYSTEM'}` — {issue.message}"
        for issue in quality.issues
        if issue.severity == "blocking"
    ]
    warning_lines = [
        f"- `{issue.isin or 'SYSTEM'}` — {issue.message}"
        for issue in quality.issues
        if issue.severity == "warning"
    ]

    status = "BLOCKED — research data is not sufficient for recommendations" if quality.blocking else "READY for later research-agent analysis"
    holdings_note = (
        "No portfolio is loaded yet, so portfolio risks and rebalancing are intentionally deferred."
        if holdings_count == 0
        else f"{holdings_count} holding snapshots are available for portfolio review."
    )
    recommendations_note = (
        "No stock recommendation has been generated in Phase 1."
        if recommendation_count == 0
        else f"{recommendation_count} recommendation records exist in the append-only ledger."
    )

    return f"""# Weekly Indian Equity Research Report

**As of:** {report_date.isoformat()}  
**System status:** {status}  
**Scope:** Research support only; no order placement.

## What changed

- Foundation contains {universe_count} active securities, {price_count} price rows, and {document_count} source documents.
- {holdings_note}
- {recommendations_note}

## What matters

- Data-quality result: **{quality.blocking} blocking**, **{quality.warnings} warning**, **{quality.info} informational** issues.
- A positive recommendation is prohibited while any blocking issue remains.

## What to watch

### Blocking issues

{chr(10).join(blocking_lines) if blocking_lines else '- None.'}

### Warnings

{chr(10).join(warning_lines) if warning_lines else '- None.'}

## What action can be considered

- Resolve missing or stale price and official-filing coverage.
- Add the portfolio later by CSV or broker adapter before enabling rebalancing analysis.
- Do not buy, average, or exit solely from this Phase 1 report.

## Why the recommendation is given

- No recommendation is given. Phase 1 deliberately validates identity, provenance, freshness, and evidence coverage first.

## What can go wrong

- Exchange feeds can change format or block automated requests.
- A filing can be captured but mapped to the wrong company unless ISIN attribution is verified.
- Delayed Google Finance values are unsuitable as an execution-grade or sole valuation source.

## When to exit

- Not applicable until a company thesis exists. The system schema requires explicit exit triggers before any future entry recommendation can be stored.
"""


def save_report(report: str, output_path: str | Path) -> None:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(report, encoding="utf-8")

