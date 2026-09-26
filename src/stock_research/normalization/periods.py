from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class ReportingPeriod:
    label: str
    period_end: date
    period_type: str


def parse_period(label: str, period_end: str, period_type: str) -> ReportingPeriod:
    normalized_type = period_type.strip().lower()
    if normalized_type not in {"quarterly", "annual"}:
        raise ValueError(f"Unsupported period type: {period_type!r}")
    if not label.strip():
        raise ValueError("Period label is required")
    return ReportingPeriod(label.strip(), date.fromisoformat(period_end.strip()), normalized_type)
