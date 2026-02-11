#!/usr/bin/env python3
import base64
import json
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv
from web3 import Web3

from logging_utils import get_logger, log_json

load_dotenv()

app = FastAPI()
http_client = httpx.AsyncClient(timeout=120.0)
logger = get_logger("bbt_mvp_server")

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:9090")
PUBLIC_BASE_URL = os.getenv("PUBLIC_BASE_URL", "").strip()
SERVER_WALLET_ENV = os.getenv("SERVER_WALLET")
STORE_ADDRESS_ENV = os.getenv("STORE_ADDRESS")
STORE_PRIVATE_KEY_ENV = os.getenv("STORE_PRIVATE_KEY")
BBT_TOKEN = os.getenv("BBT_TOKEN", "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6")
X402_EXACT_PERMIT2_PROXY_ADDRESS = os.getenv(
    "X402_EXACT_PERMIT2_PROXY_ADDRESS",
    "0xB6FD384A0626BfeF85f3dBaf5223Dd964684B09E",
)
NETWORK = "eip155:42793"
MAX_PAYMENT_SIGNATURE_B64_BYTES = int(
    os.getenv("MAX_PAYMENT_SIGNATURE_B64_BYTES", "16384")
)
MAX_SETTLE_RESPONSE_BYTES = int(os.getenv("MAX_SETTLE_RESPONSE_BYTES", "65536"))


def _resolve_server_wallet() -> str:
    if SERVER_WALLET_ENV:
        return SERVER_WALLET_ENV
    if STORE_ADDRESS_ENV:
        return STORE_ADDRESS_ENV
    if STORE_PRIVATE_KEY_ENV:
        return Web3().eth.account.from_key(STORE_PRIVATE_KEY_ENV).address
    raise RuntimeError(
        "Missing payout wallet config: set SERVER_WALLET, STORE_ADDRESS, or STORE_PRIVATE_KEY"
    )


def _to_checksum(raw: str, field_name: str) -> str:
    try:
        return Web3.to_checksum_address(raw)
    except Exception as exc:
        raise RuntimeError(f"Invalid {field_name}: {raw}") from exc


def _same_address(a: str, b: str) -> bool:
    return str(a).lower() == str(b).lower()


SERVER_WALLET = _to_checksum(_resolve_server_wallet(), "server wallet")
BBT_TOKEN = _to_checksum(BBT_TOKEN, "BBT_TOKEN")
X402_EXACT_PERMIT2_PROXY_ADDRESS = _to_checksum(
    X402_EXACT_PERMIT2_PROXY_ADDRESS, "X402_EXACT_PERMIT2_PROXY_ADDRESS"
)

PAYMENT_REQUIREMENTS = {
    "scheme": "exact",
    "network": NETWORK,
    "amount": "10000000000000000",
    "payTo": SERVER_WALLET,
    "maxTimeoutSeconds": 60,
    # Coinbase/x402 v2 uses the raw token address in `asset`.
    "asset": BBT_TOKEN,
    # Coinbase-style hint to clients about the intended settlement path.
    "extra": {"name": "BBT", "version": "1", "assetTransferMethod": "permit2"},
}

def _resource_url(request: Request) -> str:
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}/api/weather"
    return f"{str(request.base_url).rstrip('/')}/api/weather"


def _payment_required(request: Request) -> dict:
    return {
        "x402Version": 2,
        "accepts": [PAYMENT_REQUIREMENTS],
        "resource": {
            "description": "Weather data access",
            "mimeType": "application/json",
            "url": _resource_url(request),
        },
        "error": None,
    }


def _get_payment_header(request: Request) -> str | None:
    # V2 spec: Payment-Signature
    return request.headers.get("Payment-Signature") or request.headers.get(
        "payment-signature"
    )


def _requirements_match(accepted: dict, required: dict) -> bool:
    # Coinbase/x402 v2 requires the accepted requirements to match one offered in accepts[].
    if not isinstance(accepted, dict) or not isinstance(required, dict):
        return False
    # Strict key/value equality on the requirements object.
    return accepted == required

