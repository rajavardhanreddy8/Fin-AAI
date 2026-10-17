import importlib.util
import json
from datetime import date, datetime, timezone

import pytest

from stock_research.collectors.upstox import digest
from stock_research.collectors.upstox import UpstoxError


def load_command():
    path = __import__("pathlib").Path(__file__).resolve().parents[1] / "scripts" / "run_market_ingest.py"
    spec = importlib.util.spec_from_file_location("market_ingest_command", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_checkpoint_resumes_completed_units_and_reports_explicit_gap(tmp_path, monkeypatch):
    module = load_command()
    calls = []
    failed_once = [False]
    class Client:
        def __init__(self): pass
        def news(self, keys):
            calls.extend(keys)
            if keys == ["NSE_EQ|B"] and not failed_once[0]:
                failed_once[0] = True
                raise UpstoxError("temporary failure")
            raw = {"source_id": "upstox", "dataset": "news", "request": {"instrument_key": keys[0]},
                   "observed_at": "2026-10-15T10:00:00Z", "response": {"data": {keys[0]: []}}}
            raw["raw_hash"] = digest(raw)
            return [raw]
    monkeypatch.setattr(module, "UpstoxClient", Client)
    args = ["--instrument-key", "NSE_EQ|A", "--instrument-key", "NSE_EQ|B", "--output", str(tmp_path)]
    assert module.main(args) == 2
    first = json.loads((tmp_path / "market-ingest.json").read_text())
    assert first["status"] == "partial"
    assert first["coverage"]["gaps"][0]["unit"] == "news:NSE_EQ|B"
    assert len(first["snapshots"]) == 1
    assert json.loads((tmp_path / "checkpoint.json").read_text())["snapshots"] == first["snapshots"]
    assert module.main(args) == 0
    assert calls == ["NSE_EQ|A", "NSE_EQ|B", "NSE_EQ|B"]
    report = json.loads((tmp_path / "market-ingest.json").read_text())
    assert report["status"] == "complete"
    assert report["coverage"]["gaps"] == []
    assert len(report["snapshots"]) == 2
    assert json.loads((tmp_path / "checkpoint.json").read_text())["completed"] == ["news:NSE_EQ|A", "news:NSE_EQ|B"]


def test_coverage_report_detects_missing_weekdays_duplicates_revision_and_raw_hash():
    module = load_command()
    raw = {"source_id": "fixture", "dataset": "candles", "observed_at": "2026-10-15T10:00:00Z", "request": {}, "response": {}}
    raw["raw_hash"] = digest(raw)
    report = module._coverage([raw, raw], [], date(2026, 10, 14), date(2026, 10, 15))
    assert report["missing_sessions"] == ["2026-10-14", "2026-10-15"]
    assert all(row["valid"] for row in report["raw_integrity"])


def test_interrupted_run_keeps_already_completed_snapshot(tmp_path, monkeypatch):
    module = load_command()
    raw = {"source_id": "upstox", "dataset": "news", "request": {}, "observed_at": "2026-10-15T10:00:00Z", "response": {"data": {}}}
    raw["raw_hash"] = digest(raw)
    calls, interrupted = [], [False]

    class Client:
        def __init__(self): pass
        def news(self, keys):
            calls.extend(keys)
            if keys == ["NSE_EQ|B"] and not interrupted[0]:
                interrupted[0] = True
                raise KeyboardInterrupt()
            return [raw]

    monkeypatch.setattr(module, "UpstoxClient", Client)
    args = ["--instrument-key", "NSE_EQ|A", "--instrument-key", "NSE_EQ|B", "--output", str(tmp_path)]
    with pytest.raises(KeyboardInterrupt):
        module.main(args)
    assert json.loads((tmp_path / "checkpoint.json").read_text())["snapshots"] == [raw]
    assert module.main(args) == 0
    assert calls == ["NSE_EQ|A", "NSE_EQ|B", "NSE_EQ|B"]


def test_feed_registry_can_run_without_upstox_instrument_keys(tmp_path, monkeypatch):
    module = load_command()
    source = {"source_id": "official", "url": "https://feeds.example/rss", "permitted": True, "polling_interval": 3600}
    registry = tmp_path / "feeds.json"
    registry.write_text(json.dumps([source]))
    snapshot = {"source_id": "official", "dataset": "rss_atom", "request": {"url": source["url"]}, "observed_at": "2026-10-15T10:00:00Z", "response": {"xml": "<rss/>"}}
    snapshot["raw_hash"] = digest(snapshot)
    monkeypatch.setattr(module, "UpstoxClient", lambda: (_ for _ in ()).throw(AssertionError("no Upstox client needed")))
    monkeypatch.setattr(module, "fetch_feed", lambda value: snapshot)
    assert module.main(["--feed-registry", str(registry), "--output", str(tmp_path / "out"), "--max-sources", "1"]) == 0
    output = json.loads((tmp_path / "out" / "market-ingest.json").read_text())
    assert output["counts"]["snapshots"] == 1
    assert len(list((tmp_path / "out" / "raw").rglob("*.json"))) == 1
    assert (tmp_path / "out" / "events.json").exists()


def test_refresh_refetches_completed_feed_without_duplicate_raw_snapshot(tmp_path, monkeypatch):
    from stock_research.context_store import ContextStore

    module = load_command()
    source = {"source_id": "official", "url": "https://feeds.example/rss", "permitted": True, "polling_interval": 3600}
    registry = tmp_path / "feeds.json"
    registry.write_text(json.dumps([source]))
    xml = '<rss><channel><item><title>Policy update</title><link>https://publisher.example/a</link><guid>a</guid><description>Summary</description></item></channel></rss>'
    calls = []
    def snapshot_at(time):
        raw = {"source_id": "official", "dataset": "rss_atom", "request": {"url": source["url"]}, "observed_at": time, "response": {"xml": xml}}
        raw["raw_hash"] = digest(raw)
        return raw
    monkeypatch.setattr(module, "UpstoxClient", lambda: (_ for _ in ()).throw(AssertionError("no Upstox client needed")))
    monkeypatch.setattr(module, "fetch_feed", lambda value: calls.append(value["source_id"]) or snapshot_at("2026-10-15T10:00:00Z" if len(calls) == 1 else "2026-10-16T10:00:00Z"))
    base = ["--feed-registry", str(registry), "--output", str(tmp_path / "out"), "--max-sources", "1"]
    assert module.main(base) == 0
    assert module.main(base) == 0
    assert len(calls) == 1
    assert module.main(base + ["--refresh"]) == 0
    output = json.loads((tmp_path / "out" / "market-ingest.json").read_text())
    assert len(calls) == 2
    assert output["counts"]["snapshots"] == 2
    assert len(list((tmp_path / "out" / "raw").rglob("*.json"))) == 2
    assert len(output["events"]) == 1
    assert output["events"][0]["observed_at"] == "2026-10-15T10:00:00Z"
    batch = {"events": output["events"], "nodes": [], "claims": [], "relationships": [], "analogs": []}
    store = ContextStore(tmp_path / "context.db")
    assert store.import_batch(batch)["events"] == 1
    assert store.import_batch(batch)["events"] == 0


def test_integrity_failure_is_saved_as_failed_status_without_archiving_bad_raw(tmp_path):
    module = load_command()
    raw = {"source_id": "fixture", "dataset": "rss_atom", "request": {}, "observed_at": "2026-10-15T10:00:00Z", "response": {"xml": "<rss/>"}, "raw_hash": "0" * 64}
    fixture = tmp_path / "fixture.json"
    fixture.write_text(json.dumps([raw]))
    assert module.main(["--fixture", str(fixture), "--output", str(tmp_path / "out")]) == 2
    output = json.loads((tmp_path / "out" / "market-ingest.json").read_text())
    assert output["status"] == "failed"
    assert output["coverage"]["integrity_failures"] == 1
    assert not list((tmp_path / "out" / "raw").rglob("*.json"))
