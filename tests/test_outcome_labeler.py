from datetime import datetime, timedelta

import pytest

from stock_research.intraday_pilot import Bar, IST
from stock_research.outcome_labeler import label_event_outcomes


def bars(start="2026-01-02T09:15:00", count=75):
    opening = datetime.fromisoformat(start).replace(tzinfo=IST)
    return [Bar(opening + timedelta(minutes=5 * i), 100 + i, 101 + i, 99 + i,
                100 + i, 10) for i in range(count)]


def test_availability_boundary_anchors_only_at_a_completed_bar_after_event():
    result = label_event_outcomes("event-1", datetime.fromisoformat("2026-01-02T09:20:00+05:30"), bars())
    assert result["outcomes"][0]["decision_at"] == "2026-01-02T09:25:00+05:30"


def test_missing_required_bars_are_reported_as_gaps():
    rows = bars()
    result = label_event_outcomes("event-1", datetime.fromisoformat("2026-01-02T09:17:00+05:30"),
                                  [row for row in rows if row.at.minute != 20])
    assert result["outcomes"] == []
    assert result["skipped"][0]["reason"] == "missing_completed_bars"


def test_horizon_after_session_close_is_explicitly_skipped():
    result = label_event_outcomes("event-1", datetime.fromisoformat("2026-01-02T15:00:00+05:30"), bars())
    assert result["skipped"][-1] == {"horizon_minutes": 60, "reason": "session_crossing"}


def test_exact_close_return_is_reported_as_observed_not_causal():
    rows = bars()
    result = label_event_outcomes("event-1", datetime.fromisoformat("2026-01-02T09:17:00+05:30"), rows)
    five_minute = result["outcomes"][0]
    assert five_minute["outcome_bps"] == pytest.approx(100.0)
    assert "not causal" in five_minute["method"]
    assert datetime.fromisoformat(five_minute["known_at"]) >= datetime.fromisoformat(five_minute["outcome_completed_at"])


def test_repeated_runs_are_deterministic():
    at = datetime.fromisoformat("2026-01-02T09:17:00+05:30")
    assert label_event_outcomes("event-1", at, bars()) == label_event_outcomes("event-1", at, bars())
