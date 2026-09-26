/**
 * Deterministic, evidence-led company research. This module does not place
 * orders, calculate a valuation, use a market price, or make an allocation.
 *
 * `assessCompany` accepts one object from finance-seed.json. A `pass` means
 * only that the supplied evidence clears these narrow research checks; it is
 * never a trade or investment instruction.
 */

export type AssessmentStatus = "needs_data" | "review" | "pass";
export type EvidenceId = number | string | null;

export type FinanceFact = {
  fact_id?: EvidenceId;
  metric: string;
  value: number;
  unit: string;
  currency: string;
  period_end: string;
  period_type: string;
  publication_date?: string;
  statement_scope: string;
  document_id?: EvidenceId;
  source_location?: string;
  retrieved_at?: string;
};

export type GovernanceFlag = {
  severity: string;
  summary: string;
  detected_at?: string;
  source_document_id?: EvidenceId;
};

/** The company shape used by each entry in finance-seed.json. */
export type SeedCompany = {
  symbol: string;
  isin?: string;
  company_name: string;
  industry?: string;
  taxonomy: "non_financial" | "nbfc_or_financial" | string;
  facts?: FinanceFact[];
  documents?: unknown[];
  flags?: GovernanceFlag[];
  price?: unknown;
};

export type GrowthMetric = {
  metric: string;
  percent: number;
  current: Pick<FinanceFact, "fact_id" | "document_id" | "value" | "unit" | "currency" | "period_end" | "period_type" | "statement_scope">;
  prior: Pick<FinanceFact, "fact_id" | "document_id" | "value" | "unit" | "currency" | "period_end" | "period_type" | "statement_scope">;
};

/**
 * Result interface for a bounded research assessment. `missingData` explains
 * why no pass can be issued; `growth` contains only directly comparable,
 * supplied facts and cites both fact and document IDs.
 */
export type CompanyAssessment = {
  status: AssessmentStatus;
  company: Pick<SeedCompany, "symbol" | "company_name" | "taxonomy">;
  growth: GrowthMetric[];
  governanceFlags: GovernanceFlag[];
  missingData: string[];
  reviewReasons: string[];
  researchOnly: true;
  limitations: string[];
};

const copyEvidence = (fact: FinanceFact): GrowthMetric["current"] => ({
  fact_id: fact.fact_id,
  document_id: fact.document_id,
  value: fact.value,
  unit: fact.unit,
  currency: fact.currency,
  period_end: fact.period_end,
  period_type: fact.period_type,
  statement_scope: fact.statement_scope,
});

function isDate(value: string) {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const date = new Date(`${value}T00:00:00Z`);
  return !Number.isNaN(date.valueOf()) && date.toISOString().slice(0, 10) === value;
}

function priorYearEnd(periodEnd: string) {
  if (!isDate(periodEnd)) return null;
  const year = Number(periodEnd.slice(0, 4));
  return `${String(year - 1).padStart(4, "0")}${periodEnd.slice(4)}`;
}

function usableFact(fact: FinanceFact) {
  return Number.isFinite(fact.value) && Boolean(fact.unit) && Boolean(fact.currency) && Boolean(fact.period_type)
    && Boolean(fact.statement_scope) && isDate(fact.period_end);
}

type GrowthAttempt = { growth: GrowthMetric | null; reason: string | null };
const comparableTypes = new Set(["annual", "quarterly"]);

function oneValue(facts: FinanceFact[]) {
  const values = new Set(facts.map(fact => fact.value));
  if (values.size !== 1) return null;
  return [...facts].sort((a, b) => String(a.fact_id ?? "").localeCompare(String(b.fact_id ?? "")))[0];
}

