# BBT x402 Facilitator with Permit2 Support

## Project Overview

Proof of concept for x402 payment protocol on Etherlink Mainnet with Permit2 universal token support.

**Goal:** Create a facilitator that accepts Permit2 signatures, enabling ANY ERC-20 token (including BBT and vanilla USDC) to be used for x402 payments.

---

## Architecture

```
┌─────────────────────┐         ┌──────────────────┐         ┌─────────────────────┐
│  bbt_mvp_client.py  │         │ bbt_mvp_server   │         │ bbt_x402_facilitator│
│  (Permit2 signer)   │────────▶│  (port 8001)     │────────▶│  (port 9090)        │
└─────────────────────┘         └──────────────────┘         └─────────────────────┘
                                                                   │
                                                                   │ Calls
                                                                   ▼
                                                         ┌──────────────────┐
                                                         │  Permit2 Contract│
                                                         │  (on Etherlink)  │
                                                         └──────────────────┘
                                                                   │
                                                                   │ Transfers
                                                                   ▼
                                                         ┌──────────────────┐
                                                         │   Token Contract │
                                                         │   (BBT/USDC/etc) │
                                                         └──────────────────┘
```

---

## Key Constants

### Network Configuration
| Parameter | Value |
|-----------|-------|
| Network | Etherlink Mainnet |
| Chain ID | `42793` |
| CAIP-2 | `eip155:42793` |
| RPC URL | `https://rpc.bubbletez.com` |

### Contract Addresses
| Contract | Address | Notes |
|----------|---------|-------|
| **Permit2** | `0x000000000022D473030F116dDEE9F6B43aC78BA3` | Canonical CREATE2 address, works on all chains |
| **BBT Token** | `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6` | EIP-2612 Permit support only |
| **Etherlink USDC** | `0x796Ea11Fa2dD751eD01b53C372fFDB4AAa8f00F9` | Vanilla ERC-20, NO native permit |

### Wallets
| Wallet | Address | Purpose |
|--------|---------|---------|
| Server Wallet | `0x81C54CB7690016b2b0c3017a4991783964601bd9` | Receives payments |
| Client Wallet | `0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F` | Signs payments |

### Ports
| Service | Port | Notes |
|---------|------|-------|
| bbt_mvp_server.py | `8001` | FastAPI server |
| bbt_x402_facilitator | `9090` | Rust facilitator (Permit2-enabled) |
| Original facilitator | `8080` | x402-rs EIP-3009 only (ub1:100.112.150.8) |

---

## File Locations

### Local (~/Documents/x402_poc/)
| File | Purpose |
|------|---------|
| `bbt_probe.md` | This file - planning and tracking |
| `mvp_server.py` | Original server (EIP-3009, port 8000) |
| `mvp_client.py` | Original client (EIP-2612 signatures) |
| `bbt_mvp_server.py` | **NEW** Server for Permit2 (port 8001) |
| `bbt_mvp_client.py` | **NEW** Client with Permit2 signatures |
| `bbt-x402-facilitator/` | **NEW** Rust facilitator fork |
| `AGENTS.md` | Project documentation |
| `PROOF_OF_CONCEPT.md` | POC results (EIP-3009 blocked) |

### Remote (ub1 - 100.112.150.8)
| Path | Purpose |
|------|---------|
| `~/x402_rs/x402-rs/` | Original x402-rs facilitator source |
| `~/x402_rs/x402-rs/src/main.rs` | Routes |
| `~/x402_rs/x402-rs/src/network.rs` | Network config |
| `~/x402_rs/x402-rs/src/facilitator_local.rs` | EIP-3009 signature verification |
| `~/x402_rs/x402-rs/src/types.rs` | Payload structures |
| `~/x402_rs/x402-rs/src/handlers.rs` | /settle and /verify endpoints |
| `~/x402_rs/x402-rs/Cargo.toml` | Dependencies (alloy 1.0.7) |
| Docker: `x402-facilitator-etherlink` | Original container (port 8080) |

---

## Research Findings

### x402-rs EIP-3009 Implementation

**Key Files & Functions:**
- `src/facilitator_local.rs` - `assert_signature()` verifies EIP-3009 signatures
  ```rust
  fn assert_signature(payload: &ExactEvmPayload, domain: &Eip712Domain) -> Result<(), PaymentError>
  ```
- `src/types.rs` - `TransferWithAuthorization` struct definition:
  ```rust
  struct TransferWithAuthorization {
      address from;
      address to;
      uint256 value;
      uint256 validAfter;
      uint256 validBefore;
      bytes32 nonce;
  }
  ```
- `src/handlers.rs` - `post_settle()` endpoint handler
- `src/network.rs` - Network enum with Etherlink (chain_id: 42793)
- `src/provider_cache.rs` - RPC provider caching

**Dependencies:**
```toml
alloy = { version = "1.0.7" }  # Uses alloy-rs, NOT ethers-rs
axum = { version = "0.8.4" }
tokio = { version = "1.45.0" }
```

