"""File limits and output rules shared by the local applications.

These checks reduce accidental damage. They do not sandbox hostile native
libraries or defend against another process running as the same OS user.
"""

from __future__ import annotations

import fnmatch
import hashlib
import io
import os
import re
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from xml.etree import ElementTree as ET

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_ARCHIVE_BYTES = 50 * 1024 * 1024
MAX_ARCHIVE_ENTRIES = 1000
MAX_TEXT_CHARS = 250_000
DEFAULT_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "node_modules",
    "__pycache__",
    ".local-data",
    ".localflow",
    ".env",
    ".ssh",
    ".aws",
    ".config",
    "AppData",
)


class InputError(ValueError):
    """A user input is invalid or outside an explicit processing limit."""


def integer(value: object, low: int, high: int, label: str = "Value") -> int:
    try:
        number = int(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise InputError(f"{label} must be an integer.") from exc
    if (
        isinstance(value, bool)
        or (isinstance(value, float) and not value.is_integer())
        or not low <= number <= high
    ):
        raise InputError(f"{label} must be between {low} and {high}.")
    return number


def clean_name(name: str) -> str:
    # Both separator forms are rejected on every host OS.
    name = str(name).replace("\\", "/").split("/")[-1]
    name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip(" .")[:140]
    if not name or name in {".", ".."}:
        raise InputError("Enter a file name.")
    if name.split(".")[0].upper() in {
        "CON",
        "PRN",
        "AUX",
        "NUL",
        *(f"COM{i}" for i in range(1, 10)),
        *(f"LPT{i}" for i in range(1, 10)),
    }:
        name = "_" + name
    return name


def checked_path(
    value: str | Path,
    *,
    directory: bool = False,
    max_bytes: int | None = MAX_FILE_BYTES,
) -> Path:
    if not isinstance(value, (str, Path)) or not str(value).strip():
        raise InputError("Enter a full local path.")
    original = Path(value).expanduser().absolute()
    # Check ancestors before resolve() can hide a symbolic link.
    for part in (original, *original.parents):
        if part.is_symlink():
            raise InputError("Symbolic links are not processed. Select the real path.")
        if hasattr(part, "is_junction") and part.is_junction():
            raise InputError(
                "Directory junctions are not processed. Select the real path."
            )
    try:
        path = original.resolve(strict=True)
    except (OSError, RuntimeError) as exc:
        raise InputError("The local path does not exist or cannot be opened.") from exc
    if directory and not path.is_dir():
        raise InputError("Select a folder, not a file.")
    if not directory and not path.is_file():
        raise InputError("Select a regular file.")
    if not directory and max_bytes is not None and path.stat().st_size > max_bytes:
        raise InputError("This file exceeds the 25 MiB input limit.")
    return path


def within(path: Path, root: Path) -> bool:
    try:
        path.resolve().relative_to(root.resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def unique_write(path: Path, data: bytes) -> Path:
    """Create a complete new file. Never replace an existing destination."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if any(p.is_symlink() for p in (path.parent, *path.parent.parents)):
        raise InputError("Output folders must not contain symbolic links.")
    # O_EXCL prevents an existing destination from being overwritten.
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def atomic_json(path: Path, text: str) -> None:
    """Replace an app-owned configuration file, not a user source file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w", encoding="utf-8", dir=path.parent, delete=False
    ) as stream:
        tmp = Path(stream.name)
        stream.write(text)
    try:
        os.replace(tmp, path)
    finally:
        tmp.unlink(missing_ok=True)


def excluded(path: Path, root: Path, patterns: list[str] | tuple[str, ...]) -> bool:
    relative = path.relative_to(root)
    return any(
        fnmatch.fnmatch(part, pat) or fnmatch.fnmatch(relative.as_posix(), pat)
        for part in relative.parts
        for pat in patterns
    )


def walk_files(root: Path, *, patterns=DEFAULT_EXCLUDES, limit: int = 20_000):
    """Yield regular files without following links. Report inaccessible roots."""
    root = checked_path(root, directory=True)
    count = 0

    def onerror(exc: OSError) -> None:
        raise InputError(f"Cannot read a folder: {exc.filename}") from exc

    for base, dirs, files in os.walk(root, followlinks=False, onerror=onerror):
        parent = Path(base)
        dirs[:] = sorted(
            d
            for d in dirs
            if not (parent / d).is_symlink()
            and not (hasattr(parent / d, "is_junction") and (parent / d).is_junction())
            and not excluded(parent / d, root, patterns)
        )
        for name in sorted(files):
            p = parent / name
            if p.is_symlink() or excluded(p, root, patterns) or not p.is_file():
                continue
            count += 1
            if count > limit:
                raise InputError(
                    f"The folder exceeds the {limit:,} file limit. Select a smaller folder."
                )
            yield p


def archive_name_ok(name: str) -> bool:
    if not name or "\\" in name or "\x00" in name or ":" in name:
        return False
    p = PurePosixPath(name)
    return (
        not p.is_absolute()
        and ".." not in p.parts
        and all(len(s) <= 180 for s in p.parts)
    )


def open_zip(raw: bytes) -> zipfile.ZipFile:
    if len(raw) > MAX_FILE_BYTES:
        raise InputError("The archive exceeds the 25 MiB input limit.")
    archive = zipfile.ZipFile(io.BytesIO(raw))
    infos = archive.infolist()
    if len(infos) > MAX_ARCHIVE_ENTRIES:
        archive.close()
        raise InputError("The archive has more than 1,000 entries.")
    if sum(i.file_size for i in infos) > MAX_ARCHIVE_BYTES:
        archive.close()
        raise InputError("The expanded archive exceeds 50 MiB.")
    if any(
        i.file_size > MAX_FILE_BYTES
        or (i.file_size > 1_000_000 and i.file_size / max(i.compress_size, 1) > 200)
        for i in infos
    ):
        archive.close()
        raise InputError(
            "The archive contains an oversized or highly compressed entry."
        )
    return archive


def safe_xml(raw: bytes):
    if len(raw) > 5 * 1024 * 1024:
        raise InputError("An XML part exceeds 5 MiB.")
    compact = raw.replace(b"\x00", b"").upper()
    if b"<!DOCTYPE" in compact or b"<!ENTITY" in compact:
        raise InputError("XML document types and entities are not supported.")
    return ET.fromstring(raw)
