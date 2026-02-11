# Facilitator API Glossary

This glossary documents the x402 fields and endpoints your facilitator integration expects.

## HTTP endpoints

- `GET /health`: liveness check.
- `GET /supported`: capabilities (versions/schemes/networks/signers).
- `POST /settle`: settle a payment on-chain.
- `POST /verify`: optional pre-check endpoint (supported by facilitator, not required by this PoC server flow).

## Request/response headers in this PoC

- `Payment-Required`: base64-encoded x402 v2 requirements (from server on `402`).
- `Payment-Signature`: base64-encoded x402 v2 payment payload (from client on retry).
- `X-Payment-Response`: base64-encoded settlement metadata (from server on success).
- `X-Facilitator-Url`: optional server override for facilitator target.

## `Payment-Required` (x402 v2) terms

- `x402Version`: protocol version (`2`).
- `accepts[]`: offered payment requirement objects.
- `resource`: resource metadata (`url`, `description`, `mimeType`).
- `error`: optional error string.

Each requirement object includes:

- `scheme`: payment scheme (`exact`).
- `network`: CAIP-2 chain id (`eip155:42793`).
- `amount`: exact required token amount.
- `payTo`: recipient wallet.
- `asset`: token contract address.
- `maxTimeoutSeconds`: validity window.
- `extra.assetTransferMethod`: transfer path (`permit2` in this branch).

## `Payment-Signature` payload shape used here

Top-level payload:

- `x402Version`
- `accepted` (must exactly match one offered requirement)
- `resource`
- `payload`

`payload` for Permit2 witness flow:

- `signature`: EIP-712 signature bytes.
- `permit2Authorization.from`: payer wallet.
- `permit2Authorization.permitted.token`: ERC-20 token address.
- `permit2Authorization.permitted.amount`: authorized token amount.
- `permit2Authorization.spender`: must be x402 Permit2 proxy address.
- `permit2Authorization.nonce`: Permit2 nonce.
- `permit2Authorization.deadline`: Permit2 deadline.
- `permit2Authorization.witness.to`: recipient; must equal `payTo`.
- `permit2Authorization.witness.validAfter`: lower-bound timestamp.
- `permit2Authorization.witness.extra`: bytes field for witness context.

## `POST /settle` body (server -> facilitator)

```json
{
  "x402Version": 2,
  "paymentPayload": { "...": "client payload" },
  "paymentRequirements": { "...": "accepted requirements" }
}
```

## Facilitator-side validation concepts

- `AcceptedRequirementsMismatch`: client accepted terms do not match offered terms.
- `ChainIdMismatch`: requirement/payload chain mismatch.
- `AssetMismatch`: payload token differs from required asset.
- `RecipientMismatch`: recipient differs from `payTo`.
- `InvalidPaymentAmount`: payload amount differs from required amount.
- Permit2 checks:
  - spender must be x402 proxy
  - owner balance and ERC-20 allowance to canonical Permit2 must be sufficient
  - signature domain/time checks must pass

## `POST /settle` success output (typical)

Facilitator may return either:

- `{"txHash": "0x..."}`
- or `{"transaction": {"hash": "0x..."}, ...}`

The PoC server extracts either form and returns it to the client.

## Common integration errors

- `402 Accepted requirements do not match offered requirements`
- `402 Invalid spender for witness flow`
- `402 Payment amount mismatch`
- `402 Payment asset mismatch`
- `400 Invalid payment header`
- `500 Facilitator error`
