Session Summary: x402 Payment Protocol POC on Etherlink
What We Did
1. Set Up x402 Infrastructure
- Configured Python environment with x402[fastapi,httpx,evm] SDK and web3.py
- Modified remote Rust facilitator on ub1 (100.112.150.8:8080) to support Etherlink:
  - Added Network::Etherlink enum (chain ID 42793)
  - Added /api/supported route (SDK requires /api/ prefix)
  - Rebuilt Docker image: ukstv/x402-facilitator:etherlink
2. Created MVP Implementation (Bypassing Buggy SDK Middleware)
- bbt_mvp_server.py - FastAPI server that:
  - Returns HTTP 402 with X-PAYMENT-REQUIRED header
  - Accepts X-PAYMENT header with signed payment
  - Forwards to facilitator /settle endpoint
  
- bbt_mvp_client.py - Payment client that:
  - Requests protected resource, receives 402
  - Creates EIP-712 Permit2 signature for BBT token
  - Sends payment via X-PAYMENT header
3. Debugged Facilitator Integration
Fixed multiple format issues for facilitator /settle endpoint:
- Network must be "etherlink" not "eip155:42793"
- Asset must be plain address "0x7EfE..." not CAIP-10 format
- Nonce must be 32-byte hex "0x..." (64 chars)
- x402Version must be at TOP level of settle request, not inside paymentRequirements
4. Added Permit2 Support and Completed On-Chain Settlement
- Forked facilitator into /home/tzapac-server/Documents/x402_poc/bbt-x402-facilitator
- Added Permit2 support (PermitSingle/PermitDetails types, ABI, v1/v2 flows)
- Ran debug facilitator binary on ub1:9090 (Permit2-enabled)
- Fixed server response parsing for facilitator JSON/string payloads
- End-to-end HTTP flow now returns 200 with on-chain tx hash
---
Current State
What Works ✅
| Step | Status |
|------|--------|
| Server returns 402 with X-PAYMENT-REQUIRED | ✅ |
| Client decodes requirements | ✅ |
| Client creates EIP-712 Permit2 signature | ✅ |
| Client sends X-PAYMENT header | ✅ |
| Server calls facilitator /settle | ✅ |
What's Blocked ❌
| Step | Reason |
|------|--------|
| None | Settlement verified with Permit2 |
---
Files We're Working On
Local: /home/tzapac-server/Documents/x402_poc/
| File | Purpose |
|------|---------|
| bbt_mvp_server.py | FastAPI x402 server with /settle integration |
| bbt_mvp_client.py | EIP-712 signing client (Permit2) |
| bbt_storefront.py | SDK-based server (middleware bug, not used) |
| bbt-x402-facilitator/ | Permit2-enabled Rust facilitator fork |
| AGENTS.md | Project documentation (updated with x402 section) |
| PROOF_OF_CONCEPT.md | Full POC results documentation |
| .env | Contains PRIVATE_KEY for client wallet |
Remote (ub1 - 100.112.150.8):
| Path | Purpose |
|------|---------|
| ~/x402-facilitator-debug | Permit2-enabled facilitator binary (9090) |
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
Server Wallet: configured via .env (SERVER_WALLET); POC run used 0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9
Client Wallet: configured via .env (PRIVATE_KEY); POC run used 0x3E3f637E2C052AD29558684B85a56D8Ee1334Db9
Facilitator (debug Permit2): http://100.112.150.8:9090
Facilitator (legacy container): http://100.112.150.8:8080
Latest tx: 0x0476d3bcfccf6a83644d12c5abcaf598a6fc1ac7ee1377bff35fda5b828590e1
---
What To Do Next
- Decide whether to keep using the debug Permit2 facilitator on 9090 or bake Permit2 into the Docker container.
- If needed, re-enable a separate payTo address by aligning Permit2 spender vs recipient logic in the facilitator.
---
Key Commands
# Start MVP server (tmux session 'bbt-server')
cd /home/tzapac-server/Documents/x402_poc
source venv/bin/activate
python bbt_mvp_server.py
# Run client test
python bbt_mvp_client.py
# Check facilitator logs
ssh ub1 "tail -200 /tmp/facilitator-debug.log"
# Rebuild facilitator on ub1
ssh ub1 "cd ~/x402_rs/x402-rs && docker build -t ukstv/x402-facilitator:etherlink . && docker stop x402-facilitator-etherlink && docker rm x402-facilitator-etherlink && docker run -d --name x402-facilitator-etherlink --env-file .env -p 8080:8080 ukstv/x402-facilitator:etherlink"
---
Continuation Prompt
Continue x402 POC on Etherlink. Current state:
- HTTP protocol flow WORKS (402 → payment header → server → facilitator)
- On-chain settlement VERIFIED via Permit2
- Facilitator running on 9090 (debug binary) and 8080 (legacy container)
Files: /home/tzapac-server/Documents/x402_poc/ (bbt_mvp_server.py, bbt_mvp_client.py)
Facilitator: ssh ub1, debug binary at ~/x402-facilitator-debug
Next steps:
- Decide whether to keep 9090 or migrate Permit2 support into Docker image
- If needed, rework spender/recipient handling for non-self payTo
Read AGENTS.md and PROOF_OF_CONCEPT.md for full context.
