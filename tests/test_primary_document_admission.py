import hashlib

import pytest

from stock_research.primary_document_admission import validate_primary_document
import stock_research.primary_document_admission as admission
from stock_research.context_store import ContextStore
from stock_research.parsing_storage_agent import parse_documents


TEXT = "Power Grid Corporation of India Limited announced a transmission project."


def envelope(raw):
    return {
        "identity": {
            "company": "Power Grid Corporation of India Limited",
            "symbol": "POWERGRID",
            "isin": "INE752E01010",
            "source_id": "powergrid-issuer",
            "source_url": "https://www.powergrid.in/en/press-release/example",
            "title": "Transmission project announcement",
        },
        "time": {
            "published_at": "2026-10-25",
            "observed_at": "2026-10-26T02:00:00Z",
            "rights_checked_at": "2026-10-26T02:10:00Z",
            "available_at": "2026-10-26T02:10:00Z",
        },
        "rights": {
            "automated_retrieval": True,
            "local_retention": True,
            "derived_claim_storage": True,
            "evidence_ref": "permission-review-2026-10-26",
            "terms_version": "2026-10-26",
        },
        "content": {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "scope": "full_document",
            "citations": ["announced a transmission project"],
        },
    }


def test_admits_one_exact_licensed_document_and_preserves_publication_precision():
    raw = TEXT.encode()
    admitted = validate_primary_document(envelope(raw), raw)
    assert admitted["raw_hash"] == hashlib.sha256(raw).hexdigest()
    assert admitted["published_at"] == "2026-10-25"
    assert admitted["available_at"] == "2026-10-26T02:10:00Z"
    assert admitted["text"] == TEXT


@pytest.mark.parametrize("mutate,match", [
    (lambda e: e["rights"].update(local_retention=False), "rights"),
    (lambda e: e["identity"].update(isin="WRONG"), "identity"),
    (lambda e: e["content"].update(citations=["fabricated statement"]), "verbatim"),
    (lambda e: e["time"].update(observed_at="2026-10-26T02:00:00"), "timezone"),
    (lambda e: e["time"].update(available_at="2026-10-26T02:05:00Z"), "available_at"),
])
def test_rejects_unqualified_document_before_parser_storage(mutate, match):
    raw = TEXT.encode()
    candidate = envelope(raw)
    mutate(candidate)
    with pytest.raises(ValueError, match=match):
        validate_primary_document(candidate, raw)


def test_rejects_byte_hash_mismatch():
    raw = TEXT.encode()
    with pytest.raises(ValueError, match="SHA-256"):
        validate_primary_document(envelope(raw), raw + b" changed")


def test_admission_rejects_invalid_envelope_before_storage(tmp_path, monkeypatch):
    raw = TEXT.encode()
    candidate = envelope(raw)
    candidate["rights"]["local_retention"] = False
    monkeypatch.setattr(admission, "parse_and_store", lambda *args, **kwargs: pytest.fail("storage called"))
    with pytest.raises(ValueError, match="rights"):
        admission.admit_primary_document_and_store(ContextStore(tmp_path / "invalid.db"), candidate, raw,
            start="2026-10-26T00:00:00Z", end="2026-10-27T00:00:00Z", interpret=lambda _: [])
    assert not (tmp_path / "invalid.db").exists()


def test_admission_stores_one_cited_primary_event(tmp_path):
    raw = TEXT.encode()
    candidate = envelope(raw)
    candidate["time"].update(observed_at="2026-10-26T02:00:00Z", rights_checked_at="2026-10-26T02:10:00Z")
    store = ContextStore(tmp_path / "valid.db")
    result = admission.admit_primary_document_and_store(store, candidate, raw,
        start="2026-10-26T00:00:00Z", end="2026-10-27T00:00:00Z",
        interpret=lambda _: [{"title": "Power Grid Corporation transmission project",
                              "citation": "announced a transmission project"}])
    assert result["added"]["events"] == 1
    assert result["batch"]["events"][0]["observed_at"] == "2026-10-26T02:00:00Z"
    assert result["batch"]["events"][0]["available_at"] == "2026-10-26T02:10:00Z"
    assert result["batch"]["events"][0]["published_at"] is None
    assert len(store.report("2026-10-26T02:09:59Z")["what_trust"]["events"]) == 0
    assert len(store.report("2026-10-26T02:10:00Z")["what_trust"]["events"]) == 1


def test_parser_optional_available_at_is_validated_without_changing_default():
    document = {"source_id": "one", "source_url": "https://news.test/one",
        "published_at": "2026-01-02T00:00:00Z", "observed_at": "2026-01-03T00:00:00Z",
        "text": "Acme Corporation announced a factory expansion with evidence.",
        "available_at": "2026-01-04T00:00:00Z"}
    result = parse_documents(company="Acme", symbol="ACME", aliases=["Acme Corporation"],
        start="2026-01-01T00:00:00Z", end="2026-01-05T00:00:00Z", documents=[document],
        interpret=lambda _: [{"title": "Acme factory expansion",
            "citation": "Acme Corporation announced a factory expansion"}])
    assert result["events"][0]["available_at"] == "2026-01-04T00:00:00Z"
    document["available_at"] = "2026-01-02T00:00:00Z"
    with pytest.raises(ValueError, match="available_at"):
        parse_documents(company="Acme", symbol="ACME", aliases=["Acme Corporation"],
            start="2026-01-01T00:00:00Z", end="2026-01-05T00:00:00Z", documents=[document],
            interpret=lambda _: [])
