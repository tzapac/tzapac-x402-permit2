#!/usr/bin/env python3
import base64
import copy
import json
import logging
import os
import re
import time
import uuid
from decimal import Decimal
from typing import Any

import httpx
from eth_account.messages import encode_defunct
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv
from web3 import Web3

from logging_utils import get_logger, log_json

load_dotenv()

app = FastAPI()
http_client = httpx.AsyncClient(timeout=120.0)
logger = get_logger("bbt_mvp_server")


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


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
NETWORK = os.getenv("NETWORK", "eip155:42793").strip()
EXPLORER_TX_BASE_URL = os.getenv("EXPLORER_TX_BASE_URL", "https://explorer.etherlink.com/tx").strip()
MAX_PAYMENT_SIGNATURE_B64_BYTES = int(
    os.getenv("MAX_PAYMENT_SIGNATURE_B64_BYTES", "16384")
)
MAX_SETTLE_RESPONSE_BYTES = int(os.getenv("MAX_SETTLE_RESPONSE_BYTES", "65536"))
RPC_URL = os.getenv("RPC_URL", "").strip()
CUSTOM_PRODUCTS_ENABLED = _env_bool("CUSTOM_PRODUCTS_ENABLED", True)
CUSTOM_PRODUCT_TTL_SECONDS = int(os.getenv("CUSTOM_PRODUCT_TTL_SECONDS", "86400"))
CUSTOM_PRODUCT_MAX_PER_CREATOR = int(os.getenv("CUSTOM_PRODUCT_MAX_PER_CREATOR", "5"))
CUSTOM_PRODUCT_MAX_GLOBAL = int(os.getenv("CUSTOM_PRODUCT_MAX_GLOBAL", "500"))
CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR = int(
    os.getenv("CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR", "30")
)
CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS = int(
    os.getenv("CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS", "300")
)

CUSTOM_PRODUCT_TIERS: dict[str, dict[str, str]] = {
    "tier_0_01": {"label": "0.01", "amount": "0.01"},
    "tier_0_1": {"label": "0.1", "amount": "0.1"},
    "tier_1_0": {"label": "1.0", "amount": "1.0"},
}

CREATE_RATE_WINDOW_SECONDS = 3600
CUSTOM_CREATE_CLOCK_SKEW_SECONDS = 60


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


def _to_checksum_strict(raw: Any, field_name: str) -> str:
    if not isinstance(raw, str):
        raise RuntimeError(f"Invalid {field_name}: must be a string")
    address = _to_checksum(raw, field_name)
    if not Web3.is_checksum_address(raw):
        raise RuntimeError(f"Invalid {field_name}: must be checksum address")
    return address


SERVER_WALLET = _to_checksum(_resolve_server_wallet(), "server wallet")
BBT_TOKEN = _to_checksum(BBT_TOKEN, "BBT_TOKEN")
X402_EXACT_PERMIT2_PROXY_ADDRESS = _to_checksum(
    X402_EXACT_PERMIT2_PROXY_ADDRESS, "X402_EXACT_PERMIT2_PROXY_ADDRESS"
)
network_match = re.match(r"^eip155:(\d+)$", NETWORK)
if not network_match:
    raise RuntimeError(
        f"Invalid NETWORK value: {NETWORK!r}. Expected format eip155:<chainId>"
    )
CHAIN_ID = int(network_match.group(1))

if CUSTOM_PRODUCTS_ENABLED and not RPC_URL:
    raise RuntimeError("RPC_URL is required when CUSTOM_PRODUCTS_ENABLED=true")

if CUSTOM_PRODUCT_TTL_SECONDS <= 0:
    raise RuntimeError("CUSTOM_PRODUCT_TTL_SECONDS must be > 0")
if CUSTOM_PRODUCT_MAX_PER_CREATOR <= 0:
    raise RuntimeError("CUSTOM_PRODUCT_MAX_PER_CREATOR must be > 0")
if CUSTOM_PRODUCT_MAX_GLOBAL <= 0:
    raise RuntimeError("CUSTOM_PRODUCT_MAX_GLOBAL must be > 0")
if CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR <= 0:
    raise RuntimeError("CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR must be > 0")
if CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS <= 0:
    raise RuntimeError("CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS must be > 0")

