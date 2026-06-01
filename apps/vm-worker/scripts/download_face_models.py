from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import tempfile
import urllib.request
from pathlib import Path
from typing import Any


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Download checksum-verified YuNet and SFace ONNX models."
    )
    parser.add_argument(
        "--manifest",
        type=Path,
        default=Path(__file__).parents[1] / "models" / "face_models.json",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path(".local/models"),
    )
    parser.add_argument(
        "--check-only",
        action="store_true",
        help="Verify existing files without downloading missing or invalid models.",
    )
    args = parser.parse_args()

    manifest = _load_manifest(args.manifest)
    args.output.mkdir(parents=True, exist_ok=True)
    for name, model in manifest["models"].items():
        target = args.output / model["filename"]
        expected_sha256 = model["sha256"]
        if target.is_file() and _sha256(target) == expected_sha256:
            print(f"verified {name}: {target}")
            continue
        if args.check_only:
            raise SystemExit(f"missing or invalid {name} model: {target}")
        _download_verified(model["url"], target, expected_sha256)
        print(f"downloaded {name}: {target}")


def _load_manifest(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if value.get("schemaVersion") != 1 or not isinstance(value.get("models"), dict):
        raise ValueError(f"Unsupported face-model manifest: {path}")
    for name, model in value["models"].items():
        if not isinstance(model, dict):
            raise ValueError(f"Invalid face-model entry: {name}")
        for field in ("filename", "version", "url", "sha256"):
            if not isinstance(model.get(field), str) or not model[field]:
                raise ValueError(f"Invalid {field} for face model: {name}")
    return value


def _download_verified(url: str, target: Path, expected_sha256: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temporary:
        temporary_path = Path(temporary.name)
        try:
            with urllib.request.urlopen(url) as response:
                shutil.copyfileobj(response, temporary)
        except Exception:
            temporary_path.unlink(missing_ok=True)
            raise
    actual_sha256 = _sha256(temporary_path)
    if actual_sha256 != expected_sha256:
        temporary_path.unlink(missing_ok=True)
        raise ValueError(
            f"Checksum mismatch for {url}: expected {expected_sha256}, got {actual_sha256}"
        )
    temporary_path.replace(target)


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    main()
