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


_SENSITIVE_KEYS = (
    "signature",
    "private",
    "secret",
    "authorization",
    "x-payment",
    "permit",
)


def _should_redact(key: str) -> bool:
    key_lower = key.lower()
    return any(token in key_lower for token in _SENSITIVE_KEYS)


def _redact_str(value: str) -> str:
    if len(value) <= 12:
        return "***"
    return f"{value[:6]}...{value[-4:]}"


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if _should_redact(str(key)) else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    if isinstance(value, str):
        return _redact_str(value)
    if isinstance(value, (bytes, bytearray)):
        return f"<bytes:{len(value)}>"
    return value


def log_json(logger: logging.Logger, level: int, message: str, data: Any) -> None:
    if logger.isEnabledFor(level):
        logger.log(level, "%s: %s", message, redact(data))