CUSTOM_PRODUCTS_BY_ID: dict[str, dict[str, Any]] = {}
CUSTOM_PRODUCTS_BY_CREATOR: dict[str, set[str]] = {}
USED_CREATE_NONCES: dict[str, dict[str, int]] = {}
CREATE_RATE_LIMIT_BY_IP: dict[str, list[int]] = {}

def _payment_requirements(amount_wei: str) -> dict[str, Any]:
    return {
        "scheme": "exact",
        "network": NETWORK,
        "amount": amount_wei,
        "payTo": SERVER_WALLET,
        "maxTimeoutSeconds": 60,
        # Coinbase/x402 v2 uses the raw token address in `asset`.
        "asset": BBT_TOKEN,
        # Coinbase-style hint to clients about the intended settlement path.
        "extra": {"name": "BBT", "version": "1", "assetTransferMethod": "permit2"},
    }


PRODUCTS: dict[str, dict[str, Any]] = {
    "weather": {
        "id": "weather",
        "name": "Weather Snapshot",
        "path": "/api/weather",
        "description": "Weather data access",
        "requirements": _payment_requirements("10000000000000000"),
        "response": {
            "weather": "sunny",
            "temperature": 25,
            "location": "Etherlink",
        },
    },
    "premium-content": {
        "id": "premium-content",
        "name": "Premium Content",
        "path": "/api/premium-content",
        "description": "Premium content access",
        "requirements": _payment_requirements("50000000000000000"),
        "response": {
            "content": "Premium x402 content unlocked",
            "tier": "premium",
            "location": "Etherlink",
        },
    },
}

DEFAULT_PRODUCT_ID = "weather"


def _public_base_from_headers(request: Request) -> str:
    forwarded_proto = (request.headers.get("x-forwarded-proto") or "").split(",")[0].strip().lower()
    forwarded_host = (request.headers.get("x-forwarded-host") or request.headers.get("host") or "").split(",")[0].strip()

    if forwarded_proto not in ("http", "https"):
        cf_visitor = (request.headers.get("cf-visitor") or "").lower()
        if '"scheme":"https"' in cf_visitor:
            forwarded_proto = "https"
        elif '"scheme":"http"' in cf_visitor:
            forwarded_proto = "http"

    if forwarded_host and forwarded_proto in ("http", "https"):
        return f"{forwarded_proto}://{forwarded_host}"
    if forwarded_host:
        return f"{request.url.scheme}://{forwarded_host}"
    return str(request.base_url).rstrip("/")


def _resource_url(request: Request, path: str) -> str:
    normalized_path = path if path.startswith("/") else f"/{path}"
    if PUBLIC_BASE_URL:
        return f"{PUBLIC_BASE_URL.rstrip('/')}" + normalized_path
    return f"{_public_base_from_headers(request)}" + normalized_path


def _explorer_url(tx_hash: str | None) -> str | None:
    if not tx_hash:
        return None
    base = EXPLORER_TX_BASE_URL.rstrip("/")
    return f"{base}/{tx_hash}"


def _client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        return forwarded_for.split(",")[0].strip()
    if request.client and request.client.host:
        return request.client.host
    return "unknown"


def _cleanup_custom_state(now: int | None = None) -> None:
    now_ts = int(time.time()) if now is None else now

    expired_product_ids = [
        product_id
        for product_id, product in CUSTOM_PRODUCTS_BY_ID.items()
        if int(product.get("expiresAt", 0) or 0) <= now_ts
    ]
    for product_id in expired_product_ids:
        product = CUSTOM_PRODUCTS_BY_ID.pop(product_id, None)
        if not product:
            continue
        creator_key = str(product.get("creator", "")).lower()
        creator_products = CUSTOM_PRODUCTS_BY_CREATOR.get(creator_key)
        if creator_products:
            creator_products.discard(product_id)
            if not creator_products:
                CUSTOM_PRODUCTS_BY_CREATOR.pop(creator_key, None)

    for creator_key, nonce_map in list(USED_CREATE_NONCES.items()):
        for nonce in [nonce for nonce, expires_at in nonce_map.items() if expires_at <= now_ts]:
            nonce_map.pop(nonce, None)
        if not nonce_map:
            USED_CREATE_NONCES.pop(creator_key, None)

    cutoff = now_ts - CREATE_RATE_WINDOW_SECONDS
    for ip, timestamps in list(CREATE_RATE_LIMIT_BY_IP.items()):
        fresh = [ts for ts in timestamps if ts > cutoff]
        if fresh:
            CREATE_RATE_LIMIT_BY_IP[ip] = fresh
        else:
            CREATE_RATE_LIMIT_BY_IP.pop(ip, None)


