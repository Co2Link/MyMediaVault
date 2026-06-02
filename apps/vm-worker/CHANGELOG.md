# Changelog

## 0.3.0

- Internalize preview generation so the VM worker no longer depends on a
  separately published `torrent-preview` package.
- Retain stalled sparse-swarm downloads in a bounded low-rate warm pool and
  promote delayed retries as soon as retained handles make useful progress.
- Add structured warm-pool transition logs and operator tuning settings.

## 0.2.1

- Pin `torrent-preview` 5.3.3 so the preview harness continuously fills unused
  concurrency slots while longer-running previews remain active.

## 0.2.0

- Add sequential asynchronous torrent actor identification from durable preview
  frames using checksum-pinned OpenCV YuNet and SFace models.
- Persist UUID actor identities, generated profile crops, capped versioned
  exemplars, recomputed centroids, queue diagnostics, and bounded lease-based
  retries.
- Add the strict offline actor-identification fixture evaluator and bake
  verified face models into the worker image.
