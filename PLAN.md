# Custom Token Product Flow (Demo + Store) for Permit2 on Etherlink

## Summary
Add a new demo capability where a user enters an ERC-20 token contract, creates a temporary paid product on the store for that token, approves Permit2 for that token, and pays with that token.  
The flow will be creator-scoped, session-TTL based, wallet-signed for abuse protection, and will show an explicit irreversible-payment warning before submission.

## Goals and Success Criteria
1. User can create a custom paid product from the Demo tab using a token address and preset tier.
2. Store returns that custom product in catalog only for its creator wallet.
3. Demo uses the selected product’s token for Step 4 approval and Step 5 Permit2 signing.
4. Before final submit, user sees a warning that payment is irreversible and tokens are not returned.
5. Existing built-in products (`weather`, `premium-content`) keep working unchanged.

## Scope
1. In scope:
- `bbt_mvp_server.py` store API changes for custom product creation and creator-scoped catalog.
- `wallet_connect_poc.html`, `wallet_connect_poc.js`, `wallet_connect_poc.css` demo updates.
- Docs updates in `README.md`, `docs/client_guide.md`, `docs/store_operator_guide.md`, `docs/facilitator_api_glossary.md`.
2. Out of scope:
- Facilitator protocol changes.
- Refund mechanism.
- Persistent database storage.

## Public Interface Changes

### 1) New endpoint: `POST /api/catalog/custom-token`
Request JSON:
```json
{
  "creator": "0xCreatorAddress",
  "token": "0xTokenAddress",
  "tierId": "tier_0_01",
  "nonce": "uuid-or-random-string",
  "issuedAt": 1739380000,
  "expiresAt": 1739380300,
  "chainId": 42793,
  "signature": "0x..."
}
```

Validation rules:
- `creator` and `token` must be checksum-valid EVM addresses.
- `tierId` must be one of: `tier_0_01`, `tier_0_1`, `tier_1_0`.
- `chainId` must equal `42793`.
- `issuedAt` and `expiresAt` must be sane; max signature window 5 minutes.
- Signature must recover `creator` from canonical message format.
- `nonce` must be unused for creator (replay protection).
- Token contract must exist (non-empty code) and expose `decimals()`; `symbol()` optional fallback.
- Rate/abuse limits must pass.

Response JSON:
```json
{
  "success": true,
  "product": {
    "id": "custom_...",
    "name": "Custom Token Access",
    "path": "/api/custom/custom_...",
    "url": "https://.../api/custom/custom_...",
    "description": "Custom token-gated content",
    "payment": {
      "x402Version": 2,
      "scheme": "exact",
      "network": "eip155:42793",
      "amount": "10000000000000000",
      "payTo": "0xStoreWallet",
      "asset": "0xTokenAddress",
      "maxTimeoutSeconds": 60,
      "extra": {
        "name": "TOKEN_SYMBOL",
        "version": "1",
        "assetTransferMethod": "permit2",
        "decimals": 18
      }
    },
    "expiresAt": 1739466400
  }
}
```

### 2) Updated endpoint: `GET /api/catalog`
New optional query param:
- `creator=0xCreatorAddress`

Behavior:
- Always returns built-in products.
- Returns custom products only when `creator` is present and matches stored creator.
- Expired custom products are excluded and purged.

### 3) New paid endpoint shape: `GET /api/custom/{product_id}`
Behavior:
- Same 402/Payment-Required and payment validation flow as existing products.
- Same Permit2 exact-settlement constraints.
- Returns paid JSON payload on success with settlement metadata.

### 4) Updated endpoint: `GET /config`
Add feature metadata for UI:
```json
{
  "features": {
    "customTokenProducts": true
  },
  "customProduct": {
    "ttlSeconds": 86400,
    "tiers": [
      {"id":"tier_0_01","label":"0.01"},
      {"id":"tier_0_1","label":"0.1"},
      {"id":"tier_1_0","label":"1.0"}
    ]
  }
}
```

## Implementation Design

## A) Store API (`bbt_mvp_server.py`)
1. Add in-memory registries:
- `CUSTOM_PRODUCTS_BY_ID`
- `CUSTOM_PRODUCTS_BY_CREATOR`
- `USED_CREATE_NONCES`
- `CREATE_RATE_LIMIT_BY_IP`

2. Add cleanup routine called on create/catalog/custom-access:
- Purge expired products and stale nonce/rate-limit entries.

3. Add custom product constructor:
- Resolve token metadata from RPC (`decimals`, optional `symbol`).
- Compute on-chain amount by tier:
  - `tier_0_01` => `0.01 * 10^decimals`
  - `tier_0_1` => `0.1 * 10^decimals`
  - `tier_1_0` => `1.0 * 10^decimals`
- Build requirements via existing exact Permit2 structure.
- Build dynamic `path` and response payload.