function comparableGrowth(facts: FinanceFact[], metric: string): GrowthAttempt {
  const candidates = facts.filter(fact => fact.metric === metric && usableFact(fact));
  if (!candidates.length) return { growth: null, reason: `${metric}: no valid supplied facts.` };
  const latestEnd = candidates.reduce((latest, fact) => fact.period_end > latest ? fact.period_end : latest, candidates[0].period_end);
  const latest = candidates.filter(fact => fact.period_end === latestEnd);
  const permitted = latest.filter(fact => comparableTypes.has(fact.period_type));
  if (!permitted.length) return { growth: null, reason: `${metric}: latest period ${latestEnd} has an unsupported period type.` };

  const scopes = new Set(permitted.map(fact => fact.statement_scope));
  const scope = scopes.has("consolidated") ? "consolidated" : scopes.size === 1 ? permitted[0].statement_scope : null;
  if (!scope) return { growth: null, reason: `${metric}: latest period ${latestEnd} has multiple statement scopes without a consolidated series.` };
  const scoped = permitted.filter(fact => fact.statement_scope === scope);
  const series = new Map<string, FinanceFact[]>();
  for (const fact of scoped) {
    const key = `${fact.period_type}|${fact.currency}|${fact.unit}`;
    series.set(key, [...(series.get(key) ?? []), fact]);
  }
  if (series.size !== 1) return { growth: null, reason: `${metric}: latest ${scope} facts use multiple period, currency, or unit series.` };
  const [key, currentFacts] = [...series.entries()][0];
  const current = oneValue(currentFacts);
  if (!current) return { growth: null, reason: `${metric}: conflicting duplicate facts for latest comparable period.` };
  const priorEnd = priorYearEnd(current.period_end);
  if (!priorEnd) return { growth: null, reason: `${metric}: latest period is not a valid calendar date.` };
  const [periodType, currency, unit] = key.split("|");
  const priorFacts = candidates.filter(fact => fact.period_end === priorEnd && fact.period_type === periodType
    && fact.statement_scope === scope && fact.currency === currency && fact.unit === unit);
  const prior = oneValue(priorFacts);
  if (!prior) return { growth: null, reason: priorFacts.length ? `${metric}: conflicting duplicate facts for prior comparable period.` : `${metric}: missing matching prior-year evidence for latest period ${current.period_end}.` };
  if (prior.value <= 0) return { growth: null, reason: `${metric}: prior comparable value must be positive to calculate percentage growth.` };
  return { growth: { metric, percent: ((current.value - prior.value) / prior.value) * 100, current: copyEvidence(current), prior: copyEvidence(prior) }, reason: null };
}

/**
 * Assess a company only from the evidence supplied on that object.
 * A pass requires positive year-over-year growth for both core metrics, no
 * adverse governance flag, and no missing core evidence. It is only a narrow
 * growth-check pass label, never an overall investment case.
 */
export function assessCompany(company: SeedCompany): CompanyAssessment {
  const facts = Array.isArray(company?.facts) ? company.facts : [];
  const governanceFlags = Array.isArray(company?.flags) ? company.flags : [];
  const coreMetrics = company?.taxonomy === "nbfc_or_financial"
    ? ["net_interest_income", "profit_after_tax"]
    : ["revenue", "profit_after_tax"];
  const growth: GrowthMetric[] = [];
  const missingData: string[] = [];
  const reviewReasons: string[] = [];

  for (const metric of coreMetrics) {
    const result = comparableGrowth(facts, metric);
    if (result.growth) growth.push(result.growth);
    else missingData.push(result.reason!);
  }

  for (const flag of governanceFlags) {
    const severity = String(flag.severity || "").toLowerCase();
    if (severity === "warning" || severity === "critical" || severity === "high" || severity === "blocking") {
      reviewReasons.push(`Governance flag (${flag.severity}): ${flag.summary}`);
    }
  }

  for (const item of growth) {
    if (item.percent <= 0) reviewReasons.push(`${item.metric}: comparable year-over-year growth is not positive (${item.percent.toFixed(2)}%).`);
  }

  const status: AssessmentStatus = reviewReasons.length > 0 ? "review" : missingData.length > 0 ? "needs_data" : "pass";
  return {
    status,
    company: { symbol: company.symbol, company_name: company.company_name, taxonomy: company.taxonomy },
    growth,
    governanceFlags,
    missingData,
    reviewReasons,
    researchOnly: true,
    limitations: [
      "Research only: no order routing, allocation, or investment recommendation.",
      "Growth is simple year-over-year change from supplied facts; no CAGR is inferred.",
      "No price-based valuation or cheapness conclusion is made.",
      "A pass is only a narrow growth-check label and does not assess an overall investment case, future performance, valuation, liquidity, or investor suitability.",
    ],
  };
}

