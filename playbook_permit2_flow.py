#!/usr/bin/env python3
"""Run the end-to-end Permit2 x402 flow and report on-chain proof.

This playbook is model-3 (Coinbase-style) compatible: the client signs a Permit2
SignatureTransfer (PermitWitnessTransferFrom), and the facilitator settles via
an x402 Permit2 proxy contract (the signed message `spender`).

Prereqs (non-docker mode):
- Facilitator running and configured with X402_EXACT_PERMIT2_PROXY_ADDRESS
- This script can start the local store API; client is run as a subprocess

Optional: set AUTO_STACK=1 to bring up the local docker stack defined in
COMPOSE_FILE (defaults to docker-compose.model3-etherlink.yml).
"""

from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

# Load both local and repo multitest env if present.
load_dotenv()
load_dotenv(".env.multitest", override=False)

AUTO_STACK = os.getenv("AUTO_STACK", "0") == "1"
KEEP_STACK = os.getenv("KEEP_STACK", "0") == "1"
COMPOSE_FILE = os.getenv("COMPOSE_FILE", "docker-compose.model3-etherlink.yml")
FORCE_SERVER_RESTART = os.getenv("FORCE_SERVER_RESTART", "0") == "1"

SERVER_URL = os.getenv(
    "SERVER_URL",
    "http://localhost:9091" if AUTO_STACK else "http://localhost:8001",
)
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:9090")
RPC_URL = os.getenv("RPC_URL") or os.getenv("NODE_URL")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
# Optional: used to top-up gas / tokens for the active PRIVATE_KEY wallet.
FUNDING_PRIVATE_KEY = os.getenv("FUNDING_PRIVATE_KEY")

CHAIN_ID = int(os.getenv("CHAIN_ID", "0"))
DEFAULT_BBT_TOKEN = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
BBT_TOKEN = os.getenv("BBT_TOKEN", DEFAULT_BBT_TOKEN)
MIN_NATIVE_BALANCE_WEI = int(os.getenv("MIN_NATIVE_BALANCE_WEI", str(10**15)))  # 0.001 native
MIN_BBT_BALANCE = int(os.getenv("MIN_BBT_BALANCE", "0"))

DEFAULT_PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
PERMIT2_ADDRESS = os.getenv(
    "PERMIT2_ADDRESS",
    DEFAULT_PERMIT2_ADDRESS,
)

# Etherlink-deployed x402 exact Permit2 proxy (Coinbase model 3 spender).
DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS = "0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E"
X402_EXACT_PERMIT2_PROXY_ADDRESS = os.getenv(
    "X402_EXACT_PERMIT2_PROXY_ADDRESS",
    DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS,
)
ALLOW_FUNDING_TOPUPS = os.getenv("ALLOW_FUNDING_TOPUPS", "0") == "1"
FUNDING_CHAIN_ALLOWLIST = {
    int(v.strip())
    for v in os.getenv("FUNDING_CHAIN_ALLOWLIST", "42793").split(",")
    if v.strip()
}

TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()
TX_RE = re.compile(r"0x[a-fA-F0-9]{64}")

ERC20_ABI = [
    {
        "name": "balanceOf",
        "type": "function",
        "stateMutability": "view",
        "inputs": [{"name": "owner", "type": "address"}],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "allowance",
        "type": "function",
        "stateMutability": "view",
        "inputs": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
        ],
        "outputs": [{"name": "", "type": "uint256"}],
    },
    {
        "name": "approve",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "spender", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "name": "transfer",
        "type": "function",
        "stateMutability": "nonpayable",
        "inputs": [
            {"name": "to", "type": "address"},
            {"name": "amount", "type": "uint256"},
        ],
        "outputs": [{"name": "", "type": "bool"}],
    },
    {
        "anonymous": False,
        "name": "Transfer",
        "type": "event",
        "inputs": [
            {"indexed": True, "name": "from", "type": "address"},
            {"indexed": True, "name": "to", "type": "address"},
            {"indexed": False, "name": "value", "type": "uint256"},
        ],
    },
]


