# Server Integration Guide

This guide documents how the store API server in this repo performs x402 gating and settlement.

## Reference implementation

- Server: bbt_mvp_server.py
- Protected endpoint: GET /api/weather
- Config endpoint: GET /config

## What the server enforces

The server validates before calling facilitator:

- payment payload is valid base64 JSON
- accepted exists and matches settlement-critical offered requirements
- permit2Authorization exists
- witness.to == payTo
- spender == X402_EXACT_PERMIT2_PROXY_ADDRESS
- permitted.token == asset
- permitted.amount == required amount

Then it calls facilitator:

- POST {facilitator}/settle with x402 v2 settle request

## Environment variables

Core:

- FACILITATOR_URL
- SERVER_WALLET (or STORE_ADDRESS / STORE_PRIVATE_KEY fallback)
- BBT_TOKEN
- X402_EXACT_PERMIT2_PROXY_ADDRESS
- PUBLIC_BASE_URL
- EXPLORER_TX_BASE_URL (optional override for tx links in responses)

Safety/limits:

- MAX_PAYMENT_SIGNATURE_B64_BYTES
- MAX_SETTLE_RESPONSE_BYTES
- MAX_FACILITATOR_URL_BYTES
- COMPLIANCE_SCREENING_ENABLED (default: true)
- COMPLIANCE_PROVIDER (chainalysis by default)
- COMPLIANCE_DENY_LIST (comma-separated addresses)
- COMPLIANCE_ALLOW_LIST (comma-separated addresses)
- CHAINALYSIS_REST_URL
- CHAINALYSIS_API_KEY
- COMPLIANCE_TIMEOUT_MS
- COMPLIANCE_BLOCKED_STATUS
- COMPLIANCE_FAIL_CLOSED

## Facilitator URL override

For per-request settlement routing:

- client can send X-Facilitator-Url
- server normalizes/validates it
- server returns the chosen URL in response as facilitatorUrl

Validation rules:

- only http or https
- no query/fragment
- public hosts must use https

## HTTP contract

### Unpaid request

- status: 402
- headers:
  - Payment-Required (base64 JSON)
  - X-Facilitator-Url (effective URL used)

### Paid request

- status: 200
- header: X-Payment-Response
- body includes payment_settled, txHash, facilitatorUrl, explorer

## Running locally

```bash
uvicorn bbt_mvp_server:app --host 0.0.0.0 --port 8001
```

or via compose:

```bash
docker compose -f docker-compose.wallet-poc.yml up -d --build
```

## Extending to multiple products

Current server has one paid route with one static requirement object. To add product-specific pricing:

- map product id -> payment requirement object
- generate Payment-Required dynamically by route/product
- keep the same settlement validation rules per requirement
