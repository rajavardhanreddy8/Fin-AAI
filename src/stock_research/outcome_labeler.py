"""Deterministic observed price-reaction labels for event research."""
from __future__ import annotations

import hashlib
import math
from datetime import datetime, time, timedelta, timezone
from typing import Sequence

from .intraday_pilot import BAR_INTERVAL, IST, Bar

HORIZONS_MINUTES = (5, 30, 60)


def label_event_outcomes(event_id: str, available_at: datetime, bars: Sequence[Bar]) -> dict:
    """Label close-to-close reactions after event availability; this is not causal attribution."""
    if not isinstance(event_id, str) or not event_id.strip():
        raise ValueError("event_id is required")
    if available_at.tzinfo is None or available_at.utcoffset() is None:
        raise ValueError("available_at must include a timezone")
    available_at = available_at.astimezone(IST)
    normalized = []
    for bar in bars:
        at = bar.at.replace(tzinfo=IST) if bar.at.tzinfo is None else bar.at.astimezone(IST)
        values = (bar.open, bar.high, bar.low, bar.close, bar.volume)
        if (any(not math.isfinite(value) for value in values) or min(values[:4]) <= 0 or bar.volume < 0
                or bar.low > min(bar.open, bar.close) or bar.high < max(bar.open, bar.close)
                or bar.high < bar.low):
            raise ValueError("bars must contain finite, valid OHLCV values")
        if at.second or at.microsecond or at.minute % 5 or not time(9, 15) <= at.time() <= time(15, 25):
            raise ValueError("bars must use regular-session five-minute start timestamps")
        if normalized and at <= normalized[-1].at:
            raise ValueError("bars must be strictly chronological")
        normalized.append(Bar(at, *values))

    anchor_index = next((i for i, bar in enumerate(normalized)
                         if bar.at + BAR_INTERVAL > available_at), None)
    if anchor_index is None:
        return {"outcomes": [], "skipped": [
            {"horizon_minutes": horizon, "reason": "no_completed_bar_after_availability"}
            for horizon in HORIZONS_MINUTES
        ]}
    anchor = normalized[anchor_index]
    decision_at = anchor.at + BAR_INTERVAL
    if decision_at <= available_at:
        raise AssertionError("outcome anchor must follow event availability")

    outcomes, skipped = [], []
    by_close = {bar.at + BAR_INTERVAL: (i, bar) for i, bar in enumerate(normalized)}
    for horizon in HORIZONS_MINUTES:
        target_at = decision_at + timedelta(minutes=horizon)
        if target_at.date() != decision_at.date() or target_at.time() > time(15, 30):
            skipped.append({"horizon_minutes": horizon, "reason": "session_crossing"})
            continue
        required = [decision_at + timedelta(minutes=5 * step)
                    for step in range(1, horizon // 5 + 1)]
        missing = [stamp.isoformat() for stamp in required if stamp not in by_close]
        crossed = any(stamp.date() != decision_at.date() for stamp in required)
        if crossed:
            skipped.append({"horizon_minutes": horizon, "reason": "session_crossing"})
            continue
        target = by_close.get(target_at)
        if missing or target is None or target[0] <= anchor_index:
            skipped.append({"horizon_minutes": horizon, "reason": "missing_completed_bars",
                            "missing_close_times": missing or [target_at.isoformat()]})
            continue
        target_bar = target[1]
        bps = (target_bar.close / anchor.close - 1.0) * 10000
        identity = f"{event_id}|{decision_at.isoformat()}|{horizon}"
        analog_id = hashlib.sha256(identity.encode()).hexdigest()
        outcomes.append({"analog_id": analog_id, "event_id": event_id,
                         "decision_at": decision_at.isoformat(),
                         "outcome_completed_at": target_at.isoformat(),
                         "known_at": target_at.astimezone(timezone.utc).isoformat(),
                         "horizon_minutes": horizon,
                         "method": "observed close-to-close price reaction; not causal impact",
                         "outcome": "positive" if bps > 0 else "negative" if bps < 0 else "flat",
                         "outcome_bps": bps, "evidence_refs": []})
    return {"outcomes": outcomes, "skipped": skipped}
