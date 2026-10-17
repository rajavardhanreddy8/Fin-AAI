"""Deterministic, time-locked research context. Scores are shadow baselines only."""
from __future__ import annotations

import hashlib
import json
import math
import statistics
from datetime import datetime, timezone
from typing import Iterable

CATEGORIES = ("company_performance", "valuation_expectations", "sector_conditions", "governance_policy",
              "domestic_economy", "global_conditions", "external_risks", "market_behaviour")


def _time(value: str | None) -> datetime | None:
    if value is None:
        return None
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include timezone")
    return parsed.astimezone(timezone.utc)


def _canonical(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _event_at_cutoff(event: dict, cutoff: datetime) -> bool:
    available = _time(event.get("available_at"))
    published = _time(event.get("published_at"))
    return bool(available and available <= cutoff and (published is None or published <= cutoff))


def select_events(events: Iterable[dict], asof: str) -> list[dict]:
    """Select the latest known revision per canonical event; syndicated copies count once."""
    cutoff = _time(asof)
    if cutoff is None:
        raise ValueError("asof required")
    selected: dict[str, dict] = {}
    for event in events:
        if not _event_at_cutoff(event, cutoff):
            continue
        identity = str(event.get("canonical_id") or event.get("event_id") or "")
        if not identity:
            raise ValueError("event requires canonical_id or event_id")
        prev = selected.get(identity)
        revision_time = _time(event["available_at"])
        prev_time = _time(prev["available_at"]) if prev else None
        tie_break = (str(event.get("event_id", "")), _canonical(event))
        prev_tie_break = (str(prev.get("event_id", "")), _canonical(prev)) if prev else None
        if prev is None or revision_time > prev_time or (revision_time == prev_time and tie_break > prev_tie_break):
            selected[identity] = event
    return [selected[key] for key in sorted(selected)]


def _belongs(event: dict, target: str) -> bool:
    entities = event.get("entities", [])
    return target in entities if isinstance(entities, list) else target in entities


def _latest_dated_snapshot(rows: Iterable[dict], cutoff: datetime) -> tuple[str | None, list[dict], bool]:
    groups: dict[str, list[dict]] = {}
    for row in rows:
        known, effective = _time(row.get("known_at")), _time(row.get("effective_at"))
        if known is None or effective is None or type(row.get("complete")) is not bool:
            raise ValueError("membership rows require known_at, effective_at and declared completeness")
        snapshot_id = str(row.get("snapshot_id") or f"{effective.isoformat()}|{known.isoformat()}")
        groups.setdefault(snapshot_id, []).append(row)
    candidates = []
    for snapshot_id, members in groups.items():
        stamps = {(_time(row["known_at"]), _time(row["effective_at"]), row["complete"]) for row in members}
        if len(stamps) != 1:
            raise ValueError("mixed membership snapshot metadata")
        known, effective, complete = next(iter(stamps))
        if known <= cutoff and effective <= cutoff:
            candidates.append((effective, known, snapshot_id, members, complete))
    if not candidates:
        return None, [], False
    newest = max((row[0], row[1]) for row in candidates)
    latest = [row for row in candidates if row[:2] == newest]
    if len(latest) != 1:
        raise ValueError("ambiguous membership snapshots at cutoff")
    _, _, snapshot_id, members, complete = latest[0]
    member_ids = [str(row.get("member", "")) for row in members]
    if not all(member_ids) or len(set(member_ids)) != len(member_ids):
        raise ValueError("membership snapshot has missing or duplicate members")
    return snapshot_id, members, complete


def build_snapshot(*, asof: str, target: str, events: Iterable[dict], annotations: Iterable[dict] = (), membership: Iterable[dict] = ()) -> dict:
    """Create frozen equal-weight category scores only from explicitly scored source evidence."""
    cutoff = _time(asof)
    if cutoff is None:
        raise ValueError("asof required")
    available = select_events(events, asof)
    selected_ids = {str(e.get("event_id")): e for e in available}
    latest_annotations: dict[tuple[str, str], dict] = {}
    for annotation in annotations:
        known = _time(annotation.get("available_at"))
        if not known or known > cutoff:
            continue
        event = selected_ids.get(str(annotation.get("event_id")))
        if event is None or not _belongs(event, target):
            continue
        score, confidence = float(annotation["score"]), float(annotation["confidence"])
        if not -100 <= score <= 100 or not 0 <= confidence <= 1:
            raise ValueError("event score/confidence out of bounds")
        if not annotation.get("evidence_refs"):
            raise ValueError("scored annotation requires source evidence references")
        for category in annotation.get("categories", []):
            if category not in CATEGORIES:
                raise ValueError("unknown market-context category")
            key = (str(annotation["event_id"]), category)
            old = latest_annotations.get(key)
            if old is None or known > _time(old["available_at"]) or (known == _time(old["available_at"]) and _canonical(annotation) > _canonical(old)):
                latest_annotations[key] = annotation
    scored = sorted(((selected_ids[event_id], annotation, category) for (event_id, category), annotation in latest_annotations.items()),
                    key=lambda item: (str(item[0].get("canonical_id")), str(item[0].get("event_id")), item[2]))
    categories = {}
    for category in CATEGORIES:
        rows = [(e, a) for e, a, label in scored if category == label]
        score = round(sum(float(a["score"]) for _, a in rows) / len(rows), 4) if rows else None
        confidence = round(sum(float(a["confidence"]) for _, a in rows) / len(rows), 4) if rows else None
        fresh = [_time(a["available_at"]) for _, a in rows]
        categories[category] = {"score": score, "confidence": confidence,
            "coverage": len(rows), "freshness_seconds": min((cutoff - t).total_seconds() for t in fresh) if fresh else None,
            "evidence_refs": sorted({ref for _, a in rows for ref in a.get("evidence_refs", [])})}
    membership_id, active_membership, membership_complete = _latest_dated_snapshot(membership, cutoff) if membership else (None, [], False)
    payload = {"asof": cutoff.isoformat(), "target": target, "status": "shadow_unvalidated",
        "method": "equal_weight_mean_of_unique_canonical_source_events", "categories": categories,
        "membership_snapshot_id": membership_id, "membership_complete": membership_complete,
        "membership": sorted(active_membership, key=lambda r: str(r.get("member")))}
    payload["snapshot_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload


def index_contributions(*, index_return: float, constituent_returns: dict[str, float], weights: Iterable[dict], asof: str) -> dict:
    """Apply known beginning-of-period weights without coverage renormalization."""
    cutoff = _time(asof)
    if cutoff is None:
        raise ValueError("asof required")
    snapshot_id, selected_weights, complete = _latest_dated_snapshot(weights, cutoff)
    contributions, covered, weight_coverage = {}, 0.0, 0.0
    for row in selected_weights:
        member, weight = str(row["member"]), float(row["weight"])
        if weight < 0 or weight > 1:
            raise ValueError("membership weight out of bounds")
        weight_coverage += weight
        if member in constituent_returns:
            contributions[member] = contributions.get(member, 0.0) + weight * float(constituent_returns[member])
            covered += weight
    if weight_coverage > 1 + 1e-8:
        raise ValueError("beginning weights exceed 100%")
    known_contribution = sum(contributions.values())
    status = ("missing_weights" if snapshot_id is None else "incomplete_weight_snapshot" if not complete
              else "weight_coverage_gap" if weight_coverage < 1 - 1e-8
              else "partial_price_coverage" if covered < 1 - 1e-8 else "full_coverage")
    return {"contributions": contributions, "coverage_weight": covered,
        "known_contribution": known_contribution, "residual": float(index_return) - known_contribution,
        "weight_snapshot_id": snapshot_id, "weight_snapshot_complete": complete,
        "weight_coverage": weight_coverage, "weight_gap": max(0.0, 1.0 - weight_coverage), "status": status}


def compare_sector_peers(*, asof: str, target: str, peer_set: dict, observations: Iterable[dict]) -> dict:
    """Compare against an explicit, documented, point-in-time peer set."""
    cutoff = _time(asof)
    if cutoff is None:
        raise ValueError("asof required")
    peer_ids = peer_set.get("peer_ids")
    expected_metrics = peer_set.get("metrics")
    if (not isinstance(peer_ids, list) or not peer_ids or any(not isinstance(x, str) or not x for x in peer_ids)
            or target in peer_ids or len(peer_ids) != len(set(peer_ids))):
        raise ValueError("peer set requires unique documented peers excluding target")
    if (not isinstance(expected_metrics, list) or not expected_metrics
            or any(not isinstance(metric, str) or not metric for metric in expected_metrics)
            or len(expected_metrics) != len(set(expected_metrics))):
        raise ValueError("peer set requires unique expected metrics")
    source_refs = peer_set.get("source_refs")
    if (not isinstance(peer_set.get("peer_set_id"), str) or not peer_set["peer_set_id"]
            or not peer_set.get("sector") or not peer_set.get("methodology")
            or not isinstance(source_refs, list) or not source_refs
            or not all(isinstance(ref, str) and ref for ref in source_refs)):
        raise ValueError("peer set requires sector, methodology and source_refs")
    documented = _time(peer_set.get("documented_at"))
    effective = _time(peer_set.get("effective_at"))
    if documented is None or effective is None or documented > cutoff or effective > cutoff:
        raise ValueError("peer set unavailable at comparison cutoff")
    latest: dict[tuple[str, str], tuple[datetime, datetime, dict]] = {}
    for row in observations:
        company, metric = row.get("company"), row.get("metric")
        if company != target and company not in peer_ids:
            continue
        known, period = _time(row.get("available_at")), _time(row.get("effective_at"))
        published = _time(row.get("published_at"))
        if known is None or period is None or known > cutoff or period > cutoff or (published is not None and published > cutoff):
            continue
        value = float(row["value"])
        if not math.isfinite(value) or not metric:
            raise ValueError("peer observations require finite values and a metric")
        key = (str(company), str(metric))
        previous = latest.get(key)
        candidate = (period, known, row)
        tie_break = (str(row.get("revision_id", "")), _canonical(row))
        previous_tie_break = (str(previous[2].get("revision_id", "")), _canonical(previous[2])) if previous else None
        if previous is None or candidate[:2] > previous[:2] or (candidate[:2] == previous[:2] and tie_break > previous_tie_break):
            latest[key] = candidate
    metrics = sorted(set(expected_metrics) | {metric for _, metric in latest})
    result = {}
    for metric in metrics:
        target_row = latest.get((target, metric))
        values = {peer: latest[(peer, metric)][2]["value"] for peer in peer_ids if (peer, metric) in latest}
        result[metric] = {"target": target_row[2]["value"] if target_row else None,
            "peer_median": statistics.median(values.values()) if values else None,
            "peer_count": len(values), "peer_expected": len(peer_ids),
            "peer_coverage": len(values) / len(peer_ids),
            "target_coverage": target_row is not None,
            "covered_peers": sorted(values), "missing_peers": sorted(set(peer_ids) - set(values))}
    payload = {"asof": cutoff.isoformat(), "target": target, "sector": peer_set["sector"],
        "peer_set_id": peer_set.get("peer_set_id"), "peer_methodology": peer_set["methodology"],
        "peer_source_refs": sorted(set(source_refs)), "metrics": result,
        "status": "shadow_unvalidated"}
    payload["comparison_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload


def build_investigation(*, investigation_id: str, kind: str, decision_at: str,
                        decision_snapshot: dict, decision_evidence: Iterable[dict] = (),
                        discoveries: Iterable[dict] = ()) -> dict:
    """Freeze decision-time evidence apart from later, non-causal discoveries."""
    cutoff = _time(decision_at)
    if cutoff is None or kind not in {"winning_trade", "losing_trade", "eligible_no_trade"} or not investigation_id:
        raise ValueError("valid investigation id, kind and decision_at required")
    if decision_snapshot.get("asof") != cutoff.isoformat() and _time(decision_snapshot.get("asof")) != cutoff:
        raise ValueError("decision snapshot cutoff mismatch")
    original = []
    for evidence in decision_evidence:
        available = _time(evidence.get("available_at"))
        published = _time(evidence.get("published_at"))
        if available is None or available > cutoff or (published is not None and published > cutoff):
            raise ValueError("decision evidence was unavailable at decision time")
        original.append(evidence)
    if kind == "eligible_no_trade" and not decision_snapshot.get("eligible_no_trade", False):
        raise ValueError("no-trade investigation requires explicit eligibility")
    later = []
    for item in discoveries:
        available = _time(item.get("available_at"))
        if available is None or available <= cutoff:
            raise ValueError("later discoveries must follow the decision timestamp")
        later.append({"label": "possible_explanation", "status": "unverified", "evidence": item})
    payload = {"investigation_id": investigation_id, "kind": kind,
        "decision_at": cutoff.isoformat(), "decision_snapshot": decision_snapshot,
        "original_decision_evidence": sorted(original, key=_canonical),
        "later_discoveries": sorted(later, key=_canonical),
        "causal_claim": None, "status": "shadow_unvalidated"}
    payload["record_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload


def build_candidate_review(*, candidate_version: str, records: Iterable[dict],
                           train_through: str, validation_through: str,
                           cost_bps: float) -> dict:
    """Fit category weights chronologically and compare with frozen equal weights."""
    train_cutoff, validation_cutoff = _time(train_through), _time(validation_through)
    if not candidate_version or train_cutoff is None or validation_cutoff is None or validation_cutoff <= train_cutoff:
        raise ValueError("candidate version and increasing chronological cutoffs required")
    if not math.isfinite(float(cost_bps)) or cost_bps < 0:
        raise ValueError("realistic nonnegative cost_bps required")
    eligible = []
    ids = set()
    for row in records:
        decision = _time(row.get("decision_at"))
        outcome_at = _time(row.get("outcome_at"))
        event_id = str(row.get("event_id", ""))
        if not event_id or event_id in ids:
            raise ValueError("candidate records require unique event_id values")
        ids.add(event_id)
        if decision is None or outcome_at is None or outcome_at <= decision:
            raise ValueError("candidate record outcome must follow decision")
        if not row.get("snapshot_hash"):
            raise ValueError("candidate record requires frozen snapshot_hash")
        snapshot_at = _time(row.get("snapshot_asof"))
        if snapshot_at is None or snapshot_at > decision:
            raise ValueError("candidate snapshot contains future information")
        if not math.isfinite(float(row["outcome_bps"])):
            raise ValueError("candidate outcome must be finite")
        categories = row.get("categories", {})
        if set(categories) - set(CATEGORIES):
            raise ValueError("unknown category in candidate record")
        if any(value is not None and not math.isfinite(float(value)) for value in categories.values()):
            raise ValueError("candidate category scores must be finite")
        eligible.append((decision, outcome_at, row))
    eligible.sort(key=lambda item: (item[0], str(item[2]["event_id"])))
    train = [r for d, o, r in eligible if d <= train_cutoff and o <= train_cutoff]
    validation = [r for d, o, r in eligible if train_cutoff < d <= validation_cutoff and o <= validation_cutoff]
    if not train:
        raise ValueError("chronological training sample is empty")
    # Deterministic, nonnegative correlation weights fitted only to train rows.
    raw = {}
    for category in CATEGORIES:
        pairs = [(float(row["categories"][category]), float(row["outcome_bps"]))
                 for row in train if row["categories"].get(category) is not None]
        if len(pairs) < 2:
            raw[category] = 0.0
            continue
        xs, ys = zip(*pairs)
        denominator = math.sqrt(sum((x - statistics.mean(xs)) ** 2 for x in xs) * sum((y - statistics.mean(ys)) ** 2 for y in ys))
        raw[category] = max(0.0, sum((x - statistics.mean(xs)) * (y - statistics.mean(ys)) for x, y in pairs) / denominator) if denominator else 0.0
    total = sum(raw.values())
    weights = {category: (raw[category] / total if total else 1 / len(CATEGORIES)) for category in CATEGORIES}

    def measure(sample: list[dict], selected_weights: dict[str, float]) -> dict:
        returns, trades = [], 0
        for row in sample:
            available = {key: float(value) for key, value in row["categories"].items() if key in CATEGORIES and value is not None}
            if not available:
                continue
            available_weight = sum(selected_weights[key] for key in available)
            if not available_weight:
                available_weight = len(available)
                score = sum(value for value in available.values()) / available_weight
            else:
                score = sum(selected_weights[key] * value for key, value in available.items()) / available_weight
            if score == 0:
                returns.append(0.0)
            else:
                trades += 1
                gross = float(row["outcome_bps"]) * (1 if score > 0 else -1)
                returns.append(gross - float(cost_bps))
        mean = statistics.mean(returns) if returns else None
        stderr = statistics.stdev(returns) / math.sqrt(len(returns)) if len(returns) > 1 else None
        return {"sample_count": len(returns), "trade_count": trades, "mean_net_bps": mean,
                "standard_error_bps": stderr, "cost_bps_per_observation": float(cost_bps)}

    baseline = {category: 1 / len(CATEGORIES) for category in CATEGORIES}
    payload = {"candidate_version": candidate_version, "weights_version": candidate_version,
        "train_through": train_cutoff.isoformat(),
        "validation_through": validation_cutoff.isoformat(), "weights": weights,
        "baseline": {"version": "frozen_equal_weight_v1", "weights": baseline,
            "validation": measure(validation, baseline)},
        "candidate_validation": measure(validation, weights),
        "train_sample_count": len(train), "validation_sample_count": len(validation),
        "unassigned_record_count": len(eligible) - len(train) - len(validation),
        "cost_evidence_status": "unverified" if float(cost_bps) == 0 else "operator_supplied_unverified",
        "uncertainty": "standard_error_of_net_bps; descriptive, not qualification",
        "status": "candidate_review_only", "auto_promote": False}
    payload["review_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload


def review_rl_outcomes(decisions: Iterable[dict], *, cost_bps: float) -> dict:
    """Report RL rewards only where the recommendation was actually executed unchanged."""
    if not math.isfinite(float(cost_bps)) or cost_bps < 0:
        raise ValueError("realistic nonnegative cost_bps required")
    rows, seen = [], set()
    for row in decisions:
        identity = str(row.get("decision_id", ""))
        if not identity or identity in seen:
            raise ValueError("RL review requires unique decision_id")
        seen.add(identity)
        decision_at, outcome_at = _time(row.get("decision_at")), _time(row.get("outcome_at"))
        if decision_at is None or outcome_at is None or outcome_at <= decision_at:
            raise ValueError("RL outcome must follow its decision")
        engine_evidence = row.get("execution_matched_rl") is True and row.get("engine_version") == 2
        unchanged = (engine_evidence and not row.get("overridden")
                     and row.get("rl_action") == row.get("executed_action"))
        gross = row.get("realized_return_bps") if unchanged else None
        if gross is not None and not math.isfinite(float(gross)):
            raise ValueError("RL outcome return must be finite")
        reward = float(gross) - float(cost_bps) if gross is not None else None
        rows.append({"decision_id": identity, "policy_version": row.get("policy_version"),
            "rl_action": row.get("rl_action"), "executed_action": row.get("executed_action"),
            "execution_matched_rl": engine_evidence, "engine_version": row.get("engine_version"),
            "overridden": bool(row.get("overridden")), "reward_net_bps": reward,
            "reward_status": "attributed" if reward is not None else "not_attributed"})
    payload = {"decisions": sorted(rows, key=lambda row: row["decision_id"]),
        "cost_bps_per_trade": float(cost_bps),
        "cost_evidence_status": "unverified" if float(cost_bps) == 0 else "operator_supplied_unverified",
        "decision_count": len(rows), "attributed_count": sum(row["reward_status"] == "attributed" for row in rows),
        "status": "candidate_review_only", "auto_promote": False}
    payload["review_hash"] = hashlib.sha256(_canonical(payload).encode()).hexdigest()
    return payload
