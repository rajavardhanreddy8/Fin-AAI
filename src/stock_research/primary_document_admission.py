"""Admission gate for one rights-cleared primary company document."""
from __future__ import annotations

from datetime import date, datetime, timezone
import hashlib
import re
from urllib.parse import urlsplit

from stock_research.parsing_storage_agent import parse_and_store


POWERGRID = {
    "company": "Power Grid Corporation of India Limited",
    "symbol": "POWERGRID",
    "isin": "INE752E01010",
}
REQUIRED_RIGHTS = ("automated_retrieval", "local_retention", "derived_claim_storage")


def _aware(value: object, name: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise ValueError(f"{name} must be a timezone-aware ISO timestamp") from None
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ValueError(f"{name} must include a timezone")
    return parsed.astimezone(timezone.utc)


def _published(value: object) -> date | datetime:
    if isinstance(value, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        try:
            return date.fromisoformat(value)
        except ValueError:
            pass
    return _aware(value, "published_at")


def validate_primary_document(envelope: dict, raw_bytes: bytes) -> dict:
    """Validate exact retained evidence and return the parser's bounded document shape."""
    if not isinstance(envelope, dict) or not isinstance(raw_bytes, bytes) or not raw_bytes or len(raw_bytes) > 65536:
        raise ValueError("one non-empty primary document envelope and its exact bytes are required")

    identity = envelope.get("identity")
    if not isinstance(identity, dict) or any(identity.get(key) != value for key, value in POWERGRID.items()):
        raise ValueError("document identity must match POWERGRID company, symbol, and ISIN")
    source_id, source_url, title = (identity.get(key) for key in ("source_id", "source_url", "title"))
    parsed_url = urlsplit(source_url) if isinstance(source_url, str) else None
    if (not isinstance(source_id, str) or not source_id.strip() or not parsed_url
            or parsed_url.scheme != "https" or not parsed_url.netloc or not isinstance(title, str) or not title.strip()):
        raise ValueError("a source ID, canonical HTTPS URL, and document title are required")

    content = envelope.get("content")
    if not isinstance(content, dict):
        raise ValueError("content metadata is required")
    try:
        text = raw_bytes.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise ValueError("retained document bytes must be UTF-8 text") from None
    digest = hashlib.sha256(raw_bytes).hexdigest()
    if content.get("sha256") != digest:
        raise ValueError("retained bytes do not match the declared SHA-256")
    if content.get("scope") not in {"full_document", "excerpt"}:
        raise ValueError("content scope must identify a full document or excerpt")
    citations = content.get("citations")
    if not isinstance(citations, list) or not citations or any(
        not isinstance(citation, str) or len(citation) < 8 or citation not in text for citation in citations
    ):
        raise ValueError("each proposed citation must occur verbatim in the retained document")

    rights = envelope.get("rights")
    if (not isinstance(rights, dict) or any(rights.get(key) is not True for key in REQUIRED_RIGHTS)
            or not isinstance(rights.get("evidence_ref"), str) or not rights["evidence_ref"].strip()
            or not isinstance(rights.get("terms_version"), str) or not rights["terms_version"].strip()):
        raise ValueError("affirmative retrieval, local-retention, and derived-claim rights are required")

    timing = envelope.get("time")
    if not isinstance(timing, dict):
        raise ValueError("publication, observation, review, and availability times are required")
    observed = _aware(timing.get("observed_at"), "observed_at")
    reviewed = _aware(timing.get("rights_checked_at"), "rights_checked_at")
    available = _aware(timing.get("available_at"), "available_at")
    published = _published(timing.get("published_at"))
    if available < max(observed, reviewed) or (isinstance(published, datetime) and available < published):
        raise ValueError("available_at cannot precede publication, observation, or rights review")
    if isinstance(published, date) and not isinstance(published, datetime) and available.date() < published:
        raise ValueError("available_at cannot precede the date-only publication date")

    return {
        "source_id": source_id,
        "source_url": source_url,
        "title": title.strip(),
        "published_at": timing["published_at"],
        "observed_at": observed.isoformat().replace("+00:00", "Z"),
        "available_at": available.isoformat().replace("+00:00", "Z"),
        "raw_hash": digest,
        "text": text,
        "citations": citations,
    }


def admit_primary_document_and_store(store, envelope: dict, raw_bytes: bytes, *, start: str, end: str,
                                    interpret) -> dict:
    """Validate one retained source before passing only its cited proposals to ContextStore."""
    admitted = validate_primary_document(envelope, raw_bytes)
    if admitted["available_at"] != admitted["observed_at"]:
        raise ValueError("the current parser requires rights review and publication to be known by observation time")
    published = admitted["published_at"]
    if isinstance(published, str) and re.fullmatch(r"\d{4}-\d{2}-\d{2}", published):
        published = None  # Keep date-only precision in the admission record; the parser accepts timestamps only.

    def cited_interpretation(document):
        return [proposal for proposal in interpret(document)
                if isinstance(proposal, dict) and proposal.get("citation") in admitted["citations"]]

    result = parse_and_store(store, company=POWERGRID["company"], symbol=POWERGRID["symbol"],
        aliases=["Power Grid Corporation", "POWERGRID"], start=start, end=end,
        documents=[{key: admitted[key] for key in ("source_id", "source_url", "raw_hash", "text", "observed_at")}
                   | {"published_at": published}], interpret=cited_interpretation)
    result["admitted_source"] = admitted
    return result
