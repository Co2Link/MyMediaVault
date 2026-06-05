from __future__ import annotations

import asyncio
import json
import textwrap

import pytest

import mymediavault_vm_worker.preview.decoding.ffmpeg as ffmpeg_decoder
from mymediavault_vm_worker.preview.decoding.ffmpeg import (
    FFmpegFrameDecoder,
    _anchor_candidate_timestamps,
    _scale_filter,
)
from mymediavault_vm_worker.preview.decoding.ffmpeg import _parse_showinfo_timestamps
from mymediavault_vm_worker.preview.decoding.ffmpeg import _timestamp_in_anchor_window


def test_ffmpeg_decoder_preserves_source_dimensions_by_default() -> None:
    assert _scale_filter(None) is None


def test_ffmpeg_decoder_can_build_optional_width_limit_filter() -> None:
    assert _scale_filter(1280) == "scale='min(1280,iw)':-2"


def test_ffmpeg_decoder_rejects_invalid_width_limit() -> None:
    with pytest.raises(ValueError, match="max_frame_width"):
        FFmpegFrameDecoder(max_frame_width=0)


def test_showinfo_parser_keeps_absolute_decoded_timestamps() -> None:
    timestamps = _parse_showinfo_timestamps(
        b"[Parsed_showinfo_1] n:0 pts:9460 pts_time:9460 pos:1\n",
        window_start=1735.0,
        window_seconds=4.0,
    )

    assert timestamps == [9460.0]
    assert not _timestamp_in_anchor_window(
        timestamps[0], window_start=1735.0, window_seconds=4.0
    )


def test_showinfo_parser_normalizes_window_relative_timestamps() -> None:
    timestamps = _parse_showinfo_timestamps(
        b"[Parsed_showinfo_1] n:0 pts:1 pts_time:1 pos:1\n",
        window_start=1735.0,
        window_seconds=4.0,
    )

    assert timestamps == [1736.0]
    assert _timestamp_in_anchor_window(
        timestamps[0], window_start=1735.0, window_seconds=4.0
    )


def test_anchor_candidate_timestamps_are_spaced_around_anchor() -> None:
    assert _anchor_candidate_timestamps(
        duration=100.0,
        anchor_ratio=0.5,
        window_seconds=30.0,
        count=3,
    ) == [47.0, 50.0, 53.0]


def test_ffmpeg_decoder_times_out_stuck_subprocess(tmp_path) -> None:
    ffmpeg_path = tmp_path / "fake-ffmpeg"
    ffmpeg_path.write_text(
        "#!/usr/bin/env python3\nimport time\ntime.sleep(30)\n",
        encoding="utf-8",
    )
    ffmpeg_path.chmod(0o755)

    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(_write_fake_ffprobe(tmp_path)),
    )

    frames = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            tmp_path / "frames",
            target_frames=1,
            timeout_seconds=0.01,
            anchors=(0.5,),
        )
    )
    assert frames == []


def test_ffmpeg_decoder_returns_only_verified_anchor_frames(
    tmp_path,
) -> None:
    ffmpeg_path = _write_fake_ffmpeg(
        tmp_path,
        """
        import sys
        from pathlib import Path

        output = Path(sys.argv[-1])
        if "candidate_anchor_000" in output.name:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_name("candidate_anchor_000_0001.jpg").write_bytes(b"anchor")
            sys.stderr.write("[Parsed_showinfo_1] n:0 pts:0 pts_time:0 pos:1\\n")
        """,
    )
    ffprobe_path = _write_fake_ffprobe(tmp_path)
    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(ffprobe_path),
    )

    frames = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            tmp_path / "frames",
            target_frames=3,
            timeout_seconds=5,
            anchors=(0.15, 0.5, 0.85),
            anchor_window_seconds=4.0,
        )
    )

    assert [frame.decode_method for frame in frames] == ["anchor-window"]
    assert [frame.timestamp_seconds for frame in frames] == [15.0]


def test_ffmpeg_decoder_generates_multiple_spaced_anchor_candidates(
    tmp_path,
) -> None:
    calls_path = tmp_path / "ffmpeg-calls.json"
    ffmpeg_path = _write_fake_ffmpeg(
        tmp_path,
        f"""
        import json
        import sys
        from pathlib import Path

        calls_path = Path({str(calls_path)!r})
        calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
        calls.append(sys.argv)
        calls_path.write_text(json.dumps(calls))

        output = Path(sys.argv[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        for index, timestamp in enumerate((0, 3, 6), start=1):
            output.with_name(
                output.name.replace("%04d", f"{{index:04d}}")
            ).write_bytes(f"anchor-{{index}}".encode())
            sys.stderr.write(
                "[Parsed_showinfo_1] "
                f"n:{{index - 1}} pts:{{timestamp}} "
                f"pts_time:{{timestamp}} pos:1\\n"
            )
        """,
    )
    ffprobe_path = _write_fake_ffprobe(tmp_path)
    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(ffprobe_path),
    )

    frames = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            tmp_path / "frames",
            target_frames=1,
            timeout_seconds=5,
            anchors=(0.5,),
            anchor_window_seconds=30.0,
            extract_frames_per_anchor=3,
        )
    )

    calls = json.loads(calls_path.read_text())
    assert len(calls) == 1
    assert calls[0][calls[0].index("-ss") + 1] == "47.000"
    assert calls[0][calls[0].index("-vf") + 1] == "fps=1/3.000000,showinfo"
    assert [frame.timestamp_seconds for frame in frames] == [47.0, 50.0, 53.0]
    assert [frame.anchor_index for frame in frames] == [0, 0, 0]