async def _rpc_request(method: str, params: list[Any]) -> Any:
    if not RPC_URL:
        raise RuntimeError("RPC_URL is not configured")
    payload = {
        "jsonrpc": "2.0",
        "id": int(time.time() * 1000),
        "method": method,
        "params": params,
    }
    try:
        resp = await http_client.post(RPC_URL, json=payload)
        resp.raise_for_status()
        body = resp.json()
    except Exception as exc:
        raise RuntimeError(f"RPC request failed for {method}: {exc}") from exc
    if not isinstance(body, dict):
        raise RuntimeError(f"RPC returned invalid response for {method}")
    if body.get("error"):
        raise RuntimeError(f"RPC error for {method}: {body['error']}")
    return body.get("result")


def _decode_uint256_hex(result: Any, field_name: str) -> int:
    if not isinstance(result, str) or not result.startswith("0x"):
        raise ValueError(f"Invalid {field_name} response from token contract")
    hex_body = result[2:]
    if not hex_body:
        raise ValueError(f"Empty {field_name} response from token contract")
    try:
        return int(hex_body, 16)
    except ValueError as exc:
        raise ValueError(f"Invalid {field_name} response from token contract") from exc


def _decode_abi_symbol(result: Any) -> str | None:
    if not isinstance(result, str) or not result.startswith("0x"):
        return None
    raw = bytes.fromhex(result[2:]) if len(result) > 2 else b""
    if not raw:
        return None
    if len(raw) == 32:
        text = raw.rstrip(b"\x00").decode("utf-8", errors="ignore").strip()
    else:
        if len(raw) < 96:
            return None
        try:
            data_offset = int.from_bytes(raw[0:32], "big")
            if data_offset + 64 > len(raw):
                return None
            data_length = int.from_bytes(raw[data_offset : data_offset + 32], "big")
            start = data_offset + 32
            end = start + data_length
            if end > len(raw):
                return None
            text = raw[start:end].decode("utf-8", errors="ignore").strip()
        except Exception:
            return None
    if not text:
        return None
    cleaned = "".join(ch for ch in text if 32 <= ord(ch) <= 126).strip()
    if not cleaned:
        return None
    return cleaned[:32]


async def _resolve_token_metadata(token: str) -> tuple[int, str]:
    code = await _rpc_request("eth_getCode", [token, "latest"])
    if not isinstance(code, str) or code in {"0x", "0x0", "0x00"}:
        raise ValueError("Token address has no deployed contract code")

    try:
        decimals_hex = await _rpc_request(
            "eth_call",
            [{"to": token, "data": "0x313ce567"}, "latest"],
        )
    except RuntimeError as exc:
        raise ValueError("Token contract does not expose decimals()") from exc

    decimals = _decode_uint256_hex(decimals_hex, "decimals")
    if decimals < 0 or decimals > 255:
        raise ValueError("Token decimals() is out of supported bounds")

    symbol = "ERC20"
    try:
        symbol_hex = await _rpc_request(
            "eth_call",
            [{"to": token, "data": "0x95d89b41"}, "latest"],
        )
        decoded_symbol = _decode_abi_symbol(symbol_hex)
        if decoded_symbol:
            symbol = decoded_symbol
    except Exception:
        pass
    return decimals, symbol


def _custom_create_message(
    chain_id: int,
    creator: str,
    token: str,
    tier_id: str,
    nonce: str,
    issued_at: int,
    expires_at: int,
) -> str:
    return (
        "TZ APAC x402 Custom Product Creation\n"
        f"chainId:{chain_id}\n"
        f"creator:{creator}\n"
        f"token:{token}\n"
        f"tierId:{tier_id}\n"
        f"nonce:{nonce}\n"
        f"issuedAt:{issued_at}\n"
        f"expiresAt:{expires_at}"
    )


