import json
from datetime import datetime, timezone
from decimal import Decimal

from stock_research.context_store import NODE_TYPES
from stock_research.document_parser_agents import NovaRelationshipInterpreter, RELATIONSHIP_PROMPT
from stock_research.market_context import CATEGORIES
from stock_research.pilot_agents import NOVA_MODEL, PriceEvidence, UsageLedger

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)
TEXT = "ACME won a large contract, improving sector outlook."
NODES = [{"node_type": "company", "node_id": "ACME"}, {"node_type": "sector", "node_id": "technology"}]


class Fake:
    provider, model, max_tokens = "nova", NOVA_MODEL, 512
    def __init__(self, payload): self.payload, self.calls = payload, 0
    def __call__(self, prompt, user):
        self.calls += 1
        assert "estimated relationship hypotheses" in prompt
        return {"text": json.dumps(self.payload), "model": NOVA_MODEL, "version": NOVA_MODEL, "request_id": "req-test",
                "finish_reason": "end_turn", "usage": {"inputTokens": 100, "outputTokens": 30}}


def proposal(**changes):
    item = {"title": "Contract may support sector", "citation": "won a large contract", "subject_type": "company", "subject_id": "ACME",
        "object_type": "sector", "object_id": "technology", "category": CATEGORIES[0], "sentiment": 0.6, "impact_weight": 0.4,
        "confidence": 0.7, "horizon_minutes": 30, "mechanism": "Revenue expectations may improve."}
    item.update(changes)
    return item


def setup(tmp_path, result, credit="100"):
    ledger = UsageLedger(tmp_path / "usage.db", credit)
    for scope in ("infra", "storage", "bedrock"): ledger.reconcile(scope, "0", NOW.isoformat(), "offline")
    prices = PriceEvidence(NOVA_MODEL, Decimal("0.000001"), Decimal("0.000002"), "offline", NOW.isoformat(), 10000)
    fake = Fake(result)
    interpreter = NovaRelationshipInterpreter(ledger, prices, "relationship-test", transport=fake, clock=lambda: NOW)
    return interpreter, fake


def document():
    return {"source_id": "feed", "source_url": "https://example.test/a", "published_at": NOW.isoformat(),
            "observed_at": NOW.isoformat(), "text": TEXT, "company_names": ["ACME"], "allowed_nodes": NODES}


def test_valid_edge_cached_with_provenance_and_distinct_prompt(tmp_path):
    interpreter, fake = setup(tmp_path, [proposal()])
    result = interpreter.interpret_with_audit(document())
    cached = interpreter.interpret_with_audit(document())
    assert result["proposals"] == cached["proposals"] == [proposal()]
    assert result["audit"] == cached["audit"] and result["status"] == "completed"
    assert fake.calls == 1
    from stock_research.pilot_agents import canonical, digest
    input_hash = digest(canonical(document()))
    call_id = digest(canonical(["relationship-test", input_hash, digest(RELATIONSHIP_PROMPT), NOVA_MODEL]))
    audit = interpreter.ledger.audit(call_id)
    assert audit["resolved_model"] == audit["model_version"] == NOVA_MODEL
    assert audit["request_id"] == "req-test" and audit["usage"]["outputTokens"] == 30
    assert datetime.fromisoformat(audit["completion_at"]) == NOW
    with interpreter.ledger.connect() as db:
        legacy = dict(audit)
        legacy.pop("input_hash"); legacy.pop("prompt_hash")
        db.execute("UPDATE api_calls SET audit_json=? WHERE call_id=?", (json.dumps(legacy), call_id))
    enriched = interpreter.interpret_with_audit(document())["audit"]
    assert enriched["input_hash"] == input_hash and enriched["prompt_hash"] == digest(RELATIONSHIP_PROMPT)
    assert "input_hash" not in interpreter.ledger.audit(call_id)


def test_interpret_with_audit_invalid_input_has_no_audit(tmp_path):
    interpreter, _ = setup(tmp_path, [])
    result = interpreter.interpret_with_audit({**document(), "allowed_nodes": []})
    assert result == {"proposals": [], "status": "blocked", "audit": None}


def test_rejects_malformed_endpoints_numbers_fields_and_future_leak(tmp_path):
    bad = [proposal(object_id="invented"), proposal(subject_id="technology", subject_type="sector"),
           proposal(sentiment=True), proposal(confidence=float("nan")), proposal(horizon_minutes=999),
           proposal(extra="field"), proposal(citation="not in source"), proposal(subject_id="ACME", object_id="ACME", object_type="company")]
    for i, item in enumerate(bad):
        (tmp_path / str(i)).mkdir()
        interpreter, fake = setup(tmp_path / str(i), [item])
        assert interpreter(document()) == [] and fake.calls == 1
    (tmp_path / "future").mkdir()
    interpreter, fake = setup(tmp_path / "future", [proposal()])
    assert interpreter({**document(), "allowed_nodes": [{"node_type": "company", "node_id": "ACME", "known_at": "future"}]}) == []
    assert fake.calls == 0


def test_duplicate_and_malformed_allowed_nodes_fail_before_transport(tmp_path):
    interpreter, fake = setup(tmp_path, [])
    for nodes in ([NODES[0], NODES[0]], [{"node_type": "bad", "node_id": "x"}], [{"node_type": "company", "node_id": " "}]):
        assert interpreter({**document(), "allowed_nodes": nodes}) == []
    assert set(NODE_TYPES) and fake.calls == 0


def test_budget_block_never_calls_model(tmp_path):
    interpreter, fake = setup(tmp_path, [], credit="0.00000001")
    assert interpreter(document()) == []
    assert fake.calls == 0


def test_observation_and_completion_times_must_be_aware_and_ordered(tmp_path):
    interpreter, fake = setup(tmp_path, [proposal()])
    assert interpreter({**document(), "observed_at": "2026-10-20T12:00:00"}) == []
    assert interpreter({**document(), "published_at": "2026-10-20T12:01:00+00:00"}) == []
    assert fake.calls == 0
    backwards = iter((NOW, NOW, NOW.replace(hour=11)))
    clocked = NovaRelationshipInterpreter(interpreter.ledger, interpreter.prices, "backwards", transport=fake, clock=lambda: next(backwards))
    assert clocked(document()) == [] and fake.calls == 1


def test_relationship_prompt_enumerates_categories_and_separates_signed_concepts():
    assert all(category in RELATIONSHIP_PROMPT for category in CATEGORIES)
    assert "narrative polarity" in RELATIONSHIP_PROMPT and "transmission" in RELATIONSHIP_PROMPT
