import { assessCompany, type CompanyAssessment, type SeedCompany } from "./finance-investing.ts";

export type ResearchRole = "fundamentals" | "governance" | "valuation";
export type ModelCaller = (system: string, evidence: unknown) => Promise<unknown>;
export type ResearchClaim = { text: string; factIds: (number | string)[]; documentIds: (number | string)[] };
export type SpecialistAnalysis = { summary: string; claims: ResearchClaim[]; missingData: string[] };
export type ResearchSynthesis = { summary: string; questions: string[] };
export type ResearchSpecialistResult = SpecialistAnalysis & { role: ResearchRole };
export type ResearchResult = {
  assessment: CompanyAssessment;
  evidenceSnapshot: Readonly<SeedCompany>;
  specialists: ResearchSpecialistResult[];
  synthesis: ResearchSynthesis;
};

const ROLES: ResearchRole[] = ["fundamentals", "governance", "valuation"];
const SPECIALIST_KEYS = ["summary", "claims", "missingData"];
const CLAIM_KEYS = ["text", "factIds", "documentIds"];
const SYNTHESIS_KEYS = ["summary", "questions"];

function deepFreeze<T>(value: T): T {
  if (value && typeof value === "object" && !Object.isFrozen(value)) {
    Object.freeze(value);
    for (const item of Object.values(value as Record<string, unknown>)) deepFreeze(item);
  }
  return value;
}

function exactKeys(value: Record<string, unknown>, keys: string[]) {
  const actual = Object.keys(value).sort(), expected = [...keys].sort();
  return actual.length === expected.length && actual.every((key, index) => key === expected[index]);
}

function boundedText(value: unknown, max: number) {
  return typeof value === "string" && value.trim().length > 0 && value.length <= max;
}

function boundedStrings(value: unknown, maxItems: number, maxText: number) {
  return Array.isArray(value) && value.length <= maxItems && value.every(item => boundedText(item, maxText));
}

function ids(value: unknown, known: Set<number | string>) {
  return Array.isArray(value) && value.length <= 12 && value.every(id => (typeof id === "number" || typeof id === "string") && known.has(id));
}

function validateSpecialist(value: unknown, knownFactIds: Set<number | string>, knownDocumentIds: Set<number | string>): SpecialistAnalysis {
  if (!value || typeof value !== "object" || Array.isArray(value) || !exactKeys(value as Record<string, unknown>, SPECIALIST_KEYS)) throw new Error("Specialist response must use exactly summary, claims, and missingData.");
  const response = value as Record<string, unknown>;
  if (!boundedText(response.summary, 2000) || !boundedStrings(response.missingData, 20, 500) || !Array.isArray(response.claims) || response.claims.length > 20) throw new Error("Specialist response exceeds the bounded schema.");
  for (const claim of response.claims) {
    if (!claim || typeof claim !== "object" || Array.isArray(claim) || !exactKeys(claim as Record<string, unknown>, CLAIM_KEYS)) throw new Error("Each claim must use exactly text, factIds, and documentIds.");
    const item = claim as Record<string, unknown>;
    if (!boundedText(item.text, 1000) || !ids(item.factIds, knownFactIds) || !ids(item.documentIds, knownDocumentIds)) throw new Error("A claim has invalid text or an unknown evidence ID.");
    if ((item.factIds as unknown[]).length + (item.documentIds as unknown[]).length < 1) throw new Error("Each claim requires at least one supplied fact or document citation.");
  }
  return response as unknown as SpecialistAnalysis;
}

function validateSynthesis(value: unknown): ResearchSynthesis {
  if (!value || typeof value !== "object" || Array.isArray(value) || !exactKeys(value as Record<string, unknown>, SYNTHESIS_KEYS)) throw new Error("Synthesis response must use exactly summary and questions.");
  const response = value as Record<string, unknown>;
  if (!boundedText(response.summary, 2000) || !boundedStrings(response.questions, 20, 500)) throw new Error("Synthesis response exceeds the bounded schema.");
  return response as unknown as ResearchSynthesis;
}

function specialistSystem(role: ResearchRole) {
  return `You are the ${role} research specialist. Use only the frozen evidence object supplied to you: its facts, flags, and document metadata/excerpts. Do not fetch, infer from, or claim to read a full filing. Return JSON only with exactly {summary,claims,missingData}; every claim needs at least one supplied factIds or documentIds citation. Do not give a buy/sell view, target, price claim, score, status, arithmetic, or allocation.`;
}

const SYNTHESIS_SYSTEM = "You are the research synthesizer. Use only the frozen evidence, deterministic assessment, and validated specialist analyses supplied to you. Return JSON only with exactly {summary,questions}. Do not add a score, status, buy/sell view, target, price claim, arithmetic, or allocation.";

/**
 * Runs bounded research roles against one frozen copy of one seed company.
 * The caller supplies all model access; this module performs no network or
 * secret access. Deterministic assessment status is returned unchanged.
 */
export async function runCompanyResearch(company: SeedCompany, modelCaller: ModelCaller): Promise<ResearchResult> {
  const evidenceSnapshot = deepFreeze(structuredClone(company));
  const assessment = assessCompany(evidenceSnapshot);
  const knownFactIds = new Set<number | string>((evidenceSnapshot.facts ?? []).map(fact => fact.fact_id).filter((id): id is number | string => typeof id === "number" || typeof id === "string"));
  const knownDocumentIds = new Set<number | string>([...(evidenceSnapshot.documents ?? []).map(document => typeof document === "object" && document !== null ? (document as { document_id?: unknown }).document_id : undefined), ...(evidenceSnapshot.facts ?? []).map(fact => fact.document_id)].filter((id): id is number | string => typeof id === "number" || typeof id === "string"));
  const context = deepFreeze({ evidenceSnapshot, assessment, evidenceLimit: "facts, flags, and document metadata/excerpts only; no full filing reading claim" });
  const specialists: ResearchSpecialistResult[] = [];
  for (const role of ROLES) specialists.push({ role, ...validateSpecialist(await modelCaller(specialistSystem(role), context), knownFactIds, knownDocumentIds) });
  const synthesisContext = deepFreeze({ ...context, specialists });
  const synthesis = validateSynthesis(await modelCaller(SYNTHESIS_SYSTEM, synthesisContext));
  return { assessment, evidenceSnapshot, specialists, synthesis, limitation: "Research summaries are bounded to supplied evidence and do not provide an investment recommendation, target, allocation, or order." };
}


