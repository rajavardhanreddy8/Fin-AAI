from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from enum import StrEnum


class EvidenceTier(StrEnum):
    OFFICIAL = "official"
    COMPANY_PRIMARY = "company_primary"
    REPUTABLE_SECONDARY = "reputable_secondary"
    MARKET_OPINION = "market_opinion"
    SOCIAL = "social"


class RecommendationClass(StrEnum):
    CORE = "core_investment"
    HIGH_RISK = "high_risk_investment"
    SPECULATIVE = "speculative_investment"
    WATCHLIST = "watchlist_only"
    AVOID = "avoid"


class IssueSeverity(StrEnum):
    INFO = "info"
    WARNING = "warning"
    BLOCKING = "blocking"


@dataclass(frozen=True, slots=True)
class Security:
    isin: str
    company_name: str
    nse_symbol: str | None = None
    bse_code: str | None = None
    sector: str | None = None
    style_bucket: str = "watchlist"
    active: bool = True

    def validate(self) -> None:
        if len(self.isin) != 12 or not self.isin.isalnum():
            raise ValueError(f"Invalid ISIN: {self.isin!r}")
        if not self.company_name.strip():
            raise ValueError("company_name is required")
        if not self.nse_symbol and not self.bse_code:
            raise ValueError("At least one exchange identifier is required")


@dataclass(frozen=True, slots=True)
class PriceBar:
    isin: str
    trade_date: date
    close: float
    volume: int | None
    source_id: str
    retrieved_at: datetime

    def validate(self) -> None:
        if self.close <= 0:
            raise ValueError("close must be positive")
        if self.volume is not None and self.volume < 0:
            raise ValueError("volume cannot be negative")
        if self.retrieved_at.tzinfo is None:
            raise ValueError("retrieved_at must be timezone-aware")


def utc_now() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)
