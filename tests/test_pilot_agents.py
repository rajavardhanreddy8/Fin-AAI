from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import MagicMock, patch

from stock_research.intraday_pilot import Bar, ExecutionAssumptions, IST, QPolicy, audit_forward_paper, initialize_pilot_db
from stock_research.pilot_agents import DecisionAdapter, JevTransport, NovaCoordinator, NovaTransport, PilotBudgetConfig, PriceEvidence, UsageLedger, build_paper_decider, provider_readiness

spec = importlib.util.spec_from_file_location("paper_runner", Path(__file__).parents[1] / "scripts/run_intraday_paper.py")
paper = importlib.util.module_from_spec(spec)
spec.loader.exec_module(paper)


class FakeTransport:
    def __init__(self, provider="jev", text='{"action":"BUY"}', fail=False):
        self.provider, self.text, self.fail = provider, text, fail
        self.model = "vendor/verified-version" if provider == "jev" else "amazon.nova-lite-v1:0"
        self.calls = 0

    def __call__(self, system, user):
        self.calls += 1
        self.packet = json.loads(user)
        if self.fail:
            raise TimeoutError("do not retain secret-bearing provider error")
        return {"text": self.text, "model": self.model, "version": "test-version", "usage": {"inputTokens": 100, "outputTokens": 10}, "finish_reason": "stop"}


class PilotAgentTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name)
        self.now = datetime.now(timezone.utc)
        self.ledger = UsageLedger(self.path / "usage.db", "117.44")
        for scope in ("infra", "bedrock", "storage", f"jev:{self.now:%Y-%m}"):
            self.ledger.reconcile(scope, "0", self.now.isoformat(), "test-invoice")

    def adapter(self, transport):
        price = PriceEvidence(transport.model, Decimal("0.000001"), Decimal("0.000002"), "test-price", self.now.isoformat(), 10000, Decimal("90"), "test-fx", self.now.isoformat())
        return DecisionAdapter(transport, self.ledger, price, "test-run")

    def test_project_env_loader_preserves_process_values_and_safely_reads_file(self):
        env_file = self.path / ".env"
        env_file.write_text("# local credentials\nOPENROUTER_API_KEY=file-secret\nexport AWS_PROFILE='paper-profile'\nINVALID LINE\n", encoding="utf-8")
        with patch.dict(os.environ, {"OPENROUTER_API_KEY": "process-value"}, clear=True):
            paper.load_project_env(env_file)
            self.assertEqual(os.environ["OPENROUTER_API_KEY"], "process-value")
            self.assertEqual(os.environ["AWS_PROFILE"], "paper-profile")
            self.assertNotIn("INVALID LINE", os.environ)

    def test_decision_preserves_evidence_rl_and_is_idempotent_after_restart(self):
        transport = FakeTransport()
        agent = self.adapter(transport)
        evidence = {"bar": {"close": 250}, "rules_action": "BUY"}
        self.assertEqual(agent.decide(evidence, "HOLD"), "BUY")
        self.assertEqual(self.adapter(transport).decide(evidence, "HOLD"), "BUY")
        self.assertEqual(transport.calls, 1)
        self.assertEqual(transport.packet, {"evidence": evidence, "rl_action": "HOLD"})
        self.assertTrue(agent.last_audit["override_rl"])
        self.assertEqual(agent.last_audit["resolved_model"], transport.model)
        self.assertEqual(len(agent.last_audit["input_hash"]), 64)

    def test_failures_and_invalid_outputs_abstain_keep_cost_and_do_not_retry(self):
        for index, (text, fail) in enumerate([('{"action":"buy"}', False), ('{"action":"BUY","shell":"run"}', False), ('[]', False), ('{"action":"BUY"}', True)]):
            transport = FakeTransport(text=text, fail=fail)
            agent = self.adapter(transport)
            evidence = {"case": index}
            self.assertEqual(agent.decide(evidence, None), "ABSTAIN")
            self.assertEqual(agent.decide(evidence, None), "ABSTAIN")
            self.assertEqual(transport.calls, 1)
            audit = self.ledger.audit(agent.last_audit["call_id"])
            self.assertGreater(Decimal(audit["charged_cost"]), 0)
            self.assertNotIn("secret-bearing", json.dumps(audit))

    def test_crashed_reservation_is_never_reissued(self):
        transport = FakeTransport()
        agent = self.adapter(transport)
        agent.decide({"bar": 1}, None)
        call_id = agent.last_audit["call_id"]
        with self.ledger.connect() as db:
            db.execute("UPDATE api_calls SET audit_json=? WHERE call_id=?", (json.dumps({"action": "ABSTAIN", "status": "reserved", "failure": "unfinished_call"}), call_id))
        self.assertEqual(self.adapter(transport).decide({"bar": 1}, None), "ABSTAIN")
        self.assertEqual(transport.calls, 1)

    def test_budget_stop_and_stale_fx_fail_before_network(self):
        self.ledger.reconcile(f"jev:{self.now:%Y-%m}", "240", self.now.isoformat(), "test-invoice")
        transport = FakeTransport()
        agent = self.adapter(transport)
        self.assertEqual(agent.decide({"bar": 1}, None), "ABSTAIN")
        self.assertEqual(transport.calls, 0)
        self.assertIn("80%", agent.last_audit["failure"])
        stale = self.adapter(transport)
        stale.prices = PriceEvidence(transport.model, Decimal("0.000001"), Decimal("0.000002"), "test-price", self.now.isoformat(), 10000, Decimal("90"), "test-fx", (self.now - timedelta(days=2)).isoformat())
        self.assertEqual(stale.decide({"bar": 2}, None), "ABSTAIN")
        self.assertIn("exchange-rate", stale.last_audit["failure"])

    def test_exit_uses_reserved_capacity_and_config_pins_jev_snapshot(self):
        self.ledger.reconcile(f"jev:{self.now:%Y-%m}", "240", self.now.isoformat(), "test-invoice")
        adapter = self.adapter(FakeTransport())
        self.assertEqual(adapter.decide({"position": {"quantity": 1}}, "SELL"), "BUY")
        self.assertEqual(adapter.last_audit["purpose"], "exit")
        strict_ledger = UsageLedger(self.path / "strict.db", "117.44")
        for scope in ("infra", "bedrock", "storage", f"jev:{self.now:%Y-%m}"):
            strict_ledger.reconcile(scope, "0", self.now.isoformat(), "test-invoice")
        strict = DecisionAdapter(JevTransport("test-key", "typesafe/jev-1.13"), strict_ledger, PriceEvidence("typesafe/jev-1.13", Decimal("0.000001"), Decimal("0.000002"), "test-price", self.now.isoformat(), 10000, Decimal("90"), "test-fx", self.now.isoformat()), "strict", expected_resolved_model="typesafe/jev-1.13-20260917")
        body = {"id": "fixture", "model": "typesafe/jev-1.13-20260918", "answers": {"action": {"type": "choice", "choice": "BUY", "confidence": 1, "probabilities": {"BUY": 1, "HOLD": 0, "SELL": 0, "ABSTAIN": 0}}}, "usage": {"input_tokens": 1, "output_tokens": 1, "cost": 0}}
        with patch("urllib.request.urlopen") as opened:
            opened.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
            self.assertEqual(strict.decide({"bar": 1}, None), "ABSTAIN")
        self.assertIn("configured snapshot", strict.last_audit["failure"])

    def test_budget_config_requires_full_evidence(self):
        config = {"credit_usd": "117.44", "jev_resolved_model": "typesafe/jev-1.13-20260917", "prices": {"nova": {"model": "amazon.nova-lite-v1:0", "input_usd_per_token": "0.000001", "output_usd_per_token": "0.000002", "source": "test", "verified_at": self.now.isoformat(), "context_tokens": 10000}, "jev": {"model": "typesafe/jev-1.13", "input_usd_per_token": "0.000001", "output_usd_per_token": "0", "source": "test", "verified_at": self.now.isoformat(), "context_tokens": 10000, "usd_inr": "90", "fx_source": "test", "fx_verified_at": self.now.isoformat()}}, "billing": [{"scope": scope, "amount": "0", "as_of": self.now.isoformat(), "source": "test"} for scope in ("infra", "bedrock", "storage", f"jev:{self.now:%Y-%m}")]}
        path = self.path / "budget.json"
        path.write_text(json.dumps(config), encoding="utf-8")
        loaded = PilotBudgetConfig.load(path)
        self.assertEqual(loaded.jev_resolved_model, config["jev_resolved_model"])
        status = provider_readiness(budget_config=path)
        self.assertTrue(status["budget_config"]["loaded"])
        self.assertEqual(status["budget_config"]["jev_expected_snapshot"], config["jev_resolved_model"])
        self.assertIn(f"jev:{self.now:%Y-%m}", status["budget_requirements"]["billing_scopes"])
        full_billing = config["billing"]
        config["billing"] = config["billing"][:-1]
        path.write_text(json.dumps(config), encoding="utf-8")
        self.assertFalse(provider_readiness(budget_config=path)["budget_config"]["loaded"])
        config["billing"] = full_billing
        path.write_text(json.dumps(config), encoding="utf-8")
        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaisesRegex(ValueError, "OPENROUTER"):
                build_paper_decider("jev", path, self.path / "from-config.db", "test")
        jev_only = dict(config)
        jev_only["prices"] = {"jev": config["prices"]["jev"]}
        jev_only["billing"] = [item for item in config["billing"] if item["scope"] != "bedrock"]
        path.write_text(json.dumps(jev_only), encoding="utf-8")
        self.assertEqual(PilotBudgetConfig.load(path, providers={"jev"}).prices["jev"].model, "typesafe/jev-1.13")
        self.assertTrue(provider_readiness(budget_config=path, strategy="jev")["budget_config"]["loaded"])
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-key"}, clear=True):
            _, strategy_id = build_paper_decider("jev", path, self.path / "jev-only.db", "test")
        self.assertEqual(strategy_id, f"jev:{config['jev_resolved_model']}")

    def test_aws_envelope_and_outstanding_call_stay_counted(self):
        self.ledger.reconcile("infra", "46.976", self.now.isoformat(), "test-invoice")
        nova = FakeTransport("nova")
        self.assertEqual(self.adapter(nova).decide({"bar": 1}, None), "BUY")
        self.ledger.reconcile("infra", "47", self.now.isoformat(), "test-invoice")
        self.assertEqual(self.adapter(nova).decide({"bar": 2}, None), "ABSTAIN")
        self.assertEqual(nova.calls, 1)
        with self.assertRaisesRegex(ValueError, "scope"):
            self.ledger.reconcile("infra", "1", self.now.isoformat(), "test", (self.adapter(nova).last_audit.get("call_id", "missing"),))

    def test_coordinator_only_dispatches_one_allowed_tool(self):
        nova, jev = FakeTransport("nova", '{"tool":"jev_decide"}'), FakeTransport()
        coordinator = NovaCoordinator(self.adapter(nova), self.adapter(jev))
        self.assertEqual(coordinator.decide({"bar": 1}, "SELL"), "BUY")
        self.assertEqual((nova.calls, jev.calls), (1, 1))
        forbidden = FakeTransport("nova", '{"tool":"place_order"}')
        self.assertEqual(NovaCoordinator(self.adapter(forbidden), self.adapter(jev)).decide({"bar": 2}, None), "ABSTAIN")
        self.assertEqual(jev.calls, 1)

    def test_credentials_rejected_and_status_does_not_emit_secret_values(self):
        with self.assertRaisesRegex(ValueError, "credential"):
            self.adapter(FakeTransport()).decide({"BREEZE_SESSION_TOKEN": "test-secret"}, None)
        with patch.dict("os.environ", {"OPENROUTER_API_KEY": "test-secret"}):
            status = provider_readiness()
        self.assertNotIn("test-secret", json.dumps(status))
        self.assertFalse(status["ready"])

    def test_nova_explicit_region_model_and_small_output_limit(self):
        class Client:
            def converse(self, **kwargs):
                self.kwargs = kwargs
                return {"output": {"message": {"content": [{"text": '{"action":"HOLD"}'}]}}, "usage": {"inputTokens": 5, "outputTokens": 5}, "stopReason": "end_turn"}
        client = Client()
        response = NovaTransport(client=client)("system", "user")
        self.assertEqual(client.kwargs["inferenceConfig"]["maxTokens"], 192)
        self.assertEqual(response["model"], "amazon.nova-lite-v1:0")
        with self.assertRaises(ValueError):
            JevTransport("test-key", "invented-jev")

    def test_jev_documented_typed_protocol_and_resolved_snapshot(self):
        body = {"id": "fixture-generation", "model": "typesafe/jev-1.13-20260917", "answers": {"action": {"type": "choice", "choice": "BUY", "confidence": 0.9, "probabilities": {"BUY": 0.9, "HOLD": 0.05, "SELL": 0.03, "ABSTAIN": 0.02}}}, "usage": {"input_tokens": 476, "output_tokens": 70, "cost": 0.000019992}}
        transport = JevTransport("test-key", "typesafe/jev-1.13")
        agent = self.adapter(transport)
        with patch("urllib.request.urlopen") as opened:
            opened.return_value.__enter__.return_value.read.return_value = json.dumps(body).encode()
            self.assertEqual(agent.decide({"rules_action": "BUY"}, "HOLD"), "BUY")
        request = opened.call_args.args[0]
        self.assertEqual(request.full_url, "https://openrouter.ai/api/alpha/decisions")
        payload = json.loads(request.data)
        self.assertEqual(payload["questions"]["action"]["type"], "choice")
        self.assertEqual(set(payload["questions"]["action"]["criteria"]), {"BUY", "HOLD", "SELL", "ABSTAIN"})
        self.assertEqual(payload["state"]["rl_action"], "HOLD")
        self.assertNotIn("messages", payload)
        self.assertEqual(agent.last_audit["resolved_model"], body["model"])
        self.assertEqual(agent.last_audit["cost_status"], "provider_reported")

    def test_forward_observations_restart_without_duplicate_fills_or_calls(self):
        opening = datetime(2026, 10, 7, 9, 15, tzinfo=IST)
        calendar = {"year": 2026, "holidays": [], "special_sessions": {}, "source": "https://www.nseindia.com/api/holiday-master?type=trading"}
        assumptions = ExecutionAssumptions(decision_latency_seconds=180)
        calls = []
        def decide(evidence, rl_action):
            calls.append(evidence["decision_at"])
            return evidence["rules_action"]
        runner = paper.PaperRunner(self.path / "forward.db", "test", calendar, assumptions, decide=decide, strategy_id="test-adapter", now=opening)
        bars = [Bar(opening + timedelta(minutes=5 * index), 250, 250.2, 249.8, 250, 10000) for index in range(38)]
        bars[-3] = Bar(bars[-3].at, 250, 251, 249.8, 250.8, 10000)
        for bar in bars:
            summary = runner.ingest(bar, now=bar.at + timedelta(minutes=5, seconds=1))
        self.assertGreater(summary["state"]["quantity"], 0)
        calls_before = len(calls)
        restarted = paper.PaperRunner(self.path / "forward.db", "test", calendar, assumptions, decide=decide, strategy_id="test-adapter", now=opening + timedelta(days=1))
        self.assertEqual(restarted.ingest(bars[-1], now=opening + timedelta(days=1)), summary)
        self.assertEqual(len(calls), calls_before)
        stopped = Bar(bars[-1].at + timedelta(minutes=5), 250, 250.2, 248, 249, 10000)
        exited = restarted.ingest(stopped, now=stopped.at + timedelta(minutes=5, seconds=1))
        self.assertEqual(exited["completed_trades"], 1)
        self.assertEqual(exited["state"]["quantity"], 0)
        self.assertEqual(restarted.ingest(stopped, now=opening + timedelta(days=1)), exited)
        self.assertEqual(summary["observed_bars"], 38)
        self.assertEqual(summary["provenance"], "forward-observed-paper")
        self.assertFalse(summary["qualified"])
        with runner.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forward_bars").fetchone()[0], 39)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forward_trades").fetchone()[0], 1)
            self.assertEqual(db.execute("SELECT clock_source FROM forward_runs WHERE run_id='test'").fetchone()[0], "injected")
            self.assertEqual(db.execute("SELECT DISTINCT clock_source FROM forward_bars").fetchone()[0], "injected")
        forward_audit = audit_forward_paper(self.path / "forward.db")
        self.assertEqual(forward_audit["completed_trades"], 0)
        self.assertTrue(any("injected" in issue for issue in forward_audit["issues"]))
        with self.assertRaisesRegex(ValueError, "changed"):
            restarted.ingest(Bar(bars[-1].at, 251, 251.2, 250.8, 251, 10000))
        with self.assertRaisesRegex(ValueError, "stale"):
            runner.ingest(Bar(stopped.at + timedelta(minutes=5), 250, 250.2, 249.8, 250, 10000), now=opening + timedelta(days=1))
        with self.assertRaisesRegex(ValueError, "configuration"):
            paper.PaperRunner(self.path / "forward.db", "test", calendar, ExecutionAssumptions(), now=opening)

    def test_context_snapshot_is_shadow_journaled_frozen_and_time_locked(self):
        from stock_research.market_context import build_snapshot

        opening = datetime(2026, 10, 7, 9, 15, tzinfo=IST)
        calendar = {"year": 2026, "holidays": [], "special_sessions": {}, "source": "https://www.nseindia.com/api/holiday-master?type=trading"}
        assumptions = ExecutionAssumptions(decision_latency_seconds=180)
        decision_at = opening + timedelta(minutes=175)
        snapshot = build_snapshot(asof=decision_at.isoformat(), target="NIFTYBEES", events=[])
        path = self.path / "context-forward.db"
        calls = []
        decide = lambda evidence, action: calls.append(action) or evidence["rules_action"]
        runner = paper.PaperRunner(path, "context", calendar, assumptions, decide=decide, context_snapshot=snapshot, now=opening)
        bars = [Bar(opening + timedelta(minutes=5 * i), 250, 250.2, 249.8, 250, 10000) for i in range(36)]
        for bar in bars:
            summary = runner.ingest(bar, now=bar.at + timedelta(minutes=5, seconds=1))
        with runner.connect() as db:
            rows = db.execute("SELECT context_hash,payload FROM forward_context_snapshots WHERE run_id='context'").fetchall()
            self.assertGreaterEqual(len(rows), 1)
            self.assertTrue(all((row[0], json.loads(row[1])["snapshot_hash"]) == (snapshot["snapshot_hash"], snapshot["snapshot_hash"]) for row in rows))
        restarted = paper.PaperRunner(path, "context", calendar, assumptions, decide=decide, context_snapshot=snapshot, now=opening + timedelta(days=1))
        calls_before_restart = len(calls)
        self.assertEqual(restarted.ingest(bars[-1], now=opening + timedelta(days=1)), summary)
        self.assertEqual(len(calls), calls_before_restart)
        changed = build_snapshot(asof=decision_at.isoformat(), target="NIFTYBEES", events=[{"event_id":"e1", "canonical_id":"x", "available_at":decision_at.isoformat(), "entities":["NIFTYBEES"]}], annotations=[{"event_id":"e1", "available_at":decision_at.isoformat(), "categories":["company_performance"], "score":20, "confidence":.8, "evidence_refs":["https://example.test/source"]}])
        with self.assertRaisesRegex(ValueError, "configuration"):
            paper.PaperRunner(path, "context", calendar, assumptions, decide=decide, context_snapshot=changed, now=opening + timedelta(days=1))
        late = build_snapshot(asof=(decision_at + timedelta(seconds=1)).isoformat(), target="NIFTYBEES", events=[])
        late_runner = paper.PaperRunner(self.path / "late-context.db", "late", calendar, assumptions, context_snapshot=late, now=opening)
        for bar in bars[:-2]:
            late_runner.ingest(bar, now=bar.at + timedelta(minutes=5, seconds=1))
        with self.assertRaisesRegex(ValueError, "not available"):
            late_runner.ingest(bars[-2], now=bars[-2].at + timedelta(minutes=5, seconds=1))
        with late_runner.connect() as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forward_bars").fetchone()[0], 34)
            self.assertEqual(db.execute("SELECT COUNT(*) FROM forward_context_snapshots").fetchone()[0], 0)

    def test_forward_audit_rebuilds_only_system_clock_complete_sessions(self):
        opening = datetime(2026, 10, 7, 9, 15, tzinfo=IST)
        calendar = {"year": 2026, "holidays": [], "special_sessions": {}, "source": "https://www.nseindia.com/api/holiday-master?type=trading"}
        class Clock:
            current = opening - timedelta(minutes=1)
            @classmethod
            def now(cls, tz=None):
                return cls.current.astimezone(tz) if tz else cls.current
        bars = [Bar(opening + timedelta(minutes=5 * index), 250, 250.2, 249.8, 250, 10000) for index in range(75)]
        bars[35] = Bar(bars[35].at, 250, 251, 249.8, 250.8, 10000)
        for index in range(36, 75):
            bars[index] = Bar(bars[index].at, 250.8, 251, 250.5, 250.8, 10000)
        with patch.object(paper, "datetime", Clock):
            runner = paper.PaperRunner(self.path / "complete-forward.db", "rules", calendar, ExecutionAssumptions(decision_latency_seconds=180))
            for bar in bars:
                Clock.current = bar.at + timedelta(minutes=5, seconds=1)
                summary = runner.ingest(bar)
        self.assertEqual(summary["completed_trades"], 1)
        audit = audit_forward_paper(self.path / "complete-forward.db")
        self.assertEqual(audit["issues"], [])
        self.assertEqual((audit["completed_trades"], audit["completed_sessions"], audit["trade_sessions"]), (1, 1, 1))
        with runner.connect() as db:
            db.execute("UPDATE forward_bars SET calendar_json='{}' WHERE run_id='rules' AND at=(SELECT MIN(at) FROM forward_bars WHERE run_id='rules')")
        tampered_calendar = audit_forward_paper(self.path / "complete-forward.db")
        self.assertEqual(tampered_calendar["completed_trades"], 0)
        self.assertTrue(any("calendar" in issue for issue in tampered_calendar["issues"]))
        with runner.connect() as db:
            db.execute("UPDATE forward_bars SET calendar_json=? WHERE run_id='rules'", (paper.canonical(calendar),))
            db.execute("UPDATE forward_trades SET payload='{}' WHERE run_id='rules'")
        tampered = audit_forward_paper(self.path / "complete-forward.db")
        self.assertEqual(tampered["completed_trades"], 0)
        self.assertTrue(any("trade hash" in issue for issue in tampered["issues"]))

    def test_paper_runner_loads_an_explicit_frozen_policy_and_fingerprints_it(self):
        policy_db = self.path / "pilot.db"
        initialize_pilot_db(policy_db)
        assumptions = ExecutionAssumptions(decision_latency_seconds=180)
        values = QPolicy({"1:0:0:0:0:0:0": {"BUY": 2.0}})
        metadata = {"provenance": "historical-training-only", "execution_assumptions": vars(assumptions)}
        with closing(sqlite3.connect(policy_db)) as db, db:
            db.execute("INSERT INTO pilot_policies(version,status,trained_at,values_json,metadata_json) VALUES(?,?,?,?,?)", ("candidate-1", "candidate", "2026-10-07T09:15:00+05:30", values.to_json(), json.dumps(metadata)))
        policy, strategy_id = paper.load_frozen_policy(policy_db, "candidate-1", assumptions)
        self.assertEqual(policy.version, "candidate-1")
        self.assertTrue(strategy_id.startswith("rl:candidate-1:"))
        opening = datetime(2026, 10, 7, 9, 15, tzinfo=IST)
        calendar = {"year": 2026, "holidays": [], "special_sessions": {}, "source": "https://www.nseindia.com/api/holiday-master?type=trading"}
        runner = paper.PaperRunner(self.path / "frozen-forward.db", "frozen", calendar, assumptions, policy=policy, strategy_id=strategy_id, now=opening)
        with runner.connect() as db:
            config = json.loads(db.execute("SELECT config FROM forward_runs WHERE run_id='frozen'").fetchone()[0])
        self.assertEqual(config["policy"], values.to_json())
        with self.assertRaisesRegex(ValueError, "assumptions"):
            paper.load_frozen_policy(policy_db, "candidate-1", ExecutionAssumptions(decision_latency_seconds=181))

    def test_provider_cli_requires_explicit_budget_configuration(self):
        assumptions = self.path / "assumptions.json"
        assumptions.write_text(json.dumps({"decision_latency_seconds": 180}), encoding="utf-8")
        with patch("sys.argv", ["run_intraday_paper.py", "--start", "--assumptions", str(assumptions), "--strategy", "jev"]):
            self.assertEqual(paper.main(), 2)

    def test_provider_probe_serializes_bedrock_datetime_metadata(self):
        client = MagicMock()
        client.get_foundation_model.return_value = {"modelDetails": {"modelId": "amazon.nova-lite-v1:0", "modelName": "Nova Lite", "modelLifecycle": {"status": "ACTIVE", "startOfLifeTime": datetime(2024, 12, 3, tzinfo=timezone.utc)}, "inferenceTypesSupported": ["ON_DEMAND"]}}
        session = MagicMock()
        session.client.return_value = client
        response = MagicMock()
        response.__enter__.return_value.read.return_value = b'{"data":[{"id":"typesafe/jev-1.13"}]}'
        fake_boto3 = types.ModuleType("boto3")
        fake_boto3.Session = MagicMock(return_value=session)
        fake_botocore = types.ModuleType("botocore")
        fake_botocore.__path__ = []
        fake_config = types.ModuleType("botocore.config")
        fake_config.Config = MagicMock()
        with patch("stock_research.pilot_agents.importlib.util.find_spec", return_value=object()), patch.dict(sys.modules, {"boto3": fake_boto3, "botocore": fake_botocore, "botocore.config": fake_config}), patch("stock_research.pilot_agents.urllib.request.urlopen", return_value=response):
            report = provider_readiness(probe=True)
        self.assertEqual(report["nova_catalogue"]["modelLifecycle"]["startOfLifeTime"], "2024-12-03T00:00:00+00:00")
        json.dumps(report)

    def test_provider_cli_reads_optional_aws_profile(self):
        assumptions = self.path / "assumptions.json"
        budget = self.path / "budget.json"
        assumptions.write_text(json.dumps({"decision_latency_seconds": 180}), encoding="utf-8")
        budget.write_text("{}", encoding="utf-8")
        class Runner:
            started_at = datetime(2026, 10, 7, tzinfo=timezone.utc)
            strategy_id = "jev-v1"
        with patch("sys.argv", ["run_intraday_paper.py", "--start", "--assumptions", str(assumptions), "--strategy", "jev", "--budget-config", str(budget)]), patch.object(paper, "build_paper_decider", return_value=(None, "jev-v1")) as decider, patch.object(paper, "load_calendar", return_value={}), patch.object(paper, "PaperRunner", return_value=Runner()), patch.dict("os.environ", {"AWS_PROFILE": "paper"}, clear=False):
            self.assertEqual(paper.main(), 0)
        self.assertEqual(decider.call_args.kwargs["profile"], "paper")


if __name__ == "__main__":
    unittest.main()