@dataclass
class RunResult:
    transfer_tx: str
    transfer_from: Optional[str]
    transfer_to: Optional[str]
    transfer_amount: Optional[int]
    block_number: Optional[int]
    status: Optional[int]


def _print_header(title: str) -> None:
    print("\n" + "=" * 72)
    print(title)
    print("=" * 72)


def _redact_rpc_url(url: str) -> str:
    if not url:
        return url
    try:
        parsed = urlsplit(url)
    except Exception:
        return "***"
    query = parse_qsl(parsed.query, keep_blank_values=True)
    redacted_query = urlencode([(k, "***") for (k, _v) in query], doseq=True)
    host = parsed.hostname or ""
    if parsed.port:
        host = f"{host}:{parsed.port}"
    return urlunsplit((parsed.scheme, host, parsed.path, redacted_query, parsed.fragment))


def _assert_chain_safety(chain_id: int) -> None:
    if chain_id == 42793:
        return
    required_explicit = (
        "BBT_TOKEN",
        "PERMIT2_ADDRESS",
        "X402_EXACT_PERMIT2_PROXY_ADDRESS",
    )
    missing = [k for k in required_explicit if not os.getenv(k)]
    if missing:
        raise RuntimeError(
            "Non-Etherlink run requires explicit env vars: "
            + ", ".join(missing)
        )


def _extract_client_payload_preview(output: str) -> Optional[dict]:
    marker = "Payment payload prepared (redacted):"
    idx = output.find(marker)
    if idx < 0:
        return None
    tail = output[idx + len(marker) :]
    start = tail.find("{")
    if start < 0:
        return None
    depth = 0
    end = None
    for i, ch in enumerate(tail[start:]):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = start + i + 1
                break
    if end is None:
        return None
    try:
        return json.loads(tail[start:end])
    except Exception:
        return None


def _assert_client_payload_invariants(
    output: str, expected_spender: str, expected_to: str, expected_amount: int
) -> None:
    preview = _extract_client_payload_preview(output)
    if not isinstance(preview, dict):
        raise RuntimeError("Could not parse client payment payload preview from output")
    auth = (
        preview.get("payload", {})
        .get("permit2Authorization", {})
    )
    spender = auth.get("spender")
    witness_to = (auth.get("witness") or {}).get("to")
    permitted_amount = (auth.get("permitted") or {}).get("amount")

    if not spender or spender.lower() != expected_spender.lower():
        raise RuntimeError(
            f"Client payload spender mismatch: expected {expected_spender}, got {spender}"
        )
    if not witness_to or witness_to.lower() != expected_to.lower():
        raise RuntimeError(
            f"Client payload witness.to mismatch: expected {expected_to}, got {witness_to}"
        )
    try:
        amount = int(permitted_amount)
    except Exception as exc:
        raise RuntimeError("Client payload has invalid permitted.amount") from exc
    if amount != int(expected_amount):
        raise RuntimeError(
            f"Client payload amount mismatch: expected {expected_amount}, got {amount}"
        )


def _docker_compose(args: list[str]) -> None:
    cmd = ["docker", "compose", "-f", COMPOSE_FILE, *args]
    proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"docker compose failed: {' '.join(cmd)}\n{proc.stdout}")


def _child_env() -> dict[str, str]:
    env = os.environ.copy()
    env["SERVER_URL"] = SERVER_URL
    env["FACILITATOR_URL"] = FACILITATOR_URL
    env["RPC_URL"] = RPC_URL
    env["CHAIN_ID"] = os.getenv("CHAIN_ID", str(CHAIN_ID))
    env["PERMIT2_ADDRESS"] = PERMIT2_ADDRESS
    env["BBT_TOKEN"] = BBT_TOKEN
    env["X402_EXACT_PERMIT2_PROXY_ADDRESS"] = X402_EXACT_PERMIT2_PROXY_ADDRESS
    return env


