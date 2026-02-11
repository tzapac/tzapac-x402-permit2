# tzapac-x402

Etherlink-focused **x402 Beta** demonstrating paid API access with a custom facilitator and storefront flow for a specific BBT token.

This project showcases an end-to-end x402 payment flow on Etherlink (`eip155:42793`) using:
- a facilitator (`bbt-x402-facilitator`)
- a Python store API (`bbt_mvp_server.py`)
- a wallet-based demo UI (`wallet_connect_poc.html`)

## Purpose

This repository is a practical demo of pay-per-request APIs over x402 for Etherlink.

The protected resource is a sample weather endpoint, and payment is denominated in BBT (`0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`).

## Quick Start

Start here for the fastest setup path:
- `docs/quick_start.md`

## Access Links

Local Docker setup (from this repo, and current UI defaults):
- Demo storefront UI: `http://localhost:9091`
- Local facilitator: `http://localhost:9090`
- Local protected endpoint via proxy: `http://localhost:9091/api/weather`

Optional hosted endpoints (if your deployment exposes them):
- Facilitator: `https://exp-faci.bubbletez.com`
- Store API endpoint: `https://exp-store.bubbletez.com/api/weather`

## Project Structure

- `bbt-x402-facilitator/`: Rust x402 facilitator implementation and chain/scheme crates (Etherlink-focused build)
- `bbt_mvp_server.py`: Python store API, x402 challenge/verification, and settlement handling
- `wallet_connect_poc.html`: browser demo shell and markup
- `wallet_connect_poc.css`: externalized demo styles (CSP-safe, no inline style block)
- `wallet_connect_poc.js`: externalized demo logic (CSP-safe, no inline script block)
- `docker-compose.wallet-poc.yml`: local stack wiring (facilitator + store-api + storefront proxy)
- `bbt-x402-facilitator/bbt_config.multitest.json`: facilitator runtime config for Etherlink multitest
- `docs/quick_start.md`: quick setup and run guide, with links to deeper docs
- `docs/bbt_token_reference.md`: BBT example token details used by this Beta
- `bbt_client.py`, `bbt_storefront.py`, `manual_payment_test.py`, `sdk_payment_proof.py`: deprecated compatibility wrappers that redirect to supported v2 flows
- `deployment_info.md`: deployment-time proxy initialization risks and required safeguards
- `.github/workflows/ci.yml`: CI checks for Python syntax and Compose config validation

## Payment Flow (High-Level)

1. Client requests `GET /api/weather`.
2. Store returns `402 Payment Required` with `Payment-Required` containing x402 requirements (base64 JSON, x402 v2).
3. Client signs payment data and sends `Payment-Signature` (base64 JSON payload) to the same endpoint.
4. Settlement uses facilitator-gas mode (Coinbase-style witness flow; `X-GAS-PAYER` resolves to facilitator).
5. Server verifies/settles payment and returns `200` plus `X-Payment-Response` with tx metadata.
6. Response includes an Etherlink explorer link for the settlement transaction.

## Why Permit2 (and not EIP-3009 here)

The Rust facilitator in `bbt-x402-facilitator` supports both:
- **EIP-3009** (`transferWithAuthorization`)
- **Permit2** (via an x402 Permit2 proxy)

This Beta demo flow uses **Permit2** because the example token used here (BBT) is not wired as an EIP-3009 token in this setup.

### Example: EIP-3009 (transferWithAuthorization)

If you use a token that supports EIP-3009, the payment payload uses `payload.authorization` (signed EIP-712) instead of Permit2.

Below is an example **facilitator** `/settle` request (x402 v2) shape using EIP-3009:

```json
{
  "x402Version": 2,
  "paymentRequirements": {
    "scheme": "exact",
    "network": "eip155:42793",
    "amount": "10000000000000000",
    "payTo": "0xPAY_TO_ADDRESS",
    "maxTimeoutSeconds": 60,
    "asset": "0xTOKEN_ADDRESS",
    "extra": {
      "name": "TOKEN_EIP712_NAME",
      "version": "TOKEN_EIP712_VERSION"
    }
  },
  "paymentPayload": {
    "x402Version": 2,
    "accepted": {
      "scheme": "exact",
      "network": "eip155:42793",
      "amount": "10000000000000000",
      "payTo": "0xPAY_TO_ADDRESS",
      "maxTimeoutSeconds": 60,
      "asset": "0xTOKEN_ADDRESS",
      "extra": {
        "name": "TOKEN_EIP712_NAME",
        "version": "TOKEN_EIP712_VERSION"
      }
    },
    "payload": {
      "signature": "0xEIP712_SIGNATURE",
      "authorization": {
        "from": "0xPAYER_ADDRESS",
        "to": "0xPAY_TO_ADDRESS",
        "value": "10000000000000000",
        "validAfter": "1700000000",
        "validBefore": "1700003600",
        "nonce": "0x32_BYTE_NONCE"
      }
    }
  }
}
```

