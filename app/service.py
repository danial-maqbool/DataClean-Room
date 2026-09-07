"""Private scanning workspace with source-integrity checks and copy-only exports."""

from __future__ import annotations
import base64
import json
import uuid
from pathlib import Path
from localdesk.base import BaseApplication
from localdesk.jobs import utcnow
from localdesk.safety import InputError, checked_path, digest, unique_write
from .detectors import KINDS, detect, redact
from .native import request as native_request
from .sanitizer import analyze, clean_archive, clean_text, image_clean, png_info


class Application(BaseApplication):
    def setup(self):
        self.store.execute(
            "CREATE TABLE IF NOT EXISTS scans("
            "id TEXT PRIMARY KEY,path TEXT,created TEXT,report TEXT,settings TEXT,output TEXT)"
        )

    def settings(self, body):
        enabled = body.get("enabled", list(KINDS))
        literals = body.get("literals", [])
        if isinstance(literals, str):
            literals = [s.strip() for s in literals.splitlines() if s.strip()]
        detect("", enabled=enabled, literals=literals)
        return {
            "enabled": enabled,
            "literals": literals,
            "ocr": bool(body.get("ocr", False)),
        }

    def state(self):
        rows = self.store.rows(
            "SELECT id,path,created,report,output FROM scans ORDER BY created DESC,rowid DESC LIMIT 100"
        )
        entries = []
        for row in rows:
            report = json.loads(row.pop("report"))
            row.update(
                {
                    k: report.get(k)
                    for k in [
                        "name",
                        "size",
                        "findings",
                        "supported",
                        "export_mode",
                        "warnings",
                    ]
                }
            )
            row["output"] = json.loads(row["output"]) if row["output"] else None
            entries.append(row)
        return {
            "entries": entries,
            "kinds": KINDS,
            "jobs": self.jobs.recent(),
            "stats": {
                "files": len(entries),
                "findings": sum(e["findings"] or 0 for e in entries),
                "copies": sum(bool(e["output"]) for e in entries),
            },
        }

    def scan(self, ident):
        row = self.store.one("SELECT * FROM scans WHERE id=?", (str(ident),))
        if not row:
            raise InputError("This scan does not exist.")
        row["report"] = json.loads(row["report"])
        row["settings"] = json.loads(row["settings"])
        row["output"] = json.loads(row["output"]) if row["output"] else None
        return row

    def get(self, action, query):
        if action == "scan":
            row = self.scan(query.get("id", ""))
            if query.get("preview") == "1":
                source = checked_path(row["path"])
                if digest(source) != row["report"]["sha256"]:
                    raise InputError("The source changed. Scan it again before review.")
                row["report"] = analyze(source, **row["settings"], include_text=True)
            return row
        if action == "image":
            row = self.scan(query.get("id", ""))
            source = checked_path(row["path"])
            if row["report"]["export_mode"] not in {"image", "pdf"}:
                raise InputError("This scan is not an image.")
            if digest(source) != row["report"]["sha256"]:
                raise InputError("The source changed. Scan it again.")
            raw = source.read_bytes()
            if row["report"]["export_mode"] == "pdf":
                result = native_request(
                    raw, ".pdf", "preview", page=query.get("page", 1)
                )
                return {
                    "mime": "image/png",
                    "data": base64.b64encode(result["content"]).decode("ascii"),
                    "width": result["width"],
                    "height": result["height"],
                    "page": result["page"],
                }
            # Display the same orientation used by the pixel-redaction coordinates.
            raw, _ = image_clean(raw, row["report"]["format"])
            return {
                "mime": "image/png",
                "data": base64.b64encode(raw).decode("ascii"),
                "width": row["report"].get("width"),
                "height": row["report"].get("height"),
            }
        if action == "examples":
            return {
                "files": [
                    str(p)
                    for p in sorted((self.root / "examples").iterdir())
                    if p.is_file() and p.name != "README.txt"
                ]
            }
        return super().get(action, query)

    def post(self, action, body):
        if action == "scan":
            paths = body.get("paths") or [body.get("path", "")]
            if not isinstance(paths, list) or not 1 <= len(paths) <= 20:
                raise InputError("Scan between 1 and 20 files per batch.")
            settings = self.settings(body)
            sources = [checked_path(p) for p in paths]

            def work(context):
                results = []
                for index, path in enumerate(sources):
                    context.progress(
                        int(100 * index / len(sources)), f"Scanning {path.name}"
                    )
                    report = analyze(path, **settings)
                    ident = uuid.uuid4().hex
                    self.store.execute(
                        "INSERT INTO scans VALUES(?,?,?,?,?,NULL)",
                        (
                            ident,
                            str(path),
                            utcnow(),
                            json.dumps(report),
                            json.dumps(settings),
                        ),
                    )
                    results.append({"id": ident, "report": report})
                return {"scans": results}

            return {"job_id": self.jobs.submit("Scan privacy patterns", work)}
        if action == "paste":
            text = str(body.get("text", ""))
            if not text.strip() or len(text) > 250_000:
                raise InputError("Paste between 1 and 250,000 characters.")
            folder = self.data / "inbox" / uuid.uuid4().hex
            path = unique_write(folder / "pasted-text.txt", text.encode("utf-8"))
            return self.post("scan", {**body, "paths": [str(path)]})
        if action == "sanitize":
            row = self.scan(body.get("id", ""))
            source = checked_path(row["path"])
            if not row["report"]["supported"]:
                raise InputError("This input has no implemented clean-copy export.")
            mode = body.get("mode", "labels")
            if mode not in {"labels", "blocks"}:
                raise InputError("Choose labels or blocks.")
            rectangles = body.get("rectangles", [])
            settings = row["settings"]

            def work(context):
                context.progress(10, "Checking that the input has not changed.")
                if digest(source) != row["report"]["sha256"]:
                    raise InputError(
                        "The source changed after scanning. Scan it again."
                    )
                export_mode = row["report"]["export_mode"]
                context.progress(30, "Creating a new copy.")
                if export_mode == "text":
                    raw, audit = clean_text(
                        source,
                        enabled=settings["enabled"],
                        literals=settings["literals"],
                        mode=mode,
                        accept_partial=bool(body.get("accept_partial", False)),
                    )
                    filename = "clean-copy.txt"
                elif export_mode in {"pdf", "office"}:
                    result = native_request(
                        source.read_bytes(),
                        row["report"]["format"],
                        export_mode,
                        enabled=settings["enabled"],
                        literals=settings["literals"],
                        ocr=settings["ocr"],
                        mode=mode,
                        rectangles=body.get("page_rectangles", []),
                    )
                    raw, audit = result["content"], result["audit"]
                    filename = "clean-copy" + result["extension"]
                elif export_mode == "image" and settings["ocr"]:
                    result = native_request(
                        source.read_bytes(),
                        row["report"]["format"],
                        "image",
                        enabled=settings["enabled"],
                        literals=settings["literals"],
                        ocr=True,
                        rectangles=rectangles,
                    )
                    raw, audit = result["content"], result["audit"]
                    filename = "clean-image.png"
                elif export_mode == "image":
                    if row["report"]["matches"] and not rectangles:
                        raise InputError(
                            "OCR found visible private text. Select pixel regions before exporting this image."
                        )
                    raw, notes = image_clean(
                        source.read_bytes(), row["report"]["format"], rectangles
                    )
                    check = png_info(raw)
                    audit = {
                        "selected_regions": len(rectangles),
                        "remaining_nonessential_chunks": len(check["metadata"]),
                        "warnings": notes,
                        "visible_content_fully_verified": False,
                        "source_sha256": row["report"]["sha256"],
                    }
                    filename = "clean-image.png"
                elif export_mode == "archive":
                    raw, audit = clean_archive(
                        source.read_bytes(),
                        enabled=settings["enabled"],
                        literals=settings["literals"],
                        mode=mode,
                    )
                    filename = "clean-bundle.zip"
                else:
                    raise InputError("This export mode is not implemented.")
                if digest(source) != row["report"]["sha256"]:
                    raise InputError(
                        "The source changed during processing. The output was discarded. Scan it again."
                    )
                folder = self.new_output("clean-copy")
                path = unique_write(folder / filename, raw)
                audit["original_unchanged"] = digest(source) == row["report"]["sha256"]
                audit["source_filenames_copied"] = False
                report = unique_write(
                    folder / "clean-copy-report.json",
                    json.dumps(audit, indent=2).encode("utf-8"),
                )
                record = {
                    "output": self.artifact(path),
                    "report": self.artifact(report),
                    "audit": audit,
                }
                self.store.execute(
                    "UPDATE scans SET output=? WHERE id=?",
                    (json.dumps(record), row["id"]),
                )
                return record

            return {"job_id": self.jobs.submit("Create clean copy", work)}
        if action == "export-report":
            row = self.scan(body.get("id", ""))
            report = {
                k: v
                for k, v in row["report"].items()
                if k not in {"name", "text", "preview", "members"}
            }
            if "members" in row["report"]:
                report["archive_member_count"] = len(row["report"]["members"])
            folder = self.new_output("privacy-report")
            path = unique_write(
                folder / "privacy-scan-report.json",
                json.dumps(report, indent=2).encode("utf-8"),
            )
            return self.artifact(path)
        return super().post(action, body)
