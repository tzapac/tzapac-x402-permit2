import logging
import os
from typing import Any

_CONFIGURED = False


def _resolve_level() -> int:
    level = os.getenv("LOG_LEVEL")
    if level:
        return getattr(logging, level.upper(), logging.INFO)
    if os.getenv("DEBUG") == "1":
        return logging.DEBUG
    return logging.INFO


def configure_logging() -> None:
    global _CONFIGURED
    if _CONFIGURED:
        return

    logging.basicConfig(
        level=_resolve_level(),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    _CONFIGURED = True


def get_logger(name: str | None = None) -> logging.Logger:
    configure_logging()
    return logging.getLogger(name or __name__)


_SENSITIVE_EXACT_KEYS = {
    "authorization",
    "payment-signature",
    "payment_required",
    "private_key",
    "secret",
    "signature",
    "x-payment-response",
}
_SENSITIVE_SUFFIXES = ("_private_key", "_secret", "_signature", "_authorization")
_SENSITIVE_SUBSTRINGS = (
    "x-payment",
    "payment-signature",
)


def _should_redact(key: str) -> bool:
    key_lower = key.lower()
    if key_lower in _SENSITIVE_EXACT_KEYS:
        return True
    if key_lower.endswith(_SENSITIVE_SUFFIXES):
        return True
    return any(token in key_lower for token in _SENSITIVE_SUBSTRINGS)


def _redact_str(value: str) -> str:
    return f"<redacted:{len(value)} chars>"


def redact(value: Any, *, sensitive: bool = False) -> Any:
    if isinstance(value, dict):
        return {
            key: redact(item, sensitive=(sensitive or _should_redact(str(key))))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item, sensitive=sensitive) for item in value]
    if isinstance(value, tuple):
        return tuple(redact(item, sensitive=sensitive) for item in value)
    if isinstance(value, str):
        return _redact_str(value) if sensitive else value
    if isinstance(value, (bytes, bytearray)):
        return f"<redacted:bytes:{len(value)}>" if sensitive else f"<bytes:{len(value)}>"
    return value


def log_json(logger: logging.Logger, level: int, message: str, data: Any) -> None:
    if logger.isEnabledFor(level):
        logger.log(level, "%s: %s", message, redact(data))
