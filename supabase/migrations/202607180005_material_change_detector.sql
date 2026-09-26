-- Idempotent, source-backed weekly material changes. Service-managed only.

create table public.material_changes (
    change_id bigint generated always as identity primary key,
    isin text not null references public.securities (isin),
    change_key text not null,
    change_type text not null,
    severity text not null check (severity in ('info', 'warning', 'blocking')),
    summary text not null,
    source_document_id bigint references public.documents (document_id),
    effective_date date not null,
    detected_at timestamptz not null,
    status text not null default 'new' check (status in ('new', 'reviewed')),
    unique (isin, change_key)
);

create index material_changes_isin_effective_idx
    on public.material_changes (isin, effective_date desc, severity);
create index material_changes_source_document_id_idx
    on public.material_changes (source_document_id);

alter table public.material_changes enable row level security;
revoke all on public.material_changes from anon, authenticated;
revoke all on sequence public.material_changes_change_id_seq from anon, authenticated;
grant select, insert, update, delete on public.material_changes to service_role;
grant usage, select on sequence public.material_changes_change_id_seq to service_role;
