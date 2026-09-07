"""Materialize checked source for publication. Not part of application startup."""

from pathlib import Path, PurePosixPath
import base64
import hashlib
import io
import json
import lzma
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
COMMON = [
    "run.py",
    "bootstrap.py",
    "start.bat",
    "start.sh",
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "SECURITY.md",
    "AGENTS.md",
    "requirements.txt",
    "requirements-desktop.txt",
    "requirements-neural.txt",
    "requirements-dev.txt",
    "requirements-optional.txt",
    "web/common.js",
    "web/index.html",
    "web/style.css",
    "scripts/browser_check.py",
    "scripts/verify.py",
    "scripts/materialize.py",
    "tests/support.py",
    "tests/fixtures.py",
    "tests/test_advanced_common.py",
    "tests/test_http.py",
    "tests/test_safety.py",
    "tests/test_vault.py",
    "tests/test_portability.py",
    "tests/__init__.py",
    "docs/SETUP.md",
    "docs/BACKGROUND.md",
    "docs/SECURITY_REVIEW.md",
    "docs/SOURCES.md",
    "docs/UPGRADING.md",
    "docs/BUILD_STANDARDS.md",
    "CONTRIBUTING.md",
    ".github/ISSUE_TEMPLATE/bug_report.md",
    ".github/pull_request_template.md",
]


def main():
    source = ROOT / "_runtime"
    if not (ROOT / ".runtime-version").exists():
        shutil.copytree(source / "localdesk", ROOT / "localdesk", dirs_exist_ok=True)
        for name in COMMON:
            target = ROOT / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source / name, target)
        (ROOT / ".runtime-version").write_text(
            "a42262279fef3a69f031fecfcdd54cabc78c682b\n"
        )
    transport = ROOT / ".release"
    parts = sorted(transport.glob("part-*"))
    if parts:
        encoded = "".join(p.read_text().strip() for p in parts)
        if len(encoded) > 5_000_000:
            raise ValueError("Publication package is too large.")
        compressed = base64.b64decode(encoded, validate=True)
        expected = (transport / "project.sha256").read_text().strip()
        if hashlib.sha256(compressed).hexdigest() != expected:
            raise ValueError("Publication checksum does not match.")
        decoder = lzma.LZMADecompressor(memlimit=256_000_000)
        data = decoder.decompress(compressed, max_length=10_000_001)
        if len(data) > 10_000_000 or not decoder.eof or decoder.unused_data:
            raise ValueError("Publication package exceeds its expansion limit.")
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            if (
                len(archive.infolist()) > 300
                or sum(i.file_size for i in archive.infolist()) > 10_000_000
            ):
                raise ValueError("Publication file limits exceeded.")
            names = set()
            for item in archive.infolist():
                path = PurePosixPath(item.filename)
                if (
                    item.filename in names
                    or path.is_absolute()
                    or ".." in path.parts
                    or "\\" in item.filename
                    or ".git" in path.parts
                    or ".github" in path.parts
                ):
                    raise ValueError("Invalid publication path.")
                if ((item.external_attr >> 16) & 0o170000) == 0o120000:
                    raise ValueError("Publication symlinks are not allowed.")
                names.add(item.filename)
                target = ROOT.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(item))
        shutil.rmtree(transport)
    shutil.rmtree(source, ignore_errors=True)
    (ROOT / "docs/assets").mkdir(parents=True, exist_ok=True)
    files = {}
    for parent in ["app", "localdesk", "web", "tests", "scripts", "examples"]:
        for path in (ROOT / parent).rglob("*"):
            if path.is_file() and "__pycache__" not in path.parts:
                files[path.relative_to(ROOT).as_posix()] = hashlib.sha256(
                    path.read_bytes()
                ).hexdigest()
    (ROOT / "source-manifest.json").write_text(
        json.dumps({"files": files}, indent=2, sort_keys=True) + "\n"
    )
    for name in ["README.md", "project.json", "app/service.py", "run.py", "web/app.js"]:
        if not (ROOT / name).is_file():
            raise ValueError("Required source is absent: " + name)
    print("Standalone source prepared without importing user data.")


if __name__ == "__main__":
    main()
