# x402 Payment Protocol - Etherlink BBT Token Proof of Concept

**Date:** 2026-02-02  
**Network:** Etherlink Mainnet (Chain ID: 42793)  
**Token:** BBT (bbtez) - `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`

---

## Executive Summary

| Component | Status | Notes |
|-----------|--------|-------|
| HTTP 402 Challenge | **VERIFIED** | Server returns proper `X-PAYMENT-REQUIRED` header |
| EIP-712 Permit Signing | **VERIFIED** | Client creates valid BBT permit signature |
| Payment Header Exchange | **VERIFIED** | `X-PAYMENT` header accepted by server |
| Server → Facilitator `/settle` | **VERIFIED** | Server forwards payment to facilitator |
| Facilitator Signature Validation | **BLOCKED** | Signature format mismatch (see below) |
| On-Chain Settlement | **BLOCKED** | Cannot proceed due to signature issue |

**Conclusion:** The x402 HTTP protocol flow works on Etherlink. On-chain settlement is BLOCKED due to EIP-712 signature format mismatch between client (EIP-2612 Permit) and facilitator (EIP-3009 TransferWithAuthorization).

---

## Component Receipts

### 1. Facilitator (ub1: 100.112.150.8:8080)

**Endpoint:** `/api/supported`  
**Response:**
```json
{
  "kinds": [
    {
      "network": "eip155:42793",
      "scheme": "exact",
      "x402Version": 1
    }
  ]
}
```

**Container:** `x402-facilitator-etherlink`  
**Image:** `ukstv/x402-facilitator:etherlink`  
**Status:** Running

---

### 2. MVP Server (localhost:8000)

**File:** `mvp_server.py`

**Request 1 - No Payment:**
```
GET /api/weather HTTP/1.1
Host: localhost:8000
```

**Response 1 - 402 Payment Required:**
```
HTTP/1.1 402 Payment Required
X-PAYMENT-REQUIRED: eyJ4NDAyVmVyc2lvbiI6IDEsICJhY2NlcHRzIjogW3...
Content-Type: application/json

{"error": "Payment Required", "message": "Send X-PAYMENT header"}
```

**Decoded X-PAYMENT-REQUIRED:**
```json
{
  "x402Version": 1,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:42793",
      "maxAmountRequired": "10000000000000000",
      "resource": "http://localhost:8000/api/weather",
      "description": "Weather data access",
      "mimeType": "application/json",
      "payTo": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
      "maxTimeoutSeconds": 60,
      "asset": "eip155:42793/erc20:0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
      "extra": {
        "name": "BBT",
        "version": "1"
      }
    }
  ],
  "error": null
}
```

---

### 3. MVP Client Payment

**File:** `mvp_client.py`

**Client Wallet:** `0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F`

**EIP-712 Permit Parameters:**
| Field | Value |
|-------|-------|
| Token | `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6` (BBT) |
| Owner | `0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F` |
| Spender | `0x81C54CB7690016b2b0c3017a4991783964601bd9` |
| Value | `10000000000000000` (0.01 BBT) |
| Deadline | `1770018036` (Unix timestamp) |
| Nonce | `0` |
| Chain ID | `42793` |

**Generated Signature:**
```
c0aaa2cfdf2d10652a33d3fbfc5ce5b4d2210e76a4ca99f0f07ecfd7bca22ace2b6382c7b6973fc6dfa34e9906ddae949b703d12f2dd6998200c81240e14dff21b
```

**X-PAYMENT Header Payload:**
```json
{
  "x402Version": 1,
  "scheme": "exact",
  "network": "eip155:42793",
  "payload": {
    "signature": "c0aaa2cfdf2d10652a33d3fbfc5ce5b4d2210e76a4ca99f0f07ecfd7bca22ace2b6382c7b6973fc6dfa34e9906ddae949b703d12f2dd6998200c81240e14dff21b",
    "authorization": {
      "from": "0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F",
      "to": "0x81C54CB7690016b2b0c3017a4991783964601bd9",
      "value": "10000000000000000",
      "validAfter": "0",
      "validBefore": "1770018036",
      "nonce": "0"
    }
  }
}
```

