from __future__ import annotations

import asyncio

import cv2
import numpy as np
import pytest

from .scripts.run_test_torrents import _llm_judge_required, _sheet_check
from mymediavault_vm_worker.preview.core.models import GeneratedSheet
from mymediavault_vm_worker.preview.harness import cancel_preview_tasks


def test_cancel_tasks_cancels_pending_tasks() -> None:
    async def run() -> None:
        started = asyncio.Event()

        async def wait_forever() -> tuple[int, dict[str, object]]:
            started.set()
            await asyncio.Event().wait()
            return 0, {}

        task = asyncio.create_task(wait_forever())
        await started.wait()

        await cancel_preview_tasks([task])

        assert task.cancelled()

    asyncio.run(run())


def test_cancel_tasks_waits_for_cancel_cleanup() -> None:
    async def run() -> None:
        cleaned_up = False
        started = asyncio.Event()

        async def wait_forever() -> tuple[int, dict[str, object]]:
            nonlocal cleaned_up
            started.set()
            try:
                await asyncio.Event().wait()
            finally:
                cleaned_up = True
            return 0, {}

        task = asyncio.create_task(wait_forever())
        await started.wait()

        await cancel_preview_tasks([task])

        assert cleaned_up is True
        assert task.cancelled()

    asyncio.run(run())


def test_cancel_tasks_keeps_completed_results() -> None:
    async def run() -> None:
        async def complete() -> tuple[int, dict[str, object]]:
            return 1, {"ok": True}

        task = asyncio.create_task(complete())
        assert await task == (1, {"ok": True})

        await cancel_preview_tasks([task])

        assert task.result() == (1, {"ok": True})

    asyncio.run(run())


def test_cancel_tasks_preserves_non_cancel_exceptions() -> None:
    async def run() -> None:
        async def fail() -> tuple[int, dict[str, object]]:
            msg = "boom"
            raise RuntimeError(msg)

        task = asyncio.create_task(fail())
        with pytest.raises(RuntimeError, match="boom"):
            await task

        await cancel_preview_tasks([task])

        with pytest.raises(RuntimeError, match="boom"):
            task.result()

    asyncio.run(run())


def test_llm_judge_not_required_for_incomplete_truthful_partial() -> None:
    data = {
        "frames": [{"path": "frame.jpg"}],
        "diagnostics": {
            "last_complete_piece_count": 1,
            "last_requested_piece_count": 2,
        },
    }
    status_check = {"ok": True, "mode": "truthful-partial"}

    assert _llm_judge_required(data, status_check) is False


def test_partial_sheet_accepts_single_row_height(tmp_path) -> None:
    sheet_path = tmp_path / "preview_sheet.jpg"
    image = np.full((200, 992, 3), 180, dtype=np.uint8)
    assert cv2.imwrite(str(sheet_path), image)
    sheet = GeneratedSheet(
        path=sheet_path,
        width=992,
        height=200,
        mime_type="image/jpeg",
    )

    check = _sheet_check(sheet)

    assert check["ok"] is True
