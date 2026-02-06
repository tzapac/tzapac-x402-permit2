"""X402 BBT Token Storefront on Etherlink."""

import os

from logging_utils import get_logger

from fastapi import FastAPI, Request

from x402.http import HTTPFacilitatorClient
from x402.http.middleware.fastapi import PaymentMiddlewareASGI
from x402.mechanisms.evm.exact.register import register_exact_evm_server
from x402.server import x402ResourceServer

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "https://exp-faci.etherlinkinsights.com")
ETHERLINK_CHAIN = "eip155:42793"
BBT_TOKEN_ADDRESS = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
SERVER_WALLET = os.getenv("SERVER_WALLET", "0x81C54dB7690016b2b0c3017a4981783964601bd9")

app = FastAPI(
    title="BBT Token Storefront",
    description="Accept BBT payments on Etherlink via x402 protocol",
    version="1.0.0",
)

logger = get_logger("bbt_storefront")

facilitator_client = HTTPFacilitatorClient(config={"url": FACILITATOR_URL})
resource_server = x402ResourceServer(facilitator_client)

register_exact_evm_server(resource_server, ETHERLINK_CHAIN)

routes_config = {
    "GET /api/weather": {
        "accepts": [
            {
                "scheme": "exact",
                "price": "$0.01",
                "network": ETHERLINK_CHAIN,
                "pay_to": SERVER_WALLET,
                "token": BBT_TOKEN_ADDRESS,
            }
        ],
        "description": "Get current weather data",
        "mime_type": "application/json",
    },
    "GET /api/premium-content": {
        "accepts": [
            {
                "scheme": "exact",
                "price": "$0.05",
                "network": ETHERLINK_CHAIN,
                "pay_to": SERVER_WALLET,
                "token": BBT_TOKEN_ADDRESS,
            }
        ],
        "description": "Access premium content",
        "mime_type": "application/json",
    },
}

app.add_middleware(PaymentMiddlewareASGI, routes=routes_config, server=resource_server)


@app.get("/")
async def root():
    return {
        "message": "BBT Token Storefront - Accepting payments on Etherlink",
        "currency": "BBT (bbtez)",
        "network": "Etherlink (chain 42793)",
        "facilitator": FACILITATOR_URL,
        "available_endpoints": list(routes_config.keys()),
    }


@app.get("/health")
async def health():
    return {"status": "healthy", "facilitator": FACILITATOR_URL}


@app.get("/api/weather")
async def get_weather(request: Request):
    return {
        "location": "Singapore",
        "temperature": 32,
        "condition": "Partly Cloudy",
        "currency": "BBT",
        "payment_status": "verified",
        "payment_amount": "$0.01",
    }


@app.get("/api/premium-content")
async def get_premium_content(request: Request):
    return {
        "content": "This is premium content accessible only after x402 payment",
        "currency": "BBT",
        "payment_status": "verified",
        "payment_amount": "$0.05",
    }


if __name__ == "__main__":
    import uvicorn

    logger.info("Starting BBT Token Storefront on port 8000")
    logger.info("Facilitator: %s", FACILITATOR_URL)
    logger.info("Network: %s", ETHERLINK_CHAIN)
    logger.info("BBT Token: %s", BBT_TOKEN_ADDRESS)
    uvicorn.run(app, host="0.0.0.0", port=8000)
