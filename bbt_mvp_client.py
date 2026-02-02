#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import time

import httpx
from dotenv import load_dotenv
from eth_account import Account
from web3 import Web3
from eth_abi.abi import encode
from eth_account._utils.signing import sign_message_hash

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8001")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
RPC_URL = os.getenv("NODE_URL", os.getenv("RPC_URL", "https://rpc.bubbletez.com"))

PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
CHAIN_ID = 42793

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY required in .env")

account = Account.from_key(PRIVATE_KEY)
print(f"Client wallet: {account.address}")


def get_permit2_nonce(w3: Web3, owner: str, token: str, spender: str) -> int:
    permit2_abi = [
        {
            "inputs": [
                {"internalType": "address", "name": "owner", "type": "address"},
                {"internalType": "address", "name": "token", "type": "address"},
                {"internalType": "address", "name": "spender", "type": "address"},
            ],
            "name": "allowance",
            "outputs": [
                {"internalType": "uint160", "name": "amount", "type": "uint160"},
                {"internalType": "uint48", "name": "expiration", "type": "uint48"},
                {"internalType": "uint48", "name": "nonce", "type": "uint48"},
            ],
            "stateMutability": "view",
            "type": "function",
        }
    ]
    permit2 = w3.eth.contract(
        address=Web3.to_checksum_address(PERMIT2_ADDRESS),
        abi=permit2_abi,
    )
    _, _, nonce = permit2.functions.allowance(owner, token, spender).call()
    return int(nonce)


def sign_permit2_with_domain_separator(
    w3: Web3,
    token_address: str,
    spender: str,
    amount: int,
    expiration: int,
    nonce: int,
    sig_deadline: int,
) -> str:
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
    domain_separator = permit2.functions.DOMAIN_SEPARATOR().call()

    details_typehash = Web3.keccak(
        text="PermitDetails(address token,uint160 amount,uint48 expiration,uint48 nonce)"
    )
    single_typehash = Web3.keccak(
        text=(
            "PermitSingle(PermitDetails details,address spender,uint256 sigDeadline)"
            "PermitDetails(address token,uint160 amount,uint48 expiration,uint48 nonce)"
        )
    )

    details_hash = Web3.keccak(
        encode(
            ["bytes32", "address", "uint160", "uint48", "uint48"],
            [
                details_typehash,
                Web3.to_checksum_address(token_address),
                amount,
                expiration,
                nonce,
            ],
        )
    )

    struct_hash = Web3.keccak(
        encode(
            ["bytes32", "bytes32", "address", "uint256"],
            [
                single_typehash,
                details_hash,
                Web3.to_checksum_address(spender),
                sig_deadline,
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

        payment_required_b64 = resp.headers.get("x-payment-required")
        if not payment_required_b64:
            print("No X-PAYMENT-REQUIRED header!")
            return

        payment_required = json.loads(base64.b64decode(payment_required_b64))
        print(f"\nDecoded X-PAYMENT-REQUIRED:")
        print(json.dumps(payment_required, indent=2))

    print("\n" + "=" * 60)
    print("STEP 2: Create Permit2 payment payload")
    print("=" * 60)

    accept = payment_required["accepts"][0]
    asset = accept["asset"]
    pay_to = Web3.to_checksum_address(accept["payTo"])
    max_amount = int(accept.get("amount") or accept.get("maxAmountRequired"))
    network = accept["network"]

    token_address = Web3.to_checksum_address(asset.split("erc20:")[-1])

    # With current facilitator code, spender must == payTo
    # This is a limitation we work around by using payTo as spender
    spender = pay_to
    print(f"Permit2 spender (must == payTo for this facilitator): {spender}")

    now = int(time.time())
    sig_deadline = now + 3600
    expiration = now + 3600
    nonce = get_permit2_nonce(w3, account.address, token_address, spender)

    print(f"Token: {token_address}")
    print(f"Pay to: {pay_to}")
    print(f"Amount: {max_amount} wei")
    print(f"Chain ID: {CHAIN_ID}")
    print(f"Permit2 nonce: {nonce}")

    signature = sign_permit2_with_domain_separator(
        w3=w3,
        token_address=token_address,
        spender=spender,
        amount=max_amount,
        expiration=expiration,
        nonce=nonce,
        sig_deadline=sig_deadline,
    )

    payment_payload = {
        "x402Version": 2,
        "scheme": "exact",
        "network": "eip155:42793",
        "payload": {
            "permit2": {
                "owner": account.address,
                "permitSingle": {
                    "details": {
                        "token": token_address,
                        "amount": max_amount,
                        "expiration": expiration,
                        "nonce": nonce,
                    },
                    "spender": spender,
                    "sigDeadline": sig_deadline,
                },
                "signature": f"0x{signature}",
            }
        },
    }

    print(f"\nPayment payload:")
    print(json.dumps(payment_payload, indent=2))

    payment_header = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    print("\n" + "=" * 60)
    print("STEP 3: Send request WITH payment")
    print("=" * 60)

    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.get(endpoint, headers={"X-PAYMENT": payment_header})
        print(f"Status: {resp.status_code}")
        print(f"Headers: {dict(resp.headers)}")
        print(f"\nResponse body:")
        print(json.dumps(resp.json(), indent=2))

    print("\n" + "=" * 60)
    print("PROOF COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
