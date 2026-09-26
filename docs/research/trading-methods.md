# Evidence and Validation Blueprint for Indian Cash-Equity Swing Trading

## Decision frame

This memo evaluates public, reproducible ideas rather than attempting to imitate a famous trader's private system. The account begins at ₹10,000 and receives ₹2,000 monthly, so fixed per-order charges, whole-share sizing and small position counts matter more than institutional capacity. The appropriate first objective is to identify a robust, executable research baseline in Indian delivery equities. It is not to maximize a historical Sharpe ratio or forecast returns.

The strongest starting hypotheses are medium-horizon momentum and simple trend/breakout rules. They have unusually long and broad evidence, can be implemented long-only with daily data, and need less turnover than short-horizon reversal. Machine learning belongs later, as a challenger to simple rules, because its flexibility raises the risk of selection bias and because the leading original study is based on a very large US panel rather than a small Indian retail account.

## Sourced evidence

### Trend and time-series momentum

Moskowitz, Ooi and Pedersen study 58 liquid futures and forwards across equity indices, currencies, commodities and sovereign bonds. An instrument's own trailing 12-month excess return predicts its return for roughly the next year, with partial reversal at longer horizons.^1 Hurst, Ooi and Pedersen extend a comparable trend-following construction to 1880. Their diversified multi-asset strategy has positive average returns in every decade and performed positively in eight of the ten largest drawdowns of a 60/40 portfolio.^2

These are powerful existence results, but their natural unit is a diversified futures market with long and short positions and volatility scaling. A long-only portfolio of Indian stocks is a materially different strategy. The evidence supports testing simple persistence; it does not establish that a 200-day moving average, a particular ATR stop, or a handful of NSE stocks will work.

### Cross-sectional momentum

Jegadeesh and Titman rank US stocks by prior performance and document positive returns from buying winners and selling losers over 3- to 12-month holding periods.^3 Cross-sectional momentum asks which stocks are strongest relative to peers; time-series momentum asks whether each stock's own trend is positive. In a cash-only account, the practical translation is to own a small number of liquid relative winners and hold cash rather than short the losers.

Momentum is not a smooth return source. Long historical evidence shows recurrent, abrupt losses, especially when prior losers rebound sharply.^4 That makes leverage, concentration and forced full investment poor translations for this account. It also argues for testing an absolute-trend filter alongside relative ranking.

### Breakout and mean-reversion hypotheses

Brock, Lakonishok and LeBaron test simple moving-average and trading-range-break rules on a long Dow Jones series and reject several standard random-walk nulls.^5 A breakout is therefore a legitimate benchmark, but the study predates present market structure and is based on an index. Its value here is as a deliberately simple hypothesis: persistence after a new trailing high, not an invitation to optimize dozens of channel lengths.

Short-horizon reversals also exist in the literature. Conrad and Kaul estimate rapidly decaying weekly expected-return components, especially among small firms.^6 Later work attributes much short-term reversal to liquidity provision, bid-ask effects and temporary price pressure. That mechanism is least attractive to a small retail trader paying the spread and explicit charges. Mean reversion should be a cost-sensitive challenger restricted to liquid shares and a rising market regime, not the default strategy.

### Machine learning and false discovery

Gu, Kelly and Xiu compare linear models, regularized regressions, trees and neural networks on roughly 30,000 US stocks from 1957–2016 with 94 characteristics and macro interactions. Nonlinear methods improve out-of-sample return prediction, and momentum, liquidity and volatility-related variables are influential.^7 The result shows that nonlinear interactions can contain information in a vast panel. It does not show that a deep model trained on a much shorter Indian history will beat transparent rules after costs.

Harvey, Liu and Zhu show why a conventional t-statistic near 2 is too weak after researchers have searched hundreds of factors; their multiple-testing framework suggests a newly discovered factor should clear a t-statistic above 3.^8 Bailey and López de Prado's Deflated Sharpe Ratio adjusts an observed Sharpe for multiple trials, non-normal returns and sample length.^9 Bailey, Borwein, López de Prado and Zhu's Probability of Backtest Overfitting measures how often an in-sample winner ranks poorly out of sample across combinatorial splits.^10 These methods do not rescue an undisclosed search. Every feature, parameter grid and discarded variant must be logged.

### Costs, data integrity and retail context

Frazzini, Israel and Moskowitz use $1.7 trillion of live institutional equity executions across 21 developed markets and show that costs vary with trade type, size, stock and time; a calibrated cost model predicts independent executions better than simpler alternatives.^11 Even though the account is tiny relative to market capacity, that evidence rejects a single frictionless assumption. Indian tests need brokerage, spread, slippage, STT, exchange and regulatory charges, GST, stamp duty and depository charges as applicable on the historical trade date.