def _decode_transfer_log(log: dict) -> tuple[str, str, int] | None:
    if not log.get("topics") or len(log["topics"]) < 3:
        return None
    if log["topics"][0].hex() != TRANSFER_EVENT_SIG:
        return None
    from_addr = Web3.to_checksum_address("0x" + log["topics"][1].hex()[-40:])
    to_addr = Web3.to_checksum_address("0x" + log["topics"][2].hex()[-40:])
    data = log.get("data")
    if isinstance(data, (bytes, bytearray)):
        amount = int.from_bytes(data, byteorder="big")
    else:
        amount = int(data, 16)
    return from_addr, to_addr, amount


async def _wait_for_server() -> bool:
    deadline = time.time() + 45
    async with httpx.AsyncClient(timeout=3.0) as client:
        while time.time() < deadline:
            try:
                resp = await client.get(f"{SERVER_URL}/")
                if resp.status_code == 200:
                    return True
            except Exception:
                pass
            await asyncio.sleep(0.5)
    return False


async def _fetch_payment_required() -> dict:
    endpoint = f"{SERVER_URL}/api/weather"
    async with httpx.AsyncClient(timeout=15.0) as client:
        resp = await client.get(endpoint)
        if resp.status_code != 402:
            raise RuntimeError(
                f"Expected 402 from {endpoint}, got {resp.status_code}: {resp.text}"
            )
        required_b64 = resp.headers.get("Payment-Required") or resp.headers.get(
            "payment-required"
        )
        if not required_b64:
            raise RuntimeError("Missing Payment-Required header")
        return json.loads(base64.b64decode(required_b64, validate=True))


async def _check_facilitator() -> None:
    if os.getenv("SKIP_FACILITATOR_CHECK", "0") == "1":
        print("Skipping facilitator check (SKIP_FACILITATOR_CHECK=1).")
        return

    paths = ["/api/supported", "/supported", "/health", "/"]
    async with httpx.AsyncClient(timeout=5.0) as client:
        last_error: Optional[Exception] = None
        for path in paths:
            url = f"{FACILITATOR_URL}{path}"
            try:
                resp = await client.get(url)
                if resp.status_code == 404:
                    last_error = httpx.HTTPStatusError(
                        "404 Not Found", request=resp.request, response=resp
                    )
                    continue
                resp.raise_for_status()
                data = resp.json()
                print(f"Facilitator {path}:")
                print(json.dumps(data, indent=2))
                return
            except Exception as exc:
                last_error = exc
                continue
        # Some facilitator deployments don't expose a supported-list endpoint. Treat this as a
        # soft check and continue; settlement will fail later if the URL is wrong.
        if last_error:
            print(f"WARNING: facilitator check did not succeed ({last_error}); continuing...")
            return
        print("WARNING: facilitator check did not succeed; continuing...")


def _check_rpc(w3: Web3) -> int:
    if not w3.is_connected():
        raise RuntimeError("RPC not connected")
    chain_id = int(w3.eth.chain_id)
    print(f"RPC connected. Chain ID: {chain_id}. Latest block: {w3.eth.block_number}")
    if CHAIN_ID and CHAIN_ID != chain_id:
        raise RuntimeError(f"CHAIN_ID mismatch: configured {CHAIN_ID}, RPC reports {chain_id}")
    return chain_id


def _assert_code_exists(w3: Web3, address: str, label: str) -> None:
    checksum = Web3.to_checksum_address(address)
    code = w3.eth.get_code(checksum)
    if not code:
        raise RuntimeError(f"{label} has no deployed code at {checksum}")


def _run_client() -> tuple[int, str]:
    cmd = [sys.executable, "bbt_mvp_client.py"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_child_env(),
    )
    output_lines = []
    assert proc.stdout is not None
    for line in proc.stdout:
        print(line, end="")
        output_lines.append(line)
    return_code = proc.wait()
    return return_code, "".join(output_lines)


