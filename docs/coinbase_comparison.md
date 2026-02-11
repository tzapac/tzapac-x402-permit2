# Coinbase (Permit2 Proxy) vs This Repo (Etherlink PoC)

Branch: `codex/coinbase-align-tzapac`

## Executive Summary

- The Permit2 SignatureTransfer path is aligned with Coinbase’s design: the client signs `PermitWitnessTransferFrom` where `spender` is an x402 Permit2 proxy, the facilitator pays gas and calls `proxy.settle(...)`, and the proxy enforces `witness.to == payTo` on-chain.
- The primary difference is deployment/infrastructure, not protocol semantics: Coinbase deploys a known proxy address per supported chain; Etherlink does not have Coinbase’s proxy deployed, so we deployed the same proxy source at a different address and override it via `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

## Data Flow Comparison

### PaymentRequired / requirements

Coinbase (spec intent):
- `x402Version: 2`
- `PaymentRequired` is returned in the `Payment-Required` response header as base64 JSON.
- `accepts[]` includes `scheme: exact`, `network: eip155:<chainId>`, `asset: <tokenAddress>`, `payTo: <serverAddress>`, `amount: <uint256>`
- `resource` is a top-level object describing the paid URL and content metadata.
- `extra.assetTransferMethod = "permit2"` signals the Permit2 flow.

This repo (current PoC):
- `x402Version: 2`
- `PaymentRequired` is returned in the `Payment-Required` response header as base64 JSON.
- `accepts[]` includes the same structural fields.
- `asset` is encoded as the raw token address (matching x402 v2 types).
- `resource` is a top-level object (matching x402 v2 types).
- We set `extra.assetTransferMethod = "permit2"`.

Impact:
- Permit2 is explicitly signaled via `assetTransferMethod`, matching Coinbase's intent for client selection.

### Payment payload (Permit2)

Coinbase:
- Payment is sent in the `Payment-Signature` request header as base64 JSON.
- `paymentPayload.accepted` must exactly match one of the requirements offered in `PaymentRequired.accepts[]`.
- `payload.signature`: EIP-712 signature over Permit2 `PermitWitnessTransferFrom`.
- `payload.permit2Authorization`: `{ from, permitted{token,amount}, spender, nonce, deadline, witness{to,validAfter,extra} }`.
- Critical invariant: `spender` must be the proxy contract, not the facilitator.

This repo:
- Matches the above shape.
- Requires `paymentPayload.accepted` and rejects if it does not exactly match the offered requirements (Coinbase-style v2 verification).
- Facilitator enforces:
  - `permit2Authorization.spender == X402_EXACT_PERMIT2_PROXY_ADDRESS`
  - `permit2Authorization.witness.to == payTo`
  - `permit2Authorization.permitted.amount == amountRequired`

Impact:
- The facilitator cannot alter recipient or amount; it can only submit the settlement transaction.

## Money Flow Comparison

Coinbase:
- Tokens move directly from client wallet to `payTo` via Permit2 SignatureTransfer executed by the proxy.
- Facilitator pays gas, but never receives tokens unless you explicitly add a fee mechanism.

This repo:
- Same: tokens move client -> payTo.
- Facilitator pays gas (the default and enforced mode in this Coinbase-aligned branch).

## On-Chain Enforcement Comparison

Coinbase proxy:
- Enforces `block.timestamp >= witness.validAfter`.
- Enforces `amount <= permitted.amount`.
- Computes `witnessHash` and calls `Permit2.permitWitnessTransferFrom(...)`.
- Because `witness.to` is signed and enforced, the facilitator cannot redirect funds.

This repo:
- Uses the same proxy source as Coinbase’s verified proxy (extracted from Base Sepolia verification) deployed on Etherlink.

## Configuration Differences

Coinbase intended deployment model:
- Proxy deployed (ideally deterministic address across chains).

This repo:
- Etherlink proxy address is `0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`.
- This proxy was deployed by us (not Coinbase), so trust is anchored to our deployment and operational controls.
- Blockscout verification (exact match): `https://explorer.etherlink.com/address/0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E#code`.
- The address must be set consistently across:
  - facilitator runtime
  - client signing (because it is part of the signed message as `spender`)
- Mechanism: `X402_EXACT_PERMIT2_PROXY_ADDRESS`.
- Facilitator runtime can pin bytecode hash with `X402_EXACT_PERMIT2_PROXY_CODEHASH_ALLOWLIST`.
- Permit2 deployment is a chain prerequisite; in this repo it is configurable via `PERMIT2_ADDRESS`.
- Store/UI execution is hard-enforced to facilitator-gas Coinbase flow (legacy client/store gas handling removed).

## Not Implemented Here (Compared to Coinbase Specs)

### Sponsored approval extensions

Coinbase specs describe extensions for cases where the user has no native gas to do the one-time `ERC20.approve(Permit2)`:
- `erc20ApprovalGasSponsoring`: user provides a raw signed approval transaction; facilitator may fund gas and relay it, then settle.
- `eip2612GasSponsoring`: if token supports EIP-2612, user signs a permit; facilitator submits permit + settle.

This repo:
- Does not implement Coinbase’s end-to-end sponsored-approval flows (payload shapes, relaying/bundling, and operational pipeline).
- Assumes the user already has Permit2 allowance set (or can set it themselves).

Nuance:
- The deployed proxy contract source includes `settleWithPermit(...)`, which can combine an EIP-2612 `permit()` + Permit2 witness settlement in a single on-chain call for tokens that support EIP-2612. This PoC does not currently wire a client/facilitator flow that uses that method.

### Atomic bundling / ordering guarantees

Coinbase specs require an atomic bundle for the sponsored-approval flow to avoid front-running between:
- funding user gas
- relaying approval
- settling via proxy

This repo:
- Does not implement a bundling mechanism.
- The Etherlink public RPC endpoint `https://node.mainnet.etherlink.com` does not expose common bundle/private-transaction RPC methods (for example `eth_sendBundle`, `mev_sendBundle`, `eth_sendPrivateTransaction`), so this PoC does not attempt to support atomic multi-tx bundling via RPC.

## Practical Consequence

If Coinbase deploys their official proxy on Etherlink, the Coinbase integration should reduce to changing only `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

What stays the same:
- signed data format
- verification invariants
- settlement call (`proxy.settle`)
- on-chain witness enforcement

What differs in this PoC:
- token address and proxy address differ from Coinbase's deployments per chain
- no sponsored-approval extensions / bundling pipeline

Header note:
- This repo now uses x402 v2 header names (`Payment-Required`, `Payment-Signature`) and does not rely on legacy `X-PAYMENT-*` transport headers.
