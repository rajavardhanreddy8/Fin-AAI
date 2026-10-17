# NIFTYBEES data and isolation status

Verified 2026-10-07. Requested history: 2023-10-09 through 2026-10-06.

The interrupted collector was no longer running. This milestone made no Breeze requests and did not read or request credential values. It recovered the already saved 2025-08-20 raw snapshot, audited the full requested range, and resumed pending uploads using the existing restricted role in `ap-southeast-2`.

## Reusable inputs

| Artifact | Evidence |
| --- | --- |
| `output/market-data/audited-bars.csv` | 34,425 bars; 459 complete regular sessions; exact columns `at,open,high,low,close,volume`; unique ascending aware IST bar-start timestamps. |
| Dataset SHA-256 | `0c795c96b74fa40effd9278a35567e161c3761966afca819a0a1b757d8253969` |
| `output/market-data/dataset-manifest.json` | Included dates, excluded-session details, raw and CSV hashes, S3 receipts, source-file hashes, calendar and corporate-action/cost qualification gaps. |
| `output/market-data/verification-report.json` | Independently checked all 460 local raw hashes, all 459 per-session CSV hashes, aggregate CSV hash and timestamps; downloaded the two newly uploaded raw versions and the manifest version to verify their hashes. |
| `output/market-data/manifest.json` | 459 valid, 1 invalid and 310 missing entries. All 460 preserved raw snapshots have matching upload hashes and recorded S3 version IDs. Prior upload receipts were retained, not individually downloaded again. |
| `output/market-data/collection-result.json` | Completed upload report and exact archive-manifest S3 key/version. Exit code 2 denotes outstanding quality/calendar gaps, despite successful uploads. |

First included bar: `2023-10-09T09:15:00+05:30`. Last: `2026-10-01T15:25:00+05:30`. Regular cached coverage runs through 2025-08-20, followed by the isolated 2026-10-01 session; the dates between them are not continuous coverage.

The invalid 2024-01-12 session has an invalid 09:15 OHLCV row and therefore only 74 valid expected bars. Its entire session is excluded from the aggregate CSV; the original 76-row raw response remains preserved. Each complete session contributes 75 bar starts, 09:15 through 15:25 IST. The provider's 15:30 endpoint is preserved only in raw evidence. No bars were filled or invented.

## Exact gaps and source reconciliation

`reference/calendar-reconciliation.json` preserves the exact date lists and source paths/hashes. Its categories partition the 310 missing manifest entries:

| Category | Dates |
| --- | --- |
| Regular closures supported by saved NSE notices | 32; includes previously empty provider dates and five dates never cached. These are regular-session closures, not missing regular candles. |
| Uncached dates without a saved closure/special-session explanation | 275, between 2025-08-21 and 2026-10-06. This is not a verified final count of trading sessions. |
| Known special dates already in the missing manifest | 2024-11-01 and 2025-10-21; Muhurat timings and data remain pending. |
| Unresolved prior empty-provider date | 2024-01-22. Direct trading notices CMTR60338/60340 could not be downloaded; the saved clearing notice corroborates holiday context but does not independently verify the trading closure. |

Four additional known special dates were skipped by weekday collection and are absent from the session manifest: 2023-11-12, 2024-01-20, 2024-03-02 and 2024-05-18. The last two have two separate normal-market segments, 09:15–10:00 and 11:30–12:30. Their bars are not cached. Segment-aware audits are required before including them; regular-session expectations must not span the closed interval.

