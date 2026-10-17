# Isolated AWS environment for the NIFTYBEES paper pilot

## Purpose

Keep the Breeze API and its credentials on the local intermediary computer, and
separate stored market data from offline backtesting and paper execution in AWS.
No component in this environment submits, changes, cancels, or squares off a
broker order.

## Boundary

This diagram is the target architecture, not proof that the private worker,
gateway endpoints or audit trail have been deployed. The existing local uploader
and S3 protections were verified on 2026-10-07. Legacy cloud collector resources
and the previously created Breeze secret still require an inventory/cleanup
review before claiming complete credential isolation.

```text
Breeze historical/candle API
          |
          v
Local intermediary computer
  - app key/secret in owner-restricted .env.local; session in process memory only
  - fixed, data-only request adapter
  - assumes the restricted LocalIngestRole using the local fin-aai sign-in
  - uploads raw snapshots to S3 with one-hour AWS temporary credentials
          |
          v
Private, versioned S3 data bucket
  - raw/     immutable source snapshots and fetched candles
  - runs/    backtest inputs, versioned configuration and outputs
  - paper/   simulated decisions, fills and reconciliations
          |
          v
Paper/backtest EC2 (private subnet, no public IP, no internet route)
  - no Breeze or OpenRouter credentials
  - S3 access through a gateway endpoint
  - operator access through private Systems Manager endpoints
  - may read raw/ and write runs/ and paper/; cannot delete
```

The AWS worker lives in the assigned Region, `ap-southeast-2`, and a dedicated
VPC. It has no Breeze credentials, no broker network path, and no internet
route. The local intermediary uses the user-owned Breeze registration, then
uploads raw data to the private bucket. Require encrypted S3, block all public
access, enforce TLS in the bucket policy, and keep each AWS role limited to its
own data prefixes.

## What this does and does not isolate

- The AWS worker never receives the Breeze key, secret, or session token, so a
  model, strategy, or paper-order bug cannot use the broker API from AWS.
- The local intermediary exposes only a fixed historical/candle fetch operation.
  Do not add the Breeze trading SDK or ship order methods to it.
- The broker may issue a credential that is technically capable of orders.
  AWS network rules cannot turn that credential into a broker-enforced
  read-only key. The data-only guarantee therefore depends on the collector's
  small fixed-request adapter and on keeping broker credentials out of every
  other component.
- The initial private worker is offline: it runs backtests and deterministic
  paper simulation from stored candles. OpenRouter/Jev egress is a later,
  separate design decision; do not give broad internet access to this worker.
- Live order activation and broker execution remain outside this pilot stack.

## Evidence and audit

- Store each fetched source response separately from normalized bars, with
  retrieval time, exchange session date, instrument, interval, schema version,
  and a SHA-256 content hash.
- Keep S3 versioning enabled. The collector can add raw records but cannot
  overwrite by deleting prior versions. The simulation role cannot delete
  source data or run records.
- Enable CloudTrail management events and S3 object data events for the pilot
  bucket. Keep CloudTrail logs in a separate private, encrypted, versioned
  bucket. Monitor instance health and S3 storage/request metrics in CloudWatch.
- Record strategy, prompt, model, and RL policy versions with each run. A
  candidate policy never replaces the active paper policy automatically.

## Deployment order

1. Confirm the AWS project plan and available credits/expiry in AWS Settings and
   Billing. Confirm `ap-southeast-2` is available for the required services.
2. Deploy the dedicated VPC, private S3 buckets, least-privilege roles, and
   isolated collector/private-worker instances. Create no resource in another
   Region; the Agent Toolkit's `us-east-1` control plane is a setup exception.
3. Keep Breeze credentials out of AWS. Enter them only into the local
   intermediary's secure prompts. The collector role accepts writes to `raw/`
   only and cannot read objects or use broker APIs.
4. Verify the fixed data-only Breeze adapter and restricted role, then fetch
   completed five-minute NIFTYBEES candles and preserve raw snapshots in S3.
5. Run the offline baseline backtest on the private worker. Compare later
   versions only on identical data, costs, fills, and chronological splits.
6. Start forward paper simulation after historical-data coverage and cost
   assumptions are verified. Keep all broker order functions absent.
7. Add Jev/model inference only through a separate, budgeted gateway after the
   data collection and offline simulation path is sound.

## Cost and access gate

The design uses two EC2 instances, one billable static public IPv4 address,
private Systems Manager interface endpoints, S3, Secrets Manager, and CloudTrail
S3 data events. The private worker can be stopped outside evaluation windows;
the allocated static IPv4 and interface endpoints continue to incur charges
while retained. Verify the actual project plan, credit balance/expiry, regional
service availability, and a cost estimate before provisioning. Budget alerts
are notifications, not a hard spending cap.

The local ingestion path uses the existing `fin-aai` AWS CLI sign-in and the
`LocalIngestRole` in the assigned Region. The AWS session must be refreshed with
the normal AWS login flow when it expires. Do not configure a second profile
with long-lived access keys.

## Current readiness — 2026-10-15

No AWS command was executed this review: the current machine has no `aws` CLI
available. The recorded 2026-10-09 plan, credit, expiry, catalogue, and IAM
simulation evidence is historical only and cannot authorize provisioning or a
paid model request today. Before any deployment, install/sign in to AWS CLI,
then collect fresh project-plan, credit/expiry, selected-Region model access,
service eligibility, resource inventory, dated model-price/FX, and cumulative
billing evidence. Keep the missing evidence in the budget contract; do not
replace placeholders with inferred values.

The new local scheduler is intentionally not a cloud deployment. It consumes
only a local collector handoff after raw evidence admission. Its Breeze session
bootstrap remains interactive and ephemeral, so continuous unattended
collection is not claimed. No resource was created in `ap-southeast-2` or any
other Region.

On 2026-10-16, a fresh local AWS CLI v2.38.1 sign-in authenticated the
project-managed role. Read-only plan evidence is FREE/ACTIVE with USD 108.21
remaining and expiry 2027-04-02T13:25:02.518000+00:00. The selected Region
catalogue includes Nova Lite for on-demand inference. Cost Explorer's estimated
month-to-date unblended cost is USD -0.0000004645. This authenticates the local
session and documents current billing visibility; it does not prove a successful
Bedrock runtime call, create an AWS resource, or approve deployment.

A further read-only inventory on the same date lists the active
`apac.amazon.nova-lite-v1:0` inference profile. It also confirms that the
legacy `fin-aai-breeze-collector` t3.small remains running and that the
`fin-aai-foundation` stack is `UPDATE_COMPLETE`. This is current evidence of
ongoing legacy-runtime cost and incomplete credential-isolation review. It is
not a reason to reuse that collector for paper operation. No legacy resource
was stopped, altered, or deleted.
