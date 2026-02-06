#!/usr/bin/env python3
import base64
import json
import logging
import os

import httpx
from fastapi import FastAPI, Request, Response
from dotenv import load_dotenv
from hexbytes import HexBytes
from web3 import Web3

from logging_utils import get_logger, log_json

load_dotenv()

app = FastAPI()
http_client = httpx.AsyncClient(timeout=120.0)
logger = get_logger("bbt_mvp_server")

FACILITATOR_URL = os.getenv("FACILITATOR_URL", "http://localhost:9090")
DEFAULT_SERVER_WALLET = "0xA6e868Cd44C7643Fb4Ca9E2D0D66B13f403B488F"
SERVER_WALLET_ENV = os.getenv("SERVER_WALLET")
STORE_ADDRESS_ENV = os.getenv("STORE_ADDRESS")
STORE_PRIVATE_KEY_ENV = os.getenv("STORE_PRIVATE_KEY")
BBT_TOKEN = "0x7EfE4bdd11237610bcFca478937658bE39F8dfd6"
PERMIT2_ADDRESS = "0x000000000022D473030F116dDEE9F6B43aC78BA3"
NETWORK = "eip155:42793"
RPC_URL = os.getenv("RPC_URL") or os.getenv("NODE_URL") or "https://rpc.bubbletez.com"


def _resolve_server_wallet() -> str:
    if SERVER_WALLET_ENV:
        return SERVER_WALLET_ENV
    if STORE_ADDRESS_ENV:
        return STORE_ADDRESS_ENV
    if STORE_PRIVATE_KEY_ENV:
        try:
            return Web3().eth.account.from_key(STORE_PRIVATE_KEY_ENV).address
        except Exception:
            return DEFAULT_SERVER_WALLET
    return DEFAULT_SERVER_WALLET


try:
    SERVER_WALLET = Web3.to_checksum_address(_resolve_server_wallet())
except Exception:
    SERVER_WALLET = DEFAULT_SERVER_WALLET

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

PERMIT2_ABI = [
    {
        "inputs": [
            {"internalType": "address", "name": "owner", "type": "address"},
            {
                "components": [
                    {
                        "components": [
                            {
                                "internalType": "address",
                                "name": "token",
                                "type": "address",
                            },
                            {
                                "internalType": "uint160",
                                "name": "amount",
                                "type": "uint160",
                            },
                            {
                                "internalType": "uint48",
                                "name": "expiration",
                                "type": "uint48",
                            },
                            {
                                "internalType": "uint48",
                                "name": "nonce",
                                "type": "uint48",
                            },
                        ],
                        "internalType": "struct Permit2.PermitDetails",
                        "name": "details",
                        "type": "tuple",
                    },
                    {"internalType": "address", "name": "spender", "type": "address"},
                    {
                        "internalType": "uint256",
                        "name": "sigDeadline",
                        "type": "uint256",
                    },
                ],
                "internalType": "struct Permit2.PermitSingle",
                "name": "permitSingle",
                "type": "tuple",
            },
            {"internalType": "bytes", "name": "signature", "type": "bytes"},
        ],
        "name": "permit",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"internalType": "address", "name": "from", "type": "address"},
            {"internalType": "address", "name": "to", "type": "address"},
            {"internalType": "uint160", "name": "amount", "type": "uint160"},
            {"internalType": "address", "name": "token", "type": "address"},
        ],
        "name": "transferFrom",
        "outputs": [],
        "stateMutability": "nonpayable",
        "type": "function",
    },
]

ERC20_ABI = [
    {
        "anonymous": False,
        "inputs": [
            {
                "indexed": True,
                "internalType": "address",
                "name": "from",
                "type": "address",
            },
            {
                "indexed": True,
                "internalType": "address",
                "name": "to",
                "type": "address",
            },
            {
                "indexed": False,
                "internalType": "uint256",
                "name": "value",
                "type": "uint256",
            },
        ],
        "name": "Transfer",
        "type": "event",
    }
]


def _get_web3() -> Web3:
    return Web3(Web3.HTTPProvider(RPC_URL))


def _extract_permit2_payload(payment_payload: dict) -> dict | None:
    if not isinstance(payment_payload, dict):
        return None
    payload = payment_payload.get("payload")
    if not isinstance(payload, dict):
        return None
    permit2 = payload.get("permit2")
    if not isinstance(permit2, dict):
        return None
    return permit2


