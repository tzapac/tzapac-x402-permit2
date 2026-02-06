#!/usr/bin/env python3
import asyncio
import base64
import json
import os
import secrets
import time

import httpx
from dotenv import load_dotenv
from eth_account import Account
from eth_account.messages import encode_typed_data

load_dotenv()

SERVER_URL = os.getenv("SERVER_URL", "http://localhost:8000")
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://exp-faci.etherlinkinsights.com")

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY required in .env")

account = Account.from_key(PRIVATE_KEY)
print(f"Client wallet: {account.address}")


def create_eip712_permit_signature(
    token_address: str,
    spender: str,
    value: int,
    deadline: int,
    nonce: int,
    chain_id: int,
    token_name: str = "BBT",
    token_version: str = "1",
) -> str:
    domain = {
        "name": token_name,
        "version": token_version,
        "chainId": chain_id,
        "verifyingContract": token_address,
    }

    types = {
        "EIP712Domain": [
            {"name": "name", "type": "string"},
            {"name": "version", "type": "string"},
            {"name": "chainId", "type": "uint256"},
            {"name": "verifyingContract", "type": "address"},
        ],
        "Permit": [
            {"name": "owner", "type": "address"},
            {"name": "spender", "type": "address"},
            {"name": "value", "type": "uint256"},
            {"name": "nonce", "type": "uint256"},
            {"name": "deadline", "type": "uint256"},
        ],
    }

    message = {
        "owner": account.address,
        "spender": spender,
        "value": value,
        "nonce": nonce,
        "deadline": deadline,
    }

    typed_data = {
        "types": types,
        "primaryType": "Permit",
        "domain": domain,
        "message": message,
    }

    signable = encode_typed_data(full_message=typed_data)
    signed = account.sign_message(signable)
    return signed.signature.hex()


async def main():
    endpoint = f"{SERVER_URL}/api/weather"

    print("=" * 60)
    print("STEP 1: Request without payment (expect 402)")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
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
    print("STEP 2: Create payment payload")
    print("=" * 60)

    accept = payment_required["accepts"][0]
    asset = accept["asset"]
    pay_to = accept["payTo"]
    max_amount = int(accept["maxAmountRequired"])

    token_address = asset.split("erc20:")[-1]
    chain_id = 42793

    deadline = int(time.time()) + 3600
    nonce_bytes = secrets.token_bytes(32)
    nonce_hex = "0x" + nonce_bytes.hex()
    nonce_int = int.from_bytes(nonce_bytes, "big")

    print(f"Token: {token_address}")
    print(f"Pay to: {pay_to}")
    print(f"Amount: {max_amount} wei")
    print(f"Chain ID: {chain_id}")

    signature = create_eip712_permit_signature(
        token_address=token_address,
        spender=pay_to,
        value=max_amount,
        deadline=deadline,
        nonce=nonce_int,
        chain_id=chain_id,
    )

    payment_payload = {
        "x402Version": 1,
        "scheme": "exact",
        "network": "etherlink",
        "payload": {
            "signature": f"0x{signature}",
            "authorization": {
                "from": account.address,
                "to": pay_to,
                "value": str(max_amount),
                "validAfter": "0",
                "validBefore": str(deadline),
                "nonce": nonce_hex,
            },
        },
    }

    print(f"\nPayment payload:")
    print(json.dumps(payment_payload, indent=2))

    payment_header = base64.b64encode(json.dumps(payment_payload).encode()).decode()

    print("\n" + "=" * 60)
    print("STEP 3: Send request WITH payment")
    print("=" * 60)

    async with httpx.AsyncClient() as client:
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
