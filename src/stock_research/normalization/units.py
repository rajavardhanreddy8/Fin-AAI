from __future__ import annotations

from decimal import Decimal, InvalidOperation


UNIT_FACTORS: dict[str, tuple[str, str, Decimal]] = {
    "USD_million": ("USD", "million", Decimal("1")),
    "INR_million": ("INR", "million", Decimal("1")),
    "INR_crore": ("INR", "million", Decimal("10")),
    "INR_lakh": ("INR", "million", Decimal("0.1")),
    "percent": ("PCT", "percent", Decimal("1")),
    "USD_per_share": ("USD", "per_share", Decimal("1")),
    "INR_per_share": ("INR", "per_share", Decimal("1")),
    "per_share_USD": ("USD", "per_share", Decimal("1")),
    "per_share_INR": ("INR", "per_share", Decimal("1")),
    "shares": ("COUNT", "shares", Decimal("1")),
    "ratio": ("RATIO", "ratio", Decimal("1")),
    "multiple": ("RATIO", "multiple", Decimal("1")),
}


def normalize_value(source_value: str, source_unit: str) -> tuple[Decimal, str, str]:
    if source_unit not in UNIT_FACTORS:
        raise ValueError(f"Unsupported source unit: {source_unit!r}")
    try:
        value = Decimal(source_value.replace(",", "").strip())
    except (AttributeError, InvalidOperation) as exc:
        raise ValueError(f"Invalid numeric value: {source_value!r}") from exc
    currency, normalized_unit, factor = UNIT_FACTORS[source_unit]
    return value * factor, currency, normalized_unit
