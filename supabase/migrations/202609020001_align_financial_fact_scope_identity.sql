-- SQLite and PostgreSQL must identify a fact the same way. Consolidated and
-- standalone values from one filing source are distinct accepted facts.
alter table public.financial_facts
    drop constraint if exists financial_facts_isin_metric_period_end_period_type_source_i_key;
