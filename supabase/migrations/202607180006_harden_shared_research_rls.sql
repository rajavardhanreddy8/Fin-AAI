-- Harden shared research tables for Supabase security advisors.
-- These tables remain service-managed only. End users keep access only to
-- portfolio_holdings and watchlist via user-owned RLS policies.

create policy "Service role manages securities"
on public.securities
for all
to service_role
using (true)
with check (true);

create policy "Service role manages sources"
on public.sources
for all
to service_role
using (true)
with check (true);

create policy "Service role manages documents"
on public.documents
for all
to service_role
using (true)
with check (true);

create policy "Service role manages price bars"
on public.price_bars
for all
to service_role
using (true)
with check (true);

create policy "Service role manages financial facts"
on public.financial_facts
for all
to service_role
using (true)
with check (true);

create policy "Service role manages recommendations"
on public.recommendations
for all
to service_role
using (true)
with check (true);

create policy "Service role manages recommendation evidence"
on public.recommendation_evidence
for all
to service_role
using (true)
with check (true);

create policy "Service role manages recommendation outcomes"
on public.recommendation_outcomes
for all
to service_role
using (true)
with check (true);

create policy "Service role manages quality issues"
on public.quality_issues
for all
to service_role
using (true)
with check (true);

create policy "Service role manages governance flags"
on public.governance_flags
for all
to service_role
using (true)
with check (true);

create policy "Service role manages material changes"
on public.material_changes
for all
to service_role
using (true)
with check (true);
