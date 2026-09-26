import test from "node:test";
import assert from "node:assert/strict";
import { assessCompany } from "../lib/finance-investing.ts";

const fact = (overrides = {}) => ({
  fact_id: 1, metric: "revenue", value: 100, unit: "million", currency: "INR",
  period_end: "2025-03-31", period_type: "annual", statement_scope: "consolidated", document_id: 10,
  ...overrides,
});
const company = (overrides = {}) => ({
  symbol: "TEST", company_name: "Test Company", taxonomy: "non_financial", facts: [], flags: [],
  ...overrides,
});
const growthFacts = () => [
  fact({ fact_id: 1, document_id: 11, period_end: "2024-03-31", value: 100 }),
  fact({ fact_id: 2, document_id: 12, period_end: "2025-03-31", value: 125 }),
  fact({ fact_id: 3, metric: "profit_after_tax", document_id: 13, period_end: "2024-03-31", value: 20 }),
  fact({ fact_id: 4, metric: "profit_after_tax", document_id: 14, period_end: "2025-03-31", value: 25 }),
];

test("missing core evidence is needs_data and never becomes a valuation claim", () => {
  const result = assessCompany(company());
  assert.equal(result.status, "needs_data");
  assert.equal(result.growth.length, 0);
  assert.equal(result.missingData.length, 2);
  assert.equal(result.researchOnly, true);
  assert.match(result.limitations.join(" "), /No price-based valuation/);
});

test("calculates comparable same-period prior-year growth with evidence IDs", () => {
  const result = assessCompany(company({ facts: growthFacts() }));
  assert.equal(result.status, "pass");
  assert.equal(result.growth[0].percent, 25);
  assert.equal(result.growth[0].current.fact_id, 2);
  assert.equal(result.growth[0].prior.document_id, 11);
});

test("does not mix scope, currency, unit, or different fiscal-period endings", () => {
  const result = assessCompany(company({ facts: [
    fact({ period_end: "2024-03-31", statement_scope: "standalone", value: 100 }),
    fact({ fact_id: 2, period_end: "2025-03-31", statement_scope: "consolidated", value: 120 }),
    fact({ fact_id: 3, metric: "profit_after_tax", period_end: "2024-03-30", value: 20 }),
    fact({ fact_id: 4, metric: "profit_after_tax", period_end: "2025-03-31", value: 25, currency: "USD" }),
  ] }));
  assert.equal(result.status, "needs_data");
  assert.equal(result.growth.length, 0);
  assert.equal(result.missingData.length, 2);
});

test("adverse governance evidence requires review even when growth is positive", () => {
  const result = assessCompany(company({
    facts: growthFacts(),
    flags: [{ severity: "warning", summary: "Related-party disclosure requires review.", source_document_id: 99 }],
  }));
  assert.equal(result.status, "review");
  assert.equal(result.governanceFlags[0].source_document_id, 99);
  assert.match(result.reviewReasons[0], /Related-party/);
});

test("blocking governance evidence requires review even when evidence is missing", () => {
  const result = assessCompany(company({ flags: [{ severity: "blocking", summary: "Promoter pledge disclosed.", source_document_id: 99 }] }));
  assert.equal(result.status, "review");
  assert.equal(result.missingData.length, 2);
  assert.match(result.reviewReasons[0], /Promoter pledge/);
});

test("latest current period cannot fall back to an older comparable pair", () => {
  const result = assessCompany(company({ facts: [
    fact({ period_end: "2022-03-31", value: 100 }), fact({ fact_id: 2, period_end: "2023-03-31", value: 110 }),
    fact({ fact_id: 3, period_end: "2025-03-31", value: 120 }),
    fact({ fact_id: 4, metric: "profit_after_tax", period_end: "2024-03-31", value: 10 }), fact({ fact_id: 5, metric: "profit_after_tax", period_end: "2025-03-31", value: 11 }),
  ] }));
  assert.equal(result.status, "needs_data");
  assert.equal(result.growth.map(item => item.metric).join(), "profit_after_tax");
  assert.match(result.missingData[0], /missing matching prior-year evidence.*2025-03-31/);
});

test("conflicting duplicate values and invalid dates are missing evidence", () => {
  const result = assessCompany(company({ facts: [
    fact({ period_end: "2024-03-31", value: 100 }), fact({ fact_id: 2, period_end: "2025-03-31", value: 120 }), fact({ fact_id: 3, period_end: "2025-03-31", value: 130 }),
    fact({ fact_id: 4, metric: "profit_after_tax", period_end: "2024-02-30", value: 10, period_type: "unknown_duration" }), fact({ fact_id: 5, metric: "profit_after_tax", period_end: "2025-02-28", value: 11, period_type: "unknown_duration" }),
  ] }));
  assert.equal(result.status, "needs_data");
  assert.match(result.missingData.join(" "), /conflicting duplicate/);
  assert.match(result.missingData.join(" "), /unsupported period type/);
});

test("uses consolidated evidence when latest period also contains another scope", () => {
  const result = assessCompany(company({ facts: [
    fact({ period_end: "2024-03-31", statement_scope: "standalone", value: 50 }), fact({ fact_id: 2, period_end: "2025-03-31", statement_scope: "standalone", value: 51 }),
    fact({ fact_id: 3, period_end: "2024-03-31", statement_scope: "consolidated", value: 100 }), fact({ fact_id: 4, period_end: "2025-03-31", statement_scope: "consolidated", value: 120 }),
    fact({ fact_id: 5, metric: "profit_after_tax", period_end: "2024-03-31", value: 10 }), fact({ fact_id: 6, metric: "profit_after_tax", period_end: "2025-03-31", value: 12 }),
  ] }));
  assert.equal(result.status, "pass");
  assert.equal(result.growth[0].current.statement_scope, "consolidated");
  assert.equal(result.growth[0].percent, 20);
});

test("financial companies use net interest income and profit after tax", () => {
  const result = assessCompany(company({ taxonomy: "nbfc_or_financial", facts: [
    fact({ metric: "net_interest_income", period_end: "2024-03-31", value: 50 }), fact({ fact_id: 2, metric: "net_interest_income", period_end: "2025-03-31", value: 55 }),
    fact({ fact_id: 3, metric: "profit_after_tax", period_end: "2024-03-31", value: 10 }), fact({ fact_id: 4, metric: "profit_after_tax", period_end: "2025-03-31", value: 12 }),
  ] }));
  assert.equal(result.status, "pass");
  assert.deepEqual(result.growth.map(item => item.metric), ["net_interest_income", "profit_after_tax"]);
});


