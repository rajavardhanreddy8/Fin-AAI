import json
from datetime import datetime, timezone
from decimal import Decimal

from stock_research.document_parser_agents import NovaDocumentInterpreter, build_nova_document_interpreter
from stock_research.pilot_agents import NOVA_MODEL, PilotBudgetConfig, PriceEvidence, UsageLedger

NOW = datetime(2026, 10, 20, 12, tzinfo=timezone.utc)


class FakeNova:
    provider = "nova"
    model = NOVA_MODEL
    max_tokens = 512

    def __init__(self, text, *, model=NOVA_MODEL, finish="end_turn"):
        self.text, self.resolved, self.finish, self.calls = text, model, finish, 0

    def __call__(self, system, user):
        self.calls += 1
        return {"text": self.text, "model": self.resolved, "version": self.resolved, "finish_reason": self.finish,
                "usage": {"inputTokens": 100, "outputTokens": 20}}


def setup(tmp_path, fake):
    ledger = UsageLedger(tmp_path / "usage.db", "100")
    for scope in ("infra", "storage", "bedrock"):
        ledger.reconcile(scope, "0", NOW.isoformat(), "offline test")
    prices = PriceEvidence(NOVA_MODEL, Decimal("0.000001"), Decimal("0.000002"), "offline", NOW.isoformat(), 10000)
    return NovaDocumentInterpreter(ledger, prices, "test", transport=fake, clock=lambda: NOW)


def document():
    return {"source_id": "official", "source_url": "https://example.test/report", "published_at": NOW.isoformat(),
            "text": "ACME announced revenue growth of 12 percent.", "company_names": ["ACME"]}


def test_valid_response_is_cached(tmp_path):
    fake = FakeNova(json.dumps([{"title": "ACME revenue growth", "citation": "revenue growth of 12 percent"}]))
    interpreter = setup(tmp_path, fake)
    assert interpreter(document()) == interpreter(document())
    assert fake.calls == 1


def test_malformed_uncited_truncated_and_model_mismatch_fail_closed(tmp_path):
    valid = [{"title": "ACME update", "citation": "revenue growth of 12 percent"}]
    cases = [("not json", NOVA_MODEL, "end_turn"), (json.dumps([{**valid[0], "citation": "invented citation"}]), NOVA_MODEL, "end_turn"),
             (json.dumps(valid), NOVA_MODEL, "max_tokens"), (json.dumps(valid), "other-model", "end_turn")]
    for i, (text, model, finish) in enumerate(cases):
        (tmp_path / str(i)).mkdir()
        assert setup(tmp_path / str(i), FakeNova(text, model=model, finish=finish))(document()) == []


def test_nova_only_config_does_not_require_jev_snapshot_or_billing(tmp_path):
    config = {"credit_usd": "10", "prices": {"nova": {"model": NOVA_MODEL, "input_usd_per_token": "0.000001",
              "output_usd_per_token": "0.000002", "source": "offline", "verified_at": NOW.isoformat(), "context_tokens": 1000}},
              "billing": [{"scope": scope, "amount": "0", "as_of": NOW.isoformat(), "source": "offline"}
                          for scope in ("infra", "storage", "bedrock")]}
    path = tmp_path / "budget.json"
    path.write_text(json.dumps(config))
    loaded = PilotBudgetConfig.load(path, providers={"nova"})
    loaded.validate_runtime_evidence(NOW, providers={"nova"})
    assert loaded.jev_resolved_model == ""


def test_invalid_and_oversized_input_never_calls_transport(tmp_path):
    fake = FakeNova("[]")
    interpreter = setup(tmp_path, fake)
    for invalid in ({**document(), "source_id": " "}, {**document(), "source_url": "file:///tmp/a"},
                    {**document(), "source_url": "https://user:secret@example.test/report"},
                    {**document(), "published_at": "2026-10-20T12:00:00"},
                    {**document(), "company_names": []}, {**document(), "text": "x" * 65537}):
        assert interpreter(invalid) == []
    assert fake.calls == 0


def test_production_builder_loads_nova_only_budget(tmp_path):
    now = datetime.now(timezone.utc)
    config = {"credit_usd": "10", "prices": {"nova": {"model": NOVA_MODEL, "input_usd_per_token": "0.000001",
              "output_usd_per_token": "0.000002", "source": "offline", "verified_at": now.isoformat(), "context_tokens": 1000}},
              "billing": [{"scope": scope, "amount": "0", "as_of": now.isoformat(), "source": "offline"}
                          for scope in ("infra", "storage", "bedrock")]}
    path = tmp_path / "budget-builder.json"
    path.write_text(json.dumps(config))
    interpreter = build_nova_document_interpreter(str(path), str(tmp_path / "builder.db"), "test", client=object())
    assert interpreter.transport.model == NOVA_MODEL
    assert interpreter.transport.max_tokens == 512
