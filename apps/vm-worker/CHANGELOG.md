# Changelog

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
