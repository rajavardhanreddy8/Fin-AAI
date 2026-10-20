import json
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from stock_research.context_store import ContextStore
from stock_research.parsing_storage_agent import parse_and_store, parse_documents

SCRIPT = Path(__file__).parents[1] / "scripts" / "run_parsing_storage.py"
SPEC = importlib.util.spec_from_file_location("run_parsing_storage", SCRIPT)
runner = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(runner)


def doc(source, title):
    return {"source_id": source, "source_url": f"https://news.test/{source}",
            "published_at": "2026-01-02T00:00:00Z", "observed_at": "2026-01-03T00:00:00Z",
            "text": f"Acme Corporation announced {title} on the date."}


def test_cited_proposals_group_and_store_with_source_lineage(tmp_path):
    documents = [doc("one", "a factory expansion"), doc("two", "a factory expansion")]
    proposals = lambda _: [{"title": "Acme factory expansion", "citation": "Acme Corporation announced a factory expansion"}]
    result = parse_and_store(ContextStore(tmp_path / "context.db"), company="Acme", symbol="ACME",
        aliases=["Acme Corporation"], start="2026-01-01T00:00:00Z", end="2026-01-04T00:00:00Z",
        documents=documents, interpret=proposals)
    assert len(result["batch"]["events"]) == 2
    assert len({e["canonical_id"] for e in result["batch"]["events"]}) == 1
    assert len(result["batch"]["nodes"]) == 1
    assert result["added"]["nodes"] == 3  # company plus two automatic event nodes
    assert result["added"]["claims"] == 2
    report = ContextStore(tmp_path / "context.db").report("2026-01-04T00:00:00Z")
    assert len(report["what_trust"]["events"]) == 1
    assert len(report["what_trust"]["claims"]) == 1


def test_ignores_uncited_or_out_of_range_and_rejects_naive_dates():
    document = doc("one", "a factory expansion")
    result = parse_documents(company="Acme", symbol="ACME", aliases=[], start="2026-01-01T00:00:00Z",
        end="2026-01-04T00:00:00Z", documents=[document],
        interpret=lambda _: [{"title": "Acme expansion", "citation": "invented quote"}])
    assert result["events"] == []
    with pytest.raises(ValueError, match="timezone"):
        parse_documents(company="Acme", symbol="ACME", aliases=[], start="2026-01-01", end="2026-01-04T00:00:00Z",
                        documents=[], interpret=lambda _: [])


def test_missing_publication_time_stays_unknown_but_observation_controls_cutoff(tmp_path):
    document = doc("undated", "a factory expansion")
    document["published_at"] = None
    seen = []
    proposals = lambda item: (seen.append(item) or [{"title": "Acme factory expansion",
        "citation": "Acme Corporation announced a factory expansion"}])
    store = ContextStore(tmp_path / "context.db")
    result = parse_and_store(store, company="Acme", symbol="ACME", aliases=["Acme Corporation"],
        start="2026-01-01T00:00:00Z", end="2026-01-04T00:00:00Z",
        documents=[document], interpret=proposals)
    event = result["batch"]["events"][0]
    assert seen[0]["published_at"] is None
    assert event["published_at"] is None
    assert len(store.report("2026-01-02T23:59:59Z")["what_trust"]["events"]) == 0
    assert len(store.report("2026-01-03T00:00:00Z")["what_trust"]["events"]) == 1


def test_missing_publication_time_uses_observation_for_window_and_identity_fallback():
    document = doc("undated", "a factory expansion")
    document["published_at"] = None
    result = parse_documents(company="Acme", symbol="ACME", aliases=["Acme Corporation"],
        start="2026-01-03T00:00:00Z", end="2026-01-03T00:00:00Z", documents=[document],
        interpret=lambda item: [{"title": "Acme factory expansion",
            "citation": "Acme Corporation announced a factory expansion"}])
    assert len(result["events"]) == 1
    assert result["events"][0]["published_at"] is None
    dated = doc("dated", "a factory expansion")
    dated["published_at"] = "2026-01-03T00:00:00Z"
    comparable = parse_documents(company="Acme", symbol="ACME", aliases=["Acme Corporation"],
        start="2026-01-03T00:00:00Z", end="2026-01-03T00:00:00Z", documents=[dated],
        interpret=lambda item: [{"title": "Acme factory expansion",
            "citation": "Acme Corporation announced a factory expansion"}])
    assert result["events"][0]["canonical_id"] == comparable["events"][0]["canonical_id"]
    earlier = parse_documents(company="Acme", symbol="ACME", aliases=[], start="2026-01-01T00:00:00Z",
        end="2026-01-02T23:59:59Z", documents=[document], interpret=lambda _: [])
    assert earlier["events"] == []


def test_cli_runs_offline_from_fixture_proposals(tmp_path):
    payload = {"company": "Acme", "symbol": "ACME", "aliases": [], "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-04T00:00:00Z", "documents": [doc("one", "a factory expansion") | {
            "proposals": [{"title": "Acme factory expansion", "citation": "Acme Corporation announced a factory expansion"}]}]}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    run = subprocess.run([sys.executable, str(SCRIPT), str(path)], capture_output=True, text=True)
    assert run.returncode == 0
    assert len(json.loads(run.stdout)["events"]) == 1


def test_runner_defaults_offline_and_requires_complete_nova_options(tmp_path, monkeypatch, capsys):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"company": "Acme", "symbol": "ACME", "aliases": [],
        "start": "2026-01-01T00:00:00Z", "end": "2026-01-04T00:00:00Z",
        "documents": [{"source_id": "one", "proposals": [{"title": "fixture"}]}]}), encoding="utf-8")
    called = {}
    monkeypatch.setattr(runner, "parse_documents", lambda **kw: (called.update(kw) or {"events": []}))
    monkeypatch.setattr(runner, "build_nova_document_interpreter", lambda *a, **kw: pytest.fail("Nova builder called"))
    assert runner.main([str(path)]) == 0
    assert called["interpret"](called["documents"][0]) == [{"title": "fixture"}]
    with pytest.raises(SystemExit):
        runner.main([str(path), "--nova-budget-config", "budget.json"])


def test_runner_nova_mode_uses_builder_and_never_fixture_interpreter(tmp_path, monkeypatch, capsys):
    path = tmp_path / "input.json"
    path.write_text(json.dumps({"company": "Acme", "symbol": "ACME", "aliases": [],
        "start": "2026-01-01T00:00:00Z", "end": "2026-01-04T00:00:00Z",
        "documents": [{"source_id": "one", "proposals": [{"title": "fixture"}]}]}), encoding="utf-8")
    sentinel, captured = lambda _: [{"title": "nova"}], {}
    monkeypatch.setattr(runner, "build_nova_document_interpreter", lambda *a, **kw: (captured.update(args=a, kwargs=kw) or sentinel))
    monkeypatch.setattr(runner, "parse_documents", lambda **kw: (captured.update(parse=kw) or {"events": []}))
    assert runner.main([str(path), "--nova-budget-config", "budget.json", "--usage-db", "usage.db",
                        "--namespace", "test", "--profile", "profile"]) == 0
    assert captured["args"] == ("budget.json", "usage.db", "test")
    assert captured["kwargs"] == {"profile": "profile"}
    assert captured["parse"]["interpret"] is sentinel
    assert captured["parse"]["interpret"](captured["parse"]["documents"][0]) == [{"title": "nova"}]