**Signature Verification Flow:**
1. Construct EIP-712 domain: `eip712_domain! { name, version, chain_id, verifying_contract: asset_address }`
2. Reconstruct `TransferWithAuthorization` struct from payload
3. Compute `eip712_signing_hash()`
4. Recover address from signature
5. Compare with expected `from` address

---

### Permit2 EIP-712 Types (from Official Uniswap Repo)

**Domain Separator:**
```javascript
{
  "name": "Permit2",
  "version": "1",
  "chainId": 42793,
  "verifyingContract": "0x000000000022D473030F116dDEE9F6B43aC78BA3"
}
```

**Typed Data Types:**
```javascript
{
  "PermitDetails": [
    {"name": "token", "type": "address"},
    {"name": "amount", "type": "uint160"},      // NOTE: uint160, NOT uint256
    {"name": "expiration", "type": "uint48"},   // NOTE: uint48, NOT uint256
    {"name": "nonce", "type": "uint48"}
  ],
  "PermitSingle": [
    {"name": "details", "type": "PermitDetails"},
    {"name": "spender", "type": "address"},
    {"name": "sigDeadline", "type": "uint256"}
  ]
}
```

**Message Structure:**
```javascript
{
  "details": {
    "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
    "amount": 1000000,
    "expiration": 1738464922,      // 48-bit timestamp
    "nonce": 0
  },
  "spender": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
  "sigDeadline": 1738461322        // Controls signature validity window
}
```

---

### Python Permit2 Signature Example (for bbt_mvp_client.py)

```python
from eth_account import Account
import time

# Configuration
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
CHAIN_ID = 42793
TOKEN_ADDRESS = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
SPENDER_ADDRESS = "0x81C54CB7690016b2b0c3017a4991783964601bd9"

# Domain separator
domain_data = {
    "name": "Permit2",
    "version": "1",
    "chainId": CHAIN_ID,
    "verifyingContract": PERMIT2_ADDRESS,
}

# EIP-712 type definitions
msg_types = {
    "PermitDetails": [
        {"name": "token", "type": "address"},
        {"name": "amount", "type": "uint160"},
        {"name": "expiration", "type": "uint48"},
        {"name": "nonce", "type": "uint48"},
    ],
    "PermitSingle": [
        {"name": "details", "type": "PermitDetails"},
        {"name": "spender", "type": "address"},
        {"name": "sigDeadline", "type": "uint256"},
    ],
}

# Message values
current_time = int(time.time())
sig_deadline = current_time + 3600  # 1 hour
expiration = current_time + 86400    # 24 hours
nonce = 0  # Get from Permit2.allowance()

msg_data = {
    "details": {
        "token": TOKEN_ADDRESS,
        "amount": 1000000,
        "expiration": expiration,
        "nonce": nonce,
    },
    "spender": SPENDER_ADDRESS,
    "sigDeadline": sig_deadline,
}

# Sign
signed_msg = Account.sign_typed_data(PRIVATE_KEY, domain_data, msg_types, msg_data)
signature = signed_msg.signature.hex()  # 0x-prefixed 130 chars
```

---

### Getting Permit2 Nonce (Required Before Signing)

```python
from web3 import Web3

# Minimal ABI for allowance function
permit2_abi = [
    {
        "inputs": [
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"},
            {"internalType": "address", "name": "", "type": "address"}
        ],
        "name": "allowance",
        "outputs": [
            {"internalType": "uint160", "name": "amount", "type": "uint160"},
            {"internalType": "uint48", "name": "expiration", "type": "uint48"},
            {"internalType": "uint48", "name": "nonce", "type": "uint48"}
        ],
        "stateMutability": "view",
        "type": "function"
    }
]

permit2 = w3.eth.contract(address=PERMIT2_ADDRESS, abi=permit2_abi)
amount, expiration, nonce = permit2.functions.allowance(
    OWNER_ADDRESS,
    TOKEN_ADDRESS,
    SPENDER_ADDRESS
).call()
```

---

## Implementation Plan

### Phase 1: Fork & Setup
- [ ] **1. Clone x402-rs as bbt-x402-facilitator** to `~/Documents/x402_poc/bbt-x402-facilitator`
- [ ] **2. Review x402-rs facilitator code** to understand EIP-3009 implementation (`src/facilitator.rs`, `main.rs`, `network.rs`)

### Phase 2: Add Permit2 Support to Facilitator
- [ ] **3. Add Permit2 constants and config**
  - `PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"`
  - Permit2 EIP-712 domain
  - `PermitSingle` and `PermitDetails` structs
  - Auto-detection: try Permit2 first, fall back to EIP-3009

- [ ] **4. Implement Permit2 signature verification**
  - Add EIP-712 types for `PermitDetails` and `PermitSingle`
  - Verify signatures against Permit2 contract address
  - Use `Signature::recover_address_from_prehash()` (same as EIP-3009)

