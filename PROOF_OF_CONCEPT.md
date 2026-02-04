# x402 Payment Protocol - Etherlink BBT Token Proof of Concept

**Date:** 2026-02-02 (updated 2026-02-04)  
**Network:** Etherlink Mainnet (Chain ID: 42793)  
**Token:** BBT (bbtez) - `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`

---

## Executive Summary

| Component | Status | Notes |
|-----------|--------|-------|
| HTTP 402 Challenge | **VERIFIED** | Server returns proper `X-PAYMENT-REQUIRED` header |
| Permit2 Signing | **VERIFIED** | Client creates valid Permit2 signature |
| Payment Header Exchange | **VERIFIED** | `X-PAYMENT` header accepted by server |
| Server → Facilitator `/settle` | **VERIFIED** | Server forwards payment to facilitator |
| Facilitator Permit2 Validation | **VERIFIED** | Permit2 flow accepted |
| On-Chain Settlement | **VERIFIED** | Payment settles on Etherlink |

**Conclusion:** The x402 HTTP protocol flow and on-chain settlement work on Etherlink using Permit2.

---

## Component Receipts

### 1. Facilitator (ub1: 100.112.150.8:9090)

**Endpoint:** `/api/supported`  
**Response:**
```json
{
  "kinds": [
    {
      "network": "eip155:42793",
      "scheme": "exact",
      "x402Version": 2
    }
  ]
}
```

**Binary:** `~/x402-facilitator-debug`  
**Status:** Running on port 9090 (Permit2-enabled)

---

### 2. MVP Server (localhost:8001)

**File:** `bbt_mvp_server.py`

**Request 1 - No Payment:**
```
GET /api/weather HTTP/1.1
Host: localhost:8001
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
  "x402Version": 2,
  "accepts": [
    {
      "scheme": "exact",
      "network": "eip155:42793",
      "amount": "10000000000000000",
      "resource": "http://localhost:8001/api/weather",
      "description": "Weather data access",
      "mimeType": "application/json",
      "payTo": "0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9",
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

**File:** `bbt_mvp_client.py`

**Client Wallet:** Configured via `.env` (POC run used `0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9`)

**EIP-712 Permit2 Parameters:**
| Field | Value |
|-------|-------|
| Token | `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6` (BBT) |
| Owner | `0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9` |
| Spender | `0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9` |
| Value | `10000000000000000` (0.01 BBT) |
| Deadline | `1770042190` (Unix timestamp) |
| Nonce | `7` |
| Chain ID | `42793` |

**Generated Signature:**
```
996ba799657fae8f25e411ae5962dbad6553ee4ceda7ac59b3fdb1c6789f4a5969264479d735f4767c7d15b1fc8f58e71530621188e797dffc35646e2f74d99b1b
```

**X-PAYMENT Header Payload:**
```json
{
  "x402Version": 2,
  "scheme": "exact",
  "network": "eip155:42793",
  "payload": {
    "permit2": {
      "owner": "0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9",
      "permitSingle": {
        "details": {
          "token": "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6",
          "amount": 10000000000000000,
          "expiration": 1770042190,
          "nonce": 7
        },
        "spender": "0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9",
        "sigDeadline": 1770042190
      },
      "signature": "996ba799657fae8f25e411ae5962dbad6553ee4ceda7ac59b3fdb1c6789f4a5969264479d735f4767c7d15b1fc8f58e71530621188e797dffc35646e2f74d99b1b"
    }
  }
}
```

---

### 4. Paid Request & Response

**Request 2 - With Payment:**
```
GET /api/weather HTTP/1.1
Host: localhost:8001
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
  "payment_settled": true,
  "txHash": "0x0476d3bcfccf6a83644d12c5abcaf598a6fc1ac7ee1377bff35fda5b828590e1",
  "explorer": "https://explorer.etherlink.com/tx/0x0476d3bcfccf6a83644d12c5abcaf598a6fc1ac7ee1377bff35fda5b828590e1"
}
```

---

## On-Chain Settlement

### What We Implemented
The MVP server now calls the facilitator `/settle` endpoint with the Permit2 payment signature.

### Facilitator Response
```
{"success": true, "transaction": "0x0476d3bcfccf6a83644d12c5abcaf598a6fc1ac7ee1377bff35fda5b828590e1", "network": "eip155:42793"}
```

### Solutions to Unblock

| Option | Effort | Description |
|--------|--------|-------------|
| **A. Keep Permit2 facilitator** | Low | Continue using debug binary on port 9090 |
| **B. Containerize Permit2** | Medium | Bake Permit2 changes into Docker image |
| **C. Expand payTo support** | Medium | Align Permit2 spender vs recipient handling |

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
| Facilitator (Permit2 debug) | http://100.112.150.8:9090 |
| Facilitator (legacy container) | http://100.112.150.8:8080 |

---

## Files

| File | Purpose |
|------|---------|
| `bbt_mvp_server.py` | Minimal x402 server (returns 402, accepts X-PAYMENT) |
| `bbt_mvp_client.py` | Minimal x402 client (creates Permit2 payload, sends X-PAYMENT) |
| `bbt_storefront.py` | Full SDK-based server (blocked by middleware bug) |
| `bbt-x402-facilitator/` | Permit2-enabled Rust facilitator fork |
| `.env` | Private key and configuration |

---

## Next Steps

1. **Decide on facilitator deployment** - Keep 9090 or bake Permit2 into container
2. **If needed, update payTo/recipient handling** - Support non-self payTo flows
3. **Document production flow** - Capture final commands and artifacts

---

## Conclusion

The x402 HTTP payment protocol flow is **verified working** on Etherlink:

| What Works | Status |
|------------|--------|
| Server returns HTTP 402 with `X-PAYMENT-REQUIRED` | ✅ |
| Client decodes payment requirements | ✅ |
| Client creates Permit2 typed-data (EIP-712) signature | ✅ |
| Client sends `X-PAYMENT` header | ✅ |
| Server receives and parses payment | ✅ |
| Server calls facilitator `/settle` | ✅ |

| What's Blocked | Reason |
|----------------|--------|
| None | Settlement verified with Permit2 |

**The protocol and settlement work with Permit2 on Etherlink.**
