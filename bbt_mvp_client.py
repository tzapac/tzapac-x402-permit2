#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import secrets
import time

import httpx
from dotenv import load_dotenv
from eth_abi.abi import encode
from eth_account import Account
from eth_account._utils.signing import sign_message_hash
from web3 import Web3

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8001")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("NODE_URL", os.getenv("RPC_URL", "https://rpc.bubbletez.com"))

PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
CHAIN_ID = 42793

# Coinbase x402 vanity address. Not deployed on all chains.
DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS = "0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E"
X402_EXACT_PERMIT2_PROXY_ADDRESS = os.getenv(
    "X402_EXACT_PERMIT2_PROXY_ADDRESS",
    DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS,
)

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY required in .env")

account = Account.from_key(PRIVATE_KEY)
print(f"Client wallet: {account.address}")


def _permit2_domain_separator(w3: Web3) -> bytes:
    permit2 = w3.eth.contract(
        address=Web3.to_checksum_address(PERMIT2_ADDRESS),
        abi=[
            {
                "name": "DOMAIN_SEPARATOR",
                "type": "function",
                "stateMutability": "view",
                "inputs": [],
                "outputs": [{"name": "", "type": "bytes32"}],
            }
        ],
    )
    return permit2.functions.DOMAIN_SEPARATOR().call()


def sign_permit2_witness_transfer(
    w3: Web3,
    token_address: str,
    spender: str,
    amount: int,
    nonce: int,
    deadline: int,
    pay_to: str,
    valid_after: int,
    extra: bytes,
) -> str:
    """Sign Permit2 PermitWitnessTransferFrom (Coinbase x402 model 3 style)."""
    domain_separator = _permit2_domain_separator(w3)

    token_permissions_typehash = Web3.keccak(
        text="TokenPermissions(address token,uint256 amount)"
    )
    witness_typehash = Web3.keccak(text="Witness(address to,uint256 validAfter,bytes extra)")

    # Dependencies must be appended in alphabetical order after the primary type:
    # TokenPermissions < Witness
    permit_typehash = Web3.keccak(
        text=(
            "PermitWitnessTransferFrom(TokenPermissions permitted,address spender,uint256 nonce,uint256 deadline,Witness witness)"
            "TokenPermissions(address token,uint256 amount)"
            "Witness(address to,uint256 validAfter,bytes extra)"
        )
    )

    token_permissions_hash = Web3.keccak(
        encode(
            ["bytes32", "address", "uint256"],
            [
                token_permissions_typehash,
                Web3.to_checksum_address(token_address),
                amount,
            ],
        )
    )

    witness_hash = Web3.keccak(
        encode(
            ["bytes32", "address", "uint256", "bytes32"],
            [
                witness_typehash,
                Web3.to_checksum_address(pay_to),
                valid_after,
                Web3.keccak(extra),
            ],
        )
    )

    struct_hash = Web3.keccak(
        encode(
            ["bytes32", "bytes32", "address", "uint256", "uint256", "bytes32"],
            [
                permit_typehash,
                token_permissions_hash,
                Web3.to_checksum_address(spender),
                nonce,
                deadline,
                witness_hash,
            ],
        )
    )

    digest = Web3.keccak(b"\x19\x01" + domain_separator + struct_hash)
    _, _, _, signature = sign_message_hash(account._key_obj, digest)
    return signature.hex()


async def main():
    endpoint = f"{SERVER_URL}/api/weather"
    w3 = Web3(Web3.HTTPProvider(RPC_URL))

    print("=" * 60)
    print("STEP 1: Request without payment (expect 402)")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(endpoint)
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")

        if resp.status_code != 402:
            print(f"Expected 402, got {resp.status_code}")
            print(f"Body: {resp.text}")
            return

        payment_required_b64 = resp.headers.get("payment-required") or resp.headers.get(
            "x-payment-required"
        )
        if not payment_required_b64:
            print("No Payment-Required header!")
            return

        payment_required = json.loads(base64.b64decode(payment_required_b64))
        print("\nDecoded Payment-Required:")
        print(json.dumps(payment_required, indent=2))

    print("\n" + "=" * 60)
    print("STEP 2: Create Permit2 (PermitWitnessTransferFrom) payment payload")
    print("=" * 60)

    accept = payment_required["accepts"][0]
    extra = accept.get("extra") or {}
    asset_transfer_method = extra.get("assetTransferMethod")
    if asset_transfer_method and asset_transfer_method != "permit2":
        raise RuntimeError(
            f"Unsupported assetTransferMethod={asset_transfer_method!r}; this PoC client only supports 'permit2'."
        )
    asset = accept["asset"]
    pay_to = Web3.to_checksum_address(accept["payTo"])
    amount_raw = accept.get("amount") or accept.get("maxAmountRequired")
    max_amount = int(amount_raw)

    token_address = Web3.to_checksum_address(asset)
    spender = Web3.to_checksum_address(X402_EXACT_PERMIT2_PROXY_ADDRESS)

    now = int(time.time())
    deadline = now + 3600
    valid_after = max(0, now - 10 * 60)
    nonce = secrets.randbits(256)
    extra = b""  # "0x"

    print(f"Token: {token_address}")
    print(f"Pay to (witness.to): {pay_to}")
    print(f"Amount: {max_amount}")
    print(f"Chain ID: {CHAIN_ID}")
    print(f"Permit2 proxy spender: {spender}")
    if spender.lower() == DEFAULT_X402_EXACT_PERMIT2_PROXY_ADDRESS.lower():
        print(
            "NOTE: Using default Etherlink proxy address. Override via "
            "X402_EXACT_PERMIT2_PROXY_ADDRESS if needed."
        )
    print(f"Nonce: {nonce}")
    print(f"Deadline: {deadline}")

    signature = sign_permit2_witness_transfer(
        w3=w3,
        token_address=token_address,
        spender=spender,
        amount=max_amount,
        nonce=nonce,
        deadline=deadline,
        pay_to=pay_to,
        valid_after=valid_after,
        extra=extra,
    )

    payment_payload = {
        "x402Version": 2,
        "accepted": accept,
        "resource": payment_required.get("resource"),
        "payload": {
            "signature": f"0x{signature}",
            "permit2Authorization": {
                "from": account.address,
                "permitted": {"token": token_address, "amount": str(max_amount)},
                "spender": spender,
                "nonce": str(nonce),
                "deadline": str(deadline),
                "witness": {
                    "to": pay_to,
                    "validAfter": str(valid_after),
                    "extra": "0x",
                },
            },
        },
    }

    payment_header = base64.b64encode(json.dumps(payment_payload).encode()).decode()
    print("\nPayment payload prepared (redacted):")
    print(
        json.dumps(
            {
                "x402Version": payment_payload["x402Version"],
                "accepted": payment_payload["accepted"],
                "payload": {
                    "permit2Authorization": payment_payload["payload"]["permit2Authorization"],
                    "signature": "[REDACTED]",
                },
                "paymentSignatureLength": len(payment_header),
            },
            indent=2,
        )
    )

    print("\n" + "=" * 60)
    print("STEP 3: Send request WITH payment")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(
            endpoint,
            headers={
                # V2 spec header name:
                "Payment-Signature": payment_header,
                # Legacy PoC compatibility:
                "X-PAYMENT": payment_header,
            },
        )
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        print("\nResponse body:")
        try:
            print(json.dumps(resp.json(), indent=2))
        except Exception:
            print(resp.text)

    print("\n" + "=" * 60)
    print("PROOF COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
