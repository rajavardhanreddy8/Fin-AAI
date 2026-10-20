import json
import subprocess
import sys
from pathlib import Path

import pytest

from stock_research.context_store import ContextStore
from stock_research.parsing_storage_agent import parse_and_store, parse_documents


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


def test_cli_runs_offline_from_fixture_proposals(tmp_path):
    payload = {"company": "Acme", "symbol": "ACME", "aliases": [], "start": "2026-01-01T00:00:00Z",
        "end": "2026-01-04T00:00:00Z", "documents": [doc("one", "a factory expansion") | {
            "proposals": [{"title": "Acme factory expansion", "citation": "Acme Corporation announced a factory expansion"}]}]}
    path = tmp_path / "input.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    script = Path(__file__).parents[1] / "scripts" / "run_parsing_storage.py"
    run = subprocess.run([sys.executable, str(script), str(path)], capture_output=True, text=True)
    assert run.returncode == 0
    assert len(json.loads(run.stdout)["events"]) == 1