def _start_server() -> subprocess.Popen:
    cmd = [sys.executable, "bbt_mvp_server.py"]
    return subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=_child_env(),
    )


def _is_server_alive() -> bool:
    try:
        resp = httpx.get(f"{SERVER_URL}/", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def _kill_host_server() -> None:
    # Best-effort: kill a locally-run FastAPI process on the host.
    # This is only used for non-docker runs where we control the process lifecycle.
    try:
        subprocess.run(
            ["pkill", "-f", "bbt_mvp_server.py"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except Exception:
        pass


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _build_fee_params(w3: Web3) -> dict:
    latest = w3.eth.get_block("latest")
    base_fee = latest.get("baseFeePerGas") if isinstance(latest, dict) else None
    if base_fee is not None:
        try:
            priority = w3.eth.max_priority_fee
        except Exception:
            priority = Web3.to_wei(1, "gwei")
        max_fee = int(base_fee) * 2 + int(priority)
        return {
            "type": 2,
            "maxFeePerGas": max_fee,
            "maxPriorityFeePerGas": int(priority),
        }
    return {"gasPrice": w3.eth.gas_price}


def _native_balance(w3: Web3, addr: str) -> int:
    return int(w3.eth.get_balance(Web3.to_checksum_address(addr)))


def _erc20_balance(w3: Web3, token_address: str, owner: str) -> int:
    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    return int(token.functions.balanceOf(Web3.to_checksum_address(owner)).call())


def _ensure_native_topup(w3: Web3, to_addr: str, min_balance_wei: int, chain_id: int) -> None:
    if not FUNDING_PRIVATE_KEY:
        return
    if not ALLOW_FUNDING_TOPUPS:
        print("Funding wallet configured, but top-ups are disabled (ALLOW_FUNDING_TOPUPS != 1).")
        return
    if chain_id not in FUNDING_CHAIN_ALLOWLIST:
        raise RuntimeError(
            f"Refusing native top-up on chain {chain_id}; allowed chains={sorted(FUNDING_CHAIN_ALLOWLIST)}"
        )

    current = _native_balance(w3, to_addr)
    if current >= int(min_balance_wei):
        return

    funder = Account.from_key(FUNDING_PRIVATE_KEY)
    funder_addr = Web3.to_checksum_address(funder.address)
    to_addr = Web3.to_checksum_address(to_addr)

    # Conservative fixed top-up.
    topup = int(min_balance_wei) * 5
    print(
        f"Top-up native balance: {to_addr} has {current} wei (<{min_balance_wei}); "
        f"sending {topup} wei from {funder_addr}"
    )

    nonce = w3.eth.get_transaction_count(funder_addr, "pending")
    fee_params = _build_fee_params(w3)
    tx = {
        "from": funder_addr,
        "to": to_addr,
        "value": topup,
        "nonce": nonce,
        "chainId": chain_id,
        **fee_params,
    }
    gas_est = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_est * 12 // 10)
    signed = w3.eth.account.sign_transaction(tx, private_key=FUNDING_PRIVATE_KEY)
    raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.get("status") != 1:
        raise RuntimeError("native top-up transaction failed")
    print(f"Native top-up tx: {tx_hash.hex()}")


def _ensure_bbt_topup(w3: Web3, token_address: str, to_addr: str, min_amount: int, chain_id: int) -> None:
    if min_amount <= 0 or not FUNDING_PRIVATE_KEY:
        return
    if not ALLOW_FUNDING_TOPUPS:
        print("Funding wallet configured, but top-ups are disabled (ALLOW_FUNDING_TOPUPS != 1).")
        return
    if chain_id not in FUNDING_CHAIN_ALLOWLIST:
        raise RuntimeError(
            f"Refusing token top-up on chain {chain_id}; allowed chains={sorted(FUNDING_CHAIN_ALLOWLIST)}"
        )

    to_addr = Web3.to_checksum_address(to_addr)
    current = _erc20_balance(w3, token_address, to_addr)
    if current >= int(min_amount):
        return

    funder = Account.from_key(FUNDING_PRIVATE_KEY)
    funder_addr = Web3.to_checksum_address(funder.address)

    funder_bal = _erc20_balance(w3, token_address, funder_addr)
    if funder_bal <= 0:
        raise RuntimeError(
            f"BBT top-up requested but funding wallet {funder_addr} has 0 BBT"
        )

    # Send at least what is needed (or 2x to avoid re-running).
    needed = int(min_amount) - int(current)
    amount = min(int(funder_bal), max(needed, int(min_amount)))
    print(
        f"Top-up BBT balance: {to_addr} has {current} (<{min_amount}); "
        f"sending {amount} from {funder_addr}"
    )

    token = w3.eth.contract(address=Web3.to_checksum_address(token_address), abi=ERC20_ABI)
    nonce = w3.eth.get_transaction_count(funder_addr, "pending")
    fee_params = _build_fee_params(w3)
    tx = token.functions.transfer(to_addr, amount).build_transaction(
        {
            "from": funder_addr,
            "nonce": nonce,
            "chainId": chain_id,
            **fee_params,
        }
    )
    gas_est = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_est * 12 // 10)
    signed = w3.eth.account.sign_transaction(tx, private_key=FUNDING_PRIVATE_KEY)
    raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.get("status") != 1:
        raise RuntimeError("BBT top-up transfer failed")
    print(f"BBT top-up tx: {tx_hash.hex()}")


def _ensure_erc20_allowance_to_permit2(
    w3: Web3,
    account,
    token_address: str,
    required_amount: int,
    chain_id: int,
) -> None:
    token = w3.eth.contract(
        address=Web3.to_checksum_address(token_address),
        abi=ERC20_ABI,
    )
    owner = Web3.to_checksum_address(account.address)
    permit2 = Web3.to_checksum_address(PERMIT2_ADDRESS)

    current = token.functions.allowance(owner, permit2).call()
    print(f"ERC20 allowance(owner->Permit2): {current}")
    if int(current) >= int(required_amount):
        print("Allowance OK; no approve needed.")
        return

    print("Approving Permit2 allowance (exact required amount)...")
    nonce = w3.eth.get_transaction_count(owner, "pending")

    fee_params = _build_fee_params(w3)
    tx = token.functions.approve(permit2, int(required_amount)).build_transaction(
        {
            "from": owner,
            "nonce": nonce,
            "chainId": chain_id,
            **fee_params,
        }
    )
    gas_est = w3.eth.estimate_gas(tx)
    tx["gas"] = int(gas_est * 12 // 10)

    signed = w3.eth.account.sign_transaction(tx, private_key=PRIVATE_KEY)
    raw = getattr(signed, "rawTransaction", None) or getattr(signed, "raw_transaction")
    tx_hash = w3.eth.send_raw_transaction(raw)
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    if receipt.get("status") != 1:
        raise RuntimeError("approve() transaction failed")
    print(f"Approve tx: {tx_hash.hex()} (amount={required_amount})")


def _get_transfer_receipt(w3: Web3, tx_hash: str) -> dict:
    return w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)


def _analyze_transfer(w3: Web3, tx_hash: str, token_address: str) -> RunResult:
    receipt = _get_transfer_receipt(w3, tx_hash)
    status = receipt.get("status")
    block_number = receipt.get("blockNumber")

    transfer_from = None
    transfer_to = None
    transfer_amount = None

    token_address = Web3.to_checksum_address(token_address)
    for log in receipt.get("logs", []):
        if (log.get("address") or "").lower() != token_address.lower():
            continue
        decoded = _decode_transfer_log(log)
        if decoded:
            transfer_from, transfer_to, transfer_amount = decoded
            break

    return RunResult(
        transfer_tx=tx_hash,
        transfer_from=transfer_from,
        transfer_to=transfer_to,
        transfer_amount=transfer_amount,
        block_number=block_number,
        status=status,
    )


def _extract_transfer_tx(output: str) -> Optional[str]:
    for line in output.splitlines():
        # Only treat hashes printed in a txHash context as a transfer tx.
        # Otherwise we may accidentally pick up a 32-byte chunk from a signature.
        if "txHash" in line or "explorer.etherlink.com/tx/" in line:
            match = TX_RE.search(line)
            if match:
                return match.group(0)
    return None


async def main() -> int:
    if not PRIVATE_KEY:
        print("ERROR: PRIVATE_KEY missing (set env var or .env/.env.multitest)")
        return 1
    if not RPC_URL:
        print("ERROR: RPC_URL missing (NODE_URL accepted as legacy alias)")
        return 1

    account = Account.from_key(PRIVATE_KEY)

    _print_header("ENV")
    print(f"SERVER_URL: {SERVER_URL}")
    print(f"FACILITATOR_URL: {FACILITATOR_URL}")
    print(f"RPC_URL: {_redact_rpc_url(RPC_URL)}")
    print(f"CHAIN_ID: {CHAIN_ID if CHAIN_ID else '(auto from RPC)'}")
    print(f"Client wallet: {account.address}")
    if FUNDING_PRIVATE_KEY:
        print(f"Funding wallet: {Account.from_key(FUNDING_PRIVATE_KEY).address}")
    print(f"PERMIT2_ADDRESS: {PERMIT2_ADDRESS}")
    print(f"X402_EXACT_PERMIT2_PROXY_ADDRESS: {X402_EXACT_PERMIT2_PROXY_ADDRESS}")

    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    _print_header("CHECKS")
    rpc_chain_id = _check_rpc(w3)
    tx_chain_id = CHAIN_ID or rpc_chain_id
    _assert_chain_safety(tx_chain_id)
    os.environ["CHAIN_ID"] = str(tx_chain_id)
    _assert_code_exists(w3, PERMIT2_ADDRESS, "PERMIT2_ADDRESS")
    _assert_code_exists(
        w3, X402_EXACT_PERMIT2_PROXY_ADDRESS, "X402_EXACT_PERMIT2_PROXY_ADDRESS"
    )

    if AUTO_STACK:
        _print_header("DOCKER STACK")
        print(f"Bringing up stack via {COMPOSE_FILE}...")
        # Ensure the facilitator binary matches the current branch.
        _docker_compose(["up", "-d", "--build"])

    server_proc: Optional[subprocess.Popen] = None
    server_started = False

    if _is_server_alive():
        if FORCE_SERVER_RESTART and not AUTO_STACK:
            print("Server already running; FORCE_SERVER_RESTART=1 so restarting host server...")
            _kill_host_server()
            await asyncio.sleep(0.5)
        else:
            print("Server already running; will reuse.")
    elif AUTO_STACK:
        print("Waiting for server...")
        ready = await _wait_for_server()
        if not ready:
            print("ERROR: server did not become ready")
            if not KEEP_STACK:
                _docker_compose(["down", "-v"])
            return 1
    else:
        print("Starting server...")
        server_proc = _start_server()
        server_started = True
        ready = await _wait_for_server()
        if not ready:
            print("ERROR: server did not become ready")
            if server_proc:
                _stop_process(server_proc)
            return 1

    await _check_facilitator()

    _print_header("PAYMENT REQUIRED")
    payment_required = await _fetch_payment_required()
    print(json.dumps(payment_required, indent=2))

    try:
        accept = (payment_required.get("accepts") or [])[0]
        asset = accept["asset"]
        amount = int(accept.get("amount") or accept.get("maxAmountRequired"))
        pay_to = Web3.to_checksum_address(accept["payTo"])
        token_address = Web3.to_checksum_address(asset)
    except Exception as exc:
        print(f"ERROR: could not parse Payment-Required: {exc}")
        if server_started and server_proc:
            _stop_process(server_proc)
        if AUTO_STACK and not KEEP_STACK:
            _docker_compose(["down", "-v"])
        return 1

    print(f"Token: {token_address}")
    print(f"Amount: {amount}")
    print(f"payTo: {pay_to}")

    _print_header("BALANCES (PRE)")
    client_native = _native_balance(w3, account.address)
    client_bbt = _erc20_balance(w3, token_address, account.address)
    print(f"Client native balance: {client_native} wei")
    print(f"Client BBT balance: {client_bbt}")
    if FUNDING_PRIVATE_KEY:
        funder = Account.from_key(FUNDING_PRIVATE_KEY)
        funder_native = _native_balance(w3, funder.address)
        funder_bbt = _erc20_balance(w3, token_address, funder.address)
        print(f"Funder native balance: {funder_native} wei")
        print(f"Funder BBT balance: {funder_bbt}")

    # For Permit2 SignatureTransfer, the client still needs gas at least once to approve Permit2,
    # and needs token balance to cover the payment.
    _ensure_native_topup(w3, account.address, MIN_NATIVE_BALANCE_WEI, tx_chain_id)
    _ensure_bbt_topup(
        w3, token_address, account.address, max(amount, MIN_BBT_BALANCE), tx_chain_id
    )

    _print_header("ALLOWANCE")
    _ensure_erc20_allowance_to_permit2(w3, account, token_address, amount, tx_chain_id)

    _print_header("RUN CLIENT")
    code, output = _run_client()
    if code != 0:
        print(f"ERROR: client exited with code {code}")
        if server_started and server_proc:
            _stop_process(server_proc)
        if AUTO_STACK and not KEEP_STACK:
            _docker_compose(["down", "-v"])
        return 1

    _assert_client_payload_invariants(
        output=output,
        expected_spender=Web3.to_checksum_address(X402_EXACT_PERMIT2_PROXY_ADDRESS),
        expected_to=pay_to,
        expected_amount=amount,
    )

    transfer_tx = _extract_transfer_tx(output)
    if not transfer_tx:
        print("ERROR: could not find transfer tx hash in client output")
        if server_started and server_proc:
            _stop_process(server_proc)
        if AUTO_STACK and not KEEP_STACK:
            _docker_compose(["down", "-v"])
        return 1

    _print_header("ON-CHAIN PROOF")
    result = _analyze_transfer(w3, transfer_tx, token_address)
    print(f"Transfer tx: {result.transfer_tx}")
    print(f"Transfer status: {result.status}")
    print(f"Block: {result.block_number}")

    expected_from = Web3.to_checksum_address(account.address)
    expected_to = pay_to
    expected_amount = amount

    if result.transfer_from and result.transfer_to and result.transfer_amount is not None:
        print("Transfer event:")
        print(f"  from: {result.transfer_from}")
        print(f"  to:   {result.transfer_to}")
        print(f"  amount: {result.transfer_amount}")

        mismatch = False
        if result.transfer_from.lower() != expected_from.lower():
            print(f"ERROR: transfer sender mismatch (expected {expected_from})")
            mismatch = True
        if result.transfer_to.lower() != expected_to.lower():
            print(f"ERROR: transfer recipient mismatch (expected {expected_to})")
            mismatch = True
        if result.transfer_amount != expected_amount:
            print(f"ERROR: transfer amount mismatch (expected {expected_amount})")
            mismatch = True

        if mismatch:
            if server_started and server_proc:
                _stop_process(server_proc)
            if AUTO_STACK and not KEEP_STACK:
                _docker_compose(["down", "-v"])
            return 1
    else:
        print("Transfer event: not found in receipt logs")
        if server_started and server_proc:
            _stop_process(server_proc)
        if AUTO_STACK and not KEEP_STACK:
            _docker_compose(["down", "-v"])
        return 1

    _print_header("DONE")
    if server_started and server_proc:
        print("Stopping server...")
        _stop_process(server_proc)

    if AUTO_STACK and not KEEP_STACK:
        print("Stopping docker stack...")
        _docker_compose(["down", "-v"])

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
