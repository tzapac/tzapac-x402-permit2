# Compliance Filter Implementation Plan (Initial Stage)

Status: implemented with mandatory Chainalysis off-chain screening (enabled by default).

## Current implementation

The facilitator performs a pre-check for both `/verify` and `/settle`:

- payer and payee are extracted from request payload fields.
  - `payload.authorization.from`
  - `payload.permit2.owner`
  - `payload.permit2Authorization.from`
  - `paymentRequirements.payTo`
- Screening is enabled by default and checks both addresses against deny/allow lists.
- Optional provider check uses Chainalysis (`COMPLIANCE_PROVIDER=chainalysis`).
- A deny-list match immediately rejects with `ComplianceFailed`.
- A non-empty allow-list enforces allow-only policy for all checked parties.

Implemented files:

- `bbt-x402-facilitator/crates/x402-facilitator-local/src/compliance.rs`
- `bbt-x402-facilitator/crates/x402-facilitator-local/src/facilitator_local.rs`
- `bbt-x402-facilitator/facilitator/src/run.rs`
- `bbt-x402-facilitator/crates/x402-types/src/proto/mod.rs`

## Current config

- `COMPLIANCE_SCREENING_ENABLED=true` (default)
- `COMPLIANCE_PROVIDER=chainalysis` (default)
- `COMPLIANCE_DENY_LIST`
- `COMPLIANCE_ALLOW_LIST`
- `CHAINALYSIS_REST_URL` (default: `https://public.chainalysis.com/api/v1/address`)
- `CHAINALYSIS_API_KEY`
- `COMPLIANCE_TIMEOUT_MS`
- `COMPLIANCE_BLOCKED_STATUS`
- `COMPLIANCE_FAIL_CLOSED`

Compliance screening runs by default and is required on all payment flows in this stack.
For local development or troubleshooting, `COMPLIANCE_SCREENING_ENABLED=false` can be set temporarily.

## Why this path

- No smart contract changes required.
- Existing Coinbase-aligned verifier/settler flow stays unchanged.
- Deployment policy is controlled by env values.

## Next stage

- Add response caching and structured metrics around allow/deny outcomes.
- Add retry and observability for provider failures.
