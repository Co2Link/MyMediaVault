# ADR 002: Preview Selection And Actor Analysis Semantics

- Status: Accepted
- Date: 2026-06-05

## Context

ADR 001 treated OpenAI frame selection as an acceptance gate and allowed actor
analysis to run on partial preview artifacts. That made the torrent lifecycle
harder to reason about: a fully downloaded selected media file could finish as
`complete` with a `completed_best_effort` outcome even when fewer than the
target preview frames existed, and actor analysis could persist an empty or weak
result from an incomplete preview sample.

The actor-analysis quality issue is primarily a preview-sampling issue. The
first corrective step should remain deterministic and bounded rather than
adding an adaptive actor-evidence search over the media file.

## Decision

OpenAI frame selection is a chooser, not a gate. The preview engine extracts
clean local candidates around deterministic timeline anchors, filters them with
local image sanity scoring, and asks OpenAI to choose exactly one candidate for
each target anchor only after all 9 anchors have enough clean candidates.
Structured output uses exactly 9 `{anchor_index, candidate_id}` choices. The
selector validates selected IDs against the runtime candidate pool; invalid
semantic choices fail selection instead of being repaired locally.

Preview extraction uses three separate knobs:

- `MMV_PREVIEW_EXTRACT_FRAMES_PER_ANCHOR`, default `7`.
- `MMV_PREVIEW_MIN_SELECTOR_CANDIDATES_PER_ANCHOR`, default `2`.
- `MMV_PREVIEW_MAX_SELECTOR_CANDIDATES_PER_ANCHOR`, default `4`.

The engine attempts up to the extraction count around each anchor, requires the
minimum number of clean selector candidates before an anchor is eligible for
selection, and sends at most the maximum count to OpenAI. Retry widening targets
anchors that have fewer than the minimum clean candidates.

Planned torrent-piece completeness is diagnostic, not a decode gate. A download
pass proceeds to FFmpeg when requested pieces complete, selected-file byte
progress stalls for the configured progress timeout, or the attempt's download
budget expires. FFmpeg extraction uses strict decode behavior, rejects non-zero
exits and targeted decode-corruption diagnostics, and keeps JPEG frame and sheet
artifacts for storage efficiency.

Torrent state semantics are:

- `complete`: all target anchors produced selected frames.
- `partial`: at least one eligible anchor produced selected frames and the
  torrent remains eligible for improvement.
- `exhausted`: the selected media file is fully downloaded but the engine still
  cannot produce a complete target-frame artifact.

The `completed_best_effort` outcome is removed.

Actor analysis runs only for `complete` preview artifacts. A complete preview
with no qualifying face cluster remains a successful actor-analysis run with an
empty `systemActorIds` list.

## Consequences

Preview artifacts are deterministic, bounded, and easier to explain through
diagnostics. Partial artifacts remain useful for the UI but no longer drive
actor assignments. Some fully downloaded torrents may become `exhausted` when
the selected media cannot produce enough clean candidates for every target
anchor; admins can queue them again after algorithm or configuration changes.
