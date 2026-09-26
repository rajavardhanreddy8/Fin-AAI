-- Phase 2 evidence provenance and deterministic governance flags.
-- Shared research tables remain service-managed and inaccessible to end users.

alter table public.documents
    add column document_key text,
    add column period_end date,
    add column reporting_scope text not null default 'consolidated',
    add column validation_status text not null default 'accepted';

update public.documents
set document_key = source_id || ':' || content_hash || ':' || document_id::text
where document_key is null;

alter table public.documents
    alter column document_key set not null,
    add constraint documents_reporting_scope_check
        check (reporting_scope in ('consolidated', 'standalone', 'group', 'bank')),
    add constraint documents_validation_status_check
        check (validation_status in ('accepted', 'rejected'));

create unique index documents_document_key_key
    on public.documents (document_key);
create index documents_isin_type_period_idx
    on public.documents (isin, document_type, period_end desc);

alter table public.financial_facts
    add column publication_date date,
    add column currency text not null default 'INR',
    add column source_value text,
    add column source_location text,
    add column evidence_label text not null default 'fact_source_reported',
    add column confidence_label text not null default 'high',
    add column statement_scope text not null default 'consolidated',
    add column validation_status text not null default 'accepted';

update public.financial_facts as fact
set publication_date = coalesce(document.published_at::date, fact.retrieved_at::date),
    source_value = fact.value::text,
    source_location = document.source_location
from public.documents as document
where document.document_id = fact.document_id;

alter table public.financial_facts
    drop constraint if exists financial_facts_isin_metric_period_end_period_type_source_id_key,
    add constraint financial_facts_confidence_label_check
        check (confidence_label in ('high', 'medium', 'low')),
    add constraint financial_facts_statement_scope_check
        check (statement_scope in ('consolidated', 'standalone', 'group', 'bank')),
    add constraint financial_facts_validation_status_check
        check (validation_status in ('accepted', 'rejected')),
    add constraint financial_facts_evidence_key
        unique (isin, metric, period_end, period_type, source_id, statement_scope);

create table public.governance_flags (
    flag_id bigint generated always as identity primary key,
    isin text not null references public.securities (isin),
    rule_id text not null,
    event_key text not null,
    severity text not null check (severity in ('info', 'warning', 'blocking')),
    message text not null,
    source_document_id bigint references public.documents (document_id),
    detected_at timestamptz not null,
    status text not null default 'open' check (status in ('open', 'resolved')),
    unique (isin, rule_id, event_key)
);

create index governance_flags_isin_status_idx
    on public.governance_flags (isin, status, detected_at desc);
create index governance_flags_source_document_id_idx
    on public.governance_flags (source_document_id);

alter table public.governance_flags enable row level security;

revoke all on public.governance_flags from anon, authenticated;
revoke all on sequence public.governance_flags_flag_id_seq from anon, authenticated;
grant select, insert, update, delete on public.governance_flags to service_role;
grant usage, select on sequence public.governance_flags_flag_id_seq to service_role;
