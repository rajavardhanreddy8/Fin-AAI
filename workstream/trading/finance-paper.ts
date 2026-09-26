/** Deterministic in-memory paper ledger. It has no broker, network, or live-order capability. */
import type { Bar, Settings } from "../../momentum-site/lib/finance-core";
import { positionSize } from "../../momentum-site/lib/finance-core";

/** A raw, unadjusted completed daily OHLCV bar. Corporate-action flags halt processing for manual review. */
export type PaperBar = Bar & { completedAt: string; corporateAction?: string | null };
/** An explicitly supplied research decision; this module never creates signals. */
export type PaperResearchSignal = { id: string; symbol: string; signalAt: string; stop: number; target: number; rationale: string };
export type PaperOrderRequest = { id: string; research: PaperResearchSignal };
export type PaperOrder = PaperOrderRequest & { status: "pending" | "filled" | "rejected"; queuedAt: string; rejection?: string; fillId?: string };
export type PaperFill = { id: string; orderId: string; symbol: string; side: "buy" | "sell"; at: string; price: number; quantity: number; fee: number; reason: string };
export type PaperPosition = { symbol: string; quantity: number; entryPrice: number; entryAt: string; stop: number; target: number; orderId: string; lastPrice: number };
/** A serializable, immutable snapshot. Persist snapshots outside this module if continuity is needed. */
export type PaperLedger = { kind: "paper-ledger"; settings: Settings; cash: number; orders: PaperOrder[]; fills: PaperFill[]; positions: Record<string, PaperPosition>; processedEventIds: string[]; lastBarDateBySymbol: Record<string, string> };

const iso = (x: unknown) => typeof x === "string" && Number.isFinite(Date.parse(x)) && /(?:Z|[+-]\d\d:\d\d)$/.test(x);
const positive = (x: unknown) => typeof x === "number" && Number.isFinite(x) && x > 0;
const copy = (l: PaperLedger): PaperLedger => ({ ...l, settings: { ...l.settings }, orders: l.orders.map(o => ({ ...o, research: { ...o.research } })), fills: l.fills.map(f => ({ ...f })), positions: Object.fromEntries(Object.entries(l.positions).map(([k, p]) => [k, { ...p }])), processedEventIds: [...l.processedEventIds], lastBarDateBySymbol: { ...l.lastBarDateBySymbol } });
const fees = (s: Settings) => s.costBps / 10000;
const slip = (s: Settings) => s.slippageBps / 10000;

function validateSettings(s: Settings) {
  for (const key of ["initial", "monthly", "riskPct", "positionPct", "costBps", "slippageBps"] as const) if (!Number.isFinite(s[key])) throw new Error("Paper settings must contain finite numbers.");
  if (s.initial <= 0 || s.riskPct <= 0 || s.positionPct <= 0 || s.costBps < 0 || s.slippageBps < 0) throw new Error("Paper settings have invalid limits.");
}
function validateBar(b: PaperBar) {
  if (!b || !/^\d{4}-\d{2}-\d{2}$/.test(b.date) || !iso(b.completedAt)) throw new Error("Paper bars require a session date and completedAt ISO timestamp.");
  if (b.corporateAction) throw new Error("Corporate-action bar requires manual review before paper-ledger advancement.");
  if (!new Date(b.completedAt).toISOString().startsWith(`${b.date}T`)) throw new Error("Paper bar completedAt must fall on its session date (UTC).");
  for (const k of ["open", "high", "low", "close"] as const) if (!positive(b[k])) throw new Error("Paper bar prices must be positive.");
  if (!Number.isFinite(b.volume) || b.volume < 0 || b.high < Math.max(b.open, b.close, b.low) || b.low > Math.min(b.open, b.close, b.high)) throw new Error("Paper bar OHLCV is inconsistent.");
}