def test_ffmpeg_decoder_removes_stale_anchor_candidates_before_retry(tmp_path) -> None:
    calls_path = tmp_path / "ffmpeg-calls"
    ffmpeg_path = _write_fake_ffmpeg(
        tmp_path,
        f"""
        import sys
        from pathlib import Path

        calls_path = Path({str(calls_path)!r})
        output = Path(sys.argv[-1])
        if not calls_path.exists():
            calls_path.write_text("called")
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_name("candidate_anchor_000_0001.jpg").write_bytes(b"anchor")
            sys.stderr.write("[Parsed_showinfo_1] n:0 pts:0 pts_time:0 pos:1\\n")
        """,
    )
    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(_write_fake_ffprobe(tmp_path)),
    )
    output_dir = tmp_path / "frames"

    first = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            output_dir,
            target_frames=1,
            timeout_seconds=5,
            anchors=(0.5,),
        )
    )
    second = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            output_dir,
            target_frames=1,
            timeout_seconds=5,
            anchors=(0.5,),
        )
    )

    assert len(first) == 1
    assert second == []


def test_ffmpeg_decoder_scales_anchor_timeout_for_multiple_candidates(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(ffmpeg_decoder, "_ANCHOR_TIMEOUT_CAP_SECONDS", 0.1)
    ffmpeg_path = _write_fake_ffmpeg(
        tmp_path,
        """
        import sys
        import time
        from pathlib import Path

        time.sleep(0.1)
        output = Path(sys.argv[-1])
        output.parent.mkdir(parents=True, exist_ok=True)
        for index, timestamp in enumerate((0, 3, 6), start=1):
            output.with_name(
                output.name.replace("%04d", f"{index:04d}")
            ).write_bytes(f"anchor-{index}".encode())
            sys.stderr.write(
                "[Parsed_showinfo_1] "
                f"n:{index - 1} pts:{timestamp} "
                f"pts_time:{timestamp} pos:1\\n"
            )
        """,
    )
    ffprobe_path = _write_fake_ffprobe(tmp_path)
    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(ffprobe_path),
    )

    frames = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            tmp_path / "frames",
            target_frames=1,
            timeout_seconds=1.0,
            anchors=(0.5,),
            anchor_window_seconds=30.0,
            extract_frames_per_anchor=3,
        )
    )

    assert [frame.timestamp_seconds for frame in frames] == [47.0, 50.0, 53.0]


def test_ffmpeg_decoder_uses_one_timeout_budget_across_anchor_windows(tmp_path) -> None:
    calls_path = tmp_path / "ffmpeg-calls.json"
    ffmpeg_path = _write_fake_ffmpeg(
        tmp_path,
        f"""
        import json
        import sys
        import time
        from pathlib import Path

        calls_path = Path({str(calls_path)!r})
        calls = json.loads(calls_path.read_text()) if calls_path.exists() else []
        calls.append(sys.argv[-1])
        calls_path.write_text(json.dumps(calls))

        output = Path(sys.argv[-1])
        if "candidate_anchor" in output.name:
            time.sleep(0.2)
            output.parent.mkdir(parents=True, exist_ok=True)
            output.with_name(output.name.replace("%04d", "0001")).write_bytes(b"anchor")
            sys.stderr.write("[Parsed_showinfo_1] n:0 pts:1 pts_time:1 pos:1\\n")
        """,
    )
    ffprobe_path = _write_fake_ffprobe(tmp_path)
    decoder = FFmpegFrameDecoder(
        ffmpeg_path=str(ffmpeg_path),
        ffprobe_path=str(ffprobe_path),
    )

    frames = asyncio.run(
        decoder.extract_frames(
            tmp_path / "video.mp4",
            tmp_path / "frames",
            target_frames=3,
            timeout_seconds=0.35,
            anchors=(0.15, 0.5),
            anchor_window_seconds=4.0,
        )
    )

    calls = json.loads(calls_path.read_text())
    assert len(calls) == 2
    assert frames == []


def _write_fake_ffmpeg(tmp_path, body: str):
    path = tmp_path / "fake-ffmpeg"
    path.write_text(
        "#!/usr/bin/env python3\n" + textwrap.dedent(body).strip() + "\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path


def _write_fake_ffprobe(tmp_path):
    path = tmp_path / "fake-ffprobe"
    path.write_text(
        "#!/usr/bin/env python3\n"
        "import sys\n"
        "if 'format=duration' in sys.argv:\n"
        "    print('100')\n"
        "else:\n"
        "    print('640x360')\n",
        encoding="utf-8",
    )
    path.chmod(0o755)
    return path
