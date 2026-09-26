-- Cover foreign keys not already covered by a composite primary or unique key.
create index financial_facts_document_id_idx on public.financial_facts (document_id);
create index financial_facts_source_id_idx on public.financial_facts (source_id);
create index portfolio_holdings_isin_idx on public.portfolio_holdings (isin);
create index price_bars_source_id_idx on public.price_bars (source_id);
create index quality_issues_isin_idx on public.quality_issues (isin);
create index recommendation_evidence_document_id_idx on public.recommendation_evidence (document_id);
create index watchlist_isin_idx on public.watchlist (isin);
