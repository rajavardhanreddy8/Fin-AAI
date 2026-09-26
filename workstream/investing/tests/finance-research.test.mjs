import test from "node:test";
import assert from "node:assert/strict";
import { runCompanyResearch } from "../lib/finance-research.ts";

const company = {
  symbol: "TEST", company_name: "Test Co", taxonomy: "non_financial", flags: [],
  facts: [
    { fact_id: 1, metric: "revenue", value: 100, unit: "million", currency: "INR", period_end: "2024-03-31", period_type: "annual", statement_scope: "consolidated", document_id: 10 },
    { fact_id: 2, metric: "revenue", value: 120, unit: "million", currency: "INR", period_end: "2025-03-31", period_type: "annual", statement_scope: "consolidated", document_id: 11 },
    { fact_id: 3, metric: "profit_after_tax", value: 10, unit: "million", currency: "INR", period_end: "2024-03-31", period_type: "annual", statement_scope: "consolidated", document_id: 10 },
    { fact_id: 4, metric: "profit_after_tax", value: 12, unit: "million", currency: "INR", period_end: "2025-03-31", period_type: "annual", statement_scope: "consolidated", document_id: 11 },
  ],
  documents: [{ document_id: 10, title: "FY24" }, { document_id: 11, title: "FY25" }],
};
const specialist = { summary: "Evidence is limited to the supplied snapshot.", claims: [{ text: "Revenue increased in the supplied facts.", factIds: [2], documentIds: [] }], missingData: [] };

test("runs labeled specialists and synthesis against one frozen evidence snapshot", async () => {
  const calls = [];
  const result = await runCompanyResearch(company, async (system, evidence) => {
    calls.push({ system, evidence });
    return system.includes("synthesizer") ? { summary: "Questions remain for primary research.", questions: ["What changed in operating conditions?"] } : specialist;
  });
  assert.equal(result.assessment.status, "pass");
  assert.deepEqual(result.specialists.map(item => item.role), ["fundamentals", "governance", "valuation"]);
  assert.equal(calls.length, 4);
  assert.ok(Object.isFrozen(result.evidenceSnapshot));
  assert.equal(calls[0].evidence.evidenceSnapshot, result.evidenceSnapshot);
  assert.equal(result.specialists[1].claims[0].factIds[0], 2);
});

test("rejects invented fact or document citations", async () => {
  await assert.rejects(() => runCompanyResearch(company, async system => system.includes("synthesizer")
    ? { summary: "Synthesis.", questions: [] }
    : { ...specialist, claims: [{ ...specialist.claims[0], factIds: [999] }] }), /unknown evidence ID/);
});

test("rejects malformed model output and uncited claims", async () => {
  await assert.rejects(() => runCompanyResearch(company, async () => ({ summary: "Bad schema", claims: [], missingData: [], status: "pass" })), /exactly summary/);
  await assert.rejects(() => runCompanyResearch(company, async system => system.includes("synthesizer")
    ? { summary: "Synthesis.", questions: [] }
    : { ...specialist, claims: [{ text: "No citation.", factIds: [], documentIds: [] }] }), /requires at least one/);
});

