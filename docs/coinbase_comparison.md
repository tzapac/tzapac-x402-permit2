# Coinbase (Permit2 Proxy) vs This Repo (Etherlink PoC)

Branch: `codex/x402-coinbase-model3-align`

## Executive Summary

- The Permit2 SignatureTransfer path is aligned with Coinbase’s design: the client signs `PermitWitnessTransferFrom` where `spender` is an x402 Permit2 proxy, the facilitator pays gas and calls `proxy.settle(...)`, and the proxy enforces `witness.to == payTo` on-chain.
- The primary difference is deployment/infrastructure, not protocol semantics: Coinbase targets a deterministic proxy address on supported chains; Etherlink does not have Coinbase’s proxy deployed, so we deployed the same proxy source at a different address and override it via `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

## Data Flow Comparison

### PaymentRequired / requirements

Coinbase (spec intent):
- `x402Version: 2`
- `accepts[]` includes `scheme: exact`, `network: eip155:<chainId>`, `asset: <tokenAddress>`, `payTo: <serverAddress>`, `amount: <uint256>`
- `extra.assetTransferMethod = "permit2"` signals the Permit2 flow.

This repo (current PoC):
- `x402Version: 2`
- `accepts[]` includes the same structural fields.
- `asset` is encoded as `"eip155:42793/erc20:<token>"` (PoC convenience format), and client/server extract the token address by splitting on `"erc20:"`.
- We do not currently set `extra.assetTransferMethod = "permit2"`.

Impact:
- This repo’s Permit2 selection is effectively hard-wired by the PoC client/server rather than negotiated via `assetTransferMethod`.

### Payment payload (Permit2)

Coinbase:
- `payload.signature`: EIP-712 signature over Permit2 `PermitWitnessTransferFrom`.
- `payload.permit2Authorization`: `{ from, permitted{token,amount}, spender, nonce, deadline, witness{to,validAfter,extra} }`.
- Critical invariant: `spender` must be the proxy contract, not the facilitator.

This repo:
- Matches the above shape.
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
- Facilitator pays gas (when using facilitator-gas mode).

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
- The address must be set consistently across:
  - facilitator runtime
  - client signing (because it is part of the signed message as `spender`)
- Mechanism: `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

## Not Implemented Here (Compared to Coinbase Specs)

### Sponsored approval extensions

Coinbase specs describe extensions for cases where the user has no native gas to do the one-time `ERC20.approve(Permit2)`:
- `erc20ApprovalGasSponsoring`: user provides a raw signed approval transaction; facilitator may fund gas and relay it, then settle.
- `eip2612GasSponsoring`: if token supports EIP-2612, user signs a permit; facilitator submits permit + settle.

This repo:
- Does not implement these extensions.
- Assumes the user already has Permit2 allowance set (or can set it themselves).

### Atomic bundling / ordering guarantees

Coinbase specs require an atomic bundle for the sponsored-approval flow to avoid front-running between:
- funding user gas
- relaying approval
- settling via proxy

This repo:
- Does not implement a bundling mechanism.

## Practical Consequence

If Coinbase deploys their official proxy on Etherlink, the Coinbase integration should reduce to changing only `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

What stays the same:
- signed data format
- verification invariants
- settlement call (`proxy.settle`)
- on-chain witness enforcement

What differs in this PoC:
- token address and PoC-specific `asset` string formatting
- no sponsored-approval extensions / bundling pipeline
