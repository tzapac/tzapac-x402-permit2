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
