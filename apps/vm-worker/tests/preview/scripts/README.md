# Integration Test Scripts

These scripts are manual integration checks. They are not part of normal pytest because they use real torrent networking, libtorrent, and ffmpeg.
Set `OPENAI_API_KEY` before running the default acceptance script; accepted frame-bearing results require the Pydantic AI judge.

Run all local test torrents with the configured cache:

```bash
uv run python tests/preview/scripts/run_test_torrents.py --debug
```

Run the fresh-cache acceptance path:

```bash
uv run python tests/preview/scripts/run_test_torrents.py --debug --clear-cache
```

The script removes the configured output directory at startup, then writes
selected frames, preview sheets, and `results.json` from the current run there.
It uses `PreviewWorkerHarness` with a file-backed job source, so the script also
serves as a small example of a client application adapter. It uses the internal
preview engine's default torrent cache under the operating system temporary
directory; pass `--torrent-cache-dir` to choose a cache location or
`--clear-cache` to remove the configured cache before a fresh acceptance run.

By default, torrents run one at a time so diagnostics are easy to read. Pass
`--concurrency N` to run multiple torrent previews concurrently through the
same `PreviewEngine`; `results.json` is still written in sorted torrent-path
order. Per-torrent `RESULT` lines print as each torrent finishes only when
`--debug` is enabled.

Use `--target-frames` to select the frame count. Supported values are `3`, `9`,
and `16`; the engine derives evenly spaced anchors from that count.
`--anchor-window-seconds` controls how wide each verified decode window may be.
`--anchor-candidates-per-anchor` controls how many timestamp-spaced candidates
the decoder may generate inside each anchor window before ranking.
`--anchor-range-mb` controls the MiB-sized byte window planned around each
timeline anchor. `--edge-range-mb` controls the MiB-sized byte windows planned
at the selected file head and tail.

Fixtures are split into strict-success and truthful-partial sets. Root-level
fixtures and fixtures under `tmp/test-torrents/strict/` must produce one
selected LLM-accepted frame for every target anchor.
Truthful-partial fixtures live under `tmp/test-torrents/truthful-partial/` and
may pass with a partial result when the returned frames and sheet pass local
checks. The default LLM judge is required only when planned pieces completed;
incomplete-piece partials are accepted as truthful diagnostics without requiring
the LLM to endorse their usefulness. Truthful-partial fixtures may also pass
with a failed result when no displayable artifact was available, which verifies
that failed previews do not produce sheets.

The fixture folders contain user-defined acceptance expectations. Do not move
existing torrent files between `strict/` and `truthful-partial/` to make a run
pass. If acceptance fails after clearing or disabling the cache, improve the
engine defaults or implementation, or ask whether the fixture expectation
should change.

Add new fixtures by placing the `.torrent` file into the matching subfolder:

```bash
tmp/test-torrents/strict/example.torrent
tmp/test-torrents/truthful-partial/example.torrent
```

Use `--allow-truthful-partial` only for diagnostics where every torrent may pass
with truthful partial or failed output.