def _tier_amount_to_base_units(tier_id: str, decimals: int) -> int:
    tier_config = CUSTOM_PRODUCT_TIERS[tier_id]
    scaled = Decimal(tier_config["amount"]) * (Decimal(10) ** decimals)
    if scaled != scaled.to_integral_value():
        raise ValueError("Token decimals too small for selected tier amount")
    amount_int = int(scaled)
    if amount_int <= 0:
        raise ValueError("Computed token amount must be positive")
    return amount_int


def _custom_product_requirements(
    token: str,
    amount: str,
    symbol: str,
    decimals: int,
) -> dict[str, Any]:
    return {
        "scheme": "exact",
        "network": NETWORK,
        "amount": amount,
        "payTo": SERVER_WALLET,
        "maxTimeoutSeconds": 60,
        "asset": token,
        "extra": {
            "name": symbol,
            "version": "1",
            "assetTransferMethod": "permit2",
            "decimals": decimals,
        },
    }


def _build_custom_product(
    creator: str,
    token: str,
    tier_id: str,
    decimals: int,
    symbol: str,
    now_ts: int,
) -> dict[str, Any]:
    amount = _tier_amount_to_base_units(tier_id, decimals)
    product_id = f"custom_{uuid.uuid4().hex}"
    path = f"/api/custom/{product_id}"
    expires_at = now_ts + CUSTOM_PRODUCT_TTL_SECONDS
    return {
        "id": product_id,
        "name": "Custom Token Access",
        "path": path,
        "description": "Custom token-gated content",
        "requirements": _custom_product_requirements(token, str(amount), symbol, decimals),
        "response": {
            "content": "Custom token-gated content unlocked",
            "tierId": tier_id,
            "creator": creator,
            "asset": token,
            "symbol": symbol,
        },
        "creator": creator,
        "tierId": tier_id,
        "expiresAt": expires_at,
        "createdAt": now_ts,
    }


def _payment_required(
    request: Request,
    requirements: dict[str, Any],
    resource_path: str,
    resource_description: str,
) -> dict[str, Any]:
    return {
        "x402Version": 2,
        "accepts": [requirements],
        "resource": {
            "description": resource_description,
            "mimeType": "application/json",
            "url": _resource_url(request, resource_path),
        },
        "error": None,
    }


def _get_payment_header(request: Request) -> str | None:
    # V2 spec: Payment-Signature
    return request.headers.get("Payment-Signature") or request.headers.get(
        "payment-signature"
    )


def _requirements_match(accepted: dict, required: dict) -> bool:
    # Accept additional non-critical fields from clients, but enforce all settlement-critical terms exactly.
    if not isinstance(accepted, dict) or not isinstance(required, dict):
        return False

    critical_keys = (
        "scheme",
        "network",
        "amount",
        "payTo",
        "maxTimeoutSeconds",
        "asset",
    )
    for key in critical_keys:
        if str(accepted.get(key)) != str(required.get(key)):
            return False

    return accepted.get("extra") == required.get("extra")

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


def _catalog_product(request: Request, product: dict[str, Any]) -> dict[str, Any]:
    requirements = product["requirements"]
    catalog_entry = {
        "id": product["id"],
        "name": product["name"],
        "path": product["path"],
        "url": _resource_url(request, product["path"]),
        "description": product["description"],
        "payment": {
            "x402Version": 2,
            "scheme": requirements["scheme"],
            "network": requirements["network"],
            "amount": requirements["amount"],
            "payTo": requirements["payTo"],
            "asset": requirements["asset"],
            "maxTimeoutSeconds": requirements["maxTimeoutSeconds"],
            "extra": requirements.get("extra"),
        },
    }
    if "expiresAt" in product:
        catalog_entry["expiresAt"] = product["expiresAt"]
    return catalog_entry


