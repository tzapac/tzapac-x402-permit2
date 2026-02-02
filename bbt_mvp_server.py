#!/usr/bin/env python3
import base64
import json
import os

import httpx
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
http_client = httpx.AsyncClient(timeout=120.0)

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:9090")
SERVER_WALLET = os.getenv("SERVER_WALLET", "0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F")
BBT_TOKEN = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
NETWORK = "eip155:42793"

PAYMENT_REQUIRED = {
    "x402Version": 2,
    "accepts": [
        {
            "scheme": "exact",
            "network": NETWORK,
            "amount": "10000000000000000",
            "resource": "http://localhost:8001/api/weather",
            "description": "Weather data access",
            "mimeType": "application/json",
            "payTo": SERVER_WALLET,
            "maxTimeoutSeconds": 60,
            "asset": f"{NETWORK}/erc20:{BBT_TOKEN}",
            "extra": {"name": "BBT", "version": "1"},
        }
    ],
    "error": None,
}


@app.get("/")
async def root():
    return {
        "status": "BBT Permit2 MVP x402 Server",
        "network": NETWORK,
        "facilitator": FACILITATOR_URL,
    }


@app.get("/api/weather")
async def weather(request: Request):
    payment_header = request.headers.get("X-PAYMENT") or request.headers.get(
        "x-payment"
    )

    if not payment_header:
        payload = base64.b64encode(json.dumps(PAYMENT_REQUIRED).encode()).decode()
        return Response(
            content=json.dumps(
                {"error": "Payment Required", "message": "Send X-PAYMENT header"}
            ),
            status_code=402,
            headers={"X-PAYMENT-REQUIRED": payload},
            media_type="application/json",
        )

    try:
        payment_payload = json.loads(base64.b64decode(payment_header))
        print(f"Received payment: {json.dumps(payment_payload, indent=2)}")
    except Exception as e:
        return Response(
            content=json.dumps({"error": f"Invalid payment header: {e}"}),
            status_code=400,
            media_type="application/json",
        )

    requirements_for_facilitator = PAYMENT_REQUIRED["accepts"][0].copy()
    requirements_for_facilitator["x402Version"] = 2
    requirements_for_facilitator["network"] = NETWORK
    requirements_for_facilitator["asset"] = BBT_TOKEN

    if isinstance(payment_payload, dict):
        payment_payload["accepted"] = requirements_for_facilitator

    settle_request = {
        "x402Version": 2,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements_for_facilitator,
    }

    print(f"Calling facilitator /settle: {FACILITATOR_URL}/settle")
    print(f"Settle request: {json.dumps(settle_request, indent=2)}")

    try:
        settle_resp = await http_client.post(
            f"{FACILITATOR_URL}/settle",
            json=settle_request,
        )
        settle_data = settle_resp.json()
        if isinstance(settle_data, str):
            try:
                settle_data = json.loads(settle_data)
            except json.JSONDecodeError:
                settle_data = {"raw": settle_data}

        if not isinstance(settle_data, dict):
            return Response(
                content=json.dumps(
                    {
                        "error": "Settlement failed",
                        "facilitator_response": settle_data,
                    }
                ),
                status_code=402,
                media_type="application/json",
            )
        print(
            f"Facilitator response ({settle_resp.status_code}): {json.dumps(settle_data, indent=2)}"
        )

        if settle_resp.status_code != 200:
            return Response(
                content=json.dumps(
                    {
                        "error": "Settlement failed",
                        "facilitator_response": settle_data,
                    }
                ),
                status_code=402,
                media_type="application/json",
            )

        tx_hash = settle_data.get("txHash") or settle_data.get("transaction", {}).get(
            "hash"
        )

    except Exception as e:
        print(f"Facilitator error: {e}")
        return Response(
            content=json.dumps({"error": f"Facilitator error: {e}"}),
            status_code=500,
            media_type="application/json",
        )

    response_payload = {
        "success": True,
        "txHash": tx_hash,
        "network": NETWORK,
        "explorer": f"https://explorer.etherlink.com/tx/{tx_hash}" if tx_hash else None,
    }
    x_payment_response = base64.b64encode(
        json.dumps(response_payload).encode()
    ).decode()

    return Response(
        content=json.dumps(
            {
                "weather": "sunny",
                "temperature": 25,
                "location": "Etherlink",
                "payment_settled": True,
                "txHash": tx_hash,
                "explorer": f"https://explorer.etherlink.com/tx/{tx_hash}"
                if tx_hash
                else None,
            }
        ),
        status_code=200,
        headers={"X-PAYMENT-RESPONSE": x_payment_response},
        media_type="application/json",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