def _verify_client_payment(
    tx_hash: str,
    owner: str,
    pay_to: str,
    token: str,
    amount: int,
) -> tuple[bool, str | None]:
    try:
        w3 = _get_web3()
        receipt = w3.eth.get_transaction_receipt(HexBytes(tx_hash))
        if receipt is None or receipt.get("status") != 1:
            return False, "transaction failed"

        owner_address = Web3.to_checksum_address(owner)
        pay_to_address = Web3.to_checksum_address(pay_to)
        token_address = Web3.to_checksum_address(token)

        tx_from = receipt.get("from")
        if tx_from and tx_from.lower() != owner_address.lower():
            return False, "transaction sender mismatch"

        token_contract = w3.eth.contract(address=token_address, abi=ERC20_ABI)
        events = token_contract.events.Transfer().process_receipt(receipt)
        for event in events:
            args = event.get("args", {})
            if (
                str(args.get("from", "")).lower() == owner_address.lower()
                and str(args.get("to", "")).lower() == pay_to_address.lower()
                and int(args.get("value", 0)) == amount
            ):
                return True, None
        return False, "transfer event not found"
    except Exception as exc:
        return False, f"verification error: {exc}"


def _settle_with_store(
    permit2_payload: dict, pay_to: str
) -> tuple[str | None, str | None]:
    store_private_key = os.getenv("STORE_PRIVATE_KEY")
    if not store_private_key:
        return None, "STORE_PRIVATE_KEY not configured"

    w3 = _get_web3()
    account = w3.eth.account.from_key(store_private_key)
    store_address = Web3.to_checksum_address(account.address)
    if Web3.to_checksum_address(SERVER_WALLET) != store_address:
        return None, "STORE_PRIVATE_KEY does not match SERVER_WALLET"

    owner_raw = permit2_payload.get("owner")
    permit_single = permit2_payload.get("permitSingle")
    signature = permit2_payload.get("signature")
    if not owner_raw or not permit_single or not signature:
        return None, "missing permit2 payload fields"

    details = permit_single.get("details")
    spender_raw = permit_single.get("spender")
    sig_deadline_raw = permit_single.get("sigDeadline")
    if not details or not spender_raw or sig_deadline_raw is None:
        return None, "missing permit2 permitSingle fields"

    owner = Web3.to_checksum_address(owner_raw)
    spender = Web3.to_checksum_address(spender_raw)
    if spender.lower() != store_address.lower():
        return None, "spender must be store wallet for store-gas mode"

    token_raw = details.get("token")
    amount_raw = details.get("amount")
    expiration_raw = details.get("expiration")
    nonce_raw = details.get("nonce")
    if (
        token_raw is None
        or amount_raw is None
        or expiration_raw is None
        or nonce_raw is None
    ):
        return None, "missing permit2 details"

    token = Web3.to_checksum_address(token_raw)
    amount = int(amount_raw)
    expiration = int(expiration_raw)
    nonce = int(nonce_raw)
    sig_deadline = int(sig_deadline_raw)

    permit2 = w3.eth.contract(
        address=Web3.to_checksum_address(PERMIT2_ADDRESS), abi=PERMIT2_ABI
    )

    permit_args = (
        (token, amount, expiration, nonce),
        spender,
        sig_deadline,
    )

    signature_bytes = HexBytes(signature) if isinstance(signature, str) else signature
    permit_fn = permit2.functions.permit(owner, permit_args, signature_bytes)
    permit_gas = permit_fn.estimate_gas({"from": store_address})
    permit_tx = permit_fn.build_transaction(
        {
            "from": store_address,
            "nonce": w3.eth.get_transaction_count(store_address),
            "gas": permit_gas,
            "gasPrice": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
        }
    )
    signed_permit = w3.eth.account.sign_transaction(permit_tx, store_private_key)
    permit_raw = (
        signed_permit.rawTransaction
        if hasattr(signed_permit, "rawTransaction")
        else signed_permit.raw_transaction
    )
    permit_hash = w3.eth.send_raw_transaction(permit_raw)
    permit_receipt = w3.eth.wait_for_transaction_receipt(permit_hash)
    if permit_receipt.get("status") != 1:
        return None, "permit transaction failed"

    transfer_fn = permit2.functions.transferFrom(owner, pay_to, amount, token)
    transfer_gas = transfer_fn.estimate_gas({"from": store_address})
    transfer_tx = transfer_fn.build_transaction(
        {
            "from": store_address,
            "nonce": w3.eth.get_transaction_count(store_address),
            "gas": transfer_gas,
            "gasPrice": w3.eth.gas_price,
            "chainId": w3.eth.chain_id,
        }
    )
    signed_transfer = w3.eth.account.sign_transaction(transfer_tx, store_private_key)
    transfer_raw = (
        signed_transfer.rawTransaction
        if hasattr(signed_transfer, "rawTransaction")
        else signed_transfer.raw_transaction
    )
    transfer_hash = w3.eth.send_raw_transaction(transfer_raw)
    transfer_receipt = w3.eth.wait_for_transaction_receipt(transfer_hash)
    if transfer_receipt.get("status") != 1:
        return None, "transferFrom transaction failed"

    return transfer_hash.hex(), None


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
        "asset": f"{NETWORK}/erc20:{BBT_TOKEN}",
        "payTo": SERVER_WALLET,
        "amount": PAYMENT_REQUIRED["accepts"][0]["amount"],
        "facilitatorUrl": FACILITATOR_URL,
    }


