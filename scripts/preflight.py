"""Check local prerequisites without opening user files or changing OS settings."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import importlib.metadata
import json
from pathlib import Path
import re
import shutil
import sqlite3
import struct
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def requirements(root: Path, filename: str, platform: str, seen=None) -> dict[str, str]:
    """Read this project's pinned requirement files and its supported OS marker."""
    seen = set() if seen is None else seen
    name = Path(filename)
    if name.name != filename or not filename.startswith("requirements"):
        raise ValueError("Requirement includes must stay in the project root.")
    if filename in seen:
        return {}
    seen.add(filename)
    path = root / filename
    if path.is_symlink():
        raise ValueError("A requirement file cannot be a symbolic link.")
    result = {}
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        if line.startswith("-r "):
            result.update(requirements(root, line[3:].strip(), platform, seen))
            continue
        spec, separator, marker = line.partition(";")
        if separator:
            match = re.fullmatch(r'''\s*sys_platform\s*==\s*["']([^"']+)["']\s*''', marker)
            if not match:
                raise ValueError("Unsupported requirement marker. Review the requirement file.")
            if match[1] != platform:
                continue
        match = re.fullmatch(r"([A-Za-z0-9_.-]+)==([A-Za-z0-9_.+!-]+)", spec.strip())
        if not match:
            raise ValueError("Preflight expects exact runtime and test package pins.")
        package = re.sub(r"[-_.]+", "-", match[1]).lower()
        if package in result and result[package] != match[2]:
            raise ValueError("Conflicting direct package pins: " + package)
        result[package] = match[2]
    return result


def package_status(expected: dict[str, str]) -> dict:
    result = {}
    for name, version in sorted(expected.items()):
        try:
            installed = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            installed = None
        result[name] = {"required": version, "installed": installed, "matches": installed == version}
    return result


def sqlite_status() -> dict:
    db = sqlite3.connect(":memory:")
    try:
        db.execute("CREATE VIRTUAL TABLE probe USING fts5(content)")
        db.execute("INSERT INTO probe VALUES (?)", ("local search check",))
        found = db.execute("SELECT count(*) FROM probe WHERE probe MATCH ?", ("search",)).fetchone()[0]
        return {"version": sqlite3.sqlite_version, "fts5": found == 1}
    except sqlite3.DatabaseError:
        return {"version": sqlite3.sqlite_version, "fts5": False}
    finally:
        db.close()


def native_status(repository: str, tests: bool) -> dict:
    tools = {}
    names = ["tesseract"] if tests or repository in {"LocalFlow-Studio", "FileLens-Desktop", "DataClean-Room"} else []
    if repository == "RecoveryLab":
        names += ["ffmpeg", "ffprobe"]
    for name in names:
        tools[name] = {"found": shutil.which(name) is not None}
    if tools.get("tesseract", {}).get("found"):
        try:
            check = subprocess.run([shutil.which("tesseract"), "--list-langs"],
                                   capture_output=True, text=True, timeout=10, check=False)
            languages = [line.strip() for line in check.stdout.splitlines()[1:]
                         if re.fullmatch(r"[A-Za-z0-9_/-]+", line.strip())]
            tools["tesseract"].update({"english_data": check.returncode == 0 and "eng" in languages,
                                      "languages": languages})
        except (OSError, subprocess.TimeoutExpired):
            tools["tesseract"]["english_data"] = False
    return tools


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tests", action="store_true", help="Also check the development package pins.")
    parser.add_argument("--require-native", action="store_true", help="Fail if applicable native tools or English OCR data are absent.")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "artifacts/local-qa")
    args = parser.parse_args()
    output = args.report_dir.expanduser()
    if not output.is_absolute():
        output = ROOT / output
    output.mkdir(parents=True, exist_ok=True)
    report = {"status": "started", "manual_acceptance": "not_run"}
    try:
        config = json.loads((ROOT / "project.json").read_text(encoding="utf-8"))
        expected = requirements(ROOT, "requirements-dev.txt" if args.tests else "requirements.txt", sys.platform)
        packages = package_status(expected)
        database = sqlite_status()
        native = native_status(config["repository"], args.tests)
        missing_files = [name for name in ["run.py", "bootstrap.py", "start.bat", "start.sh",
                                          "HANDOFF.md", "docs/LOCAL_TESTING.md", "docs/LOCAL_AGENT_PROMPT.md"]
                         if not (ROOT / name).is_file()]
        checks = {"python_3_11_or_later": sys.version_info >= (3, 11),
                  "python_64_bit": struct.calcsize("P") * 8 == 64,
                  "direct_package_pins": all(x["matches"] for x in packages.values()),
                  "sqlite_fts5": database["fts5"], "handoff_files": not missing_files}
        if args.require_native:
            checks["native_tools"] = all(x["found"] and x.get("english_data", True) for x in native.values())
        report = {"schema_version": 1, "checked_at": datetime.now(timezone.utc).isoformat(),
                  "repository": config["repository"], "version": config["version"],
                  "python": sys.version.split()[0], "platform": sys.platform,
                  "virtual_environment": sys.prefix != sys.base_prefix,
                  "profile": "test" if args.tests else "runtime", "checks": checks,
                  "packages": packages, "sqlite": database, "native_tools": native,
                  "missing_files": missing_files, "status": "passed" if all(checks.values()) else "failed",
                  "manual_acceptance": "not_run",
                  "note": "A prerequisite check is not an application, security, or native-service acceptance test. Run pip check separately."}
    except (OSError, ValueError, sqlite3.Error) as exc:
        report = {"status": "failed", "error_type": type(exc).__name__,
                  "note": "Read the requirement files and project configuration. No OS setting or user data was changed.",
                  "manual_acceptance": "not_run"}
    (output / "preflight.json").write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
