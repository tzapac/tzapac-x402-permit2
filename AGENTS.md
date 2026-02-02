# AGENTS

## Project Overview
Proof of concept for etherlink x402 support testing via web3.py and ThirdWeb.

## Project Structure & Module Organization
- Primary project lives in `Documents/x402_poc/` with web3.py integration tests.
- Scripts and test files use `snake_case.py` convention for module names.

## Build, Test, and Development Commands
- Python venv setup (from project root):
  - `python3 -m venv venv && source venv/bin/activate`
  - `pip install -r requirements.txt`
- Run tests (pytest):
  - `pytest` (all tests)
  - `pytest tests/test_x402.py` (single test file)
  - `pytest tests/test_x402.py::test_specific_function` (single test)
  - `pytest -v -s` (verbose with print output)
- Linting:
  - `ruff check .` (lint check)
  - `ruff format .` (format)
- Type checking (if using mypy):
  - `mypy .`

## Coding Style & Naming Conventions
- Python: 4-space indent, PEP8 style.
- Module names: `snake_case.py` (e.g., `x402_client.py`, `test_integration.py`)
- Function names: `snake_case` (e.g., `connect_to_node`, `verify_x402_support`)
- Class names: `PascalCase` (e.g., `X402Client`, `ThirdWebAdapter`)
- Constants: `UPPER_SNAKE_CASE` (e.g., `DEFAULT_CHAIN_ID`, `MAX_RETRIES`)
- Private members: `_leading_underscore` (internal use only)

## Type Annotations & Error Handling
- Use python 3.10+ type hints: `def connect(url: str) -> Web3 | None:`
- Prefer `Optional[T]` over `| None` when explicit null checking needed.
- Use specific exception types: `ConnectionError`, `ValueError`, custom `X402Error`.
- Always wrap web3.py calls in try/except with proper error logging.
- Use `logging.getLogger(__name__)` for structured logging (configure root logger in main).

## web3.py & ThirdWeb Integration Patterns
- Connect via `Web3(Web3.HTTPProvider(url))` or IPC provider if available.
- Use `w3.is_connected()` check after initialization.
- Gas estimation: `w3.eth.estimate_gas(tx_dict)` before sending.
- Handle transaction receipts with status check: `tx_receipt['status'] == 1`
- Use `w3.to_checksum_address()` for address validation.
- Store private keys in `.env` (NEVER commit - add `.env` to `.gitignore`).

## Configuration & Environment
- `.env` file for node URLs, private keys, chain IDs.
- Example `.env`:
  - `NODE_URL=https://etherlink-node.example.com`
  - `PRIVATE_KEY=your_private_key_here`
  - `CHAIN_ID=1284`
- Use `python-dotenv` to load: `from dotenv import load_dotenv; load_dotenv()`

## Etherlink Node Setup (Reference)
- EVM node binary: `/home/tzapac-server/Documents/etherlink-node/octez-evm-node`
- Node logs: `/home/tzapac-server/Documents/etherlink-node/evm_node.log`
- Start node via scripts in etherlink-node directory (see README.md there).

### Reference Contracts (Mainnet)
- **bbtez (BBT) Token** - EIP-2612 verified ✅
  - Contract: `0x7EfE4bdd11237610bcFca478937658bE39F8dfd6`
  - Deployed at block: `37605399`
  - Tx hash: `bd4c8f42e609fa40bffdda68ccf6d8616178604d76cdaa1ef3e08a3adc428cae`
  - Use this contract as reference for x402/permit testing patterns.

## Testing Guidelines
- Use pytest for all tests; name test files `test_*.py`.
- Include integration tests against actual etherlink node when possible.
- Mock network calls in unit tests using `pytest-mock` or `pytest-web3`.
- Add docstrings to test functions explaining what's being verified.

## Commit & Pull Request Guidelines
- Commit messages: imperative, sentence-case (e.g., "Add x402 transaction decoding")
- Avoid committing `.env`, compiled `__pycache__`, or private keys.
- PRs should include test output showing successful runs.

## Security & Validation
- Validate inputs: address checksums, hex string lengths, numeric ranges.
- Rate limit RPC calls to avoid hitting node limits.
- Handle network timeouts gracefully (default 30s).
- Never log private keys or sensitive wallet data.

---

## x402 Protocol POC (2026-02-02)

### Overview
Testing Coinbase x402 HTTP payment protocol on Etherlink mainnet with BBT token.

### Architecture
```
Client (mvp_client.py) --> Server (mvp_server.py:8000) --> Facilitator (ub1:8080) --> Etherlink RPC
```

### Key Files
| File | Purpose |
|------|---------|
| `mvp_server.py` | FastAPI server with 402 payment flow |
| `mvp_client.py` | EIP-712 signing client |
| `bbt_storefront.py` | SDK-based server (blocked by middleware bug) |
| `PROOF_OF_CONCEPT.md` | Full documentation of POC results |

### Remote Facilitator (ub1)
- Host: `100.112.150.8` (SSH alias: `ub1`)
- Facilitator: `http://100.112.150.8:8080`
- Container: `x402-facilitator-etherlink`
- Source: `~/x402_rs/x402-rs/`
- Rebuild: `cd ~/x402_rs/x402-rs && docker build -t ukstv/x402-facilitator:etherlink . && docker stop x402-facilitator-etherlink && docker rm x402-facilitator-etherlink && docker run -d --name x402-facilitator-etherlink --env-file .env -p 8080:8080 ukstv/x402-facilitator:etherlink`

### Endpoints Modified on Facilitator
- Added `/api/supported` route (SDK expects `/api/` prefix)
- `/settle` and `/verify` for payment processing

### Run MVP Server
```bash
cd /home/tzapac-server/Documents/x402_poc
source venv/bin/activate
python mvp_server.py
```

### Run Client Test
```bash
source venv/bin/activate
python mvp_client.py
```

### Current Status: BLOCKED

**Issue**: EIP-712 signature mismatch

The x402-rs facilitator expects **EIP-3009 TransferWithAuthorization** signatures:
```
TransferWithAuthorization(address from,address to,uint256 value,uint256 validAfter,uint256 validBefore,bytes32 nonce)
```

But BBT token on Etherlink only supports **EIP-2612 Permit**:
```
Permit(address owner,address spender,uint256 value,uint256 nonce,uint256 deadline)
```

**Result**: Signature verification fails in facilitator with "Address mismatch".

### Solutions
1. **Deploy EIP-3009 token** on Etherlink (e.g., USDC with transferWithAuthorization)
2. **Modify facilitator** to support EIP-2612 Permit signatures
3. **Use Etherlink native USDC** if it supports EIP-3009

### HTTP Flow Verified
| Step | Status |
|------|--------|
| Server returns 402 with X-PAYMENT-REQUIRED | ✅ |
| Client decodes requirements | ✅ |
| Client creates EIP-712 signature | ✅ |
| Client sends X-PAYMENT header | ✅ |
| Server forwards to facilitator /settle | ✅ |
| Facilitator validates signature | ❌ (format mismatch) |
| On-chain settlement | ❌ (blocked) |

### Network Configuration
| Parameter | Value |
|-----------|-------|
| Chain ID | 42793 |
| CAIP-2 | eip155:42793 |
| Facilitator network name | "etherlink" |
| RPC | https://rpc.bubbletez.com |
| BBT Token | 0x7EfE4bdd11237610bcFca478937658bE39F8dfd6 |
| Server Wallet | 0x81C54CB7690016b2b0c3017a4991783964601bd9 |