4. Signature verification protocol:
- Use EIP-191 message (`encode_defunct`) with exact template:
```text
TZ APAC x402 Custom Product Creation
chainId:{chainId}
creator:{creator}
token:{token}
tierId:{tierId}
nonce:{nonce}
issuedAt:{issuedAt}
expiresAt:{expiresAt}
```
- Recover signer and compare to `creator` (case-insensitive checksum normalized).

5. Abuse guards:
- Max active custom products per creator: `5`.
- Max create requests per IP per hour: `30`.
- Max active custom products global: `500`.
- Reject when over limits with `429` or `400` as appropriate.

6. Ensure existing `_handle_paid_product` remains reused:
- Custom product object must match existing `product` schema (`requirements`, `response`, `path`, `description`).

## B) Demo UI (`wallet_connect_poc.html` + JS/CSS)
1. Add Step 3 “Custom Token Product” controls:
- Token address input.
- Tier select (`0.01`, `0.1`, `1.0`).
- `CREATE PRODUCT` button.
- Status/output area.

2. Create flow:
- Require wallet connected.
- Build create payload with fresh nonce + timestamps.
- Sign canonical message via `signer.signMessage`.
- `POST /api/catalog/custom-token`.
- On success:
  - Refresh catalog using `GET /api/catalog?creator=<wallet>`.
  - Auto-select created product URL in store input.
  - Clear payment cache and instruct user to run `GET PAYMENT`.

3. Catalog flow update:
- `refreshCatalog()` appends `creator` query only when wallet connected.
- Continue graceful fallback when catalog unavailable.

4. Dynamic token handling for Step 4 and Step 5:
- Replace hardwired BBT contract usage with “active payment token” from cached requirement.
- Instantiate ERC-20 contract against active `accept.asset`.
- Show token address and symbol dynamically in token details.
- Keep Permit2 allowance check using active token.
- Approval tx remains exact amount to canonical Permit2.

5. Irreversible warning (mandatory before submission):
- In `signAndPay()`, right before signing, show blocking confirmation:
  - “This payment is irreversible. You will not get these tokens back.”
  - Include formatted amount/symbol/token address.
- On cancel, abort submission cleanly without state corruption.

## C) Config and Env Additions
Add store env vars with defaults:
- `CUSTOM_PRODUCTS_ENABLED=true`
- `CUSTOM_PRODUCT_TTL_SECONDS=86400`
- `CUSTOM_PRODUCT_MAX_PER_CREATOR=5`
- `CUSTOM_PRODUCT_MAX_GLOBAL=500`
- `CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR=30`
- `CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS=300`
- `RPC_URL` required for token metadata validation if custom products enabled.

## D) Documentation Updates
1. `README.md`
- Add “Custom Token Product Demo” section and irreversible payment warning.
2. `docs/client_guide.md`
- Add create-product signing flow and creator-scoped catalog behavior.
3. `docs/store_operator_guide.md`
- Document new endpoints, tier mapping, TTL/rate limits.
4. `docs/facilitator_api_glossary.md`
- Clarify no facilitator API change is required; store-level extension only.

## Test Cases and Scenarios

1. Happy path custom token:
- Create with valid token + valid signature.
- Catalog includes custom product for creator.
- `GET PAYMENT` returns custom token asset and tier amount.
- Approve + sign/pay succeeds and returns `200`.

2. Creator-only visibility:
- Wallet A creates product.
- Wallet B catalog request must not include A’s custom product.

3. TTL expiry:
- After TTL, product removed from catalog.
- `GET /api/custom/{id}` returns `404`.

4. Replay and signature integrity:
- Reuse same nonce => rejected.
- Tamper token/tier after signing => rejected.
- Wrong signer for creator => rejected.

5. Abuse/rate limits:
- Exceed per-IP create rate => `429`.
- Exceed per-creator active cap => rejection.

6. Token validation:
- Non-contract address => rejected.
- Token missing/invalid `decimals` => rejected.

7. Existing flow regression:
- Built-in weather/premium products continue to return valid 402 and settle successfully.

8. UX warning:
- Sign & Pay always prompts irreversible warning for custom product.
- Cancel keeps user in step 5 without sending payment request.

## Rollout Plan
1. Implement backend feature guarded by `CUSTOM_PRODUCTS_ENABLED`.
2. Implement frontend controls and dynamic token handling.
3. Update docs and env examples.
4. Run playbook/manual browser flow for built-in and custom-token scenarios.
5. Deploy and monitor create endpoint errors/rate-limit metrics.

## Assumptions and Defaults Chosen
1. Chain remains Etherlink mainnet (`42793`) only.
2. Asset transfer method remains Permit2 only.
3. Custom product storage is in-memory only (no persistence across restart).
4. Pricing tiers are fixed at `0.01`, `0.1`, `1.0`.
5. Creator-scoped visibility is enforced via `creator` query parameter.
6. Irreversible warning is mandatory at each submit attempt.
