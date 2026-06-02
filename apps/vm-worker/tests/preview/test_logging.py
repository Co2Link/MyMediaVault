from __future__ import annotations

import io

from loguru import logger

from mymediavault_vm_worker.preview.logging import configure_default_logging


def test_default_logging_colorizes_output() -> None:
    sink = io.StringIO()

    configure_default_logging(sink=sink)
    logger.info("preview ready")

    assert "\x1b[" in sink.getvalue()
    assert "preview ready" in sink.getvalue()


def test_default_logging_can_disable_colorized_output() -> None:
    sink = io.StringIO()

    configure_default_logging(sink=sink, colorize=False)
    logger.info("preview ready")

    assert "\x1b[" not in sink.getvalue()
    assert "preview ready" in sink.getvalue()