async def _handle_paid_product(
    request: Request,
    product: dict[str, Any],
) -> Response:
    requirements = product["requirements"]
    product_response = product["response"]
    payment_header = _get_payment_header(request)
    gas_payer_header = request.headers.get("X-GAS-PAYER") or request.headers.get(
        "x-gas-payer"
    )
    gas_payer = gas_payer_header.lower() if gas_payer_header else "auto"

    if not payment_header:
        payload = base64.b64encode(
            json.dumps(
                _payment_required(
                    request,
                    requirements,
                    product["path"],
                    product["description"],
                )
            ).encode()
        ).decode()
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

    requirements_for_facilitator = copy.deepcopy(requirements)

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
            status_code=400,
            media_type="application/json",
        )

    if not _requirements_match(accepted, requirements):
        return Response(
            content=json.dumps(
                {
                    "error": "Accepted requirements do not match offered requirements",
                    "offered": requirements,
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
    nonce_raw = permit2_auth.get("nonce")
    deadline_raw = permit2_auth.get("deadline")
    signature_raw = permit2_payload.get("signature")

    witness_to = witness.get("to")
    witness_valid_after_raw = witness.get("validAfter")
    witness_extra_raw = witness.get("extra")
    if not witness_to or witness_valid_after_raw is None or witness_extra_raw is None:
        return Response(
            content=json.dumps(
                {"error": "Missing required witness fields in permit2Authorization"}
            ),
            status_code=400,
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

    if (
        not owner
        or not spender
        or not token
        or amount_raw is None
        or nonce_raw is None
        or deadline_raw is None
    ):
        return Response(
            content=json.dumps(
                {
                    "error": "Incomplete permit2 payload (missing owner/spender/token/amount/nonce/deadline)",
                }
            ),
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

    try:
        nonce_value = int(nonce_raw)
        deadline_value = int(deadline_raw)
        witness_valid_after = int(witness_valid_after_raw)
    except (TypeError, ValueError):
        return Response(
            content=json.dumps(
                {"error": "Invalid nonce/deadline/witness.validAfter in permit2Authorization"}
            ),
            status_code=400,
            media_type="application/json",
        )

    if nonce_value < 0 or deadline_value <= 0 or witness_valid_after < 0:
        return Response(
            content=json.dumps({"error": "Invalid permit2Authorization numeric bounds"}),
            status_code=400,
            media_type="application/json",
        )

    if witness_valid_after > deadline_value:
        return Response(
            content=json.dumps({"error": "Invalid witness window (validAfter > deadline)"}),
            status_code=400,
            media_type="application/json",
        )

    max_timeout_seconds = int(
        requirements_for_facilitator.get("maxTimeoutSeconds", "0") or 0
    )
    now = int(time.time())
    if max_timeout_seconds > 0 and deadline_value > (now + max_timeout_seconds + 6):
        return Response(
            content=json.dumps({"error": "Permit2 deadline exceeds maxTimeoutSeconds"}),
            status_code=400,
            media_type="application/json",
        )

    if not isinstance(signature_raw, str) or not signature_raw.startswith("0x"):
        return Response(
            content=json.dumps({"error": "Invalid signature in permit2 payload"}),
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
        "explorer": _explorer_url(tx_hash),
        "productId": product["id"],
    }
    x_payment_response = base64.b64encode(
        json.dumps(response_payload).encode()
    ).decode()

    paid_body = dict(product_response)
    paid_body.update(
        {
            "productId": product["id"],
            "payment_settled": True,
            "txHash": tx_hash,
            "explorer": _explorer_url(tx_hash),
        }
    )

    return Response(
        content=json.dumps(paid_body),
        status_code=200,
        # Match x402-axum's response header name.
        headers={"X-Payment-Response": x_payment_response},
        media_type="application/json",
    )


@app.get("/")
async def root():
    return {
        "status": "BBT Permit2 MVP x402 Server",
        "network": NETWORK,
        "facilitator": FACILITATOR_URL,
    }


@app.get("/config")
async def config():
    default_product = PRODUCTS[DEFAULT_PRODUCT_ID]
    return {
        "x402Version": 2,
        "scheme": "exact",
        "network": NETWORK,
        "asset": BBT_TOKEN,
        "payTo": SERVER_WALLET,
        "amount": default_product["requirements"]["amount"],
        "facilitatorUrl": FACILITATOR_URL,
        "defaultProductId": DEFAULT_PRODUCT_ID,
        "features": {
            "customTokenProducts": CUSTOM_PRODUCTS_ENABLED,
        },
        "customProduct": {
            "ttlSeconds": CUSTOM_PRODUCT_TTL_SECONDS,
            "tiers": [
                {"id": tier_id, "label": tier["label"]}
                for tier_id, tier in CUSTOM_PRODUCT_TIERS.items()
            ],
            "maxPerCreator": CUSTOM_PRODUCT_MAX_PER_CREATOR,
            "maxGlobal": CUSTOM_PRODUCT_MAX_GLOBAL,
            "createMaxPerIpPerHour": CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR,
            "signatureMaxAgeSeconds": CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS,
        },
    }


@app.get("/api/catalog")
async def catalog(request: Request):
    _cleanup_custom_state()
    products = [
        _catalog_product(request, PRODUCTS["weather"]),
        _catalog_product(request, PRODUCTS["premium-content"]),
    ]

    creator = request.query_params.get("creator")
    if CUSTOM_PRODUCTS_ENABLED and creator:
        try:
            creator_checksum = _to_checksum_strict(creator, "creator query parameter")
        except RuntimeError as exc:
            return Response(
                content=json.dumps({"error": str(exc)}),
                status_code=400,
                media_type="application/json",
            )
        creator_key = creator_checksum.lower()
        for product_id in sorted(CUSTOM_PRODUCTS_BY_CREATOR.get(creator_key, set())):
            product = CUSTOM_PRODUCTS_BY_ID.get(product_id)
            if product:
                products.append(_catalog_product(request, product))

    return {
        "store": "TZ APAC x402 Store",
        "network": NETWORK,
        "products": products,
    }


@app.post("/api/catalog/custom-token")
async def create_custom_token_product(request: Request):
    if not CUSTOM_PRODUCTS_ENABLED:
        return Response(
            content=json.dumps({"error": "Custom token products are disabled"}),
            status_code=404,
            media_type="application/json",
        )

    now_ts = int(time.time())
    _cleanup_custom_state(now_ts)

    client_ip = _client_ip(request)
    ip_activity = CREATE_RATE_LIMIT_BY_IP.setdefault(client_ip, [])
    if len(ip_activity) >= CUSTOM_PRODUCT_CREATE_MAX_PER_IP_PER_HOUR:
        return Response(
            content=json.dumps({"error": "Create rate limit exceeded for this IP"}),
            status_code=429,
            media_type="application/json",
        )
    ip_activity.append(now_ts)

    try:
        payload = await request.json()
    except Exception:
        return Response(
            content=json.dumps({"error": "Invalid JSON payload"}),
            status_code=400,
            media_type="application/json",
        )
    if not isinstance(payload, dict):
        return Response(
            content=json.dumps({"error": "Invalid payload format"}),
            status_code=400,
            media_type="application/json",
        )

    nonce = payload.get("nonce")
    tier_id = payload.get("tierId")
    signature = payload.get("signature")
    chain_id_raw = payload.get("chainId")
    issued_at_raw = payload.get("issuedAt")
    expires_at_raw = payload.get("expiresAt")

    if tier_id not in CUSTOM_PRODUCT_TIERS:
        return Response(
            content=json.dumps({"error": "Invalid tierId"}),
            status_code=400,
            media_type="application/json",
        )
    if not isinstance(nonce, str) or not nonce.strip():
        return Response(
            content=json.dumps({"error": "Invalid nonce"}),
            status_code=400,
            media_type="application/json",
        )
    nonce = nonce.strip()
    if len(nonce) > 256:
        return Response(
            content=json.dumps({"error": "Nonce too long"}),
            status_code=400,
            media_type="application/json",
        )
    if not isinstance(signature, str) or not signature.startswith("0x"):
        return Response(
            content=json.dumps({"error": "Invalid signature"}),
            status_code=400,
            media_type="application/json",
        )

    try:
        chain_id = int(chain_id_raw)
        issued_at = int(issued_at_raw)
        expires_at = int(expires_at_raw)
    except (TypeError, ValueError):
        return Response(
            content=json.dumps({"error": "Invalid chainId/issuedAt/expiresAt"}),
            status_code=400,
            media_type="application/json",
        )

    if chain_id != CHAIN_ID:
        return Response(
            content=json.dumps({"error": f"Unsupported chainId (expected {CHAIN_ID})"}),
            status_code=400,
            media_type="application/json",
        )
    if issued_at <= 0 or expires_at <= 0 or expires_at <= issued_at:
        return Response(
            content=json.dumps({"error": "Invalid issuedAt/expiresAt bounds"}),
            status_code=400,
            media_type="application/json",
        )
    if (expires_at - issued_at) > CUSTOM_PRODUCT_SIGNATURE_MAX_AGE_SECONDS:
        return Response(
            content=json.dumps({"error": "Signature validity window is too large"}),
            status_code=400,
            media_type="application/json",
        )
    if issued_at > now_ts + CUSTOM_CREATE_CLOCK_SKEW_SECONDS:
        return Response(
            content=json.dumps({"error": "issuedAt is too far in the future"}),
            status_code=400,
            media_type="application/json",
        )
    if expires_at < now_ts:
        return Response(
            content=json.dumps({"error": "Create request signature is expired"}),
            status_code=400,
            media_type="application/json",
        )

    try:
        creator = _to_checksum_strict(payload.get("creator"), "creator")
        token = _to_checksum_strict(payload.get("token"), "token")
    except RuntimeError as exc:
        return Response(
            content=json.dumps({"error": str(exc)}),
            status_code=400,
            media_type="application/json",
        )

    creator_key = creator.lower()
    used_nonces = USED_CREATE_NONCES.setdefault(creator_key, {})
    if nonce in used_nonces:
        return Response(
            content=json.dumps({"error": "Nonce already used for creator"}),
            status_code=400,
            media_type="application/json",
        )

    creator_products = CUSTOM_PRODUCTS_BY_CREATOR.get(creator_key, set())
    if len(creator_products) >= CUSTOM_PRODUCT_MAX_PER_CREATOR:
        return Response(
            content=json.dumps({"error": "Creator active custom product limit reached"}),
            status_code=429,
            media_type="application/json",
        )
    if len(CUSTOM_PRODUCTS_BY_ID) >= CUSTOM_PRODUCT_MAX_GLOBAL:
        return Response(
            content=json.dumps({"error": "Global custom product limit reached"}),
            status_code=429,
            media_type="application/json",
        )

    message = _custom_create_message(
        chain_id=chain_id,
        creator=creator,
        token=token,
        tier_id=tier_id,
        nonce=nonce,
        issued_at=issued_at,
        expires_at=expires_at,
    )
    try:
        recovered = Web3().eth.account.recover_message(
            encode_defunct(text=message),
            signature=signature,
        )
    except Exception as exc:
        return Response(
            content=json.dumps({"error": f"Invalid signature: {exc}"}),
            status_code=400,
            media_type="application/json",
        )

    if not _same_address(recovered, creator):
        return Response(
            content=json.dumps({"error": "Signature does not match creator"}),
            status_code=401,
            media_type="application/json",
        )

    try:
        decimals, symbol = await _resolve_token_metadata(token)
        product = _build_custom_product(
            creator=creator,
            token=token,
            tier_id=tier_id,
            decimals=decimals,
            symbol=symbol,
            now_ts=now_ts,
        )
    except ValueError as exc:
        return Response(
            content=json.dumps({"error": str(exc)}),
            status_code=400,
            media_type="application/json",
        )
    except RuntimeError as exc:
        logger.exception("Token metadata RPC failure: %s", exc)
        return Response(
            content=json.dumps({"error": "Failed to validate token metadata via RPC"}),
            status_code=502,
            media_type="application/json",
        )

    CUSTOM_PRODUCTS_BY_ID[product["id"]] = product
    CUSTOM_PRODUCTS_BY_CREATOR.setdefault(creator_key, set()).add(product["id"])
    used_nonces[nonce] = expires_at

    return {
        "success": True,
        "product": _catalog_product(request, product),
    }


@app.get("/api/weather")
async def weather(request: Request):
    return await _handle_paid_product(request, PRODUCTS["weather"])


@app.get("/api/premium-content")
async def premium_content(request: Request):
    return await _handle_paid_product(request, PRODUCTS["premium-content"])


@app.get("/api/custom/{product_id}")
async def custom_product(product_id: str, request: Request):
    if not CUSTOM_PRODUCTS_ENABLED:
        return Response(
            content=json.dumps({"error": "Custom product not found"}),
            status_code=404,
            media_type="application/json",
        )
    _cleanup_custom_state()
    product = CUSTOM_PRODUCTS_BY_ID.get(product_id)
    if not product:
        return Response(
            content=json.dumps({"error": "Custom product not found"}),
            status_code=404,
            media_type="application/json",
        )
    return await _handle_paid_product(request, product)


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
