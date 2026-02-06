# x402 on Etherlink - Implementation & Test Suite

**Generated:** 2026-02-06
**Project:** Etherlink x402 POC with BBT token (Permit2-enabled)

## OVERVIEW
Proof of concept validating Coinbase x402 HTTP payment protocol on Etherlink mainnet using web3.py client and Permit2-enabled Rust facilitator fork.

## STRUCTURE
```
x402_poc/
├── bbt_mvp_server.py       # FastAPI server (port 8001) - Permit2 v2
├── bbt_mvp_client.py       # EIP-712 signing client
├── mvp_server.py           # Legacy EIP-2612 (port 8000, deprecated)
├── bbt_storefront.py       # SDK-based server (middleware bug)
├── playbook_permit2_flow.py # Full flow integration test
└── bbt-x402-facilitator/   # Rust workspace (Permit2)
```

## WHERE TO LOOK
| Task | Location | Notes |
|------|----------|-------|
| Run production MVP | `bbt_mvp_server.py` | `python bbt_mvp_server.py` (port 8001) |
| Test client flow | `bbt_mvp_client.py` | `python bbt_mvp_client.py` |
| Full integration | `playbook_permit2_flow.py` | Orchestrates complete flow |
| Facilitator build | `bbt-x402-facilitator/` | See sub-dir AGENTS.md |

## CONVENTIONS (Python)
- **Module names:** `snake_case.py` (e.g., `bbt_mvp_client.py`)
- **Functions:** `snake_case`
- **Classes:** `PascalCase` (e.g., `Permit2Signer`)
- **Indents:** 4 spaces (PEP8)
- **Async:** All server/client functions async (asyncio.run)

## ANTI-PATTERNS (CRITICAL)
- **NEVER commit `.env`** - contains actual private keys, not gitignored
- **Use `bbt_mvp_*.py` (Permit2)**, NOT `mvp_*.py` (legacy EIP-2612, deprecated)
- **EIP-712 Permit2:** `uint160`/`uint48` types, NOT `uint256`
- **Permit2 nonce:** MUST fetch via `Permit2.allowance()` before signing
- **Transfer index:** ALWAYS at array element 2 (tx decode)

## COMMANDS
```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run server (Permit2 v2)
python bbt_mvp_server.py

# Run client test
python bbt_mvp_client.py

# Full flow test
python playbook_permit2_flow.py

# Lint
ruff check .
ruff format .
```

## NETWORK CONFIG
| Param | Value |
|-------|-------|
| Chain ID | 42793 |
| CAIP-2 | `eip155:42793` |
| RPC | `https://rpc.bubbletez.com` |
| BBT Token | `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6` |
| Permit2 | `0x000000000022D473030F116dDEE9F6B43aC78BA3` |

## NOTES
- Dual port setups exist (8000 legacy, 8001 production) - use 8001
- Git worktrees present (`.worktrees/master/`) - ignore these copies
- venv in root (non-standard but intentional for POC)
- No `tests/` directory - tests embedded in scripts as async functions