@app.get("/api/weather")
async def weather(request: Request):
    payment_header = request.headers.get("X-PAYMENT") or request.headers.get(
        "x-payment"
    )
    gas_payer_header = request.headers.get("X-GAS-PAYER") or request.headers.get(
        "x-gas-payer"
    )
    gas_payer = gas_payer_header.lower() if gas_payer_header else "auto"

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
        log_json(logger, logging.DEBUG, "Received payment payload", payment_payload)
    except Exception as e:
        logger.warning("Invalid payment header: %s", e)
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

    permit2_payload = _extract_permit2_payload(payment_payload)
    if not permit2_payload:
        return Response(
            content=json.dumps({"error": "Missing permit2 payload"}),
            status_code=400,
            media_type="application/json",
        )

    permit_single = permit2_payload.get("permitSingle", {})
    details = permit_single.get("details", {})
    owner = permit2_payload.get("owner")
    spender = permit_single.get("spender")
    token = details.get("token")
    amount_raw = details.get("amount")
    pay_to = requirements_for_facilitator.get("payTo")

    if not owner or not spender or not token or amount_raw is None or not pay_to:
        return Response(
            content=json.dumps({"error": "Incomplete permit2 payload"}),
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

    if gas_payer not in {"facilitator", "store", "client", "auto"}:
        return Response(
            content=json.dumps({"error": "Invalid gas payer mode"}),
            status_code=400,
            media_type="application/json",
        )

    if gas_payer == "auto":
        if str(spender).lower() == str(owner).lower():
            gas_payer = "client"
        elif str(spender).lower() == str(pay_to).lower():
            gas_payer = "store"
        else:
            gas_payer = "facilitator"

    logger.info("Gas payer mode: %s", gas_payer)

    if gas_payer == "client":
        if str(spender).lower() != str(owner).lower():
            return Response(
                content=json.dumps({"error": "Client gas requires spender=owner"}),
                status_code=402,
                media_type="application/json",
            )
        payment_tx = request.headers.get("X-PAYMENT-TX") or request.headers.get(
            "x-payment-tx"
        )
        if not payment_tx:
            return Response(
                content=json.dumps({"error": "Missing X-PAYMENT-TX header"}),
                status_code=400,
                media_type="application/json",
            )

        verified, reason = _verify_client_payment(
            tx_hash=payment_tx,
            owner=owner,
            pay_to=pay_to,
            token=token,
            amount=payment_amount,
        )
        if not verified:
            return Response(
                content=json.dumps(
                    {"error": "Client payment not verified", "reason": reason}
                ),
                status_code=402,
                media_type="application/json",
            )

        tx_hash = payment_tx
    elif gas_payer == "store":
        if str(spender).lower() != str(pay_to).lower():
            return Response(
                content=json.dumps({"error": "Store gas requires spender=payTo"}),
                status_code=402,
                media_type="application/json",
            )
        tx_hash, error = _settle_with_store(permit2_payload, pay_to)
        if error:
            return Response(
                content=json.dumps(
                    {"error": "Store settlement failed", "reason": error}
                ),
                status_code=402,
                media_type="application/json",
            )
    else:
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
            if isinstance(settle_data, dict):
                tx_hash = settle_data.get("txHash")
                if not tx_hash:
                    transaction = settle_data.get("transaction")
                    if isinstance(transaction, dict):
                        tx_hash = transaction.get("hash")
                    elif isinstance(transaction, str):
                        if transaction.startswith("0x") and len(transaction) == 66:
                            tx_hash = transaction
            elif isinstance(settle_data, str):
                try:
                    parsed = json.loads(settle_data)
                    if isinstance(parsed, dict):
                        tx_hash = parsed.get("txHash")
                        if not tx_hash:
                            transaction = parsed.get("transaction")
                            if isinstance(transaction, dict):
                                tx_hash = transaction.get("hash")
                            elif isinstance(transaction, str):
                                if (
                                    transaction.startswith("0x")
                                    and len(transaction) == 66
                                ):
                                    tx_hash = transaction
                except json.JSONDecodeError:
                    if settle_data.startswith("0x") and len(settle_data) == 66:
                        tx_hash = settle_data

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
        headers={"X-PAYMENT-RESPONSE": x_payment_response},
        media_type="application/json",
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8001)
