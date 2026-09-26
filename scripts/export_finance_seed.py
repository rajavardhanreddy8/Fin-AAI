"""Export source-linked live evidence into Momentum's checked-in dashboard seed."""
from __future__ import annotations

import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def rows(connection: sqlite3.Connection, query: str, params: tuple[object, ...] = ()) -> list[dict]:
    connection.row_factory = sqlite3.Row
    return [dict(row) for row in connection.execute(query, params)]


def export_seed(database: Path, seed_path: Path) -> dict:
    seed = json.loads(seed_path.read_text(encoding="utf-8"))
    companies = seed.get("companies")
    if not isinstance(companies, list):
        raise ValueError("Seed must contain a companies list.")

    with sqlite3.connect(database) as connection:
        current = {
            item["isin"]: item
            for item in rows(connection, "SELECT isin, company_name, nse_symbol, sector FROM securities WHERE active=1")
        }
        updated = 0
        for company in companies:
            isin = company.get("isin")
            if isin not in current:
                continue
            security = current[isin]
            documents = rows(connection, """
                SELECT document_id, title, document_type, published_at, retrieved_at, source_location,
                       period_end, source_id
                FROM documents
                WHERE isin=? AND validation_status='accepted'
                ORDER BY published_at DESC, document_id DESC
            """, (isin,))
            facts = rows(connection, """
                SELECT fact_id, metric, value, unit, currency, period_end, period_type, publication_date,
                       statement_scope, document_id, source_location, retrieved_at
                FROM financial_facts
                WHERE isin=? AND validation_status='accepted'
                ORDER BY period_end DESC, metric, fact_id DESC
            """, (isin,))
            flags = rows(connection, """
                SELECT severity, message AS summary, detected_at, source_document_id
                FROM governance_flags
                WHERE isin=? AND status='open'
                ORDER BY detected_at DESC, flag_id DESC
            """, (isin,))
            price_rows = rows(connection, """
                SELECT close, volume, trade_date, source_id, retrieved_at
                FROM price_bars WHERE isin=?
                ORDER BY trade_date DESC, retrieved_at DESC LIMIT 1
            """, (isin,))
            if not documents or not facts or not price_rows:
                continue
            company.update({
                "symbol": security["nse_symbol"] or company.get("symbol"),
                "company_name": security["company_name"],
                "industry": security["sector"] or company.get("industry"),
                "documents": documents,
                "facts": facts,
                "flags": flags,
                "price": price_rows[0],
            })
            updated += 1

    seed["exportedAt"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    seed["source"] = "Official NSE and company-primary refresh exported from a local verified evidence database. Only profiles with accepted documents, facts, and an EOD price are refreshed."
    seed_path.write_text(json.dumps(seed, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    return {"identities": len(companies), "refreshed_profiles": updated, "exported_at": seed["exportedAt"]}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--seed", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(export_seed(args.db, args.seed), indent=2))


if __name__ == "__main__":
    main()
