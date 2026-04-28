# Add Video Performance

Date: 2026-04-27

Validation method:

- Backend contract and integration tests exercise `POST /videos`.
- Full Playwright flow submits a video from the browser against local services.

Result:

- Local add-video flow completed within the test timeout and returned an
  immediate accepted/succeeded status using deterministic metadata fixtures.

Residual risk:

- Production torrent metadata retrieval latency depends on the real provider.
  The provider interface keeps the user acknowledgement independent from live
  metadata retrieval work.
