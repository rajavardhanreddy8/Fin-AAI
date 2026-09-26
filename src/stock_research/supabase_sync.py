from __future__ import annotations

from pathlib import Path
from typing import Any

from .db import connect


def build_accepted_payload(db_path: str | Path, isin: str) -> dict[str, list[dict[str, Any]]]:
    """Build a server-sync payload containing accepted records only."""
    with connect(db_path) as connection:
        security = dict(connection.execute("SELECT * FROM securities WHERE isin = ?", (isin,)).fetchone())
        documents = [
            dict(row)
            for row in connection.execute(
                "SELECT * FROM documents WHERE isin = ? AND validation_status = 'accepted' ORDER BY published_at, document_id",
                (isin,),
            )
        ]
        document_ids = {row["document_id"] for row in documents}
        document_keys = {row["document_id"]: row["document_key"] for row in documents}
        facts = [
            {**dict(row), "_document_key": document_keys[row["document_id"]]}
            for row in connection.execute(
                "SELECT * FROM financial_facts WHERE isin = ? AND validation_status = 'accepted' ORDER BY period_end, metric",
                (isin,),
            )
            if row["document_id"] in document_ids
        ]
        ownership_facts = [
            {**dict(row), "_document_key": document_keys[row["document_id"]]}
            for row in connection.execute(
                "SELECT * FROM ownership_facts WHERE isin = ? AND validation_status = 'accepted' ORDER BY period_end, metric",
                (isin,),
            )
            if row["document_id"] in document_ids
        ]
        prices = [dict(row) for row in connection.execute("SELECT * FROM price_bars WHERE isin = ? ORDER BY trade_date", (isin,))]
        flags = [
            {
                **dict(row),
                "_source_document_key": document_keys.get(row["source_document_id"]),
            }
            for row in connection.execute(
                "SELECT * FROM governance_flags WHERE isin = ? ORDER BY detected_at",
                (isin,),
            )
        ]
        changes = [
            {
                **dict(row),
                "_source_document_key": document_keys.get(row["source_document_id"]),
            }
            for row in connection.execute(
                "SELECT * FROM material_changes WHERE isin = ? ORDER BY effective_date, change_key",
                (isin,),
            )
        ]
        source_ids = sorted({row["source_id"] for row in documents} | {row["source_id"] for row in prices})
        sources = [
            dict(row)
            for row in connection.execute(
                f"SELECT * FROM sources WHERE source_id IN ({','.join('?' for _ in source_ids)}) ORDER BY source_id",
                source_ids,
            )
        ] if source_ids else []
    return {
        "securities": [security],
        "sources": sources,
        "documents": documents,
        "financial_facts": facts,
        "ownership_facts": ownership_facts,
        "price_bars": prices,
        "governance_flags": flags,
        "material_changes": changes,
    }


def sync_accepted_records(db_path: str | Path, client: Any, isin: str) -> dict[str, int]:
    """Upload accepted records through a server-only Supabase client.

    The service-role client is required because shared research tables are not
    exposed to end users. Supabase identity values are never copied from SQLite;
    document foreign keys are resolved from stable document keys after upsert.
    """
    payload = build_accepted_payload(db_path, isin)

    securities = [{**row, "active": bool(row["active"])} for row in payload["securities"]]
    sources = [{**row, "enabled": bool(row["enabled"])} for row in payload["sources"]]
    documents = [{key: value for key, value in row.items() if key != "document_id"} for row in payload["documents"]]

    if securities:
        client.table("securities").upsert(securities, on_conflict="isin").execute()
    if sources:
        client.table("sources").upsert(sources, on_conflict="source_id").execute()
    if documents:
        client.table("documents").upsert(documents, on_conflict="document_key").execute()

    remote_document_ids: dict[str, int] = {}
    document_keys = [row["document_key"] for row in documents]
    if document_keys:
        response = (
            client.table("documents")
            .select("document_id,document_key")
            .in_("document_key", document_keys)
            .execute()
        )
        remote_document_ids = {
            row["document_key"]: row["document_id"] for row in response.data
        }
        missing = sorted(set(document_keys) - set(remote_document_ids))
        if missing:
            raise RuntimeError(f"Supabase did not return document IDs for: {', '.join(missing)}")

    facts: list[dict[str, Any]] = []
    for row in payload["financial_facts"]:
        document_key = row["_document_key"]
        fact = {
            key: value
            for key, value in row.items()
            if key not in {"fact_id", "document_id", "_document_key"}
        }
        fact["document_id"] = remote_document_ids[document_key]
        facts.append(fact)

    ownership_facts: list[dict[str, Any]] = []
    for row in payload["ownership_facts"]:
        document_key = row["_document_key"]
        fact = {
            key: value
            for key, value in row.items()
            if key not in {"ownership_fact_id", "document_id", "_document_key"}
        }
        fact["document_id"] = remote_document_ids[document_key]
        ownership_facts.append(fact)

    flags: list[dict[str, Any]] = []
    for row in payload["governance_flags"]:
        document_key = row["_source_document_key"]
        flag = {
            key: value
            for key, value in row.items()
            if key not in {"flag_id", "source_document_id", "_source_document_key"}
        }
        flag["source_document_id"] = (
            remote_document_ids[document_key] if document_key is not None else None
        )
        flags.append(flag)

    if facts:
        client.table("financial_facts").upsert(
            facts,
            on_conflict="isin,metric,period_end,period_type,source_id,statement_scope",
        ).execute()
    if ownership_facts:
        client.table("ownership_facts").upsert(
            ownership_facts,
            on_conflict="isin,metric,period_end,source_id",
        ).execute()
    if payload["price_bars"]:
        client.table("price_bars").upsert(
            payload["price_bars"], on_conflict="isin,trade_date,source_id"
        ).execute()
    if flags:
        client.table("governance_flags").upsert(
            flags, on_conflict="isin,rule_id,event_key"
        ).execute()

    changes: list[dict[str, Any]] = []
    for row in payload["material_changes"]:
        document_key = row["_source_document_key"]
        change = {
            key: value
            for key, value in row.items()
            if key not in {"change_id", "source_document_id", "_source_document_key"}
        }
        change["source_document_id"] = (
            remote_document_ids[document_key] if document_key is not None else None
        )
        changes.append(change)
    if changes:
        client.table("material_changes").upsert(
            changes, on_conflict="isin,change_key"
        ).execute()

    return {table: len(rows) for table, rows in payload.items()}