Saved official additions: [May 20 holiday amendment](https://nsearchives.nseindia.com/content/circulars/CMTR61518.pdf), [November 20 holiday amendment](https://nsearchives.nseindia.com/content/circulars/CMTR64960.pdf), [March 2 special-session notice](https://nsearchives.nseindia.com/content/circulars/MSD60677.pdf), [May 18 special-session notice](https://nsearchives.nseindia.com/content/circulars/MSD61893.pdf), and [January clearing revision](https://nsearchives.nseindia.com/content/circulars/CMPT60343.pdf). PDFs, extracted text and hashes are under `reference/`; failed direct January downloads are recorded in `calendar-amendment-sources.json`.

Calendar coverage remains partial. The saved base calendars for 2023–2025 have not been installed as fully verified calendars; the existing 2026 holiday calendar also does not establish exhaustive special-session coverage. Later amendments, Muhurat timing notices and independent candle-label semantics remain open. No ephemeral `BREEZE_API_SESSION` is present in this task's process; that availability check inspected only the variable's presence. Downloading the remaining history requires a fresh session supplied locally through the existing launcher.

The saved Breeze security-master ZIP and its declared hashes were verified. Its NSE row maps NIFTYBEES to Breeze NIFBEE and ISIN INF204KB14I2. The saved zero-row NSE corporate-actions response is retained; issuer distributions and adjustments still need review. Breeze V2 data is unadjusted. The owner's actual ICICI brokerage plan, effective tariffs and ETF applicability remain unverified. OHLCV does not establish actual spreads, fills or latency. `qualified_for_trading` remains false.

## Upload receipts

Bucket: `fin-aai-foundation-databucket-bficilpuii1y`, selected Region `ap-southeast-2`.

| Newly verified version | S3 version ID |
| --- | --- |
| `raw/NIFTYBEES/2025-08-20/20276e24a4a38219ee4159c3e3beb7bef42a29218d126956f9856ec949210d53.json` | `Xkbcs9sNWeRQ1HGVBgUvAzl0KMrL9B2w` |
| `raw/NIFTYBEES/2026-10-01/132a745acb81deccc345c78d677dc454a09fb1277793ce1b25503bbb538f50b6.json` | `lgUncjHLFmF_mBnjGZQLgKE_qi4bm_Oz` |
| `raw/_manifests/3f013f9f6cae39e6d8a4a93c16dac572e1dadeb9516dc0a7b9d7197e15246925.json` | `1mcpkYA18C9N4EDyys1xnlbXVm4JUwFZ` |

The narrow upload role writes candle evidence and manifests below `raw/`. No infrastructure was deployed, no orders were placed and no existing resource or secret was deleted. `.env.local` is Git-ignored and its ACL has one explicit owner access entry with inheritance disabled; values were not inspected. The existing legacy EC2 collector and cloud secret listed in `reference/aws-status.json` remain a separate project-wide isolation cleanup gap.

## Reuse and resume

From the project directory with `PYTHONPATH=src`, rebuild from cache without Breeze or AWS:

```powershell
python scripts/run_local_breeze_ingest.py --history-from 2023-10-09 --history-to 2026-10-06 --audit-cache
```

Audit and retry cached uploads without Breeze credentials or any new historical requests:

```powershell
python scripts/run_local_breeze_ingest.py --history-from 2023-10-09 --history-to 2026-10-06 --upload-cache --bucket fin-aai-foundation-databucket-bficilpuii1y
```

Ordinary ingestion reuses successful raw files. Entries created by an offline audit as `not_cached` are eligible for normal collection; prior `provider_empty` entries require explicit `--retry-missing`. Offline audits retain existing upload receipts and reject changed raw hashes before regenerating per-session CSVs. Atomic JSON writes retry brief Windows file locks; they still fail visibly if the lock persists.

Validation: 13 focused Breeze/archive checks pass, including provider-empty versus never-fetched resume, preserved upload receipts, hash rejection, invalid-session exclusion and transient Windows-lock retry. Logs: `cache-audit.log` and `cache-upload.log`. The recorded upload report is preserved until a later run replaces it; subsequent audit-only runs produce an audit-only collection report.

## C012 continuation

The archive now exposes a manifest-backed verifier used by evaluation loading. It checks the aggregate SHA-256, CSV schema, admitted and excluded session dates, and bar count before bars can enter the backtest path. A missing or mismatched `dataset-manifest.json` blocks evaluation.

Offline verification on 2026-10-07 reproduced 34,425 bars, 459 included sessions, 311 excluded sessions, and aggregate SHA-256 `0c795c96b74fa40effd9278a35567e161c3761966afca819a0a1b757d8253969`. No Breeze request or credential read was required. The 13 existing Breeze/archive checks plus the new manifest-admission checks pass.

Remote upload evidence remains scoped: all 460 raw entries have recorded S3 version IDs and matching local upload hashes, while exact-version readback was independently performed for two raw objects and one manifest. The restricted role remains write-only under `raw/`; legacy collector resources and complete historical calendar, special-session, corporate-action, and effective-fee evidence remain open gaps. `qualified_for_trading` remains false.

On 2026-10-08, the manifest-backed paper-safe replay consumed the existing archive successfully: 33,914 decisions, 32 completed trades, modeled costs of ₹279.43, net reward -₹255.76, and maximum drawdown 5.23%. Provenance is `historical-replay`; this did not deliver fresh bars or qualify the strategy.

Fresh collection is currently blocked before any provider request: the `fin-aai` AWS session expired, and no `BREEZE_API_KEY`, `BREEZE_API_SECRET`, or `BREEZE_API_SESSION` is present in the process. Reauthenticate locally with `aws login`, then run the existing launcher so secrets remain in its secure prompts:

```powershell
.\scripts\start_local_breeze_ingest.ps1 -HistoryFrom 2023-10-09 -HistoryTo 2026-10-06
```

The current 2026 NSE holiday evidence agrees with the official NSE holiday page, including the 2026-11-08 Muhurat holiday; Muhurat timings remain pending. The saved NIFTYBEES corporate-actions response is empty, so issuer distribution and price-adjustment reconciliation remains unresolved.

Fresh ingestion completed on 2026-10-09 after local AWS reauthentication. It reused prior successful records, fetched only uncached dates, preserved the invalid sessions `2024-01-12` and `2025-10-21`, and produced 734 valid sessions / 55,050 bars. The aggregate SHA-256 is `e0a20b5233d16740cab8236c5a8b6b99393f8b70f1f3f3d45d8ed93d3106a4b5`; the manifest upload is `raw/_manifests/09f615e48641bb890254e2c9a3f76751cd262ab269042b3942d7f99d529deca8.json` version `KFqSwkgYiRo2rxd9H6_mdZXcM6ujZ_cp`.

The 32 dates backed by saved NSE regular-closure evidence were classified `exchange_closed` without a further Breeze request. The fresh historical replay consumed the new aggregate with 54,264 decisions, 32 completed trades, modeled costs ₹279.43, and remained `unqualified`.

Current local verification completed on 2026-10-09. `verification-report.json` verified the current manifest hash, aggregate hash, 736 preserved raw snapshots, 734 normalized session CSVs and 28 saved reference files. It also confirmed 736 recorded raw upload receipts. This local pass deliberately made no S3 request; its `remote_version_checks` field is `not_run`, so the previous exact-version readbacks must not be treated as verification of the newly fetched objects.

Reproduce the non-network verification from the project directory:

```powershell
python scripts/run_local_breeze_ingest.py --verify-cache --archive-dir output/market-data
```

With the existing local AWS sign-in, verify every recorded raw-object version and the current manifest version without downloading candle bodies:

```powershell
python scripts/run_local_breeze_ingest.py --verify-uploaded-versions --archive-dir output/market-data --aws-profile fin-aai
```

The focused Breeze/archive suite now has eight passing checks, including the current-manifest/local-hash verification path, explicit special-session retry protection, and recorded-version metadata verification. The archive remains unsuitable for paper trading until special-session timing, historical calendar scope, corporate actions, and effective execution costs are resolved.

Calendar reconciliation advanced on 2026-10-09. The 2024-01-22 provider-empty entry is now `exchange_closed`, backed by the saved NSE Clearing capital-market circular, which explicitly cites NSE/CMTR/60338 and 60340 as the trading-holiday notices. The direct market-notice PDF remains unavailable, and this source limitation is retained in the evidence scope. The 2024-11-01 provider-empty entry is now `special_session_unresolved`: it is an NSE Diwali/Muhurat special session whose timings and bars remain unverified. It will not be fetched or admitted unless an explicit retry follows timing reconciliation. There are now 33 `exchange_closed` entries, one `special_session_unresolved` entry, and no `provider_empty` entries. The 2025-10-21 raw response remains an invalid, preserved 15-bar special-session response and stays excluded.

The manifest-backed paper runner accepted this reconciled aggregate in run `c012-calendar-reconciled-20261009`: 54,264 decisions, 32 completed trades, ₹279.43 modeled costs, net reward `-255.764903`, and 5.23% maximum drawdown. Provenance remains `historical-replay` and qualification remains `unqualified`.

The revised manifest is uploaded at `raw/_manifests/30a1f8930f3b7071f07895bd9b34728552f11be0cf36d0247bd92fb9ac298df9.json`, version `5xb4mEJnWCOric0D_lZ4zsWyT3htf24Z`. The read-only uploaded-version verifier then checked all 736 recorded raw S3 versions plus this exact manifest version against their saved SHA-256 metadata. Its result is recorded in `verification-report.json` as `remote_version_checks.status = verified`.

Corporate-action reconciliation advanced on 2026-10-09. The saved Nippon India issuer factsheet identifies `NIFTYBEES` / `INF204KB14I2`, records distributions in 2013–15, and records the unit face-value change from ₹10 to ₹1 effective 2019-12-20. The empty NSE API result covers 2023-10-09 through 2026-10-06. Together they support retaining unadjusted Breeze candles and applying no synthetic adjustment, but they do not prove that no issuer action occurred after the 2021 factsheet; that remains an explicit gap. The current evidence manifest is `raw/_manifests/d3fcb379feaf0cbddf27765b639bbbd7a2b2a696d6fa9aba99ecf81a51bf7f69.json`, version `vOgiZNDRBVo65moFkg_AE9AzI851v5QY`; its remote verifier checked 736 raw versions and 29 local source files.

The official NSE capital-market notice `NSE/CMTR/64628` resolves the 2024-11-01 Muhurat normal-market segment as 18:00–19:00 IST. The date is now `special_session_not_fetched`, rather than an unresolved provider gap: the ordinary daytime query was not a valid request for that segment. An explicit `--retry-missing` now uses the saved single segment; cache-only modes preserve the exclusion without fetching. Multi-segment special sessions still fail visibly until segment-aware aggregation is implemented. The final manifest is `raw/_manifests/c7650f7cb51f00610e35e74a5a44249656f58edb1fb811bab0aa4dc9dc807095.json`, version `8v9WVV62Txb.3HwrOXmmnW0Pdg0g5Bkf`; its report verifies 736 raw versions, 734 normalized CSVs, and 30 source files.

All known special-session dates in the requested range are now materialized in the manifest: `2023-11-12` and `2024-01-20` are `special_session_unresolved`; `2024-03-02` and `2024-05-18` are `special_session_multi_segment_not_fetched`; and `2024-11-01` is `special_session_not_fetched`. This increases explicit missing entries to 38 without changing the 55,050-bar aggregate. The uploaded manifest is `raw/_manifests/5022d61989793683247fcdafbeb9474cc683205941aaf312a05cd236888daebc.json`, version `c3SpdR1bFly5RBkihtcF3EKKfh4R9Wmo`; remote verification covers it and all 736 raw versions. The focused archive suite has nine passing checks.

Further official notices resolve the remaining timing ambiguity: `2023-11-12` is a single 18:15–19:15 IST Muhurat normal-market segment, and `2024-01-20` is a two-segment special live session (09:15–10:00 and 11:30–12:30 IST). The manifest now records two `special_session_not_fetched` dates and three `special_session_multi_segment_not_fetched` dates; none are silently omitted. The current uploaded manifest is `raw/_manifests/d4624c907f72045f27c0f256fd646d6e03994f291685b3304f1618740b04b25a.json`, version `8sdI7OHl_xipryiUJthQXeFm1w7rm7x8`. Its verification report confirms 736 raw versions, 734 normalized CSVs, and 32 source files.

On 2026-10-09, the local collector gained segment-aware handling for official special sessions. Each official time segment is fetched to its own immutable raw snapshot and independently audited; aggregation is permitted only when every segment is complete, valid, chronologically ordered, and represented by an upload receipt. A failed or absent segment leaves the date excluded. Legacy one-snapshot sessions retain their existing manifest and S3-receipt shape. This enables explicit retries for the three saved multi-segment dates once a fresh Breeze session is locally available; it does not fetch them during cache-only modes.

After this code change, local verification still reproduces the current archive unchanged: 55,050 bars, 734 valid / 2 invalid / 38 missing sessions, aggregate SHA-256 `e0a20b5233d16740cab8236c5a8b6b99393f8b70f1f3f3d45d8ed93d3106a4b5`, 736 raw hashes and receipts, 734 normalized hashes, and 32 source hashes. The local verification did not make an S3 request. The full repository suite passed 131 tests, including the nine archive checks; the new segment test verifies two independently fetched/uploaded raw files are required before 21 audited bars are admitted.

The secure PowerShell launcher now accepts `-RetryMissing` and passes it only to history ingestion. From the project directory, once prompted for a fresh Breeze session, resume the saved special-session work with:

```powershell
.\scripts\start_local_breeze_ingest.ps1 -HistoryFrom 2023-11-12 -HistoryTo 2024-05-18 -RetryMissing
```

It reuses cached successful dates, requests only the missing timed special-session segments, and clears all Breeze values from the launcher process when it exits. A collector exit status of `2` is reported as completed with explicit exclusions, rather than masking newly persisted evidence as a launcher failure. The AWS profile remains `fin-aai` in `ap-southeast-2`.

Remote receipt verification was rerun on 2026-10-09 after the segment-aware collector change. The read-only verifier confirmed SHA-256 metadata for all 736 recorded raw S3 object versions and `raw/_manifests/d4624c907f72045f27c0f256fd646d6e03994f291685b3304f1618740b04b25a.json`, version `8sdI7OHl_xipryiUJthQXeFm1w7rm7x8`. `verification-report.json` now records `remote_version_checks.status = verified`; the dataset remains unchanged at 55,050 bars.

Segment retry handling was hardened on 2026-10-09. If one segment returns an empty provider response after an earlier segment has been saved, the manifest now retains the completed segment's local path and SHA-256 under `raw_evidence`, classifies the date as `provider_empty_segment`, and excludes it from the dataset. A later `--retry-missing` reuses that raw file and requests only the absent segment. The focused archive suite has eleven passing checks, including this interrupted-segment resume path and a source-backed non-normal-session exclusion.

The official NSE capital-market [Muhurat notice](https://nsearchives.nseindia.com/content/circulars/CMTR70319.pdf) resolves 2025-10-21: normal market was 13:45–14:45 IST and the separately announced closing session was 14:55–15:05 IST. Its saved PDF has SHA-256 `19b7d88003cb05eb8c6abdc8d1bfad5df821a17e4f9ae36f75e327a68a48d258`. The preserved Breeze response contains all twelve completed five-minute normal-market bars from 13:45 through 14:40, the 14:45 endpoint, and two published closing-session bars. The cache auditor now excludes the endpoint and the two closing-session bars explicitly; it admits the twelve normal-market bars without synthesizing data.

After cache-only reconciliation and a manifest-only upload, the archive contains 55,062 bars across 735 valid, one invalid, and 38 missing sessions. Aggregate SHA-256 is `951a116914a1d9b1214be278a1931a9718fdab6d2ee3c7bf3d0eb414a66bff05`; manifest SHA-256 is `e353a9c13e2c18e3040099abe03f003f6bb2fcb546d05e007517e06b29603bce`, uploaded as `raw/_manifests/e353a9c13e2c18e3040099abe03f003f6bb2fcb546d05e007517e06b29603bce.json`, version `x9qraR_YXxNZCodlijig3yfhSEtB6frt`. Read-only S3 verification confirms all 736 raw versions, this exact manifest version, 735 normalized hashes, and 33 source hashes.

The manifest-gated paper replay `c012-muhurat-reconciled-20261009` consumed the 55,062-bar aggregate: 54,276 decisions, 32 completed trades, ₹279.43 modeled costs, net reward `-255.764903`, and 5.23% maximum drawdown. It remains unqualified and explicitly flags the special 2025-10-21 session as starting after 09:15, so the new special-session bars cannot silently affect qualification.

Issuer identity evidence was refreshed from Nippon India Mutual Fund's February 2025 [NIFTY 50 BeES product note](https://mf.nipponindiaim.com/FundsAndPerformance/ProductNotes/NipponIndia-ETF-Nifty-50-BeES-Feb-2025.pdf), saved as `nippon-niftybees-product-note-feb-2025.pdf` with SHA-256 `9fae6743913d92ba105915f938a894a98b102e76ca3258dcf1676c563e1c3ac9`. It identifies the NSE symbol `NIFTYBEES`, describes the unit value as approximately one-hundredth of the Nifty 50 Index, and confirms individual-unit exchange trading. It is not a corporate-action ledger; the post-2021 action gap remains explicit in `corporate-actions-source.json`.

The final evidence manifest is `raw/_manifests/ca8ee5ba283c732939170c4e8845c09a22e93fe404c93bea6eb91c06db75beca.json`, version `6qICi0Zs615S8rm1n29Mq_2Tke1QjOvF`. Its read-only verifier confirms 736 raw S3 versions, 735 normalized hashes, and 34 source hashes. No raw candle was duplicated for either manifest update.

The paper replay now reads single-segment special-session windows from the verified dataset manifest. A source-backed special session is marked complete only when its approved opening, closing, five-minute continuity, and expected bar count all match; it is still execution-blocked because the frozen rules are calibrated for regular hours. Replay `c012-muhurat-windowed-20261009` consumed the same 55,062 bars with 54,276 decisions and 32 completed trades, and records no execution defects. Qualification remains `unqualified` for the independent calendar, corporate-action, cost, and strategy gates. The full suite has 134 passing tests.

The replay now also supports official multi-segment schedules from the same verified manifest. It accepts only the published gap between segments, rejects a missing bar inside either segment, and marks every special session execution-blocked. Replay `c012-schedule-aware-20261009` still records no execution defects. This makes the 2024-01-20, 2024-03-02, and 2024-05-18 special sessions ready for paper-runner admission once their separately preserved raw segment responses are collected and audited. The full suite has 136 passing tests.