---

### 4. Paid Request & Response

**Request 2 - With Payment:**
```
GET /api/weather HTTP/1.1
Host: localhost:8000
X-PAYMENT: eyJ4NDAyVmVyc2lvbiI6IDEsICJzY2hlbWUiOiAiZXhhY3Qi...
```

**Response 2 - 200 OK:**
```
HTTP/1.1 200 OK
Content-Type: application/json

{
  "weather": "sunny",
  "temperature": 25,
  "location": "Etherlink",
  "payment_received": true,
  "payment_scheme": "exact"
}
```

---

## On-Chain Settlement Attempt

### What We Implemented
The MVP server now calls the facilitator `/settle` endpoint with the payment signature.

### Facilitator Response
```
Settlement failed
error: Invalid signature: Address mismatch
  recovered: 0xBB29d3eAaF085D8D70904D9D91Ae56b66eA4EA7c
  expected:  0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F
```

### Root Cause: EIP-712 Type Mismatch

The x402-rs facilitator expects **EIP-3009 TransferWithAuthorization** signatures:
```solidity
TransferWithAuthorization(
  address from,
  address to,
  uint256 value,
  uint256 validAfter,
  uint256 validBefore,
  bytes32 nonce
)
```

But BBT token on Etherlink only supports **EIP-2612 Permit**:
```solidity
Permit(
  address owner,
  address spender,
  uint256 value,
  uint256 nonce,
  uint256 deadline
)
```

These have different EIP-712 typed data structures, so the signature that validates against Permit will NOT validate against TransferWithAuthorization.

### Solutions to Unblock

| Option | Effort | Description |
|--------|--------|-------------|
| **A. Deploy EIP-3009 token** | Medium | Deploy a token with `transferWithAuthorization` on Etherlink |
| **B. Modify x402-rs facilitator** | High | Add EIP-2612 Permit support alongside EIP-3009 |
| **C. Use existing EIP-3009 token** | Low | Find/use Etherlink USDC if it supports EIP-3009 |
| **D. Fork x402 SDK** | High | Create Permit-compatible version of the protocol |

---

## Network Configuration

| Parameter | Value |
|-----------|-------|
| Network Name | Etherlink Mainnet |
| Chain ID | 42793 |
| CAIP-2 | eip155:42793 |
| RPC URL | https://rpc.bubbletez.com |
| Explorer | https://explorer.etherlink.com |
| BBT Token | 0x7EfE4bdd11237610bcFca478937658bE39F8dfd6 |
| Facilitator | http://100.112.150.8:8080 |

---

## Files

| File | Purpose |
|------|---------|
| `mvp_server.py` | Minimal x402 server (returns 402, accepts X-PAYMENT) |
| `mvp_client.py` | Minimal x402 client (creates EIP-712 permit, sends X-PAYMENT) |
| `bbt_storefront.py` | Full SDK-based server (blocked by middleware bug) |
| `.env` | Private key and configuration |

---

## Next Steps

1. **Find/Deploy EIP-3009 compatible token** - Required for on-chain settlement
2. **Or modify x402-rs facilitator** - Add EIP-2612 Permit support
3. **Debug SDK middleware** - Fix `RouteConfigurationError` for production use
4. **Complete end-to-end test** - Once signature format is resolved

---

## Conclusion

The x402 HTTP payment protocol flow is **verified working** on Etherlink:

| What Works | Status |
|------------|--------|
| Server returns HTTP 402 with `X-PAYMENT-REQUIRED` | ✅ |
| Client decodes payment requirements | ✅ |
| Client creates EIP-712 signature | ✅ |
| Client sends `X-PAYMENT` header | ✅ |
| Server receives and parses payment | ✅ |
| Server calls facilitator `/settle` | ✅ |

| What's Blocked | Reason |
|----------------|--------|
| Facilitator signature validation | EIP-3009 vs EIP-2612 format mismatch |
| On-chain token transfer | Blocked by above |
| Transaction hash proof | Blocked by above |

**The protocol works. The token doesn't support the required signature format.**
