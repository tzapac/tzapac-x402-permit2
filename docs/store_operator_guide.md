# Store Operator Guide

This guide explains how to run an x402 store, accept a token of your choice, and structure APIs for multiple paid products.

## What this store does

- Exposes protected API routes (example: `/api/weather`).
- Returns `402 Payment Required` with x402 v2 requirements.
- Accepts `Payment-Signature` on retry.
- Calls a facilitator (`/settle`) to settle on-chain.

## Quick start (Docker)

```bash
docker pull ghcr.io/tzapac/tzapac-x402-permit2-store-api:latest
# Optional: build/pull bbt-store-web only if you use a custom web-image compose.
cp .env.example .env.multitest
# edit .env.multitest

docker compose -f docker-compose.wallet-poc.yml --env-file .env.multitest up -d --build
```

Check endpoints:

```bash
curl -s http://localhost:8001/config | jq
curl -i http://localhost:8001/api/weather
```

## Minimum env for a store

- `FACILITATOR_URL`: base URL of facilitator (`https://...` in production).
- `RPC_URL`: Etherlink RPC endpoint.
- `SERVER_WALLET` or `STORE_ADDRESS` or `STORE_PRIVATE_KEY`: payout wallet source.
- `BBT_TOKEN`: token contract to charge.
- `X402_EXACT_PERMIT2_PROXY_ADDRESS`: x402 Permit2 proxy address.

## Using any ERC-20 token as payment asset

In this repo, the charged token is read from `BBT_TOKEN` in `bbt_mvp_server.py`.

To switch token:

1. Set `BBT_TOKEN` to your ERC-20 contract on Etherlink.
2. Keep `network` as `eip155:42793` unless you also migrate chain.
3. Keep `assetTransferMethod` as `permit2` for Coinbase-aligned flow.
4. Ensure customers approve canonical Permit2 (`0x000000000022D473030F116dDEE9F6B43aC78BA3`) for that token.
5. Ensure facilitator and server use the same `X402_EXACT_PERMIT2_PROXY_ADDRESS`.

Note: naming is historical (`BBT_TOKEN` variable). It can hold any token address.

## Multi-product store model

You can expose a free product catalog and keep each product endpoint paid.

Example catalog response (`GET /api/catalog`):

```json
{
  "store": "TZ APAC Data Store",
  "products": [
    {
      "id": "weather-basic",
      "path": "/api/products/weather-basic",
      "description": "Current weather snapshot",
      "payment": {
        "network": "eip155:42793",
        "asset": "0xTokenAddressA",
        "amount": "10000000000000000",
        "payTo": "0xStoreWallet",
        "assetTransferMethod": "permit2"
      }
    },
    {
      "id": "weather-pro",
      "path": "/api/products/weather-pro",
      "description": "Forecast + historical series",
      "payment": {
        "network": "eip155:42793",
        "asset": "0xTokenAddressB",
        "amount": "50000000000000000",
        "payTo": "0xStoreWallet",
        "assetTransferMethod": "permit2"
      }
    }
  ]
}
```

### Example unpaid response for a product

`GET /api/products/weather-pro` without payment:

- Status: `402`
- Header: `Payment-Required: <base64-json>`

Decoded `Payment-Required` body shape:

```json
{
  "x402Version": 2,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:42793",
      "amount": "50000000000000000",
      "payTo": "0xStoreWallet",
      "maxTimeoutSeconds": 60,
      "asset": "0xTokenAddressB",
      "extra": {
        "name": "MyToken",
        "version": "1",
        "assetTransferMethod": "permit2"
      }
    }
  ],
  "resource": {
    "description": "Pro weather payload",
    "mimeType": "application/json",
    "url": "https://store.example.com/api/products/weather-pro"
  },
  "error": null
}
```

### Example paid response for a product

`GET /api/products/weather-pro` with valid `Payment-Signature`:

- Status: `200`
- Header: `X-Payment-Response: <base64-json>`

Body example:

```json
{
  "product": "weather-pro",
  "data": {
    "location": "Etherlink",
    "current": "sunny",
    "forecast": ["sunny", "windy", "rain"]
  },
  "payment_settled": true,
  "txHash": "0xabc...",
  "facilitatorUrl": "https://facilitator.example.com"
}
```

## Recommended product API pattern

- `GET /api/catalog`: free listing of products and price terms.
- `GET /api/products/{id}`: paid endpoint; returns `402` then `200` after payment.
- `GET /config`: store-level payment defaults (already implemented in this repo).

## Custom token products (creator-scoped)

This store can create temporary custom paid products from user-specified ERC-20 tokens.

Endpoints:
- `POST /api/catalog/custom-token`: create a custom product for a `creator` wallet from a signed request.
- `GET /api/catalog?creator=0x...`: always returns built-ins; returns active custom products only for that creator.
- `GET /api/custom/{product_id}`: paid endpoint with the same `402`/`Payment-Signature`/settle flow as built-ins.
- `GET /config`: exposes `features.customTokenProducts` and `customProduct` metadata (`ttlSeconds`, tier list).

Tier mapping:
- `tier_0_01` => `0.01 * 10^decimals`
- `tier_0_1` => `0.1 * 10^decimals`
- `tier_1_0` => `1.0 * 10^decimals`

Custom product env defaults:
- `CUSTOM_PRODUCTS_ENABLED=true`
- `CUSTOM_PRODUCT_TTL_SECONDS=86400`
- `CUSTOM_PRODUCT_MAX_PER_CREATOR=5`
- `CUSTOM_PRODUCT_MAX_GLOBAL=500`
- `CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR=30`
- `CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS=300`

Operational notes:
- `RPC_URL` is required when custom products are enabled (token metadata checks).
- Creation signatures are short-lived and nonces are replay-protected.
- Custom products are in-memory and expire automatically (TTL), with expired entries purged from catalog.
- Demo UI must present a final irreversible-payment confirmation before submit.
- Facilitator API is unchanged; this is a store-layer extension only.

## Store implementation checklist

- Match `accepted` exactly with the offered requirement object.
- Validate `token == asset`, `amount == required amount`, `witness.to == payTo`.
- Enforce spender equals configured x402 Permit2 proxy.
- Prefer HTTPS facilitator URLs (server enforces this for public hosts).
