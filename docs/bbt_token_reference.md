# BBT Token Reference (Example Asset)

This project uses a sample BBT token deployment as the payment asset for the Beta flow.

## Overview

- Purpose: example ERC-20 token used by this repository's x402 payment flow
- Network: Etherlink Mainnet (`eip155:42793`)
- Contract: `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`

## On-Chain Token Details

As checked on February 11, 2026:

| Field | Value |
|---|---|
| Name | `bbtez` |
| Symbol | `BBT` |
| Decimals | `18` |
| Total Supply | `1000000000000000000000` (1000 BBT) |
| Contract Code Present | `true` |

## Permit / Signature Capabilities

- ERC-2612 indicators: present
  - `DOMAIN_SEPARATOR()` returns a valid 32-byte hash
  - `nonces(address)` returns a valid nonce value
  - `permit(...)` selector responds (invalid-input probe reverts, which is expected for bad signatures)
- This Beta integration still uses Permit2 witness flow as the default payment path.

## How This Repo Uses BBT

- Server default token is set in `bbt_mvp_server.py` via `BBT_TOKEN`.
- `Payment-Required.accepts[].asset` is this token address.
- Frontend and playbook requests are priced in BBT units (18 decimals).

## Explorer

- [Etherlink Blockscout token address](https://explorer.etherlink.com/address/0x7EfE4bdd11237610bcFca478937658bE39F8dfd6)
