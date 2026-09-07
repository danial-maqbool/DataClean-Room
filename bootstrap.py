"""Create a private virtual environment and install local runtime dependencies."""

from __future__ import annotations
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dev", action="store_true",
                        help="Install the test tools in the project virtual environment.")
    parser.add_argument(
        "--desktop",
        action="store_true",
        help="Also install mouse and keyboard automation tools.",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Install only from --wheelhouse, without an index.",
    )
    parser.add_argument(
        "--wheelhouse",
        type=Path,
        help="A folder of packages for this OS and Python version.",
    )
    args = parser.parse_args()
    if sys.version_info < (3, 11):
        parser.error("Install Python 3.11 or later.")
    if args.offline and (not args.wheelhouse or not args.wheelhouse.is_dir()):
        parser.error("--offline needs an existing --wheelhouse folder.")
    root = Path(__file__).resolve().parent
    environment = root / ".venv"
    if environment.is_symlink():
        parser.error("The project virtual environment cannot be a symbolic link.")
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    try:
        if not python.is_file():
            print(
                "Creating .venv. System Python packages will not be changed.",
                flush=True,
            )
            venv.EnvBuilder(with_pip=True).create(environment)
        command = [
            str(python),
            "-m",
            "pip",
            "--disable-pip-version-check",
            "install",
            "--require-virtualenv",
            "-r",
            str(root / "requirements.txt"),
        ]
        if args.dev:
            command += ["-r", str(root / "requirements-dev.txt")]
        if args.desktop:
            command += ["-r", str(root / "requirements-desktop.txt")]
        if args.wheelhouse:
            command += ["--find-links", str(args.wheelhouse.resolve())]
        if args.offline:
            command += ["--no-index"]
        subprocess.run(command, cwd=root, check=True)
        subprocess.run(
            [str(python), str(root / "run.py"), "doctor"], cwd=root, check=True
        )
        print("Setup finished. Run start.bat on Windows or sh start.sh on Linux/macOS.")
        print(
            "Install Tesseract language data separately for OCR. RecoveryLab video repair also needs FFmpeg."
        )
        return 0
    except (OSError, subprocess.CalledProcessError) as exc:
        print(f"Setup did not finish: {exc}", file=sys.stderr)
        print(
            "Check Python, internet access, package wheels, and OS dependencies. No app data was deleted.",
            file=sys.stderr,
        )
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
