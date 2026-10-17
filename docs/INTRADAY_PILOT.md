# NIFTYBEES intraday pilot

The pilot is a five-minute, long-only, paper-first experiment. It starts with
₹5,000, has one position maximum, caps planned risk at 0.25% per trade and
pauses on a simulated 5% drawdown. The first engine milestone is tested; see
[implementation phases and verified gaps](INTRADAY_IMPLEMENTATION.md).
No command in this repository enables live orders.

## Model settings

The local computer is the Breeze intermediary. The app key and secret are saved
in the Git-ignored `.env.local`, with Windows file permissions restricted to the
current user. A fresh Breeze session is prompted each run and is not saved. These
values are not read from AWS Secrets Manager or printed to reports or shell
history. The local uploader assumes the restricted `LocalIngestRole`, which can
write raw snapshots but cannot read or delete S3 objects. Backtesting and paper
simulation do not call broker order APIs.

The selected AWS Region is `ap-southeast-2`. Keep model-provider credentials
separate from Breeze credentials. Provider adapters exist, but their access,
model identity, pricing and billing evidence require verification before use.

For local development, use the secure PowerShell launcher. It prompts for the
three Breeze values, removes them from the process environment when it exits,
and uses the existing `fin-aai` sign-in to assume the one-hour upload role:

```powershell
.\scripts\start_local_breeze_ingest.ps1 `
  -FromAt "2026-10-01T09:15:00+05:30" `
  -ToAt "2026-10-01T15:30:00+05:30" `
  -Key "raw/NIFTYBEES/2026-10-01.json"
```

Install the optional AWS SDK dependencies once:

```powershell
python -m pip install -e ".[aws]"
```

The AWS browser-login credentials need a recent Boto3 version plus AWS CRT for
automatic refresh. Confirm an active `fin-aai` sign-in before running the
collector.

The launcher checks Breeze DNS and verified TLS before prompting for credentials,
and retries DNS failures up to five times. The collector adds Certifi's public
CA bundle to Python's default trust store to handle missing public CA roots.

If Breeze TLS verification still fails because the network inspects HTTPS, set
`BREEZE_CA_BUNDLE` to the trusted inspection CA certificate in PEM format in the
PowerShell process. Certificate verification remains enabled.

The collector must call only the Breeze historical/candle data endpoints. Its
code and runtime must not include or expose order placement, modification,
cancellation, or square-off operations. The private worker writes simulated
fills to its separate paper ledger. A Breeze API credential may still be
broker-capable, so this boundary is enforced by keeping it off the paper worker
and restricting the collector program to fixed data requests.

Before creating more AWS resources, verify the AWS project plan and actual credit
balance and expiry in AWS Settings. S3 storage and requests are billable. The
Jev cap is ₹300/month and separate from AWS billing.

## Operations

Create a CSV with `at,open,high,low,close,volume`, containing chronological,
completed five-minute candles. Run:

```powershell
$env:PYTHONPATH = "src"
python -m stock_research.cli pilot-backtest data/niftybees-5m.csv --run-id baseline-001
python -m stock_research.cli pilot-status --forward-db output/intraday-forward.db --strategy-id rules-v2
python -m stock_research.cli pilot-provider-status
python -m stock_research.cli pilot-train-bars output/market-data/audited-bars.csv --version candidate-001
python -m stock_research.cli pilot-compare output/market-data/audited-bars.csv --version candidate-001
```

Candidate training uses only actions that were actually executed unchanged from
the RL policy. A Jev override is retained for evaluation but is excluded from
the learning reward. A rules-only baseline supplies no matched RL actions;
train a candidate only from a separately recorded RL experiment.

`pilot-train-bars` is the seeded, manifest-verified RL-only path. It uses the
first 60% of complete chronological sessions and preserves the final 20% as
holdout. `pilot-compare` reports frozen rules-only and RL-only holdout results.
Jev-only and RL+Jev require exact persisted decision packets, resolved model
identity and verified provider costs, so they remain explicit gaps rather than
simulated CLI variants.

The agreed live gate requires at least 100 holdout trades, 30 completed forward
paper trades across at least 30 sessions, positive expectancy after trading
costs, drawdown below 5%, no unresolved execution defects and RL improvement
over Jev-only. Preserve any stricter existing requirements. The current gate
implementation is incomplete and cannot certify these conditions. Explicit
activation, a current Breeze session token and verified broker execution
requirements would also be needed. Live activation and order submission are
intentionally not implemented in this first code delivery: they require a
verified Breeze account, broker-supported protection details and an observed
paper record.
