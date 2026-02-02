Session Summary: x402 Payment Protocol POC on Etherlink
What We Did
1. Set Up x402 Infrastructure
- Configured Python environment with x402[fastapi,httpx,evm] SDK and web3.py
- Modified remote Rust facilitator on ub1 (100.112.150.8:8080) to support Etherlink:
  - Added Network::Etherlink enum (chain ID 42793)
  - Added /api/supported route (SDK requires /api/ prefix)
  - Rebuilt Docker image: ukstv/x402-facilitator:etherlink
2. Created MVP Implementation (Bypassing Buggy SDK Middleware)
- mvp_server.py - FastAPI server that:
  - Returns HTTP 402 with X-PAYMENT-REQUIRED header
  - Accepts X-PAYMENT header with signed payment
  - Forwards to facilitator /settle endpoint
  
- mvp_client.py - Payment client that:
  - Requests protected resource, receives 402
  - Creates EIP-712 permit signature for BBT token
  - Sends payment via X-PAYMENT header
3. Debugged Facilitator Integration
Fixed multiple format issues for facilitator /settle endpoint:
- Network must be "etherlink" not "eip155:42793"
- Asset must be plain address "0x7EfE..." not CAIP-10 format
- Nonce must be 32-byte hex "0x..." (64 chars)
- x402Version must be at TOP level of settle request, not inside paymentRequirements
4. Hit Fundamental Blocker
Facilitator returns signature validation error:
Invalid signature: Address mismatch
  recovered: 0xBB29d3eAaF085D8D70904D9D91Ae56b66eA4EA7c
  expected:  0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F
Root Cause: x402-rs facilitator expects EIP-3009 TransferWithAuthorization signatures, but BBT token only supports EIP-2612 Permit. These have different EIP-712 typed data structures.
---
Current State
What Works ✅
| Step | Status |
|------|--------|
| Server returns 402 with X-PAYMENT-REQUIRED | ✅ |
| Client decodes requirements | ✅ |
| Client creates EIP-712 signature | ✅ |
| Client sends X-PAYMENT header | ✅ |
| Server calls facilitator /settle | ✅ |
What's Blocked ❌
| Step | Reason |
|------|--------|
| Facilitator signature validation | EIP-3009 vs EIP-2612 mismatch |
| On-chain token transfer | Blocked by above |
| Transaction hash proof | Blocked by above |
---
Files We're Working On
Local: /home/tzapac-server/Documents/x402_poc/
| File | Purpose |
|------|---------|
| mvp_server.py | FastAPI x402 server with /settle integration |
| mvp_client.py | EIP-712 signing client |
| bbt_storefront.py | SDK-based server (middleware bug, not used) |
| AGENTS.md | Project documentation (updated with x402 section) |
| PROOF_OF_CONCEPT.md | Full POC results documentation |
| .env | Contains PRIVATE_KEY for client wallet |
Remote (ub1 - 100.112.150.8):
| Path | Purpose |
|------|---------|
| ~/x402_rs/x402-rs/ | Rust facilitator source |
| ~/x402_rs/x402-rs/src/main.rs | Routes (added /api/supported) |
| ~/x402_rs/x402-rs/src/network.rs | Network enum (added Etherlink) |
| Docker: x402-facilitator-etherlink | Running facilitator container |
---
Configuration
Network: Etherlink Mainnet
Chain ID: 42793
RPC: https://rpc.bubbletez.com
BBT Token: 0x7EfE4bdd11237610bcFca478937658bE39F8dfd6
Server Wallet: 0x81C54CB7690016b2b0c3017a4991783964601bd9
Client Wallet: 0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F
Facilitator: http://100.112.150.8:8080
---
What To Do Next
Option A: Find/Deploy EIP-3009 Token (Recommended)
1. Check if Etherlink USDC (0x796Ea11Fa2dD751eD01b53C372fFDB4AAa8f00F9) supports transferWithAuthorization
2. If not, deploy a test token with EIP-3009 support
3. Update mvp_server.py and mvp_client.py to use new token
4. Re-run payment flow for on-chain proof
Option B: Modify x402-rs Facilitator
1. SSH to ub1: ssh ub1
2. Edit ~/x402_rs/x402-rs/src/facilitator_local.rs
3. Add EIP-2612 Permit signature verification alongside EIP-3009
4. Rebuild: docker build -t ukstv/x402-facilitator:etherlink .
5. Restart container
Option C: Use Different Network
Test on Base Sepolia where official USDC with EIP-3009 exists.
---
Key Commands
# Start MVP server (in tmux session 'storefront')
cd /home/tzapac-server/Documents/x402_poc
source venv/bin/activate
python mvp_server.py
# Run client test
python mvp_client.py
# Check facilitator logs
ssh ub1 "docker logs x402-facilitator-etherlink --tail 20"
# Rebuild facilitator on ub1
ssh ub1 "cd ~/x402_rs/x402-rs && docker build -t ukstv/x402-facilitator:etherlink . && docker stop x402-facilitator-etherlink && docker rm x402-facilitator-etherlink && docker run -d --name x402-facilitator-etherlink --env-file .env -p 8080:8080 ukstv/x402-facilitator:etherlink"
---
Continuation Prompt
Continue x402 POC on Etherlink. Current state:
- HTTP protocol flow WORKS (402 → payment header → server → facilitator)
- On-chain settlement BLOCKED: facilitator expects EIP-3009 TransferWithAuthorization signatures, but BBT token only supports EIP-2612 Permit
Files: /home/tzapac-server/Documents/x402_poc/ (mvp_server.py, mvp_client.py)
Facilitator: ssh ub1, source at ~/x402_rs/x402-rs/
Next step options:
A) Check if Etherlink USDC (0x796Ea11Fa2dD751eD01b53C372fFDB4AAa8f00F9) supports EIP-3009
B) Modify facilitator to support EIP-2612 Permit
C) Deploy test EIP-3009 token on Etherlink
Read AGENTS.md and PROOF_OF_CONCEPT.md for full context.