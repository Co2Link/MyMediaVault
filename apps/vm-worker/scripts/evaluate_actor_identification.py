from __future__ import annotations

import argparse
import json
from pathlib import Path

from mymediavault_vm_worker.actor_analysis import (
    ActorAnalysisConfig,
    FaceModels,
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
        args.output.write_text(f"{serialized}\n", encoding="utf-8")
    raise SystemExit(0 if result["passed"] else 1)


if __name__ == "__main__":
    main()
