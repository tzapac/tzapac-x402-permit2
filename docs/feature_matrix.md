# x402 Feature Matrix (Coinbase vs This Repo)

Legend: ✓ = supported in-repo, ✗ = not supported, ~ = partially supported (see notes).

| Feature | Coinbase `coinbase/x402` | This repo (`tzapac-x402-permit2`, Etherlink PoC) | Notes |
|---|---:|---:|---|
| x402 v2 transport (`Payment-Required`, `Payment-Signature`) | ✓ | ✓ | Both use base64-encoded JSON headers. |
| Backward-compatible legacy headers (`X-PAYMENT-*`) | ✓ | ✗ | This repo now uses canonical x402 v2 header names only. |
| Exact scheme (EVM) | ✓ | ✓ | "exact" is implemented in both. |
| Exact scheme (Solana/SVM) | ✓ | ✗ | Coinbase repo ships SVM mechanisms and paywall templates. |
| EVM asset transfer: EIP-3009 (`transferWithAuthorization`) | ✓ | ~ | Facilitator supports it, but this PoC demo stack is wired to Permit2. |
| EVM asset transfer: Permit2 (Exact proxy + witness) | ✓ | ✓ | Coinbase vanity proxy is not deployed on Etherlink; we deploy the same code at a different address. |
| Permit2 "upto" proxy address + ABI | ✓ | ✗ | Coinbase publishes an `upto` proxy address/ABI; this repo focuses on `exact`. |
| Client routing via `extra.assetTransferMethod` | ✓ | ✗ | Coinbase SDKs route `eip3009` vs `permit2` based on requirements; this PoC client is Permit2-only. |
| Server signaling via `extra.assetTransferMethod="permit2"` | ✓ | ✓ | Used to force Permit2 when EIP-3009 is not applicable. |
| Facilitator pays settlement gas (default model) | ✓ | ✓ | Coinbase-aligned model: user signs, facilitator submits tx and pays gas. |
| Client pays gas mode (client submits on-chain txs) | ✗ | ✗ | Removed from the PoC frontend; not part of Coinbase model. |
| Store pays gas mode (store submits on-chain txs) | ✗ | ✗ | Removed from the PoC frontend; not part of Coinbase model. |
| Legacy Permit2 allowance payload path (`payload.permit2`) | ✗ | ✗ | Server now accepts only witness-based `permit2Authorization` payloads. |
| On-chain recipient binding (witness enforces `payTo`) | ✓ | ✓ | Trustless recipient binding via Permit2 witness. |
| Proxy contract Solidity source included in repo | ✗ | ✓ | Coinbase repo exposes ABIs/constants + spec reference code; this repo includes extracted Solidity + verification input. |
| Etherlink deployment of Permit2 proxy | ✗ | ✓ | Deployed and verified on Etherlink: `0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E`. |
| Sponsored ERC20 approval extension (`erc20ApprovalGasSponsoring`) | ✗ | ✗ | Documented in Coinbase specs; not implemented end-to-end in this PoC. |
| Sponsored EIP-2612 extension (`eip2612GasSponsoring`) | ✗ | ✗ | Proxy supports `settleWithPermit` at contract level, but no end-to-end flow is implemented here. |
| Atomic bundling / private RPC settlement for sponsored approvals | ✗ | ✗ | Etherlink RPC endpoints tested do not expose bundle/private-tx methods (e.g. `eth_sendBundle`). |
| Multi-language SDKs (Go/TS/Python/Java) | ✓ | ✗ | This repo is a focused PoC + Rust facilitator fork, not a full SDK suite. |
| End-to-end integration tests in repo | ✓ | ✓ | Coinbase has `e2e/`; this repo has a Playbook that runs real txs against Etherlink. |
