// Read-only daily historical strategy evaluation; JSON goes to stdout.
import { createRequire } from "node:module";
import { fileURLToPath, pathToFileURL } from "node:url";
import path from "node:path";

const root = fileURLToPath(new URL("../momentum-site/", import.meta.url));
const require = createRequire(new URL("../momentum-site/package.json", import.meta.url));
const { createServer } = await import(pathToFileURL(require.resolve("vite")).href);
const vite = await createServer({ appType: "custom", configFile: false, root,
  resolve: { alias: { "@": root } }, server: { middlewareMode: true } });

try {
  const { priceHistory } = await vite.ssrLoadModule("/lib/finance-market.ts");
  const { backtest, DEFAULT_SETTINGS } = await vite.ssrLoadModule("/lib/finance-core.ts");
  const { promotionGate } = await vite.ssrLoadModule("/lib/strategy-promotion.ts");
  const seed = (await vite.ssrLoadModule("/lib/finance-seed.json")).default;
  const symbols = seed.companies.filter(company => company.facts?.length && company.documents?.length && company.price).map(company => company.symbol);
  const perSymbol = [];
  for (const symbol of symbols) {
    try {
      const history = await priceHistory(symbol);
      const result = backtest(history.bars, DEFAULT_SETTINGS);
      perSymbol.push({ symbol, latestCompletedDate: history.latestCompletedDate,
        holdoutTrades: result.test.tradeCount,
        holdoutReturnPct: Number((result.test.netReturn * 100).toFixed(2)),
        benchmarkReturnPct: Number((result.test.benchmarkReturn * 100).toFixed(2)),
        maxDrawdownPct: Number((result.test.maxDrawdown * 100).toFixed(2)) });
    } catch (error) {
      perSymbol.push({ symbol, error: error instanceof Error ? error.message : String(error) });
    }
  }
  const promotion = promotionGate(perSymbol, symbols.length);
  process.stdout.write(JSON.stringify({ evaluatedAt: new Date().toISOString(),
    strategy: "Breakout 20 / trend 200 / volume 1.5 / ATR stop 2 / target 2R / time 20",
    source: "Yahoo Finance adjusted daily history; exploratory data only.",
    settings: DEFAULT_SETTINGS, universe: symbols, promotionGate: promotion, perSymbol }) + "\n");
} finally {
  await vite.close();
}
