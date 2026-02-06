#!/usr/bin/env python3
"""Run the end-to-end Permit2 x402 flow and report on-chain proof."""

from __future__ import annotations

import asyncio
import json
import os
import re
import signal
import subprocess
import sys
import time
from dataclasses import dataclass
from typing import Optional

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8001")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://exp-faci.etherlinkinsights.com")
RPC_URL = os.getenv("NODE_URL", os.getenv("RPC_URL", "https://rpc.bubbletez.com"))
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
SERVER_WALLET = os.getenv("SERVER_WALLET", "0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F")

BBT_TOKEN = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
CHAIN_ID = 42793

TRANSFER_EVENT_SIG = Web3.keccak(text="Transfer(address,address,uint256)").hex()

TX_RE = re.compile(r"0x[a-fA-F0-9]{64}")
AMOUNT_RE = re.compile(r"Amount:\s+(\d+)\s+wei")


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


def _find_tx_hashes(output: str) -> list[str]:
    return TX_RE.findall(output)


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
    deadline = time.time() + 30
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


async def _check_facilitator() -> None:
    paths = ["/api/supported", "/supported", "/api/"]
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
        if last_error:
            raise last_error
        raise RuntimeError("Facilitator check failed")


def _check_rpc(w3: Web3) -> None:
    if not w3.is_connected():
        raise RuntimeError("RPC not connected")
    print(f"RPC connected. Latest block: {w3.eth.block_number}")


def _run_client() -> tuple[int, str]:
    cmd = [sys.executable, "bbt_mvp_client.py"]
    proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
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
    )


def _is_server_alive() -> bool:
    try:
        resp = httpx.get(f"{SERVER_URL}/", timeout=1.5)
        return resp.status_code == 200
    except Exception:
        return False


def _stop_process(proc: subprocess.Popen) -> None:
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


def _get_transfer_receipt(w3: Web3, tx_hash: str) -> dict:
    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    return receipt


def _analyze_transfer(w3: Web3, tx_hash: str) -> RunResult:
    receipt = _get_transfer_receipt(w3, tx_hash)
    status = receipt.get("status")
    block_number = receipt.get("blockNumber")
    tx = w3.eth.get_transaction(tx_hash)
    from_addr = tx.get("from")

    transfer_from = None
    transfer_to = None
    transfer_amount = None

    for log in receipt.get("logs", []):
        if (log.get("address") or "").lower() != BBT_TOKEN.lower():
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
    hashes = _find_tx_hashes(output)
    # Prefer hash after "txHash" if present
    for line in output.splitlines():
        if "txHash" in line:
            match = TX_RE.search(line)
            if match:
                return match.group(0)
    return hashes[-1] if hashes else None


def _extract_expected_amount(output: str) -> Optional[int]:
    for line in output.splitlines():
        match = AMOUNT_RE.search(line)
        if match:
            return int(match.group(1))
    return None


async def main() -> int:
    if not PRIVATE_KEY:
        print("ERROR: PRIVATE_KEY missing in .env")
        return 1

    account = Account.from_key(PRIVATE_KEY)

    _print_header("ENV")
    print(f"SERVER_URL: {SERVER_URL}")
    print(f"FACILITATOR_URL: {FACILITATOR_URL}")
    print(f"RPC_URL: {RPC_URL}")
    print(f"Client wallet: {account.address}")
    print(f"Server wallet (payTo): {SERVER_WALLET}")

    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    _print_header("CHECKS")
    _check_rpc(w3)
    await _check_facilitator()

    server_proc: Optional[subprocess.Popen] = None
    server_started = False
    if _is_server_alive():
        print("Server already running; will reuse.")
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

    _print_header("RUN CLIENT")
    code, output = _run_client()
    if code != 0:
        print(f"ERROR: client exited with code {code}")
        if server_started and server_proc:
            _stop_process(server_proc)
        return 1

    transfer_tx = _extract_transfer_tx(output)
    if not transfer_tx:
        print("ERROR: could not find transfer tx hash in client output")
        if server_started and server_proc:
            _stop_process(server_proc)
        return 1

    _print_header("ON-CHAIN PROOF")
    result = _analyze_transfer(w3, transfer_tx)
    print(f"Transfer tx: {result.transfer_tx}")
    print(f"Transfer status: {result.status}")
    print(f"Block: {result.block_number}")

    expected_from = Web3.to_checksum_address(account.address)
    expected_to = Web3.to_checksum_address(SERVER_WALLET)
    expected_amount = _extract_expected_amount(output)

    if (
        result.transfer_from
        and result.transfer_to
        and result.transfer_amount is not None
    ):
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
        if expected_amount is not None and result.transfer_amount != expected_amount:
            print(f"ERROR: transfer amount mismatch (expected {expected_amount})")
            mismatch = True

        if mismatch:
            if server_started and server_proc:
                _stop_process(server_proc)
            return 1
    else:
        print("Transfer event: not found in receipt logs")
        if server_started and server_proc:
            _stop_process(server_proc)
        return 1

    _print_header("DONE")
    if server_started and server_proc:
        print("Stopping server...")
        _stop_process(server_proc)

    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(asyncio.run(main()))
    except KeyboardInterrupt:
        raise SystemExit(130)
