# tzapac-x402

Etherlink-focused **x402 proof of concept** demonstrating paid API access with a custom facilitator and storefront flow for a specific BBT token.

This project showcases an end-to-end x402 payment flow on Etherlink (`eip155:42793`) using:
- a facilitator (`bbt-x402-facilitator`)
- a Python store API (`bbt_mvp_server.py`)
- a wallet-based demo UI (`wallet_connect_poc.html`)

## Purpose

This repository is a practical demo of pay-per-request APIs over x402 for Etherlink.

The protected resource is a sample weather endpoint, and payment is denominated in BBT (`0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`).

## Access Links

Hosted endpoints currently used in the demo UI defaults:
- Facilitator: `https://exp-faci.bubbletez.com`
- Store API endpoint: `https://exp-store.bubbletez.com/api/weather`

Local Docker setup (from this repo):
- Demo storefront UI: `http://localhost:9091`
- Local facilitator: `http://localhost:9090`
- Local protected endpoint via proxy: `http://localhost:9091/api/weather`

## Project Structure

- `bbt-x402-facilitator/`: Rust x402 facilitator implementation and chain/scheme crates (Etherlink-focused build)
- `bbt_mvp_server.py`: Python store API, x402 challenge/verification, and settlement handling
- `wallet_connect_poc.html`: browser demo for wallet connect, Permit2 approval/signing, and paid request execution
- `docker-compose.wallet-poc.yml`: local stack wiring (facilitator + store-api + storefront proxy)
- `bbt-x402-facilitator/bbt_config.multitest.json`: facilitator runtime config for Etherlink multitest
- `.github/workflows/ci.yml`: CI checks for Python syntax and Compose config validation

## Payment Flow (High-Level)

1. Client requests `GET /api/weather`.
2. Store returns `402 Payment Required` with `X-PAYMENT-REQUIRED` containing x402 requirements.
3. Client signs payment data and sends `X-PAYMENT` (base64 JSON payload) to the same endpoint.
4. Settlement mode is selected by `X-GAS-PAYER` (`client`, `store`, `facilitator`, or `auto`).
5. Server verifies/settles payment and returns `200` plus `X-PAYMENT-RESPONSE` with tx metadata.
6. Response includes an Etherlink explorer link for the settlement transaction.

## Why Permit2 (and not EIP-3009 here)

The Rust facilitator in `bbt-x402-facilitator` supports both:
- **EIP-3009** (`transferWithAuthorization`)
- **Permit2** (via an x402 Permit2 proxy)

This PoC demo flow uses **Permit2** because the example token used here (BBT) is not wired as an EIP-3009 token in this setup.

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
- x402 Exact Permit2 Proxy (Etherlink, deployed for this PoC): `0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`

The Etherlink proxy was deployed from the same verified Coinbase proxy source (as seen on Base Sepolia); only the deployed address differs on Etherlink.

It is verified on Etherlink Blockscout as an **exact-match** Solidity source verification (contract `x402ExactPermit2Proxy`).

Set `X402_EXACT_PERMIT2_PROXY_ADDRESS` to the proxy address above in:
- the facilitator container/runtime
- any client tooling that constructs the Permit2 signature (the proxy address is the signed `spender`)

If Coinbase deploys their official x402 Permit2 proxy to Etherlink, integration should reduce to **changing only** `X402_EXACT_PERMIT2_PROXY_ADDRESS` to the Coinbase-deployed address. The payload format, settlement call, and on-chain protections remain the same.

### Local Coinbase Stack

This repo includes a dedicated compose file that pins the Etherlink proxy address:

- `docker-compose.model3-etherlink.yml`

Run:

- `docker compose -f docker-compose.model3-etherlink.yml up -d --build`
- `AUTO_STACK=0 ./.venv/bin/python playbook_permit2_flow.py` (or `AUTO_STACK=1` to let the playbook bring up the compose stack)

## Notes

- This is a proof-of-concept repository, not a hardened production deployment.
- Secrets must be provided via local env files (for example, `.env` / `.env.multitest`) and should never be committed.
