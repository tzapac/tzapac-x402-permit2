# Client Integration Guide

This guide covers browser and script clients for the Coinbase-aligned Permit2 flow.

## Client options in this repo

- Browser demo: `wallet_connect_poc.html`
- Script client: `bbt_mvp_client.py`
- End-to-end validator: `playbook_permit2_flow.py`

## Environment (script client)

Set at minimum:

- `PRIVATE_KEY`
- `RPC_URL` (legacy alias: `NODE_URL`)
- `CHAIN_ID` (42793 for Etherlink)
- `SERVER_URL`
- `PERMIT2_ADDRESS`
- `X402_EXACT_PERMIT2_PROXY_ADDRESS`

## Flow summary

1. Client requests paid API without payment header.
2. Server returns `402` + `Payment-Required`.
3. Client decodes requirements and chooses `accepts[0]`.
4. Client builds Permit2 witness payload and signs it.
5. Client sends same API request with `Payment-Signature`.
6. Server settles via facilitator and returns `200` + `X-Payment-Response`.

## Browser flow notes

- `CHECK /HEALTH`: verifies facilitator is online.
- `GET PAYMENT`: fetches and caches requirements.
- `APPROVE PERMIT2`: ERC-20 approve to canonical Permit2.
- `SIGN & PAY`: submits signed payload.

No wallet connected:

- approve button is shown, but wallet actions still require connection when clicked.

## Custom token product flow (browser demo)

1. Connect wallet, choose token + tier, and call `POST /api/catalog/custom-token`.
2. Creation request is wallet-signed and includes: `creator`, `token`, `tierId`, `nonce`, `issuedAt`, `expiresAt`, `chainId`, `signature`.
3. Refresh catalog with `GET /api/catalog?creator=<wallet>`.
4. Built-in products remain visible to everyone; custom products are visible only to the matching creator.
5. Select the custom product URL, then run `GET PAYMENT`, `APPROVE PERMIT2`, and `SIGN & PAY`.
6. Right before payment submission, the UI shows a blocking confirmation: `This payment is irreversible. You will not get these tokens back.`

`GET /config` exposes `features.customTokenProducts` and `customProduct` tier/TTL metadata used by the demo controls.

## Facilitator routing behavior

- Demo UI sends `X-Facilitator-Url` header.
- Server validates and uses that URL for `/settle`.
- This allows the same store to settle through different facilitator hosts.

## Script example

```bash
python3 bbt_mvp_client.py
```

Expected behavior:

- first call returns `402`
- second call returns `200`
- output includes settlement tx hash

## Troubleshooting

- `No code deployed at PERMIT2_ADDRESS`: wrong chain or address.
- `Unsupported assetTransferMethod`: server requirement is not Permit2.
- `Permit2 ERC20 allowance is insufficient`: run approve first.
- `Recipient mismatch` / `Payment amount mismatch`: payload fields diverge from accepted requirements.
- `RPC_URL and NODE_URL are both set but differ`: set only `RPC_URL` or make both identical.
