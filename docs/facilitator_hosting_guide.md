# Facilitator Hosting Guide

This guide covers running and operating a facilitator for this Etherlink x402 flow.

## Runtime requirements

- funded facilitator signer private key
- Etherlink RPC endpoint
- facilitator config JSON
- open port (default `9090`)

## Quick start (Docker)

```bash
docker pull ghcr.io/tzapac/tzapac-x402-permit2-facilitator:latest
```

Create `.env`:

```bash
FACILITATOR_PRIVATE_KEY=0xYOUR_FACILITATOR_PRIVATE_KEY
```

Create `bbt_config.json`:

```json
{
  "port": 9090,
  "host": "0.0.0.0",
  "chains": {
    "eip155:42793": {
      "eip1559": true,
      "signers": ["$FACILITATOR_PRIVATE_KEY"],
      "rpc": [
        { "http": "https://node.mainnet.etherlink.com", "rate_limit": 100 }
      ]
    }
  },
  "schemes": [
    { "id": "v2-eip155-exact", "chains": "eip155:42793", "enabled": true }
  ]
}
```

Run:

```bash
docker run --env-file .env -p 9090:9090 \
  -v $(pwd)/bbt_config.json:/app/bbt_config.json \
  ghcr.io/tzapac/tzapac-x402-permit2-facilitator:latest --config /app/bbt_config.json
```

## Required endpoints

Your host must expose:

- `GET /health`
- `GET /supported`
- `POST /settle`

The store in this repo settles through `/settle` and polls `/supported` from UI.

## Proxy alignment requirements

Set these consistently across server + facilitator stack:

- `X402_EXACT_PERMIT2_PROXY_ADDRESS`
- `X402_EXACT_PERMIT2_PROXY_CODEHASH_ALLOWLIST` (recommended)

If these differ, settlement will fail due to spender/proxy checks.

## Operations checklist

- Signer wallet funded for gas.
- RPC endpoint healthy and low latency.
- HTTPS enabled at edge (nginx/caddy/cloudflare).
- Logs retained for `verify`/`settle` traceability.
- Rate limiting in front of facilitator API.

## Smoke tests

```bash
curl -s https://YOUR_FACILITATOR_HOST/health
curl -s https://YOUR_FACILITATOR_HOST/supported | jq
```

Then run local end-to-end:

```bash
python3 playbook_permit2_flow.py
```

## Known network behavior

- `https://node.mainnet.etherlink.com` currently does not support atomic bundling used by sponsored approval extensions.
- This branch therefore uses Permit2 witness settlement flow without those bundling extensions.