The data set must include delisted securities, historical symbol and ISIN mappings, splits, bonuses, rights and dividends, and point-in-time universe eligibility. Selecting today's Nifty constituents for the past creates survivorship and selection bias. Signals must use adjusted history, while simulated fills and share quantities must use prices and corporate-action state actually available on the date.

SEBI's cash-equity intraday study reports that seven out of ten individual intraday traders lost money.^12 Its August 2026 derivatives update is more severe: 87.7% of individuals lost in FY26, aggregate net losses were about ₹91,685 crore, and individuals paid around ₹25,000 crore in transaction costs. About 92% of aggregate individual losses arose from options.^13 These descriptive populations are not evidence that a daily cash-equity swing rule must fail. They do establish a strong prior against high turnover and leverage and support excluding F&O from the initial program.

## Proposed experimental design and thresholds

Everything in this section is a design choice, not a sourced empirical fact.

Build one contribution-aware simulator and compare every strategy with the same dated ₹10,000 initial deposit and ₹2,000 monthly deposits. Primary benchmarks should be a broad Indian total-return index bought on contribution dates, the same index with the strategy's cash allocation, and uninvested cash. Report time-weighted performance separately from investor money-weighted return.

Freeze five experiments before viewing final holdout results:

1. **Absolute trend:** long a stock only when its 12-minus-1-month return is positive and price is above its 200-session moving average; otherwise hold cash.
2. **Cross-sectional momentum:** each month rank the liquid point-in-time universe on 12-minus-1-month total return, own up to four top-ranked stocks that also pass the absolute-trend filter, and equal-weight them.
3. **Breakout:** buy a 100-session closing high only above the 200-session average; exit on a 50-session low or one fully specified ATR stop.
4. **Short reversal challenger:** among stocks above their 200-session average, buy the largest three- to five-session declines and hold no more than five sessions. Reject quickly if costs dominate.
5. **ML challenger:** elastic net and gradient-boosted trees using only lagged momentum, volatility, turnover/liquidity and market-regime features. They must beat the frozen simple rules on untouched periods, not merely predict returns better in training.

Use expanding chronological walk-forward evaluation. Fit and select on the past, execute the next block, then advance without revising prior results. Random train/test splits are invalid. Purge training observations only when their label intervals overlap a validation interval. Add an embargo only when labels, normalization windows or residual dependence can transmit information across the boundary; for non-overlapping next-month labels with strictly lagged features, a blanket embargo discards data without fixing a real leak.

Pre-register the universe rule, five signal families, parameter grids, rebalance calendar, fill convention, missing-data policy and cost schedules. Maintain a trial ledger. Reserve the final 20% of chronology, and at least five years if the history permits, as a one-use holdout. Report monthly excess returns with heteroskedasticity/autocorrelation-aware uncertainty, skew, worst month, maximum drawdown, turnover, exposure, hit rate and contribution-adjusted rupee outcomes.

Use these initial gates:

- Out-of-sample net excess return over the broad total-return benchmark is positive overall and in at least three of four chronological subperiods.
- Deflated Sharpe probability exceeds 95%, with every attempted variant counted; CSCV PBO is below 20%. These are strict research gates, not guarantees.
- Maximum drawdown is no worse than 25% and no more than five percentage points worse than the benchmark.
- The result remains acceptable at twice the base spread/slippage estimate and after adding every explicit charge from reconstructed contract notes.
- No single stock contributes more than 25% of total strategy profit, and the conclusion survives removal of the best year.
- At least 100 completed positions and five out-of-sample years are observed before treating a backtest as decision-grade; serial dependence means trade count alone is insufficient.

For paper trading, cap planned loss at 0.5% of current equity per position, allow unfilled capacity to remain cash, and never round a position upward to force deployment. At ₹10,000, that loss budget is ₹50, so whole-share and minimum-charge constraints will legitimately skip many trades. Accumulate the ₹2,000 contribution until an order is economically meaningful. As a cost stress example, a broker charging ₹20 per executed order makes a ₹2,000 buy-and-sell pair cost ₹40 before tax and other charges—2% of capital traded—so broker choice and batching can reverse a backtest conclusion.

Paper trade the frozen winner for six to twelve months and at least 30 intended decisions. Reconcile signals, rejected orders, fills and charges daily. Proceed beyond paper only if implementation matches the simulator and net expectancy remains positive; the paper phase is an operational check, not statistically strong proof.

One current specification mismatch must be fixed before any forward claim: a backtest stop defined as **next open minus 2 ATR** and a paper rule defined as **signal close minus 2 ATR** are different strategies. Choose one reference price before the holdout and paper period, rerun all history under that rule, and invalidate comparisons made across the two definitions.

