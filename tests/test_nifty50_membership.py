from datetime import datetime, timezone

import pytest

from stock_research.collectors.nifty50_membership import build_snapshot


def payload(count=50):
    return ("Symbol,ISIN Code,Weight (%)\n" + "".join(f"S{i},IN{i:09d}{i % 10},{100/count}\n" for i in range(count))).encode()


def test_official_weight_snapshot_carries_identity_times_provenance_and_hashes():
    snap = build_snapshot(payload(), "https://www.niftyindices.com/data/nifty50.csv", observed_at=datetime(2026, 10, 15, tzinfo=timezone.utc), effective_at=datetime(2026, 10, 1, tzinfo=timezone.utc))
    assert len(snap["members"]) == 50
    assert snap["effective_at"].startswith("2026-10-01")
    assert snap["source_id"] == "nifty_indices_nifty50_weights"
    assert snap["raw_hash"] and snap["snapshot_id"]


def test_incomplete_or_unattributable_membership_is_rejected():
    with pytest.raises(ValueError, match="incomplete"):
        build_snapshot(payload(49), "https://www.niftyindices.com/data/nifty50.csv", observed_at=datetime.now(timezone.utc))
    with pytest.raises(ValueError, match="official"):
        build_snapshot(payload(), "https://example.com/nifty50.csv", observed_at=datetime.now(timezone.utc))