def _extract_permit2_payload(payment_payload: dict) -> dict | None:
    if not isinstance(payment_payload, dict):
        return None
    payload = payment_payload.get("payload")
    if not isinstance(payload, dict):
        return None
    # Coinbase x402 witness flow: SignatureTransfer (PermitWitnessTransferFrom)
    permit2_auth = payload.get("permit2Authorization")
    signature = payload.get("signature")
    if isinstance(permit2_auth, dict) and signature:
        return {
            "permit2Authorization": permit2_auth,
            "signature": signature,
        }

    return None


@app.get("/")
async def root():
    return {
        "status": "BBT Permit2 MVP x402 Server",
        "network": NETWORK,
        "facilitator": FACILITATOR_URL,
    }


@app.get("/config")
async def config():
    return {
        "x402Version": 2,
        "scheme": "exact",
        "network": NETWORK,
        "asset": BBT_TOKEN,
        "payTo": SERVER_WALLET,
        "amount": PAYMENT_REQUIREMENTS["amount"],
        "facilitatorUrl": FACILITATOR_URL,
    }


@app.get("/api/weather")
async def weather(request: Request):
    payment_header = _get_payment_header(request)
    gas_payer_header = request.headers.get("X-GAS-PAYER") or request.headers.get(
        "x-gas-payer"
    )
    gas_payer = gas_payer_header.lower() if gas_payer_header else "auto"

    if not payment_header:
        payload = base64.b64encode(json.dumps(_payment_required(request)).encode()).decode()
        return Response(
            content=json.dumps(
                {
                    "error": "Payment Required",
                    "message": "Send Payment-Signature header",
                }
            ),
            status_code=402,
            # V2: Payment-Required (base64 encoded PaymentRequired JSON)
            headers={"Payment-Required": payload},
            media_type="application/json",
        )

    try:
        if len(payment_header) > MAX_PAYMENT_SIGNATURE_B64_BYTES:
            raise ValueError("Payment-Signature header too large")
        decoded_payload = base64.b64decode(payment_header, validate=True)
        payment_payload = json.loads(decoded_payload)
        log_json(logger, logging.DEBUG, "Received payment payload", payment_payload)
    except Exception as e:
        logger.warning("Invalid payment header: %s", e)
        return Response(
            content=json.dumps({"error": f"Invalid payment header: {e}"}),
            status_code=400,
            media_type="application/json",
        )

    requirements_for_facilitator = PAYMENT_REQUIREMENTS.copy()

    if not isinstance(payment_payload, dict):
        return Response(
            content=json.dumps({"error": "Invalid payment payload"}),
            status_code=400,
            media_type="application/json",
        )

    accepted = payment_payload.get("accepted")
    if not isinstance(accepted, dict):
        return Response(
            content=json.dumps(
                {
                    "error": "Missing accepted requirements in payment payload (x402 v2)",
                }
            ),
            status_code=402,
            media_type="application/json",
        )

    if not _requirements_match(accepted, PAYMENT_REQUIREMENTS):
        return Response(
            content=json.dumps(
                {
                    "error": "Accepted requirements do not match offered requirements",
                    "offered": PAYMENT_REQUIREMENTS,
                    "accepted": accepted,
                }
            ),
            status_code=402,
            media_type="application/json",
        )

    permit2_payload = _extract_permit2_payload(payment_payload)
    if not permit2_payload:
        return Response(
            content=json.dumps({"error": "Missing permit2 payload"}),
            status_code=400,
            media_type="application/json",
        )

    pay_to = requirements_for_facilitator.get("payTo")
    if not pay_to:
        return Response(
            content=json.dumps({"error": "Missing payTo in requirements"}),
            status_code=400,
            media_type="application/json",
        )

    permit2_auth = permit2_payload.get("permit2Authorization", {}) or {}
    permitted = permit2_auth.get("permitted", {}) or {}
    witness = permit2_auth.get("witness", {}) or {}

    owner = permit2_auth.get("from")
    spender = permit2_auth.get("spender")
    token = permitted.get("token")
    amount_raw = permitted.get("amount")

    witness_to = witness.get("to")
    if not witness_to:
        return Response(
            content=json.dumps({"error": "Missing witness.to in permit2Authorization"}),
            status_code=402,
            media_type="application/json",
        )
    if not _same_address(witness_to, pay_to):
        return Response(
            content=json.dumps(
                {"error": "Recipient mismatch (witness.to must equal payTo)"}
            ),
            status_code=402,
            media_type="application/json",
        )
    if not _same_address(spender, X402_EXACT_PERMIT2_PROXY_ADDRESS):
        return Response(
            content=json.dumps(
                {
                    "error": "Invalid spender for witness flow (must be configured x402 proxy)",
                }
            ),
            status_code=402,
            media_type="application/json",
        )

    if not owner or not spender or not token or amount_raw is None:
        return Response(
            content=json.dumps({"error": "Incomplete permit2 payload"}),
            status_code=400,
            media_type="application/json",
        )
    try:
        owner = _to_checksum(owner, "payment owner")
        spender = _to_checksum(spender, "payment spender")
        token = _to_checksum(token, "payment token")
    except RuntimeError as exc:
        return Response(
            content=json.dumps({"error": str(exc)}),
            status_code=400,
            media_type="application/json",
        )

    try:
        required_amount = int(requirements_for_facilitator.get("amount", "0"))
        payment_amount = int(amount_raw)
    except (TypeError, ValueError):
        return Response(
            content=json.dumps({"error": "Invalid payment amount"}),
            status_code=400,
            media_type="application/json",
        )

    if payment_amount != required_amount:
        return Response(
            content=json.dumps({"error": "Payment amount mismatch"}),
            status_code=402,
            media_type="application/json",
        )

    required_asset = requirements_for_facilitator.get("asset")
    if not required_asset or not _same_address(token, required_asset):
        return Response(
            content=json.dumps({"error": "Payment asset mismatch"}),
            status_code=402,
            media_type="application/json",
        )

    if gas_payer not in {"facilitator", "auto"}:
        return Response(
            content=json.dumps({"error": "Only facilitator gas mode is supported"}),
            status_code=400,
            media_type="application/json",
        )

    gas_payer = "facilitator"
    logger.info("Gas payer mode: %s", gas_payer)

    settle_request = {
        "x402Version": 2,
        "paymentPayload": payment_payload,
        "paymentRequirements": requirements_for_facilitator,
    }

    logger.info("Calling facilitator /settle: %s/settle", FACILITATOR_URL)
    log_json(logger, logging.DEBUG, "Settle request", settle_request)

    try:
        settle_resp = await http_client.post(
            f"{FACILITATOR_URL}/settle",
            json=settle_request,
        )
        settle_bytes = settle_resp.content or b""
        if len(settle_bytes) > MAX_SETTLE_RESPONSE_BYTES:
            return Response(
                content=json.dumps({"error": "Settlement response too large"}),
                status_code=502,
                media_type="application/json",
            )
        settle_text = settle_bytes.decode("utf-8", errors="replace")
        try:
            settle_data = settle_resp.json()
        except Exception:
            try:
                settle_data = json.loads(settle_text)
            except json.JSONDecodeError:
                settle_data = {"raw": settle_text}

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
        log_json(
            logger,
            logging.DEBUG,
            f"Facilitator response ({settle_resp.status_code})",
            settle_data,
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

        tx_hash = None
        tx_hash = settle_data.get("txHash")
        if not tx_hash:
            transaction = settle_data.get("transaction")
            if isinstance(transaction, dict):
                tx_hash = transaction.get("hash")
            elif isinstance(transaction, str):
                if transaction.startswith("0x") and len(transaction) == 66:
                    tx_hash = transaction

    except Exception as e:
        logger.exception("Facilitator error: %s", e)
        return Response(
            content=json.dumps({"error": f"Facilitator error: {e}"}),
            status_code=500,
            media_type="application/json",
        )

    response_payload = {
        "success": True,
        "txHash": tx_hash,
        "gasPayer": gas_payer,
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
        # Match x402-axum's response header name.
        headers={"X-Payment-Response": x_payment_response},
        media_type="application/json",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
