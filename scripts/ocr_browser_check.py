"""Direct-browser check of OCR candidates, review gates, and real downloads."""

from __future__ import annotations
import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import threading
import time
import traceback
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from app.service import Application
from localdesk.server import make_server
from tests.fixtures import make_image


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    parser.add_argument("--browser", default=os.environ.get("BROWSER_EXECUTABLE"))
    args = parser.parse_args()
    dest = args.report_dir.resolve()
    dest.mkdir(parents=True, exist_ok=False)
    report = {"status": "started", "checks": [], "mode": "direct loopback navigation"}
    report_file = dest / "ocr-browser-report.json"
    report_file.write_text(json.dumps(report), encoding="utf-8")

    def checked(name, value):
        if not value:
            raise AssertionError(name)
        report["checks"].append(name)

    try:
        from PIL import Image
        from playwright.sync_api import sync_playwright, expect

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary).resolve()
            app = Application(ROOT, root / "data")
            server, token = make_server(app, app.info(), 0)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            try:
                url = "http://127.0.0.1:" + str(server.server_port)
                headers = {"X-Local-Token": token}
                with sync_playwright() as pw:
                    opts = {"headless": True}
                    if args.browser:
                        opts["executable_path"] = args.browser
                    if hasattr(os, "geteuid") and os.geteuid() == 0:
                        opts["args"] = ["--no-sandbox"]
                    browser = pw.chromium.launch(**opts)
                    try:
                        page = browser.new_page(
                            viewport={"width": 1440, "height": 1100}
                        )
                        faults, external = [], []
                        page.on("pageerror", lambda err: faults.append(str(err)))
                        page.on(
                            "request",
                            lambda req: (
                                external.append(req.url)
                                if urlsplit(req.url).hostname not in ("127.0.0.1", None)
                                else None
                            ),
                        )

                        def job(action, body, expected="done"):
                            response = page.request.post(
                                url + "/api/" + action, data=body, headers=headers
                            )
                            assert response.ok, response.status
                            ident = response.json()["job_id"]
                            deadline = time.monotonic() + 45
                            while time.monotonic() < deadline:
                                row = page.request.get(
                                    url + "/api/jobs/" + ident, headers=headers
                                ).json()
                                if row["status"] not in ("queued", "running"):
                                    assert row["status"] == expected, row.get(
                                        "error", "Unexpected job status"
                                    )
                                    return row["result"] if expected == "done" else row
                                time.sleep(0.05)
                            raise TimeoutError(action)

                        source = make_image(
                            root / "candidate.png",
                            text="PRIVATEVALU3\nPublic number 42",
                        )
                        original = source.read_bytes()
                        result = job(
                            "scan",
                            {
                                "paths": [str(source)],
                                "ocr": True,
                                "literals": ["PRIVATEVALUE"],
                            },
                        )
                        ident = result["scans"][0]["id"]
                        scan = app.scan(ident)["report"]
                        checked(
                            "Real OCR scan returns a near-match candidate",
                            bool(scan["ocr_review"]["candidates"]),
                        )
                        page.goto(url, wait_until="networkidle")
                        expect(page.locator("#image-canvas")).to_be_visible()
                        checked(
                            "Candidate outlines are enabled",
                            page.locator("#show-auto-masks").is_checked(),
                        )
                        checked(
                            "Candidate counts are shown",
                            "OCR near-match candidates: 1"
                            in page.locator("#content-review").inner_text(),
                        )
                        page.locator("#show-auto-masks").uncheck()
                        page.locator("#show-auto-masks").check()
                        page.locator("#create-copy").click()
                        expect(
                            page.locator("#clean-output [data-artifact]").first
                        ).to_be_visible(timeout=45000)
                        with page.expect_download() as download:
                            page.locator("#clean-output [data-artifact]").first.click()
                        saved = dest / "candidate-clean.png"
                        download.value.save_as(saved)
                        clean = app.scan(ident)["output"]
                        checked(
                            "Browser download bytes match backend output",
                            saved.read_bytes()
                            == app.download(clean["output"]["path"]).read_bytes(),
                        )
                        with Image.open(saved) as image:
                            checked(
                                "Exported OCR region contains black mask pixels",
                                image.convert("RGB").getpixel((60, 55)) == (0, 0, 0),
                            )
                        checked(
                            "Source bytes are unchanged",
                            source.read_bytes() == original,
                        )
                        page.screenshot(
                            path=str(dest / "candidate-review.png"), full_page=True
                        )
                        # A requested value is genuinely absent in this separate public fixture.
                        public = make_image(
                            root / "public.png", text="Public number 42"
                        )
                        result = job(
                            "scan",
                            {
                                "paths": [str(public)],
                                "ocr": True,
                                "literals": ["MISSINGSECRET"],
                            },
                        )
                        missing_id = result["scans"][0]["id"]
                        denied = job("sanitize", {"id": missing_id}, "failed")
                        checked(
                            "Backend refuses unconfirmed missing values",
                            "confirm the OCR review" in denied["error"],
                        )
                        page.reload(wait_until="networkidle")
                        expect(page.locator("#ocr-review-confirmed")).to_be_visible(
                            timeout=45000
                        )
                        checked(
                            "Export is disabled before review",
                            page.locator("#create-copy").is_disabled(),
                        )
                        page.locator("#ocr-review-confirmed").check()
                        expect(page.locator("#create-copy")).to_be_enabled()
                        page.locator("#create-copy").click()
                        expect(
                            page.locator("#clean-output [data-artifact]").first
                        ).to_be_visible(timeout=45000)
                        checked(
                            "Explicit review reaches the backend audit",
                            app.scan(missing_id)["output"]["audit"][
                                "ocr_review_confirmed"
                            ]
                            is True,
                        )
                        checked("No uncaught browser errors", not faults)
                        checked("No external page requests", not external)
                        report["browser"] = browser.version
                        report["download_sha256"] = hashlib.sha256(
                            saved.read_bytes()
                        ).hexdigest()
                    finally:
                        browser.close()
            finally:
                server.shutdown()
                server.server_close()
                thread.join(timeout=5)
                app.close()
        report["status"] = "passed"
    except Exception:
        report["status"] = "failed"
        report["error"] = traceback.format_exc()
    report_file.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "checks": len(report["checks"])}))
    return int(report["status"] != "passed")


if __name__ == "__main__":
    raise SystemExit(main())
