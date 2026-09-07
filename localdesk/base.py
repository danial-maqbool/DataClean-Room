"""Common service operations. Application logic stays in app/service.py."""

from __future__ import annotations
import base64
import binascii
import json
import threading
import uuid
from pathlib import Path
from .jobs import Jobs
from .parsers import capabilities
from .documents import advanced_capabilities
from .safety import (
    InputError,
    MAX_FILE_BYTES,
    checked_path,
    clean_name,
    unique_write,
    within,
)
from .storage import Store


class BaseApplication:
    def __init__(
        self,
        root: Path,
        data: Path,
        *,
        passphrase: str | None = None,
        allow_desktop: bool = False,
    ):
        self.root = root.resolve()
        self.data = data.resolve()
        self.data.mkdir(parents=True, exist_ok=True)
        try:
            self.data.chmod(0o700)
        except OSError:
            pass
        self.exports = self.data / "exports"
        self.exports.mkdir(exist_ok=True)
        self.allow_desktop = allow_desktop
        self.store = Store(self.data / "app.vault", passphrase)
        self.jobs = Jobs(self.store)
        self.shutdown = threading.Event()
        self.resuming_background = False
        try:
            self.setup()
        except BaseException:
            self.jobs.close()
            self.store.close()
            raise
        self.resume_error = ""
        resume = self.store.get("background_resume")
        if resume and self.store.encrypted:
            try:
                if resume["action"] not in {
                    "trigger/start",
                    "watch/start",
                    "monitor/start",
                }:
                    raise InputError("Invalid saved background operation.")
                self.resuming_background = True
                self.post(resume["action"], resume["body"])
            except Exception as exc:
                self.resume_error = str(exc)[:300]
            finally:
                self.resuming_background = False

    def setup(self) -> None:
        pass

    def info(self) -> dict:
        return {
            **json.loads((self.root / "project.json").read_text(encoding="utf-8")),
            "example_path": str(self.root / "examples"),
            "data_path": str(self.data),
            "resume_error": self.resume_error,
            "capabilities": {
                **capabilities(),
                **advanced_capabilities(),
                "encrypted_database": self.store.encrypted,
                "desktop_allowed": self.allow_desktop,
            },
        }

    def state(self) -> dict:
        return {"jobs": self.jobs.recent()}

    def new_output(self, label: str) -> Path:
        path = self.exports / f"{clean_name(label)}-{uuid.uuid4().hex[:12]}"
        path.mkdir(mode=0o700)
        return path

    def artifact(self, path: Path) -> dict:
        if not within(path, self.exports) or not path.is_file():
            raise InputError("The output file is not available.")
        return {
            "name": path.name,
            "path": path.relative_to(self.exports).as_posix(),
            "size": path.stat().st_size,
        }

    def download(self, relative: str) -> Path:
        if not relative or "\\" in relative:
            raise InputError("The output path is invalid.")
        path = checked_path(self.exports / relative, max_bytes=None)
        if not within(path, self.exports):
            raise InputError("Only app output files can be downloaded.")
        return path

    def browse(self, value: str | None) -> dict:
        path = checked_path(value or self.root / "examples", directory=True)
        rows = []
        try:
            entries = sorted(
                path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())
            )
            for p in entries[:1500]:
                if p.is_symlink() or p.name.startswith("."):
                    continue
                rows.append({"name": p.name, "path": str(p), "directory": p.is_dir()})
        except PermissionError as exc:
            raise InputError(
                "This folder cannot be listed with the current OS permissions."
            ) from exc
        return {
            "path": str(path),
            "parent": str(path.parent),
            "entries": rows,
            "limited": len(entries) > 1500,
        }

    def common_get(self, action: str, query: dict) -> dict:
        if action == "info":
            return self.info()
        if action == "state":
            return self.state()
        if action == "browse":
            return self.browse(query.get("path"))
        if action.startswith("jobs/"):
            return self.jobs.get(action.split("/", 1)[1])
        return self.get(action, query)

    def common_post(self, action: str, body: dict) -> dict:
        if action == "upload":
            content = body.get("content", "")
            if not isinstance(content, str) or len(content) > MAX_FILE_BYTES * 1.4:
                raise InputError("The uploaded file exceeds 25 MiB.")
            try:
                raw = base64.b64decode(content, validate=True)
            except (ValueError, binascii.Error) as exc:
                raise InputError("The uploaded file data is not valid.") from exc
            if len(raw) > MAX_FILE_BYTES:
                raise InputError("The uploaded file exceeds 25 MiB.")
            folder = self.data / "inbox" / uuid.uuid4().hex
            destination = folder / clean_name(body.get("name", "input.txt"))
            unique_write(destination, raw)
            return {
                "path": str(destination),
                "name": destination.name,
                "size": len(raw),
            }
        if action == "backup":
            folder = self.new_output("database-backup")
            path = folder / "app.vault"
            self.store.backup(path)
            return self.artifact(path)
        if action == "cancel":
            return self.jobs.cancel(str(body.get("id", "")))
        result = self.post(action, body)
        if action in {"trigger/start", "watch/start", "monitor/start"}:
            self.store.set("background_resume", {"action": action, "body": body})
        elif action in {"trigger/stop", "watch/stop", "monitor/stop"}:
            self.store.set("background_resume", None)
        return result

    def get(self, action: str, query: dict) -> dict:
        raise InputError("This operation does not exist.")

    def post(self, action: str, body: dict) -> dict:
        raise InputError("This operation does not exist.")

    def close(self) -> None:
        self.shutdown.set()
        self.jobs.close()
        self.store.close()
