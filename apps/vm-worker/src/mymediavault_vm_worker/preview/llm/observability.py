"""Logfire observability setup."""

from __future__ import annotations

import os

import logfire

DISABLE_LOGFIRE_ENV = "TORRENT_PREVIEW_DISABLE_LOGFIRE"
_LOGFIRE_CONFIGURED = False


def configure_logfire() -> None:
    """Configure Logfire once per process."""

    global _LOGFIRE_CONFIGURED

    if _LOGFIRE_CONFIGURED:
        return
    send_to_logfire: bool | str = "if-token-present"
    if os.getenv(DISABLE_LOGFIRE_ENV):
        send_to_logfire = False
    logfire.configure(
        send_to_logfire=send_to_logfire,
        service_name="torrent-preview",
        console=False,
    )
    _LOGFIRE_CONFIGURED = True