/** Start a cash-only paper account. `settings.initial` becomes available cash. */
export function createPaperLedger(settings: Settings): PaperLedger {
  validateSettings(settings);
  return { kind: "paper-ledger", settings: { ...settings }, cash: settings.initial, orders: [], fills: [], positions: {}, processedEventIds: [], lastBarDateBySymbol: {} };
}
/** Queue one research-supplied long order. It cannot fill until a subsequent completed session. */
export function queuePaperOrder(ledger: PaperLedger, request: PaperOrderRequest, queuedAt: string): PaperLedger {
  if (!request?.id || !iso(queuedAt)) throw new Error("Paper order id and queuedAt ISO timestamp are required.");
  const r = request.research;
  if (!r?.id || !r.symbol || !r.rationale || !iso(r.signalAt) || !positive(r.stop) || !positive(r.target) || r.stop >= r.target) throw new Error("Paper orders require a complete researched long signal.");
  if (Date.parse(queuedAt) < Date.parse(r.signalAt)) throw new Error("Paper order cannot be queued before its research signal.");
  if (ledger.orders.some(o => o.id === request.id) || ledger.processedEventIds.includes(request.id)) return ledger;
  if (ledger.positions[r.symbol] || ledger.orders.some(o => o.status === "pending" && o.research.symbol === r.symbol)) throw new Error("A paper position or pending order already exists for this symbol.");
  const next = copy(ledger); next.orders.push({ ...request, research: { ...r }, status: "pending", queuedAt }); next.processedEventIds.push(request.id); return next;
}
/**
 * Consume one raw, completed bar. `eventId` makes replay idempotent. Existing
 * positions exit first; a new order fills at this bar's open and does not use
 * the same bar's high/low, preventing same-bar look-ahead.
 */
export function advancePaperLedger(ledger: PaperLedger, eventId: string, symbol: string, bar: PaperBar): PaperLedger {
  if (!eventId || !symbol) throw new Error("Paper bar eventId and symbol are required.");
  if (ledger.processedEventIds.includes(eventId)) return ledger;
  validateBar(bar); const old = ledger.lastBarDateBySymbol[symbol]; if (old && bar.date <= old) throw new Error("Paper bars must move forward exactly once per symbol.");
  const next = copy(ledger), fee = fees(next.settings), slippage = slip(next.settings);
  const held = next.positions[symbol];
  if (held) {
    let raw: number | null = null, reason = "";
    if (bar.open <= held.stop) { raw = bar.open; reason = "Gap through stop"; }
    else if (bar.low <= held.stop) { raw = held.stop; reason = "Stop (first if both touched)"; }
    else if (bar.open >= held.target || bar.high >= held.target) { raw = held.target; reason = "Target"; }
    if (raw !== null) { const price = raw * (1 - slippage), gross = price * held.quantity, exitFee = gross * fee; next.cash += gross - exitFee; next.fills.push({ id: `${eventId}:exit`, orderId: held.orderId, symbol, side: "sell", at: bar.completedAt, price, quantity: held.quantity, fee: exitFee, reason }); delete next.positions[symbol]; }
    else held.lastPrice = bar.close;
  }
  const order = next.orders.find(o => o.status === "pending" && o.research.symbol === symbol && bar.date > o.research.signalAt.slice(0, 10));
  if (order) {
    const price = bar.open * (1 + slippage), equity = next.cash + Object.values(next.positions).reduce((n, p) => n + p.quantity * p.lastPrice * (1 - slippage) * (1 - fee), 0), quantity = positionSize(equity, next.cash, price, order.research.stop, next.settings), entryFee = price * quantity * fee;
    if (!quantity || price * quantity + entryFee > next.cash + 1e-9) { order.status = "rejected"; order.rejection = "Insufficient cash for risk-limited whole-share order."; }
    else { next.cash -= price * quantity + entryFee; order.status = "filled"; order.fillId = `${eventId}:entry`; next.positions[symbol] = { symbol, quantity, entryPrice: price, entryAt: bar.completedAt, stop: order.research.stop, target: order.research.target, orderId: order.id, lastPrice: bar.close }; next.fills.push({ id: order.fillId, orderId: order.id, symbol, side: "buy", at: bar.completedAt, price, quantity, fee: entryFee, reason: "Next completed session open" }); }
  }
  next.processedEventIds.push(eventId); next.lastBarDateBySymbol[symbol] = bar.date; return next;
}
