# POWERGRID primary-document admission

Use this path only for one issuer or exchange document whose retention and
derived-claim rights have been positively recorded. It is an evidence path,
not a market-impact or trading path.

## Required envelope

Keep the exact retained UTF-8 text in a local file. Create a separate JSON
envelope with this shape; calculate `content.sha256` from those exact bytes.

```json
{
  "identity": {
    "company": "Power Grid Corporation of India Limited",
    "symbol": "POWERGRID",
    "isin": "INE752E01010",
    "source_id": "powergrid-issuer",
    "source_url": "https://example.com/canonical-document-url",
    "title": "Exact displayed document title"
  },
  "time": {
    "published_at": "2026-10-26",
    "observed_at": "2026-10-26T02:00:00Z",
    "rights_checked_at": "2026-10-26T02:10:00Z",
    "available_at": "2026-10-26T02:10:00Z"
  },
  "rights": {
    "automated_retrieval": true,
    "local_retention": true,
    "derived_claim_storage": true,
    "evidence_ref": "saved-terms-or-written-permission-reference",
    "terms_version": "2026-10-26"
  },
  "content": {
    "sha256": "exact-64-character-SHA-256-of-the-retained-bytes",
    "scope": "full_document",
    "citations": ["a short exact sentence from the retained text"]
  }
}
```

`published_at` may be a date when the source does not reveal a time. Do not
invent a time. `available_at` must not precede publication, capture, or rights
review, so the graph will not make the document visible too early in replay.

## What the software enforces

`validate_primary_document` rejects a mismatched hash, missing affirmative
rights, non-HTTPS canonical source URL, wrong POWERGRID identity, unsupported
timestamp, or citation that is absent from the saved text.

`admit_primary_document_and_store` creates an append-only evidence event only
after that validation. `extend_primary_graph` then creates a new graph-database
copy; it does not modify the existing graph. The only automatic relation is:

```
cited primary document event -> POWERGRID
```

It does **not** infer a directional price effect, a sector/index relationship,
or a trading decision.

## Before using a real document

1. Record the specific terms page or written permission that permits collection,
   local retention, and storage of derived claims.
2. Retain the exact text and SHA-256; do not use a secondary summary.
3. Confirm source publication and capture time with their original precision.
4. Run the offline admission and graph-copy tests before adding a new importer.
