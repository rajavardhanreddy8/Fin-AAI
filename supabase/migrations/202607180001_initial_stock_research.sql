-- Phase 1 cloud schema. Shared research data is service-managed; portfolios
-- and watchlists are private to the authenticated Supabase user who owns them.

create schema if not exists private;

create table public.securities (
    isin text primary key,
    company_name text not null,
    nse_symbol text,
    bse_code text,
    sector text,
    style_bucket text not null default 'watchlist',
    active boolean not null default true,
    created_at timestamptz not null default timezone('utc', now()),
    updated_at timestamptz not null default timezone('utc', now())
);
create unique index securities_nse_symbol_key on public.securities (nse_symbol) where nse_symbol is not null;
create unique index securities_bse_code_key on public.securities (bse_code) where bse_code is not null;

create table public.sources (
    source_id text primary key,
    source_name text not null,
    base_url text,
    evidence_tier text not null check (evidence_tier in ('official', 'company_primary', 'reputable_secondary', 'market_opinion', 'social')),
    enabled boolean not null default true,
    created_at timestamptz not null default timezone('utc', now())
);

create table public.documents (
    document_id bigint generated always as identity primary key,
    isin text references public.securities (isin),
    source_id text not null references public.sources (source_id),
    document_type text not null,
    title text not null,
    published_at timestamptz,
    retrieved_at timestamptz not null,
    source_location text not null,
    content_hash text not null,
    confidence double precision not null check (confidence between 0 and 1),
    raw_text text,
    unique (source_id, source_location, content_hash)
);
create index documents_isin_published_idx on public.documents (isin, published_at desc);

create table public.price_bars (
    isin text not null references public.securities (isin),
    trade_date date not null,
    close numeric not null check (close > 0),
    volume bigint check (volume is null or volume >= 0),
    source_id text not null references public.sources (source_id),
    retrieved_at timestamptz not null,
    primary key (isin, trade_date, source_id)
);
create index price_bars_isin_trade_date_idx on public.price_bars (isin, trade_date desc);

create table public.financial_facts (
    fact_id bigint generated always as identity primary key,
    isin text not null references public.securities (isin),
    metric text not null,
    value numeric,
    unit text,
    period_end date not null,
    period_type text not null,
    source_id text not null references public.sources (source_id),
    document_id bigint references public.documents (document_id),
    retrieved_at timestamptz not null,
    unique (isin, metric, period_end, period_type, source_id)
);
create index financial_facts_isin_metric_period_idx on public.financial_facts (isin, metric, period_end desc);

create table public.portfolio_holdings (
    holding_id bigint generated always as identity primary key,
    user_id uuid not null references auth.users (id) on delete cascade,
    portfolio_name text not null,
    isin text not null references public.securities (isin),
    quantity numeric not null check (quantity >= 0),
    average_cost numeric check (average_cost is null or average_cost >= 0),
    as_of_date date not null,
    import_source text not null,
    imported_at timestamptz not null default timezone('utc', now()),
    unique (user_id, portfolio_name, isin, as_of_date)
);
create index portfolio_holdings_user_as_of_idx on public.portfolio_holdings (user_id, as_of_date desc);

create table public.watchlist (
    user_id uuid not null references auth.users (id) on delete cascade,
    isin text not null references public.securities (isin),
    added_at timestamptz not null default timezone('utc', now()),
    reason text,
    priority smallint not null default 3 check (priority between 1 and 5),
    primary key (user_id, isin)
);
create index watchlist_user_priority_idx on public.watchlist (user_id, priority, added_at desc);

create table public.recommendations (
    recommendation_id bigint generated always as identity primary key,
    isin text not null references public.securities (isin),
    created_at timestamptz not null,
    classification text not null check (classification in ('core_investment', 'high_risk_investment', 'speculative_investment', 'watchlist_only', 'avoid')),
    action text not null,
    score numeric,
    confidence double precision not null check (confidence between 0 and 1),
    facts_json jsonb not null,
    assumptions_json jsonb not null,
    risks_json jsonb not null,
    opinion text not null,
    entry_zone_json jsonb,
    exit_triggers_json jsonb not null check (exit_triggers_json <> '[]'::jsonb),
    thesis text not null,
    policy_version text not null,
    status text not null default 'active'
);
create index recommendations_isin_created_at_idx on public.recommendations (isin, created_at desc);

create table public.recommendation_evidence (
    recommendation_id bigint not null references public.recommendations (recommendation_id),
    document_id bigint not null references public.documents (document_id),
    claim text not null,
    primary key (recommendation_id, document_id, claim)
);

create table public.recommendation_outcomes (
    outcome_id bigint generated always as identity primary key,
    recommendation_id bigint not null references public.recommendations (recommendation_id),
    measured_at timestamptz not null,
    horizon_days integer not null check (horizon_days > 0),
    absolute_return numeric,
    benchmark_return numeric,
    thesis_status text not null,
    review_notes text,
    unique (recommendation_id, horizon_days)
);

create table public.quality_issues (
    issue_id bigint generated always as identity primary key,
    run_id text not null,
    isin text references public.securities (isin),
    check_name text not null,
    severity text not null check (severity in ('info', 'warning', 'blocking')),
    message text not null,
    detected_at timestamptz not null,
    resolved_at timestamptz
);
create index quality_issues_run_id_idx on public.quality_issues (run_id);

create function private.prevent_recommendation_mutation()
returns trigger
language plpgsql
set search_path = ''
as $$
begin
    raise exception 'recommendations are append-only';
end;
$$;
revoke all on function private.prevent_recommendation_mutation() from public;

create trigger recommendations_no_update
before update on public.recommendations
for each row execute function private.prevent_recommendation_mutation();

create trigger recommendations_no_delete
before delete on public.recommendations
for each row execute function private.prevent_recommendation_mutation();

alter table public.securities enable row level security;
alter table public.sources enable row level security;
alter table public.documents enable row level security;
alter table public.price_bars enable row level security;
alter table public.financial_facts enable row level security;
alter table public.portfolio_holdings enable row level security;
alter table public.watchlist enable row level security;
alter table public.recommendations enable row level security;
alter table public.recommendation_evidence enable row level security;
alter table public.recommendation_outcomes enable row level security;
alter table public.quality_issues enable row level security;

revoke all on all tables in schema public from anon, authenticated;
revoke all on all sequences in schema public from anon, authenticated;

grant select, insert, update, delete on public.portfolio_holdings to authenticated;
grant usage, select on sequence public.portfolio_holdings_holding_id_seq to authenticated;
grant select, insert, update, delete on public.watchlist to authenticated;

create policy "Users can read their own holdings"
on public.portfolio_holdings for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add their own holdings"
on public.portfolio_holdings for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update their own holdings"
on public.portfolio_holdings for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
create policy "Users can delete their own holdings"
on public.portfolio_holdings for delete to authenticated
using ((select auth.uid()) = user_id);

create policy "Users can read their own watchlist"
on public.watchlist for select to authenticated
using ((select auth.uid()) = user_id);
create policy "Users can add their own watchlist items"
on public.watchlist for insert to authenticated
with check ((select auth.uid()) = user_id);
create policy "Users can update their own watchlist items"
on public.watchlist for update to authenticated
using ((select auth.uid()) = user_id)
with check ((select auth.uid()) = user_id);
create policy "Users can delete their own watchlist items"
on public.watchlist for delete to authenticated
using ((select auth.uid()) = user_id);
