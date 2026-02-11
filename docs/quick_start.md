# Quick Start

Use this guide to run the Beta stack quickly, then follow the deeper guides for your role.

## 1) Prerequisites

- Docker + Docker Compose
- An Etherlink RPC URL
- At least one funded wallet for payment tests

## 2) Configure environment

From repo root:

```bash
cp .env.example .env
```

Set at minimum:

- `RPC_URL` (or `NODE_URL`) to a working Etherlink endpoint
- `CHAIN_ID=42793`
- `SERVER_WALLET` or `STORE_PRIVATE_KEY`
- `X402_EXACT_PERMIT2_PROXY_ADDRESS=0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`
- `PERMIT2_ADDRESS=0x000000000022D473030F116dDEE9F6B43aC78BA3`

## 3) Start the stack

```bash
docker compose -f docker-compose.wallet-poc.yml --env-file .env up -d --build
```

## 4) Open and test

- Frontend: `http://localhost:9091`
- Facilitator health: `http://localhost:9090/health`
- Protected API: `http://localhost:9091/api/weather`

Basic flow:

1. Open the frontend.
2. Click `GET PAYMENT` to fetch requirements.
3. Approve token allowance if needed.
4. Click `SIGN & PAY` to complete settlement.

## 5) Optional end-to-end validation

```bash
RPC_URL=<your_rpc> CHAIN_ID=42793 AUTO_STACK=0 ./.venv/bin/python playbook_permit2_flow.py
```

## Further Reading

- Store Operator Guide: `docs/store_operator_guide.md`
- Server Integration Guide: `docs/server_guide.md`
- Client Integration Guide: `docs/client_guide.md`
- Facilitator API Glossary: `docs/facilitator_api_glossary.md`
- Facilitator Hosting Guide: `docs/facilitator_hosting_guide.md`
- Coinbase Comparison: `docs/coinbase_comparison.md`
- Feature Matrix: `docs/feature_matrix.md`