## India retail-algo boundary

SEBI's February 4, 2025 framework requires API-originated algo orders to be tagged; brokers must control and monitor API access, and self-developed retail algos require exchange registration only when they cross the specified order-per-second threshold. It also calls for client/vendor-specific keys, static-IP controls, OAuth and two-factor authentication.^14 The September 30, 2025 extension made the framework and exchange operational modalities applicable to all stock brokers from April 1, 2026.^15 NSE's implementation material identifies 10 orders per second as the threshold and clarifies that API orders still receive standardized tagging below it.^16

As of September 11, 2026, this is an implemented framework, not merely a proposal. Exact onboarding, static-IP, tagging and order-type behavior depends on the broker and current exchange circulars. Re-verify the broker's approved workflow and the latest NSE/BSE modalities immediately before enabling order submission. Research, signal generation and paper trading can remain read-only while this is resolved.

## Sources

1. Tobias J. Moskowitz, Yao Hua Ooi and Lasse Heje Pedersen. “[Time Series Momentum: Original Paper Data](https://www.aqr.com/Insights/Datasets/Time-Series-Momentum-Original-Paper-Data).” Original paper published May 2012; dataset page February 27, 2018.
2. Brian K. Hurst, Yao Hua Ooi and Lasse Heje Pedersen. “[A Century of Evidence on Trend-Following Investing](https://www.aqr.com/insights/research/journal-article/a-century-of-evidence-on-trend-following-investing).” October 31, 2017.
3. Narasimhan Jegadeesh and Sheridan Titman. “[Returns to Buying Winners and Selling Losers: Implications for Stock Market Efficiency](https://doi.org/10.1111/j.1540-6261.1993.tb04702.x).” March 1993.
4. Kent Daniel and Tobias J. Moskowitz. “[Momentum Crashes](https://www.nber.org/papers/w20439).” August 2014; published 2016.
5. William Brock, Josef Lakonishok and Blake LeBaron. “[Simple Technical Trading Rules and the Stochastic Properties of Stock Returns](https://doi.org/10.1111/j.1540-6261.1992.tb04681.x).” December 1992.
6. Jennifer Conrad and Gautam Kaul. “[Mean Reversion in Short-Horizon Expected Returns](https://academic.oup.com/rfs/article-abstract/2/2/225/1582726).” April 1989.
7. Shihao Gu, Bryan Kelly and Dacheng Xiu. “[Empirical Asset Pricing via Machine Learning](https://academic.oup.com/rfs/article/33/5/2223/5758276).” May 2020.
8. Campbell R. Harvey, Yan Liu and Heqing Zhu. “[... and the Cross-Section of Expected Returns](https://www.nber.org/papers/w20592).” October 2014; published January 2016.
9. David H. Bailey and Marcos López de Prado. “[The Deflated Sharpe Ratio: Correcting for Selection Bias, Backtest Overfitting and Non-Normality](https://doi.org/10.2139/ssrn.2460551).” July 31, 2014.
10. David H. Bailey, Jonathan M. Borwein, Marcos López de Prado and Qiji Jim Zhu. “[The Probability of Backtest Overfitting](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2326253).” February 27, 2015; published 2017.
11. Andrea Frazzini, Ronen Israel and Tobias J. Moskowitz. “[Trading Costs](https://www.aqr.com/insights/research/working-paper/trading-costs).” August 23, 2018.
12. Securities and Exchange Board of India. “[Study—Analysis of Intraday Trading by Individuals in Equity Cash Segment](https://www.sebi.gov.in/reports-and-statistics/research/jul-2024/study-analysis-of-intraday-trading-by-individuals-in-equity-cash-segment_84946.html).” July 24, 2024.
13. Securities and Exchange Board of India. “[SEBI Studies Indicate Key Trends in Retail Participation, Trading Behaviour and Profitability in the Equity Derivatives](https://www.sebi.gov.in/sebi_data/attachdocs/aug-2026/1787236407005.pdf).” August 20, 2026.
14. Securities and Exchange Board of India. “[Safer Participation of Retail Investors in Algorithmic Trading](https://www.sebi.gov.in/sebi_data/attachdocs/feb-2025/1738665456458.pdf).” February 4, 2025.
15. Securities and Exchange Board of India. “[Extension of Timeline for Implementation of the February 4, 2025 Retail Algorithmic-Trading Circular](https://www.sebi.gov.in/sebi_data/attachdocs/sep-2025/1759232056254.pdf).” September 30, 2025.
16. National Stock Exchange of India. “[Implementation Standards for Safer Participation of Retail Investors in Algorithmic Trading](https://nsearchives.nseindia.com/content/circulars/INVG67858.pdf).” May 5, 2025, with later exchange modalities applicable.
