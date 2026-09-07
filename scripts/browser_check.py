"""Exercise the UI against a real temporary backend and record actual UI states.

Install Playwright for this developer check. Use --browser for a local Chromium.
--bridge is only for test hosts that cannot navigate to loopback URLs. It renders
local app assets in a blank page and forwards fetch calls to the same HTTP server.
It does not change browser policy or application source files.
"""

from __future__ import annotations
import argparse
import base64
import io
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", default=os.environ.get("BROWSER_EXECUTABLE"))
    parser.add_argument("--bridge", action="store_true")
    parser.add_argument("--record", action="store_true")
    parser.add_argument("--report-dir", type=Path, default=ROOT / "docs",
                        help="Output folder for this run, including recorded media.")
    args = parser.parse_args()
    report_dir = args.report_dir.expanduser()
    if not report_dir.is_absolute():
        report_dir = ROOT / report_dir
    report_dir.mkdir(parents=True, exist_ok=True)
    (report_dir / "browser-report.json").write_text(
        json.dumps({"status": "started", "complete": False, "passed": 0}) + "\n",
        encoding="utf-8",
    )
    from playwright.sync_api import sync_playwright

    config = json.loads((ROOT / "project.json").read_text())
    (report_dir / "assets").mkdir(parents=True, exist_ok=True)
    frames = []
    checks = []
    errors = []
    requests = []
    started = time.monotonic()

    def checked(name, condition=True):
        if not condition:
            raise AssertionError(name)
        checks.append(name)

    with tempfile.TemporaryDirectory() as temp, sync_playwright() as pw:
        process = subprocess.Popen(
            [
                sys.executable,
                "-u",
                str(ROOT / "run.py"),
                "--demo",
                "--no-browser",
                "--port",
                "0",
                "--data-dir",
                temp,
            ],
            cwd=ROOT,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        browser = None
        try:
            first = process.stdout.readline()
            match = re.search(r"http://127\.0\.0\.1:\d+", first)
            if not match:
                raise RuntimeError("The app did not report a local URL: " + first)
            url = match.group()
            launch = {"headless": True}
            if args.browser:
                launch["executable_path"] = args.browser
            if hasattr(os, "geteuid") and os.geteuid() == 0:
                launch["args"] = ["--no-sandbox"]
            browser = pw.chromium.launch(**launch)
            page = browser.new_page(
                viewport={"width": 1440, "height": 1040}, device_scale_factor=1
            )
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("request", lambda request: requests.append(request.url))
            if args.bridge:
                html = urllib.request.urlopen(url, timeout=5).read().decode()
                html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.S)
                html = re.sub(r"<link[^>]*>", "", html)
                page.set_content(html)
                page.add_style_tag(content=(ROOT / "web/style.css").read_text())

                def bridge(_source, resource, options):
                    if not resource.startswith("/api/"):
                        raise ValueError(
                            "Only local API paths are allowed in this test."
                        )
                    request = urllib.request.Request(
                        url + resource,
                        data=(
                            options.get("body", "").encode()
                            if options.get("body")
                            else None
                        ),
                        headers=options.get("headers", {}),
                        method=options.get("method", "GET"),
                    )
                    try:
                        with urllib.request.urlopen(request, timeout=35) as r:
                            return {
                                "status": r.status,
                                "body": base64.b64encode(r.read()).decode(),
                                "content_type": r.headers.get("Content-Type", ""),
                            }
                    except urllib.error.HTTPError as r:
                        return {
                            "status": r.code,
                            "body": base64.b64encode(r.read()).decode(),
                            "content_type": r.headers.get("Content-Type", ""),
                        }

                page.expose_binding("__local_http", bridge)
                page.evaluate(
                    """()=>{window.fetch=async(resource,options={})=>{const r=await window.__local_http(String(resource),options);return new Response(Uint8Array.from(atob(r.body),c=>c.charCodeAt(0)),{status:r.status,headers:{'Content-Type':r.content_type}});};}"""
                )
                common = (ROOT / "web/common.js").read_text().replace("export ", "")
                common = common.replace(
                    "const theme=localStorage.getItem('localdesk-theme') || 'light';",
                    "const theme='light';",
                ).replace("localStorage.setItem('localdesk-theme',next);", "")
                app = re.sub(
                    r"import [\s\S]*?from './common.js';",
                    "",
                    (ROOT / "web/app.js").read_text(),
                    count=1,
                )
                page.evaluate("async()=>{" + common + "\n" + app + "}")
            else:
                page.goto(url, wait_until="networkidle")
            page.wait_for_selector("#view h1")
            checked("Main view renders")

            def settle():
                page.wait_for_timeout(250)
                page.locator("#job-bar").wait_for(state="hidden", timeout=30000)
                page.wait_for_timeout(200)
                faults = page.locator(".toast.error").all_text_contents()
                if faults:
                    raise AssertionError("UI operation failed: " + str(faults))

            def frame(label, scroll=None):
                settle()
                page.locator(".toast").evaluate_all("(xs)=>xs.forEach(x=>x.remove())")
                if scroll:
                    page.locator(scroll).scroll_into_view_if_needed()
                else:
                    page.evaluate("window.scrollTo(0,0)")
                page.wait_for_timeout(100)
                if args.record:
                    frames.append((label, page.screenshot()))

            frame("Start with a local workspace")
            name = config["repository"]
            if name == "LocalFlow-Studio":
                checked(
                    "All 17 workflow node types are available",
                    page.locator("[data-add-node]").count() == 17,
                )
                checked(
                    "OCR, tables, semantic, summary, and desktop controls exist",
                    all(
                        page.locator('[data-add-node="' + kind + '"]').count() == 1
                        for kind in ["ocr", "tables", "semantic", "summary", "desktop"]
                    ),
                )
                page.locator("#preview-run").click()
                settle()
                checked(
                    "Workflow preview completes",
                    page.locator(".node-result").count() == 6,
                )
                frame("Preview the six-step invoice workflow", ".workflow-grid")
                page.locator("#real-run").click()
                settle()
                checked(
                    "Workflow output artifacts are listed",
                    page.locator("[data-artifact]").count() == 5,
                )
                frame(
                    "Create three invoice copies, a CSV, and a run report",
                    "#run-results",
                )
                page.locator("#save-flow").click()
                settle()
                checked("Workflow definition can be saved")
                page.locator('[data-node="id"]').click()
                checked(
                    "Node settings can be selected",
                    page.locator("#node-config").input_value().find("invoice_id") >= 0,
                )
                frame("Inspect extraction settings", ".workflow-grid")
            elif name == "FileLens-Desktop":
                page.locator("#load-demo").click()
                settle()
                checked(
                    "Demo index returns search results",
                    page.locator(".search-hit").count() > 0,
                )
                frame("Search the local document index")
                page.locator("#search-mode").select_option("keyword")
                settle()
                checked(
                    "Search mode control works",
                    page.locator("#search-mode").input_value() == "keyword",
                )
                page.locator("#search-query").fill("attention")
                page.locator("#run-search").click()
                settle()
                checked(
                    "Keyword filter returns one file",
                    page.locator(".search-hit").count() == 1,
                )
                frame("Read matching text without opening the source")
                page.locator("#file-tags").fill("course,review")
                page.locator("#save-tags").click()
                settle()
                checked("File tags save")
                page.locator("#save-search").click()
                page.locator("#ask-value").fill("Transformer notes")
                page.locator("#ask-save").click()
                settle()
                checked("Search can be saved")
                page.locator("#search-mode").select_option("semantic")
                settle()
                checked(
                    "Semantic search returns local results",
                    page.locator(".search-hit").count() > 0,
                )
                frame("Rank local document meaning without a cloud model")
                page.locator('[data-nav="duplicates"]').click()
                settle()
                checked(
                    "Duplicate view shows matching copies",
                    "2 identical copies" in page.locator("#view").inner_text(),
                )
                frame("Compare byte-identical copies")
                page.locator('[data-nav="search"]').click()
                settle()
            elif name == "RecoveryLab":
                page.locator("#use-samples").click()
                settle()
                checked(
                    "Five sample files are inspected",
                    page.locator("[data-inspection]").count() == 5,
                )
                frame("Inspect damaged and valid sample files")
                page.locator("#recover-file").click()
                settle()
                checked(
                    "A recovered copy has download artifacts",
                    page.locator("[data-artifact]").count() == 2,
                )
                frame("Read the recovery evidence", "#recovery-output")
                page.locator("#recover-batch").click()
                settle()
                checked(
                    "Batch recovery marks all five copies",
                    "5" in page.locator(".stat-value").last.inner_text(),
                )
                page.locator("[data-inspection]").filter(
                    has_text="missing-directory"
                ).click()
                settle()
                frame(
                    "Recover surviving entries from a damaged ZIP", "#inspection-panel"
                )
                page.locator("#view-hex").click()
                settle()
                checked("Read-only hex view opens", page.locator("#modal").is_visible())
                page.locator("#modal-close").click()
            elif name == "ActivityGraph":
                page.locator("#demo").click()
                settle()
                checked(
                    "Demo timeline contains eight labeled events",
                    page.locator("[data-event]").count() == 8,
                )
                frame("Review the labeled demo timeline")
                page.locator("#edit-tags").fill("demo,review")
                page.locator("#save-event").click()
                settle()
                checked("Event notes and tags can be saved")
                page.locator("#add-note").click()
                page.locator("#note-text").fill("A manual note from the browser test.")
                page.locator("#save-note").click()
                settle()
                checked(
                    "Manual note appears", page.locator("[data-event]").count() == 9
                )
                page.locator('[data-nav="graph"]').click()
                settle()
                checked(
                    "Project graph has real event nodes",
                    page.locator("[data-graph-node]").count() > 0,
                )
                frame("Explore project and file relationships")
                page.locator('[data-nav="folders"]').click()
                settle()
                checked(
                    "Monitoring remains paused",
                    "Monitoring paused" in page.locator("#view").inner_text(),
                )
                checked(
                    "Window-title capture requires consent",
                    "Enable with consent" in page.locator("#view").inner_text(),
                )
                checked(
                    "Selected browser import control exists",
                    page.locator("#browser-records").count() == 1,
                )
                frame("Control folders, history retention, and monitoring")
                page.locator('[data-nav="timeline"]').click()
                settle()
            elif name == "DataClean-Room":
                page.locator("#demo-files").click()
                settle()
                checked(
                    "Four example files are scanned",
                    page.locator("[data-scan]").count() == 4,
                )
                checked(
                    "Clean preview removes the sample email",
                    "alex@example.test"
                    not in page.locator("#clean-preview").inner_text(),
                )
                frame(
                    "Review pattern matches and the replacement text", "#content-review"
                )
                page.locator("#create-copy").click()
                settle()
                checked(
                    "Clean text and audit report are available",
                    page.locator("#clean-output [data-artifact]").count() == 2,
                )
                frame("Create a new copy and keep the input unchanged", "#clean-output")
                page.locator("[data-scan]").filter(
                    has_text="image-with-comment"
                ).click()
                settle()
                page.wait_for_selector("#image-canvas")
                if page.locator("#add-region").count():
                    page.locator("#add-region").click()
                    page.locator("#coord-2").fill("120")
                    page.locator("#coord-3").fill("50")
                    page.locator("#save-region").click()
                    settle()
                    checked(
                        "Image region selection is available",
                        "1 selected regions"
                        in page.locator("#region-count").inner_text(),
                    )
                    frame(
                        "Select visible pixels for opaque redaction", "#content-review"
                    )
                    page.locator("#create-copy").click()
                    settle()
                    checked(
                        "Image clean copy is exported",
                        page.locator("#clean-output [data-artifact]").count() == 2,
                    )
                page.locator("[data-scan]").filter(has_text="sample-contact").click()
                settle()
            # Every route must render without an exception or error placeholder.
            for nav in page.locator(".nav-link").all():
                label = nav.inner_text()
                nav.click()
                settle()
                checked(
                    "Navigation: " + label,
                    "could not load" not in page.locator("#view").inner_text(),
                )
            page.locator(".nav-link").first.click()
            settle()
            page.locator(".toast").evaluate_all("(xs)=>xs.forEach(x=>x.remove())")
            page.evaluate("window.scrollTo(0,0)")
            if args.record:
                page.screenshot(
                    path=str(report_dir / "assets/screenshot.png"), full_page=True
                )
            page.locator("#theme-button").click()
            checked(
                "Dark theme control works",
                page.locator("html").get_attribute("data-theme") == "dark",
            )
            if args.record:
                page.screenshot(
                    path=str(report_dir / "assets/dark-mode.png"), full_page=True
                )
            page.locator("#theme-button").click()
            page.set_viewport_size({"width": 390, "height": 844})
            settle()
            checked(
                "Mobile viewport has no page-wide overflow",
                page.evaluate(
                    "document.documentElement.scrollWidth<=window.innerWidth+2"
                ),
            )
            if args.record:
                page.screenshot(
                    path=str(report_dir / "assets/mobile.png"), full_page=True
                )
            checked("No uncaught browser errors", not errors)
            checked(
                "No external browser network request",
                all(x.startswith((url, "data:", "blob:")) for x in requests),
            )
            if args.record and frames:
                from PIL import Image

                images = [
                    Image.open(io.BytesIO(raw))
                    .convert("RGB")
                    .resize((1080, 780))
                    .quantize(colors=128)
                    for _, raw in frames
                ]
                images[0].save(
                    report_dir / "assets/demo.gif",
                    save_all=True,
                    append_images=images[1:],
                    duration=[1800] * len(images),
                    loop=0,
                    optimize=True,
                )
                (report_dir / "assets/demo-frames.json").write_text(
                    json.dumps(
                        [
                            {"frame": i + 1, "caption": text, "duration_ms": 1800}
                            for i, (text, _) in enumerate(frames)
                        ],
                        indent=2,
                    )
                    + "\n"
                )
            browser_version = browser.version
            browser.close()
            browser = None
            checked(
                "Closing the browser leaves the worker running", process.poll() is None
            )
            with urllib.request.urlopen(url + "/healthz", timeout=5) as health:
                checked(
                    "Worker health remains available after browser close",
                    health.status == 200,
                )
            report = {
                "project": name,
                "status": "passed",
                "complete": True,
                "browser": browser_version,
                "mode": (
                    "local-asset rendering with real HTTP bridge"
                    if args.bridge
                    else "direct loopback navigation"
                ),
                "checks": checks,
                "passed": len(checks),
                "errors": errors,
                "seconds": round(time.monotonic() - started, 3),
                "media": "Actual recorded application states, not mockups. GIF timing is illustrative.",
            }
            (report_dir / "browser-report.json").write_text(
                json.dumps(report, indent=2) + "\n"
            )
            print(json.dumps(report, indent=2))
        except Exception as exc:
            (report_dir / "browser-report.json").write_text(
                json.dumps({"project": config["repository"], "status": "failed",
                            "complete": False, "passed": len(checks), "checks": checks,
                            "errors": errors + [type(exc).__name__ + ": " + str(exc)]},
                           indent=2) + "\n", encoding="utf-8")
            raise
        finally:
            if browser:
                browser.close()
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