Notes:
- `extra.name` / `extra.version` are optional, but including them avoids extra RPC calls to fetch the token EIP-712 domain fields.
- The facilitator pays gas to submit `transferWithAuthorization(...)`, but the destination/amount are fixed by the signed authorization.

## Coinbase (Permit2 Proxy)

This branch aligns the Etherlink Permit2 flow with Coinbase's design for the x402 `exact` scheme:

- The client signs a Permit2 `PermitWitnessTransferFrom` (SignatureTransfer) where `spender` is an **x402 Permit2 proxy contract** (not the facilitator).
- The facilitator pays gas and calls the proxy `settle(...)` method.
- The proxy enforces `witness.to == payTo` on-chain, so the facilitator cannot redirect funds.
- Funds move **directly from the client wallet to `payTo`**; the facilitator never takes custody.

### Etherlink Addresses

- Canonical Permit2 (Etherlink): `0x000000000022D473030F116dDEE9F6B43aC78BA3`
- x402 Exact Permit2 Proxy (Etherlink, deployed for this Beta): `0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`

Prerequisite:
- Permit2 must be deployed at `PERMIT2_ADDRESS` on the target chain. In this Beta it defaults to the canonical Permit2 address above, but it is configurable via `PERMIT2_ADDRESS`.

The Etherlink proxy was deployed from the same verified Coinbase proxy source (as seen on Base Sepolia); only the deployed address differs on Etherlink.
This proxy deployment was performed by us (not Coinbase), so there is an explicit trust assumption in our deployment and operational controls.

It is verified on Etherlink Blockscout as an **exact-match** Solidity source verification (contract `x402ExactPermit2Proxy`):
- https://explorer.etherlink.com/address/0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E#code

Set `X402_EXACT_PERMIT2_PROXY_ADDRESS` to the proxy address above in:
- the facilitator container/runtime
- any client tooling that constructs the Permit2 signature (the proxy address is the signed `spender`)

If Coinbase deploys their official x402 Permit2 proxy to Etherlink, integration should reduce to **changing only** `X402_EXACT_PERMIT2_PROXY_ADDRESS` to the Coinbase-deployed address. The payload format, settlement call, and on-chain protections remain the same.

For proxy trust hardening, facilitator verify/settle supports proxy bytecode hash pinning via:
- `X402_EXACT_PERMIT2_PROXY_CODEHASH_ALLOWLIST` (comma-separated `0x...` keccak256 bytecode hashes)

This stack pins the deployed Etherlink proxy runtime hash by default:
- `0x73020ff18bfd4eaba45de17760ad433063ed6267a8371ef54a39083a14180366`

### Local Coinbase Stack

This repo includes a dedicated compose file that pins the Etherlink proxy address:

- `docker-compose.model3-etherlink.yml`

Run:

- `docker compose -f docker-compose.model3-etherlink.yml up -d --build`
- `RPC_URL=<your_rpc> CHAIN_ID=42793 AUTO_STACK=0 ./.venv/bin/python playbook_permit2_flow.py` (or `AUTO_STACK=1` to let the playbook bring up the compose stack)

### Proxy Deployment Safety

The upstream Coinbase proxy uses a one-time `initialize(address permit2)` call. To avoid deploy/init race conditions on fresh deployments, use atomic deploy+initialize in one transaction via:

- `contracts/x402ExactPermit2ProxyFactory.sol`

This deployer creates `x402ExactPermit2Proxy` and calls `initialize(permit2)` immediately before returning the proxy address.

### Server and Playbook Safety Defaults

- `bbt_mvp_server.py` no longer falls back to a hard-coded payout address. One of `SERVER_WALLET`, `STORE_ADDRESS`, or `STORE_PRIVATE_KEY` must be set.
- `bbt_mvp_server.py` validates that the signed payment token equals the required `asset`.
- `bbt_mvp_server.py` emits `Payment-Required.resource.url` dynamically from `PUBLIC_BASE_URL` (if set) or the incoming request base URL.
- `bbt_mvp_server.py` enforces Coinbase-style witness flow and facilitator gas only (legacy client/store gas branches are removed).
- `playbook_permit2_flow.py` requires explicit `RPC_URL`/`NODE_URL`.
- `playbook_permit2_flow.py` validates chain-id consistency and verifies deployed code exists at both `PERMIT2_ADDRESS` and `X402_EXACT_PERMIT2_PROXY_ADDRESS`.
- `playbook_permit2_flow.py` uses bounded Permit2 approvals (exact required amount).
- Funding top-ups are opt-in with `ALLOW_FUNDING_TOPUPS=1`.

## Notes

- This is a Beta repository, not a hardened production deployment.
- Secrets must be provided via local env files (for example, `.env` / `.env.multitest`) and should never be committed.
