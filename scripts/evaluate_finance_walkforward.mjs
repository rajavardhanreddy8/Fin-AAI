// Reproducible rolling-window evaluation. It never changes strategy parameters
// and never uses a later window to select an earlier one.
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
  const seed = (await vite.ssrLoadModule("/lib/finance-seed.json")).default;
  const symbols = seed.companies.filter((company) => company.facts?.length && company.documents?.length && company.price).map((company) => company.symbol);
  const windows = [];
  // The engine reserves 221 warm-up sessions; 315 bars leaves a 94-session holdout.
  const windowBars = 315;
  const stepBars = 63;
  for (const symbol of symbols) {
    const history = await priceHistory(symbol);
    const bars = history.bars;
    const symbolWindows = [];
    for (let start = 0; start + windowBars <= bars.length; start += stepBars) {
      const slice = bars.slice(start, start + windowBars);
      const result = backtest(slice, DEFAULT_SETTINGS);
      symbolWindows.push({
        start: slice[0].date,
        end: slice.at(-1).date,
        holdoutStart: result.test.start,
        holdoutEnd: result.test.end,
        holdoutTrades: result.test.tradeCount,
        holdoutReturnPct: Number((result.test.netReturn * 100).toFixed(2)),
        benchmarkReturnPct: Number((result.test.benchmarkReturn * 100).toFixed(2)),
        maxDrawdownPct: Number((result.test.maxDrawdown * 100).toFixed(2)),
      });
    }
    windows.push({ symbol, latestCompletedDate: history.latestCompletedDate, windows: symbolWindows });
  }
  const all = windows.flatMap((entry) => entry.windows);
  process.stdout.write(JSON.stringify({
    evaluatedAt: new Date().toISOString(),
    strategy: "Breakout 20 / trend 200 / volume 1.5 / ATR stop 2 / target 2R / time 20",
    source: "Yahoo Finance adjusted daily history; rolling windows are exploratory and do not authorize capital.",
    settings: DEFAULT_SETTINGS,
    protocol: { windowBars, stepBars, minimumBarsPerWindow: windowBars, holdoutFraction: 0.3 },
    universe: symbols,
    windows,
    summary: {
      totalWindows: all.length,
      totalHoldoutTrades: all.reduce((sum, item) => sum + item.holdoutTrades, 0),
      positiveHoldoutWindows: all.filter((item) => item.holdoutReturnPct > 0).length,
      benchmarkBeatingWindows: all.filter((item) => item.holdoutReturnPct > item.benchmarkReturnPct).length,
    },
  }, null, 2) + "\n");
} finally {
  await vite.close();
}
