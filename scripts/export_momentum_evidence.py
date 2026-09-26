"""Export accepted public research evidence to the Momentum finance source bundle.

No credentials, portfolio holdings, or raw database files are copied.
"""
import argparse
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path


def export(database, output):
    connection = sqlite3.connect(Path(database).resolve().as_uri() + "?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    members = connection.execute("SELECT symbol,isin,company_name,industry,taxonomy FROM universe_members WHERE snapshot_id=(SELECT snapshot_id FROM universe_snapshots ORDER BY retrieved_at DESC LIMIT 1) ORDER BY symbol").fetchall()
    companies = []
    for member in members:
        company = dict(member)
        company["facts"] = [dict(row) for row in connection.execute("SELECT fact_id,metric,value,unit,currency,period_end,period_type,publication_date,statement_scope,document_id,source_location,retrieved_at FROM financial_facts WHERE isin=? AND validation_status='accepted' ORDER BY period_end", (member["isin"],))]
        company["documents"] = [dict(row) for row in connection.execute("SELECT d.document_id,d.title,d.document_type,d.published_at,d.retrieved_at,d.source_location,d.period_end,s.evidence_tier FROM documents d JOIN sources s USING(source_id) WHERE d.isin=? AND d.validation_status='accepted' ORDER BY d.published_at DESC", (member["isin"],))]
        company["flags"] = [dict(row) for row in connection.execute("SELECT severity,message AS summary,detected_at,source_document_id FROM governance_flags WHERE isin=? AND status='open'", (member["isin"],))]
        price = connection.execute("SELECT close,volume,trade_date,source_id,retrieved_at FROM price_bars WHERE isin=? ORDER BY trade_date DESC,CASE WHEN source_id='nse_eod_bhavcopy' THEN 0 ELSE 1 END LIMIT 1", (member["isin"],)).fetchone()
        company["price"] = dict(price) if price else None
        companies.append(company)
    result = {"exportedAt": datetime.now(timezone.utc).isoformat(), "source": "fin-AAI accepted evidence ledger", "companies": companies}
    Path(output).parent.mkdir(parents=True, exist_ok=True)
    Path(output).write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"Exported {len(companies)} identities; {sum(bool(c['facts']) for c in companies)} with financial evidence.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("database")
    parser.add_argument("output")
    args = parser.parse_args()
    export(args.database, args.output)
