"""Small structured logging helpers."""

from __future__ import annotations

import sys
from typing import Any, Protocol, TextIO, cast

from loguru import logger


class BoundLogger(Protocol):
    """Subset of Loguru used by torrent-preview."""

    def bind(self, **kwargs: object) -> BoundLogger: ...

    def debug(self, message: str, *args: object, **kwargs: object) -> None: ...

    def info(self, message: str, *args: object, **kwargs: object) -> None: ...

    def warning(self, message: str, *args: object, **kwargs: object) -> None: ...


def bind_log(**fields: object) -> BoundLogger:
    """Return a Loguru logger with empty context fields removed."""

    return cast(
        "BoundLogger",
        logger.bind(
            **{key: value for key, value in fields.items() if value is not None}
        ),
    )


def configure_default_logging(
    *,
    debug: bool = False,
    sink: TextIO | None = None,
    colorize: bool = True,
) -> None:
    """Configure user-friendly Loguru output for torrent-preview workflows."""

    logger.remove()
    output = sink or sys.stderr
    logger.add(
        lambda message: print(message, end="", file=output, flush=True),
        level="DEBUG" if debug else "INFO",
        format=cast("Any", _format_log_record),
        colorize=colorize,
    )


def _format_log_record(record: dict[str, Any]) -> str:
    extra = record["extra"]
    fields = _log_context_fields(extra)
    context = f" | {' '.join(fields)}" if fields else ""
    return (
        f"<green>{{time:YYYY-MM-DD HH:mm:ss.SSS}}</green> | "
        f"<level>{{level}}</level> | "
        f"<level>{{message}}</level><cyan>{context}</cyan>\n"
    )


def _log_context_fields(extra: dict[str, Any]) -> list[str]:
    fields: list[str] = []
    torrent_label = extra.get("torrent_title") or extra.get("torrent_path")
    if torrent_label:
        fields.append(_log_field("torrent", torrent_label))
    selected_file = extra.get("selected_file")
    if selected_file and selected_file != torrent_label:
        fields.append(_log_field("file", selected_file))
    for key in (
        "job_id",
        "status",
        "selected_frame_count",
        "target_frames",
        "candidate_count",
        "candidates_per_anchor",
        "model_selected_frame_count",
        "downloaded_bytes",
        "expected_download_bytes",
        "planned_bytes",
        "selected_file_size",
        "torrent_total_size",
        "elapsed_seconds",
        "status_reason",
    ):
        value = extra.get(key)
        if value is not None:
            fields.append(_log_field(_display_key(key), _display_value(key, value)))
    return fields


def _display_key(key: str) -> str:
    if key.endswith("_bytes"):
        return f"{key[:-6]}_mb"
    if key.endswith("_size"):
        return f"{key}_mb"
    return key


def _display_value(key: str, value: object) -> object:
    if (key.endswith("_bytes") or key.endswith("_size")) and isinstance(
        value, int | float
    ):
        return f"{_bytes_to_mb(value):.2f}"
    return value


def _log_field(key: str, value: object) -> str:
    return f'{key}="{_log_value(value)}"'


def _log_value(value: object) -> str:
    return (
        str(value)
        .replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("{", "{{")
        .replace("}", "}}")
    )


def _bytes_to_mb(value: int | float) -> float:
    return float(value) / (1024 * 1024)
