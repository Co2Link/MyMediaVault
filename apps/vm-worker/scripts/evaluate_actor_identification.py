from __future__ import annotations

import argparse
import json
from pathlib import Path

import cv2
import numpy as np

from mymediavault_vm_worker.actor_analysis import (
    ActorAnalysisConfig,
    FaceModels,
    ProfileCandidate,
    YuNetSFaceAnalyzer,
    evaluate_fixture_partitions,
)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate actor identification against labeled preview fixtures."
    )
    parser.add_argument("--previews", type=Path, required=True)
    parser.add_argument("--ground-truth", type=Path, required=True)
    parser.add_argument("--models-dir", type=Path, default=Path(".local/models"))
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--profile-output",
        type=Path,
        help="Write selected profile crops, annotated alternatives, and a Markdown report.",
    )
    args = parser.parse_args()

    analyzer = YuNetSFaceAnalyzer(
        models=FaceModels.from_manifest(models_dir=args.models_dir),
        config=ActorAnalysisConfig(),
    )
    result = evaluate_fixture_partitions(
        previews_dir=args.previews,
        ground_truth_path=args.ground_truth,
        analyzer=analyzer,
    )
    serialized = json.dumps(result, indent=2, sort_keys=True)
    print(serialized)
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(f"{serialized}\n", encoding="utf-8")
    if args.profile_output:
        _write_profile_report(
            previews_dir=args.previews,
            output_dir=args.profile_output,
            analyzer=analyzer,
            identity_result=result,
        )
    raise SystemExit(0 if result["passed"] else 1)


def _write_profile_report(
    *,
    previews_dir: Path,
    output_dir: Path,
    analyzer: YuNetSFaceAnalyzer,
    identity_result: dict[str, object],
) -> None:
    selected_dir = output_dir / "selected"
    contact_sheet_dir = output_dir / "contact-sheets"
    selected_dir.mkdir(parents=True, exist_ok=True)
    contact_sheet_dir.mkdir(parents=True, exist_ok=True)
    report = [
        "# Actor Profile Evaluation",
        "",
        "Generated locally. Review selected crops and annotated alternatives visually.",
        "",
        "## Identity Metrics",
        "",
        f"- Recall: `{identity_result['recall']}`",
        f"- False merges: `{len(identity_result['falseMerges'])}`",
        f"- Identity splits: `{len(identity_result['identitySplits'])}`",
        "",
        "## Profile Candidates",
        "",
    ]
    for torrent_dir in sorted(path for path in previews_dir.iterdir() if path.is_dir()):
        frame_paths = sorted(torrent_dir.glob("frame_*.jpg"))
        frame_paths_by_key = {path.name: path for path in frame_paths}
        observations = analyzer.analyze_frames(frame_paths)
        clusters = analyzer.main_clusters(observations)
        for cluster_index, cluster in enumerate(clusters, start=1):
            candidates = analyzer.profile_candidates(
                frame_paths_by_key=frame_paths_by_key,
                cluster=cluster,
                observations=observations,
            )
            if not candidates:
                continue
            stem = f"{torrent_dir.name}-cluster-{cluster_index}"
            selected_path = selected_dir / f"{stem}.jpg"
            selected_path.write_bytes(candidates[0].jpeg)
            sheet_path = contact_sheet_dir / f"{stem}.jpg"
            _write_contact_sheet(sheet_path, candidates)
            report.extend(
                [
                    f"### `{torrent_dir.name}` cluster `{cluster_index}`",
                    "",
                    f"- Selected: [`{selected_path.name}`](selected/{selected_path.name})",
                    f"- Alternatives: [`{sheet_path.name}`](contact-sheets/{sheet_path.name})",
                    "",
                    "| Rank | Frame | Score | Flags | Components |",
                    "| --- | --- | ---: | --- | --- |",
                ]
            )
            for rank, candidate in enumerate(candidates, start=1):
                components = ", ".join(
                    f"{name}={value:.3f}"
                    for name, value in sorted(candidate.components.items())
                )
                report.append(
                    f"| {rank} | `{candidate.frame_key}` | {candidate.score:.3f} | "
                    f"{', '.join(candidate.flags) or '-'} | {components} |"
                )
            report.append("")
    (output_dir / "report.md").write_text("\n".join(report), encoding="utf-8")


def _write_contact_sheet(path: Path, candidates: list[ProfileCandidate]) -> None:
    tiles = [_annotated_tile(candidate, rank=index) for index, candidate in enumerate(candidates, 1)]
    encoded, jpeg = cv2.imencode(".jpg", np.hstack(tiles))
    if not encoded:
        raise ValueError(f"Unable to encode profile contact sheet: {path}")
    path.write_bytes(jpeg.tobytes())


def _annotated_tile(candidate: ProfileCandidate, *, rank: int) -> np.ndarray:
    image = cv2.imdecode(
        np.frombuffer(candidate.jpeg, dtype=np.uint8),
        cv2.IMREAD_COLOR,
    )
    if image is None:
        raise ValueError(f"Unable to decode generated profile candidate: {candidate.frame_key}")
    tile = np.full((340, 256, 3), 255, dtype=np.uint8)
    tile[:256] = cv2.resize(image, (256, 256), interpolation=cv2.INTER_AREA)
    lines = [
        f"#{rank} {candidate.score:.3f}",
        candidate.frame_key,
        ",".join(candidate.flags) or "no flags",
    ]
    for index, line in enumerate(lines):
        cv2.putText(
            tile,
            line[:36],
            (5, 280 + index * 22),
            cv2.FONT_HERSHEY_SIMPLEX,
            0.42,
            (0, 0, 0),
            1,
            cv2.LINE_AA,
        )
    return tile


if __name__ == "__main__":
    main()
