import asyncio
import os

import httpx
from dotenv import load_dotenv
from eth_account import Account

from x402 import x402Client
from x402.http import (
    PAYMENT_REQUIRED_HEADER,
    PAYMENT_RESPONSE_HEADER,
    decode_payment_required_header,
    decode_payment_response_header,
)
from x402.http.clients import x402HttpxClient
from x402.mechanisms.evm.exact.register import register_exact_evm_client


load_dotenv()

STOREFRONT_URL = os.getenv("STOREFRONT_URL", "http://localhost:8000")
ENDPOINT = "/api/weather"
PRIVATE_KEY = os.getenv("PRIVATE_KEY")
ETHERLINK_CHAIN = "eip155:42793"

if not PRIVATE_KEY:
    raise ValueError("PRIVATE_KEY environment variable required")


async def main() -> None:
    url = f"{STOREFRONT_URL}{ENDPOINT}"

    print("STEP 1: Unpaid request (expect 402)")
    async with httpx.AsyncClient() as client:
        resp = await client.get(url)
        print(f"status={resp.status_code}")
        payment_required = resp.headers.get(PAYMENT_REQUIRED_HEADER)
        print(f"{PAYMENT_REQUIRED_HEADER}={payment_required}")
        if payment_required:
            decoded = decode_payment_required_header(payment_required)
            print("decoded_payment_required=")
            print(decoded.model_dump(by_alias=True))

    print("\nSTEP 2: Paid request (auto-handle 402)")
    account = Account.from_key(PRIVATE_KEY)
    client = x402Client()
    register_exact_evm_client(client, account.key, networks=ETHERLINK_CHAIN)

    async with x402HttpxClient(client) as paid_client:
        paid_resp = await paid_client.get(url)
        print(f"status={paid_resp.status_code}")
        payment_response = paid_resp.headers.get(PAYMENT_RESPONSE_HEADER)
        print(f"{PAYMENT_RESPONSE_HEADER}={payment_response}")
        if payment_response:
            decoded_response = decode_payment_response_header(payment_response)
            print("decoded_payment_response=")
            print(decoded_response.model_dump(by_alias=True))
        print("response_body=")
        print(paid_resp.text)


if __name__ == "__main__":
    asyncio.run(main())
