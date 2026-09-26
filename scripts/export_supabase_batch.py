from __future__ import annotations

import argparse
import json
import sqlite3
from pathlib import Path


DB_DEFAULT = Path(r"C:\tmp\fin-aai-live-complete-audit.db")


def rows(connection: sqlite3.Connection, query: str, params: tuple[object, ...]) -> list[dict]:
    return [dict(row) for row in connection.execute(query, params)]


def sql_json(payload: list[dict]) -> str:
    return "'" + json.dumps(payload, separators=(",", ":"), ensure_ascii=False).replace("'", "''") + "'::jsonb"


def build(connection: sqlite3.Connection, table: str, offset: int, limit: int) -> str:
    page = (limit, offset)
    if table == "sources":
        data = rows(connection, "select * from sources order by source_id limit ? offset ?", page)
        return f"""insert into public.sources(source_id,source_name,base_url,evidence_tier,enabled,created_at)
select * from jsonb_to_recordset({sql_json(data)}) as x(source_id text,source_name text,base_url text,evidence_tier text,enabled boolean,created_at timestamptz)
on conflict(source_id) do update set source_name=excluded.source_name,base_url=excluded.base_url,evidence_tier=excluded.evidence_tier,enabled=excluded.enabled;"""
    if table == "securities":
        data = rows(connection, "select * from securities order by isin limit ? offset ?", page)
        return f"""insert into public.securities(isin,company_name,nse_symbol,bse_code,sector,style_bucket,active,created_at,updated_at)
select * from jsonb_to_recordset({sql_json(data)}) as x(isin text,company_name text,nse_symbol text,bse_code text,sector text,style_bucket text,active boolean,created_at timestamptz,updated_at timestamptz)
on conflict(isin) do update set company_name=excluded.company_name,nse_symbol=excluded.nse_symbol,bse_code=excluded.bse_code,sector=excluded.sector,style_bucket=excluded.style_bucket,active=excluded.active,updated_at=excluded.updated_at;"""
    if table == "documents":
        data = rows(connection, """select isin,source_id,document_type,title,published_at,retrieved_at,source_location,content_hash,confidence,
case when length(raw_text)<=50000 then raw_text else null end raw_text,document_key,period_end,reporting_scope,validation_status
from documents where validation_status='accepted' order by document_key limit ? offset ?""", page)
        return f"""insert into public.documents(isin,source_id,document_type,title,published_at,retrieved_at,source_location,content_hash,confidence,raw_text,document_key,period_end,reporting_scope,validation_status)
select * from jsonb_to_recordset({sql_json(data)}) as x(isin text,source_id text,document_type text,title text,published_at timestamptz,retrieved_at timestamptz,source_location text,content_hash text,confidence float8,raw_text text,document_key text,period_end date,reporting_scope text,validation_status text)
on conflict(document_key) do update set title=excluded.title,published_at=excluded.published_at,retrieved_at=excluded.retrieved_at,source_location=excluded.source_location,content_hash=excluded.content_hash,confidence=excluded.confidence,raw_text=excluded.raw_text,period_end=excluded.period_end,reporting_scope=excluded.reporting_scope,validation_status=excluded.validation_status;"""
    if table == "financial_facts":
        data = rows(connection, """select f.isin,f.metric,f.value,f.unit,f.period_end,f.period_type,f.source_id,d.document_key,f.retrieved_at,f.publication_date,f.currency,f.source_value,f.source_location,f.evidence_label,f.confidence_label,f.statement_scope,f.validation_status
from financial_facts f join documents d on d.document_id=f.document_id where f.validation_status='accepted' order by f.isin,f.period_end,f.metric,f.source_id,f.statement_scope limit ? offset ?""", page)
        return f"""insert into public.financial_facts(isin,metric,value,unit,period_end,period_type,source_id,document_id,retrieved_at,publication_date,currency,source_value,source_location,evidence_label,confidence_label,statement_scope,validation_status)
select x.isin,x.metric,x.value,x.unit,x.period_end,x.period_type,x.source_id,d.document_id,x.retrieved_at,x.publication_date,x.currency,x.source_value,x.source_location,x.evidence_label,x.confidence_label,x.statement_scope,x.validation_status
from jsonb_to_recordset({sql_json(data)}) as x(isin text,metric text,value numeric,unit text,period_end date,period_type text,source_id text,document_key text,retrieved_at timestamptz,publication_date date,currency text,source_value text,source_location text,evidence_label text,confidence_label text,statement_scope text,validation_status text)
join public.documents d using(document_key)
on conflict(isin,metric,period_end,period_type,source_id,statement_scope) do update set value=excluded.value,unit=excluded.unit,document_id=excluded.document_id,retrieved_at=excluded.retrieved_at,publication_date=excluded.publication_date,currency=excluded.currency,source_value=excluded.source_value,source_location=excluded.source_location,evidence_label=excluded.evidence_label,confidence_label=excluded.confidence_label,validation_status=excluded.validation_status;"""
    if table == "ownership_facts":
        data = rows(connection, """select f.isin,f.metric,f.value,f.unit,f.period_end,f.source_id,d.document_key,f.retrieved_at,f.source_location,f.evidence_label,f.validation_status
from ownership_facts f join documents d on d.document_id=f.document_id where f.validation_status='accepted' order by f.isin,f.period_end,f.metric limit ? offset ?""", page)
        return f"""insert into public.ownership_facts(isin,metric,value,unit,period_end,source_id,document_id,retrieved_at,source_location,evidence_label,validation_status)
select x.isin,x.metric,x.value,x.unit,x.period_end,x.source_id,d.document_id,x.retrieved_at,x.source_location,x.evidence_label,x.validation_status
from jsonb_to_recordset({sql_json(data)}) as x(isin text,metric text,value numeric,unit text,period_end date,source_id text,document_key text,retrieved_at timestamptz,source_location text,evidence_label text,validation_status text)
join public.documents d using(document_key)
on conflict(isin,metric,period_end,source_id) do update set value=excluded.value,unit=excluded.unit,document_id=excluded.document_id,retrieved_at=excluded.retrieved_at,source_location=excluded.source_location,evidence_label=excluded.evidence_label,validation_status=excluded.validation_status;"""
    if table == "price_bars":
        data = rows(connection, "select * from price_bars order by isin,trade_date,source_id limit ? offset ?", page)
        return f"""insert into public.price_bars(isin,trade_date,close,volume,source_id,retrieved_at)
select * from jsonb_to_recordset({sql_json(data)}) as x(isin text,trade_date date,close numeric,volume bigint,source_id text,retrieved_at timestamptz)
on conflict(isin,trade_date,source_id) do update set close=excluded.close,volume=excluded.volume,retrieved_at=excluded.retrieved_at;"""
    if table in {"governance_flags", "material_changes"}:
        key = "source_document_id"
        data = rows(connection, f"""select t.*,d.document_key from {table} t left join documents d on d.document_id=t.{key} order by t.rowid limit ? offset ?""", page)
        for item in data:
            item.pop("flag_id" if table == "governance_flags" else "change_id", None)
            item.pop(key, None)
        if table == "governance_flags":
            return f"""insert into public.governance_flags(isin,rule_id,event_key,severity,message,source_document_id,detected_at,status)
select x.isin,x.rule_id,x.event_key,x.severity,x.message,d.document_id,x.detected_at,x.status from jsonb_to_recordset({sql_json(data)}) as x(isin text,rule_id text,event_key text,severity text,message text,document_key text,detected_at timestamptz,status text) left join public.documents d using(document_key)
on conflict(isin,rule_id,event_key) do update set severity=excluded.severity,message=excluded.message,source_document_id=excluded.source_document_id,detected_at=excluded.detected_at,status=excluded.status;"""
        return f"""insert into public.material_changes(isin,change_key,change_type,severity,summary,source_document_id,effective_date,detected_at,status)
select x.isin,x.change_key,x.change_type,x.severity,x.summary,d.document_id,x.effective_date,x.detected_at,x.status from jsonb_to_recordset({sql_json(data)}) as x(isin text,change_key text,change_type text,severity text,summary text,document_key text,effective_date date,detected_at timestamptz,status text) left join public.documents d using(document_key)
on conflict(isin,change_key) do update set change_type=excluded.change_type,severity=excluded.severity,summary=excluded.summary,source_document_id=excluded.source_document_id,effective_date=excluded.effective_date,detected_at=excluded.detected_at,status=excluded.status;"""
    raise ValueError(table)


parser = argparse.ArgumentParser()
parser.add_argument("table")
parser.add_argument("--db", type=Path, default=DB_DEFAULT)
parser.add_argument("--offset", type=int, default=0)
parser.add_argument("--limit", type=int, default=50)
args = parser.parse_args()
connection = sqlite3.connect(args.db)
connection.row_factory = sqlite3.Row
print(build(connection, args.table, args.offset, args.limit))
