# BBT Permit2 Facilitator Report (2026-02-04)

## Executive Summary
We implemented Permit2 support for the BBT facilitator, hardened verification and signer handling, and stabilized Docker runtime behavior. The end-to-end playbook flow was executed successfully against Etherlink mainnet, with a confirmed on-chain transfer.

## What Changed (High Level)
- Permit2 payments are accepted by the facilitator with explicit validation and settlement.
- Verification now checks Permit2 signature validity and simulates the expected token transfer with the correct sender semantics (Permit2 as `msg.sender`).
- Settlement uses a specific signer (the Permit2 `spender`) instead of round-robin, preventing mismatched spenders.
- Docker runtime now safely handles a host-mounted config with restrictive permissions and defaults to localhost binding.

## Key Fixes and Rationale
### 1) Permit2 Verification Correctness
**Issue:** `/verify` used a Multicall `transferFrom` simulation. In that context, `msg.sender` is the Multicall contract, not the configured spender. This caused false negatives/positives and mismatched settlement behavior.

**Fix:**
- `permit()` is simulated directly to validate signature.
- ERC20 allowance from owner to Permit2 is checked.
- ERC20 `transferFrom` is simulated with `from=PERMIT2_ADDRESS` to mirror actual settlement behavior.

**Outcome:** Verification now reflects the real execution path for Permit2 transfers.

### 2) Permit2 Settlement Signer Selection
**Issue:** When multiple signers exist, settlement used round-robin signers, which could mismatch the `permitSingle.spender` and fail nondeterministically.

**Fix:**
- Added `send_transaction_from` to the EIP-155 provider.
- Permit2 `permit()` and `transferFrom()` are sent from the exact `spender` address specified in the payment.

**Outcome:** Deterministic signer usage with no mismatch risk.

### 3) Docker Runtime Safety
**Issue:** Running as non-root caused failures when the mounted config file was `0600`. The entrypoint also allowed any config path and could ignore a readable copy if `--config` was already present.

**Fix:**
- Entry point enforces `/app/*` config path and requires the file to exist.
- If unreadable by the `facilitator` user, the config is copied to a readable path and always passed via `--config`.
- Compose defaults to `127.0.0.1` binding for safety; set `BBT_BIND_ADDR=0.0.0.0` for remote access.

**Outcome:** Safe defaults with predictable behavior across host permission modes.

## Test Evidence
### Playbook Run (Success)
- Script: `playbook_permit2_flow.py`
- Transfer tx: `0x3c2936aab1eb5f8e9ede25460ded7d0ae98b03c4041aae629be2cf3c3ce422c2`
- Block: `38074147`
- Status: `1`

## Remaining Known Risks (Not Yet Addressed)
### Permit2 Settlement Atomicity
- Settlement is non-atomic (`permit()` then `transferFrom()` in separate txs). If `permit()` succeeds and `transferFrom()` fails, allowance remains live. This is a known risk and would require a different on-chain flow (e.g., Permit2 SignatureTransfer or a helper contract) to fully fix.

### MVP / Playbook Known Issues (Deferred)
- Sensitive payment payloads/signatures are logged verbatim.
- Client hardcodes network `eip155:42793` instead of using server `accepts.network`.
- Client does not verify RPC chain ID against expected network.
- Server does not validate payment payload fields against invoice (amount/asset/payTo).
- Asset formatting inconsistent (raw address vs CAIP-19) in some paths.
- Playbook proof selection is permissive and should validate sender/recipient.

## Operational Notes
- For remote testing, set `BBT_BIND_ADDR=0.0.0.0` on the host running the facilitator:
  - `BBT_BIND_ADDR=0.0.0.0 docker-compose -f bbt_docker-compose.yml up -d`
- Default binding remains `127.0.0.1` for safety.

## Files Touched (Representative)
- `bbt-x402-facilitator/crates/chains/x402-chain-eip155/src/v1_eip155_exact/facilitator.rs`
- `bbt-x402-facilitator/crates/chains/x402-chain-eip155/src/chain/provider.rs`
- `bbt-x402-facilitator/docker-entrypoint.bbt.sh`
- `bbt-x402-facilitator/docker-compose.bbt.yml`
- `bbt-x402-facilitator/Dockerfile.bbt`

## Recommendations
1) Decide whether to accept non-atomic Permit2 settlement risk or invest in an atomic on-chain flow.
2) Harden `/verify` and `/settle` access control (rate limits / auth) before broader exposure.
3) Address MVP/playbook logging and validation issues before wider demos.
