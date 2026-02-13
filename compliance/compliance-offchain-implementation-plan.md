# Compliance Filter Implementation Plan (Initial Stage)

Status: implemented with optional Chainalysis off-chain screening.

## Current implementation

The facilitator performs a pre-check for both /verify and /settle:

- payer and payee are extracted from request payload fields.
  - payload.authorization.from
  - payload.permit2.owner
  - payload.permit2Authorization.from
  - paymentRequirements.payTo
- If screening is enabled, both addresses are normalized, checked against deny/allow lists, and optionally screened via provider.
- A deny-list match immediately rejects with ComplianceFailed.
- A non-empty allow-list enforces an allow-only policy for all checked parties.

Implemented files:

- bbt-x402-facilitator/crates/x402-facilitator-local/src/compliance.rs
- bbt-x402-facilitator/crates/x402-facilitator-local/src/facilitator_local.rs
- bbt-x402-facilitator/facilitator/src/run.rs
- bbt-x402-facilitator/crates/x402-types/src/proto/mod.rs

## Current config

- COMPLIANCE_SCREENING_ENABLED=true|false
- COMPLIANCE_PROVIDER=list|chainalysis
- COMPLIANCE_DENY_LIST
- COMPLIANCE_ALLOW_LIST
- CHAINALYSIS_REST_URL (default: https://public.chainalysis.com/api/v1/address)
- CHAINALYSIS_API_KEY
- COMPLIANCE_TIMEOUT_MS
- COMPLIANCE_BLOCKED_STATUS
- COMPLIANCE_FAIL_CLOSED

If COMPLIANCE_SCREENING_ENABLED is not true, checks are skipped.

## Why this path

- No smart contract changes required.
- Existing Coinbase-aligned verifier/settler flow stays unchanged.
- Deployment policy is controlled by env values.

## Next stage

- Add response caching and structured metrics around allow/deny outcomes.
- Add retry and observability for provider failures.
