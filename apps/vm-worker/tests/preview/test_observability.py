from __future__ import annotations

from typing import Any

from mymediavault_vm_worker.preview.llm import observability


def test_pytest_disables_logfire_export(monkeypatch) -> None:
    calls: list[dict[str, Any]] = []

    monkeypatch.setattr(observability, "_LOGFIRE_CONFIGURED", False)
    monkeypatch.setattr(
        observability.logfire,
        "configure",
        lambda **kwargs: calls.append(kwargs),
    )

    observability.configure_logfire()

    assert calls == [
        {
            "send_to_logfire": False,
            "service_name": "torrent-preview",
            "console": False,
        }
    ]
