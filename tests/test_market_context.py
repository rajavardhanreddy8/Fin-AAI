from __future__ import annotations

import unittest

from stock_research.market_context import (CATEGORIES, build_candidate_review,
    build_investigation, build_snapshot, compare_sector_peers,
    index_contributions, review_rl_outcomes, select_events)


class MarketContextTests(unittest.TestCase):
    def setUp(self):
        self.asof = "2026-02-01T10:00:00Z"

    def event(self, **changes):
        event = {"event_id": "r1", "canonical_id": "story", "available_at": "2026-02-01T09:00:00Z",
                 "published_at": "2026-02-01T08:00:00Z", "entities": ["ACME"], "revision_id": "1"}
        return event | changes

    def test_cutoff_revision_and_syndicated_duplicates(self):
        old = self.event()
        new = self.event(event_id="r2", revision_id="2", available_at="2026-02-01T09:30:00Z")
        future = self.event(canonical_id="future", available_at="2026-02-01T10:01:00Z")
        copy = self.event(event_id="copy", canonical_id="story", available_at="2026-02-01T09:15:00Z")
        selected = select_events([old, new, future, copy], self.asof)
        self.assertEqual(len(selected), 1)
        self.assertEqual(selected[0]["event_id"], "r2")
        self.assertEqual(select_events([old, new], "2026-02-01T09:20:00Z")[0]["event_id"], "r1")
        annotations = [
            {"event_id": "r2", "available_at": "2026-02-01T09:45:00Z", "categories": ["company_performance"], "score": 50, "confidence": .8, "evidence_refs": ["https://source/story"]},
            {"event_id": "r2", "available_at": "2026-02-01T10:01:00Z", "categories": ["company_performance"], "score": -50, "confidence": .8, "evidence_refs": ["https://source/story"]},
        ]
        snapshot = build_snapshot(asof=self.asof, target="ACME", events=[old, new, future, copy], annotations=annotations)
        self.assertEqual(snapshot["categories"]["company_performance"]["score"], 50)

    def test_same_timestamp_conflicting_event_tie_is_replay_deterministic(self):
        left = self.event(body="left")
        right = self.event(body="right", entities=[])
        annotation = {"event_id": "r1", "available_at": "2026-02-01T09:30:00Z",
            "categories": ["company_performance"], "score": 50, "confidence": .8,
            "evidence_refs": ["https://source/story"]}
        first = build_snapshot(asof=self.asof, target="ACME", events=[left, right], annotations=[annotation])
        second = build_snapshot(asof=self.asof, target="ACME", events=[right, left], annotations=[annotation])
        self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])

    def test_missing_is_gap_and_snapshot_hash_is_stable(self):
        e = self.event()
        first = build_snapshot(asof=self.asof, target="ACME", events=[e], annotations=[{"event_id": "r1", "available_at": "2026-02-01T10:01:00Z", "categories": ["company_performance"], "score": 42, "confidence": .5}])
        second = build_snapshot(asof=self.asof, target="ACME", events=[e], annotations=[{"event_id": "r1", "available_at": "2026-02-01T10:01:00Z", "categories": ["company_performance"], "score": 42, "confidence": .5}])
        self.assertIsNone(first["categories"]["company_performance"]["score"])
        self.assertEqual(first["categories"]["company_performance"]["coverage"], 0)
        self.assertEqual(first["snapshot_hash"], second["snapshot_hash"])

    def test_index_contribution_keeps_uncovered_weight_as_residual(self):
        result = index_contributions(index_return=.10, constituent_returns={"A": .20}, asof=self.asof, weights=[
            {"snapshot_id": "s1", "complete": True, "member": "A", "weight": .5, "known_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z"},
            {"snapshot_id": "s1", "complete": True, "member": "B", "weight": .5, "known_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z"},
        ])
        self.assertEqual(result["coverage_weight"], .5)
        self.assertEqual(result["weight_coverage"], 1)
        self.assertAlmostEqual(result["known_contribution"], .1)
        self.assertAlmostEqual(result["residual"], 0)
        self.assertEqual(result["status"], "partial_price_coverage")

    def test_latest_incomplete_weight_snapshot_does_not_backfill_removed_members(self):
        result = index_contributions(index_return=.1, constituent_returns={"A": .2, "B": -.1}, asof=self.asof, weights=[
            {"snapshot_id": "old", "complete": True, "member": "A", "weight": .5, "known_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z"},
            {"snapshot_id": "old", "complete": True, "member": "B", "weight": .5, "known_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z"},
            {"snapshot_id": "new", "complete": False, "member": "A", "weight": .5, "known_at": "2026-01-15T00:00:00Z", "effective_at": "2026-01-15T00:00:00Z"},
        ])
        self.assertEqual(result["weight_snapshot_id"], "new")
        self.assertEqual(result["contributions"], {"A": .1})
        self.assertEqual(result["status"], "incomplete_weight_snapshot")
        self.assertEqual(result["weight_gap"], .5)

    def test_peer_comparison_has_point_in_time_missing_peer_coverage(self):
        peers = {"peer_set_id": "banks-2026", "sector": "banks", "peer_ids": ["B", "C", "D"], "metrics": ["roe", "pb"],
                 "documented_at": "2026-01-01T00:00:00Z", "effective_at": "2026-01-01T00:00:00Z",
                 "methodology": "exchange-listed domestic banks", "source_refs": ["https://example.test/peer-method"]}
        observations = [
            {"company": "ACME", "metric": "roe", "value": 12, "effective_at": "2025-12-31T00:00:00Z", "available_at": "2026-01-05T00:00:00Z"},
            {"company": "B", "metric": "roe", "value": 8, "effective_at": "2025-12-31T00:00:00Z", "available_at": "2026-01-05T00:00:00Z", "revision_id": "1"},
            {"company": "B", "metric": "roe", "value": 10, "effective_at": "2025-12-31T00:00:00Z", "available_at": "2026-01-20T00:00:00Z", "revision_id": "2"},
            {"company": "C", "metric": "roe", "value": 14, "effective_at": "2025-12-31T00:00:00Z", "available_at": "2026-01-05T00:00:00Z"},
            {"company": "D", "metric": "roe", "value": 100, "effective_at": "2025-12-31T00:00:00Z", "available_at": "2026-02-02T00:00:00Z"},
        ]
        result = compare_sector_peers(asof=self.asof, target="ACME", peer_set=peers, observations=observations)
        self.assertEqual(result, compare_sector_peers(asof=self.asof, target="ACME", peer_set=peers, observations=reversed(observations)))
        metric = result["metrics"]["roe"]
        self.assertEqual(metric["peer_median"], 12)
        self.assertEqual(metric["missing_peers"], ["D"])
        self.assertEqual(metric["peer_coverage"], 2 / 3)
        self.assertEqual(metric["target"], 12)
        self.assertFalse(result["metrics"]["pb"]["target_coverage"])
        self.assertEqual(result["metrics"]["pb"]["missing_peers"], ["B", "C", "D"])
        with self.assertRaisesRegex(ValueError, "cutoff"):
            compare_sector_peers(asof=self.asof, target="ACME", peer_set=peers | {"documented_at": "2026-02-02T00:00:00Z"}, observations=observations)

    def test_investigation_separates_decision_evidence_from_possible_discoveries(self):
        snapshot = {"asof": self.asof, "eligible_no_trade": True, "categories": {name: None for name in CATEGORIES}}
        result = build_investigation(investigation_id="investigation-1", kind="eligible_no_trade", decision_at=self.asof,
            decision_snapshot=snapshot,
            decision_evidence=[{"available_at": "2026-02-01T09:00:00Z", "ref": "original"}],
            discoveries=[{"available_at": "2026-02-01T10:01:00Z", "ref": "later"}])
        self.assertEqual(result["original_decision_evidence"][0]["ref"], "original")
        self.assertEqual(result["later_discoveries"][0]["label"], "possible_explanation")
        self.assertIsNone(result["causal_claim"])
        with self.assertRaisesRegex(ValueError, "decision time"):
            build_investigation(investigation_id="bad", kind="winning_trade", decision_at=self.asof,
                decision_snapshot=snapshot, decision_evidence=[{"available_at": "2026-02-01T10:01:00Z"}])
        with self.assertRaisesRegex(ValueError, "eligibility"):
            build_investigation(investigation_id="bad", kind="eligible_no_trade", decision_at=self.asof,
                decision_snapshot={"asof": self.asof})

    def test_candidate_weights_are_versioned_chronological_and_isolated(self):
        records = []
        for day, score, outcome in [(1, -2, -10), (2, -1, -5), (3, 1, 5),
                                    (4, -3, -9), (5, 2, 8), (8, 100, 1000)]:
            decision = f"2026-02-{day:02d}T09:00:00Z"
            records.append({"event_id": f"e{day}", "decision_at": decision,
                "outcome_at": f"2026-02-{day:02d}T10:00:00Z", "outcome_bps": outcome,
                "snapshot_hash": f"snapshot-{day}", "snapshot_asof": decision,
                "categories": {"company_performance": score},
                "executed_action": "BUY"})
        args = dict(candidate_version="weights-v1", train_through="2026-02-03T23:59:00Z",
                    validation_through="2026-02-06T23:59:00Z", cost_bps=2)
        first = build_candidate_review(records=records, **args)
        second = build_candidate_review(records=reversed(records), **args)
        self.assertEqual(first["review_hash"], second["review_hash"])
        self.assertEqual(first["weights"], second["weights"])
        self.assertEqual(first["weights_version"], "weights-v1")
        self.assertEqual(first["train_sample_count"], 3)
        self.assertEqual(first["candidate_validation"]["sample_count"], 2)
        self.assertEqual(first["candidate_validation"]["cost_bps_per_observation"], 2)
        self.assertEqual(first["cost_evidence_status"], "operator_supplied_unverified")
        self.assertEqual(first["baseline"]["version"], "frozen_equal_weight_v1")
        self.assertFalse(first["auto_promote"])
        changed_future = records[-1] | {"outcome_bps": -9000, "categories": {"company_performance": -100}}
        future_changed_review = build_candidate_review(records=[*records[:-1], changed_future], **args)
        self.assertEqual(first["weights"], future_changed_review["weights"])
        with self.assertRaisesRegex(ValueError, "future information"):
            build_candidate_review(records=[records[0] | {"snapshot_asof": "2026-02-02T00:00:00Z"}], **args)
        with self.assertRaisesRegex(ValueError, "unique event_id"):
            build_candidate_review(records=[records[0], records[0]], **args)
        zero_cost = build_candidate_review(records=records, **(args | {"cost_bps": 0}))
        self.assertEqual(zero_cost["cost_evidence_status"], "unverified")

    def test_rl_review_never_attributes_overridden_reward_and_applies_cost(self):
        result = review_rl_outcomes([
            {"decision_id": "a", "policy_version": "rl-v1", "rl_action": "BUY", "executed_action": "BUY", "realized_return_bps": 12, "decision_at": "2026-02-01T09:00:00Z", "outcome_at": "2026-02-01T10:00:00Z", "execution_matched_rl": True, "engine_version": 2},
            {"decision_id": "b", "policy_version": "rl-v1", "rl_action": "BUY", "executed_action": "HOLD", "overridden": True, "realized_return_bps": 50, "decision_at": "2026-02-01T09:00:00Z", "outcome_at": "2026-02-01T10:00:00Z", "execution_matched_rl": True, "engine_version": 2},
            {"decision_id": "c", "policy_version": "rl-v1", "rl_action": "BUY", "executed_action": "BUY", "realized_return_bps": 50, "decision_at": "2026-02-01T09:00:00Z", "outcome_at": "2026-02-01T10:00:00Z", "execution_matched_rl": False, "engine_version": 2},
            {"decision_id": "d", "policy_version": "rl-v1", "rl_action": "BUY", "executed_action": "BUY", "realized_return_bps": 50, "decision_at": "2026-02-01T09:00:00Z", "outcome_at": "2026-02-01T10:00:00Z", "execution_matched_rl": True, "engine_version": 1},
        ], cost_bps=3)
        self.assertEqual(result["decisions"][0]["reward_net_bps"], 9)
        self.assertIsNone(result["decisions"][1]["reward_net_bps"])
        self.assertIsNone(result["decisions"][2]["reward_net_bps"])
        self.assertIsNone(result["decisions"][3]["reward_net_bps"])
        self.assertFalse(result["auto_promote"])
        zero_cost = review_rl_outcomes([], cost_bps=0)
        self.assertEqual(zero_cost["cost_evidence_status"], "unverified")


if __name__ == "__main__":
    unittest.main()
