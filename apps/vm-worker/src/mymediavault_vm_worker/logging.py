from __future__ import annotations

import re
import sys
from typing import Any

from loguru import logger

from mymediavault_vm_worker.preview import configure_default_logging
from mymediavault_vm_worker.settings import PreviewWorkerSettings

REDACTED_LOG_VALUE = "[redacted]"
SENSITIVE_LOG_KEYS = {
    "authorization",
    "aws_access_key_id",
    "aws_secret_access_key",
    "cookie",
    "mongodb_uri",
    "openai_api_key",
    "r2_access_key_id",
    "r2_secret_access_key",
    "set_cookie",
}
OPENAI_KEY_PATTERN = re.compile(r"\bsk-[A-Za-z0-9_-]{8,}\b")
MONGODB_CREDENTIAL_PATTERN = re.compile(r"(mongodb(?:\+srv)?://[^:/@\s]+:)([^@\s]+)(@)")



def _configure_vm_worker_logging(settings: PreviewWorkerSettings) -> None:
    configure_default_logging(debug=False, sink=sys.stdout)
    logger.configure(patcher=_redact_log_record)
    settings.vm_worker_debug_log_path.parent.mkdir(parents=True, exist_ok=True)
    logger.add(
        settings.vm_worker_debug_log_path,
        level="DEBUG",
        rotation=settings.vm_worker_debug_log_rotation,
        retention=settings.vm_worker_debug_log_retention,
        compression=None,
        serialize=True,
        backtrace=False,
        diagnose=False,
    )


def _redact_log_record(record: dict[str, Any]) -> None:
    record["message"] = _redact_text(str(record["message"]))
    record["extra"] = _redact_log_value(record["extra"], key=None)


def _redact_log_value(value: Any, *, key: str | None) -> Any:
    if key is not None and _is_sensitive_log_key(key):
        return REDACTED_LOG_VALUE
    if isinstance(value, dict):
        return {
            str(child_key): _redact_log_value(child_value, key=str(child_key))
            for child_key, child_value in value.items()
        }
    if isinstance(value, list):
        return [_redact_log_value(item, key=None) for item in value]
    if isinstance(value, tuple):
        return tuple(_redact_log_value(item, key=None) for item in value)
    if isinstance(value, str):
        return _redact_text(value)
    return value


def _is_sensitive_log_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return (
        normalized in SENSITIVE_LOG_KEYS
        or normalized.endswith("_api_key")
        or normalized.endswith("_password")
        or normalized.endswith("_secret")
        or normalized.endswith("_token")
    )


def _redact_text(value: str) -> str:
    redacted = OPENAI_KEY_PATTERN.sub("sk-[redacted]", value)
    return MONGODB_CREDENTIAL_PATTERN.sub(r"\1[redacted]\3", redacted)


