# MyMediaVault Preview Worker

VM-hosted Python worker that polls MongoDB for torrents needing preview images,
uses Beanie models that mirror the Mongoose torrent document, delegates polling
and concurrent execution to the `torrent-preview` worker harness, uploads the
generated sheet and frames to R2-compatible storage, and writes preview status
back to the canonical torrent document.

## Run

```bash
cp .env.example .env
uv run mymediavault-preview-worker
```

Required environment:

- `MONGODB_URI`
- `MMV_MONGODB_DB_NAME`
- `R2_ENDPOINT`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`
- `OPENAI_API_KEY`

Optional environment:

- `MMV_PREVIEW_WORKER_MAX_CONCURRENCY` defaults to `20`
- `MMV_PREVIEW_WORKER_POLL_INTERVAL_SECONDS` defaults to `5`
- `MMV_PREVIEW_REPAIR_STALE_PROCESSING_MINUTES` defaults to `120`

The VM runtime must provide Python 3.13, `libtorrent`, `ffmpeg`, and preferably
`ffprobe`. `OPENAI_API_KEY` is required because the worker intentionally runs
`torrent-preview` with the Pydantic AI ranker.
