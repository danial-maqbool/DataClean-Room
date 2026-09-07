"""Test helpers. Tests use private temporary directories and synthetic data."""

import io
import json
import tempfile
import time
import unittest
import zipfile
from pathlib import Path
from app.service import Application
from localdesk.safety import digest

ROOT = Path(__file__).resolve().parents[1]


class Context:
    def check(self):
        pass

    def progress(self, *_):
        pass


class AppCase(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name).resolve()
        self.workspace = self.base / "workspace"
        self.workspace.mkdir()
        self.app = Application(ROOT, self.base / "private")

    def tearDown(self):
        self.app.close()
        self.temp.cleanup()

    def file(self, name="sample.txt", content=b"Example text"):
        p = self.workspace / name
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(content.encode("utf-8") if isinstance(content, str) else content)
        return p

    def finish(self, action, body=None, expected="done"):
        result = self.app.common_post(action, body or {})
        return self.wait(result["job_id"], expected)

    def wait(self, ident, expected="done"):
        start = time.monotonic()
        while time.monotonic() - start < 60:
            job = self.app.jobs.get(ident)
            if job["status"] not in {"queued", "running"}:
                self.assertEqual(job["status"], expected, job)
                return job["result"] if expected == "done" else job
            time.sleep(0.01)
        self.fail("The job did not finish within 60 seconds.")

    def output(self, artifact):
        return self.app.download(artifact["path"]).read_bytes()


def zipped(members):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, value in members.items():
            archive.writestr(name, value)
    return stream.getvalue()
