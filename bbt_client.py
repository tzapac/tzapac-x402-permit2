"""Legacy SDK client example (not the Coinbase-aligned Permit2 witness path)."""

import asyncio
import os

from dotenv import load_dotenv
from eth_account import Account
from x402.client import x402Client
from x402.mechanisms.evm.exact.register import register_exact_evm_client

load_dotenv()

STOREFRONT_URL = os.getenv("STOREFRONT_URL", "http://localhost:9091")
ETHERLINK_CHAIN = "eip155:42793"
BBT_TOKEN_ADDRESS = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY environment variable required")

account = Account.from_key(PRIVATE_KEY)

print(f"Test wallet address: {account.address}")
print(f"Target endpoint: {STOREFRONT_URL}/api/weather")
print(f"Network: {ETHERLINK_CHAIN}")
print(f"BBT Token: {BBT_TOKEN_ADDRESS}")


async def test_x402_payment():
    client = x402Client()
    register_exact_evm_client(client, account.key, networks=ETHERLINK_CHAIN)

    try:
        response = await client.fetch("GET", STOREFRONT_URL + "/api/weather")
        print(f"Response status: {response.status_code}")
        print(f"Response body: {await response.text()}")
        return response
    except Exception as e:
        print(f"Error: {type(e).__name__}: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("Testing x402 payment flow with BBT token...")
    asyncio.run(test_x402_payment())
