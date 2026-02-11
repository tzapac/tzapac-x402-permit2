"""Manual x402 Payment Flow Test Script."""

import asyncio
import base64
import json
from eth_account import Account
from dotenv import load_dotenv
import httpx
import os

load_dotenv()

STOREFRONT_URL = "http://localhost:8000"
FACILITATOR_URL = "http://localhost:9090"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ETHERLINK_CHAIN = "eip155:42793"
BBT_TOKEN = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
SERVER_WALLET = "0x81C54dB7690016b2b0c3017a4981783964601bd9"

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY needed")

account = Account.from_key(PRIVATE_KEY)
print(f"Wallet: {account.address}")
print(f"Target: {STOREFRONT_URL}/api/weather\n")


async def manual_x402_flow():
    async with httpx.AsyncClient() as http:
        print("=== Step 1: GET /api/weather (expecting 402) ===")
        resp = await http.get(f"{STOREFRONT_URL}/api/weather")
        print(f"Status: {resp.status_code}")

        if resp.status_code != 402:
            print("ERROR: Expected 402 Payment Required")
            return

        payment_required = resp.headers.get("Payment-Required") or resp.headers.get(
            "payment-required"
        )
        if not payment_required:
            print("ERROR: No Payment-Required header found")
            return

        print(f"Payment-Required header (first 50 chars): {payment_required[:50]}...")

        try:
            requirements_bytes = base64.b64decode(payment_required)
            requirements = json.loads(requirements_bytes)
            print(f"\n=== Payment Requirements ===")
            print(json.dumps(requirements, indent=2))
        except Exception as e:
            print(f"ERROR decoding requirements: {e}")
            return

        print("\n=== Step 2: Create payment payload ===")
        # For EIP-2612 permit, we need to sign a permit
        # This is a simplified example - real implementation uses proper EIP-712 signing
        payment_payload = {
            "network": requirements.get("network"),
            "scheme": requirements.get("scheme"),
            "price": requirements.get("price"),
            "payTo": requirements.get("pay_to"),
            "signer": account.address,
            "timestamp": asyncio.get_event_loop().time(),
        }

        payload_json = json.dumps(payment_payload, separators=(",", ":"))
        signature_hex = account.sign_message(payload_json.encode()).signature.hex()

        print(f"Payment payload: {json.dumps(payment_payload, indent=2)}")
        print(f"Signature: {signature_hex[:30]}...")

        payment_signature_b64 = base64.b64encode(
            json.dumps(
                {"payload": payment_payload, "signature": signature_hex}
            ).encode()
        ).decode()

        print(f"\n=== Step 3: Send Payment-Signature header ===")
        resp2 = await http.get(
            f"{STOREFRONT_URL}/api/weather",
            headers={"Payment-Signature": payment_signature_b64},
        )

        print(f"\nStatus: {resp2.status_code}")
        print(f"Response: {resp2.json()}")

        return resp2


if __name__ == "__main__":
    asyncio.run(manual_x402_flow())
