"""Verify release source files and copy pinned shared files during release preparation.

This is a maintainer tool, not an application dependency or installer. Normal
clones contain the full source and never call this tool at runtime.
"""

from __future__ import annotations
import argparse
import base64
import hashlib
import json
from pathlib import Path, PurePosixPath
import re
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "source-manifest.json"


def safe_target(name: str) -> Path:
    path = PurePosixPath(name)
    if (
        path.is_absolute()
        or ".." in path.parts
        or "\\" in name
        or name.startswith(".git/")
    ):
        raise ValueError("Invalid release path: " + name)
    target = ROOT.joinpath(*path.parts)
    if target.is_symlink() or any(parent.is_symlink() for parent in target.parents):
        raise ValueError("A release path is a symlink: " + name)
    return target


def digest(raw: bytes, name: str = "") -> str:
    # Git stores canonical LF text but checks .bat files out with CRLF.
    # Normalize only that declared text format. Binary fixture bytes stay exact.
    if name.endswith(".bat"):
        raw = raw.replace(b"\r\n", b"\n")
    return hashlib.sha256(raw).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--refresh",
        action="store_true",
        help="Update hashes after a reviewed formatting-only pass.",
    )
    args = parser.parse_args()
    manifest = json.loads(MANIFEST.read_text())
    files = manifest["files"]
    if args.refresh:
        manifest["files"] = {
            name: digest(safe_target(name).read_bytes(), name) for name in files
        }
        MANIFEST.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        return
    source = manifest.get("shared_source")
    if source:
        if source[
            "repository"
        ] != "danial-maqbool/LocalFlow-Studio" or not re.fullmatch(
            "[0-9a-f]{40}", source["commit"]
        ):
            raise ValueError(
                "Shared source must be the approved repository and an immutable commit."
            )
        for name in source["paths"]:
            target = safe_target(name)
            if target.exists():
                continue
            url = (
                "https://raw.githubusercontent.com/"
                + source["repository"]
                + "/"
                + source["commit"]
                + "/"
                + name
            )
            with urllib.request.urlopen(url, timeout=30) as response:
                raw = response.read(1_000_001)
            if len(raw) > 1_000_000 or digest(raw, name) != files[name]:
                raise ValueError("Shared source hash mismatch: " + name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    for name, content in manifest.get("binary_fixtures", {}).items():
        target = safe_target(name)
        raw = base64.b64decode(content, validate=True)
        if len(raw) > 1_000_000 or digest(raw, name) != files[name]:
            raise ValueError("Fixture hash mismatch: " + name)
        if not target.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(raw)
    errors = []
    for name, expected in files.items():
        target = safe_target(name)
        if not target.is_file() or digest(target.read_bytes(), name) != expected:
            errors.append(name)
    if errors:
        raise ValueError("Source verification failed: " + ", ".join(errors))
    (ROOT / "docs/assets").mkdir(parents=True, exist_ok=True)
    print(f"Verified {len(files)} release source files. No runtime data was copied.")


if __name__ == "__main__":
    main()
