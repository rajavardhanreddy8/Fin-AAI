create table public.ownership_facts (
    ownership_fact_id bigint generated always as identity primary key,
    isin text not null references public.securities (isin),
    metric text not null check (metric in
        ('promoter_holding_pct', 'promoter_shares', 'promoter_pledged_flag')),
    value numeric not null,
    unit text not null check (unit in ('ratio', 'shares', 'boolean')),
    period_end date not null,
    source_id text not null references public.sources (source_id),
    document_id bigint not null references public.documents (document_id),
    retrieved_at timestamptz not null,
    source_location text not null,
    evidence_label text not null,
    validation_status text not null default 'accepted'
        check (validation_status in ('accepted', 'rejected')),
    unique (isin, metric, period_end, source_id)
);

create index ownership_facts_isin_period_idx
    on public.ownership_facts (isin, period_end desc, metric);

alter table public.ownership_facts enable row level security;
revoke all on public.ownership_facts from anon, authenticated;
revoke all on sequence public.ownership_facts_ownership_fact_id_seq from anon, authenticated;
grant select, insert, update, delete on public.ownership_facts to service_role;
grant usage, select on sequence public.ownership_facts_ownership_fact_id_seq to service_role;