- [ ] **5. Implement Permit2 transfer execution**
  - Add Permit2 contract ABI (`abi/Permit2.json` from official repo)
  - Call `permit2.permit()` for non-native tokens
  - Call `permit2.transferFrom()` to execute transfer
  - Handle gas estimation and transaction submission
  - Follow existing EIP-1559 gas handling pattern

- [ ] **6. Dual signature mode support**
  - Support EIP-3009 (existing) AND Permit2 (new)
  - Allow client to specify signature type in payload field
  - Or auto-detect based on payload structure

- [ ] **7. Update port configuration**
  - Change default port from `8080` to `9090`
  - Update all hardcoded references
  - Ensure clean separation from existing facilitator

- [ ] **8. Build and test Rust facilitator**
  - `cargo build --release`
  - Test locally with `cargo run`
  - Verify Docker build works

### Phase 3: Server (bbt_mvp_server.py)
- [ ] **9. Create bbt_mvp_server.py**
  - Fork from `mvp_server.py`
  - Update `FACILITATOR_URL` to `http://localhost:9090`
  - Change port to `8001`
  - Keep same HTTP 402 flow

- [ ] **10. Test server integration**
  - Start `bbt_mvp_server.py` locally
  - Verify it accepts requests correctly
  - Verify it forwards to new facilitator

### Phase 4: Client with Permit2 (bbt_mvp_client.py)
- [ ] **11. Create bbt_mvp_client.py with Permit2 signatures**
  - Fork from `mvp_client.py`
  - Replace EIP-2612 `Permit` signature generation with Permit2 `PermitSingle`
  - Update EIP-712 domain and types
  - Add nonce fetching from Permit2 contract

- [ ] **12. Test Permit2 signature generation**
  - Generate test signature for BBT token
  - Verify signature locally using web3.py
  - Confirm it matches expected Permit2 format

### Phase 5: Deploy & Full Integration Test
- [ ] **13. Deploy btt-facilitator to ub1**
  - Copy Docker image to ub1 or build on ub1
  - Run on port 9090: `docker run -d --name btt-x402-facilitator -p 9090:9090 bbt-x402-facilitator`
  - Configure environment (RPC, permits support)

- [ ] **14. Full end-to-end test with BBT**
  - Start `bbt_mvp_server.py` locally (port 8001)
  - Run `bbt_mvp_client.py`
  - Verify full flow: `402 → payment → facilitator → Permit2 → on-chain settlement`
  - Verify transaction hash returned

---

## Working Notes

### Permit2 Flow

1. **Client signs Permit2 authorization** - Signs `PermitSingle` message with:
   - Token address (BBT)
   - Amount (uint160 precision)
   - Expiration (uint48 timestamp)
   - Nonce (uint48 from Permit2.allowance())
   - Spender (facilitator wallet)
   - sigDeadline (signature validity window)

2. **Client sends payment request** - POST to server with:
   - `X-Payment` header containing signed Permit2 message
   - Standard x402 payment requirements

3. **Server forwards to facilitator** - Calls `/settle` endpoint with:
   - Permit2 signature
   - Token amount
   - Sender/recipient addresses

4. **Facilitator executes**:
   - Verifies signature against Permit2 domain
   - Calls `Permit2.permit()` to get approval (for tokens without native permit)
   - Calls `Permit2.transferFrom()` to move tokens
   - Returns transaction hash

5. **Server responds** - Returns transaction hash to client as proof of payment

---

## Deployment & Exposure

### Cloudflare Tunnel Setup (When Ready)
```bash
# On local machine or server
cloudflared tunnel --url http://localhost:9090
```

This will expose `bbt_x402_facilitator` publicly via Cloudflare tunnel.

---

## Progress Tracking

**Last Updated:** 2026-02-02 13:45

**Current Phase:** Phase 1 - Fork & Setup

**Research completed:**
- ✅ x402-rs EIP-3009 implementation analyzed
- ✅ Permit2 EIP-712 types obtained
- ✅ Python Permit2 signature examples collected
- ⏳ Waiting for: Permit2 Rust implementations, EIP-3009 vs Permit2 dual-mode patterns

**Status:** Plan created, research in progress, ready to start Phase 1

---

## Questions & Notes

- **Permit2 types**: Use `uint160` for amounts and `uint48` for expiration/nonce (NOT `uint256`)
- **Nonce handling**: Must fetch current nonce from `Permit2.allowance(owner, token, spender)` before signing
- **Gas efficiency**: Permit2 permit() is only needed for tokens WITHOUT native permit (like most ERC-20s)
- **BBT token**: Has EIP-2612, so Permit2 may use native permit internally (more efficient)

---

## References

- **Permit2 GitHub:** https://github.com/Uniswap/permit2
- **Permit2 Docs:** https://docs.uniswap.org/contracts/permit2/overview
- **Permit2 on Etherlink:** `0x000000000022D473030F116dDEE9F6B43aC78BA3`
- **x402-rs:** https://github.com/x402-rs/x402-rs
- **Proof of Concept:** `PROOF_OF_CONCEPT.md`