"""Direct-browser cancellation, navigation and modal checks on real synthetic jobs."""

from pathlib import Path
import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report-dir", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    os.chdir(root)
    base = args.report_dir.resolve()
    base.mkdir(parents=True, exist_ok=False)
    sys.path.insert(0, str(root))
    from tests.fixtures import make_image, make_pdf

    name = json.loads((root / "project.json").read_text())["repository"]
    work = base / "synthetic"
    work.mkdir()
    if name == "ActivityGraph":
        for i in range(2000):
            (work / f"file-{i:04}.txt").write_text("PUBLIC_FIXTURE")
    elif name == "RecoveryLab":
        for i in range(20):
            make_pdf(work / f"document-{i:02}.pdf", text=f"PUBLIC INVOICE {i+1000}")
    else:
        for i in range(20):
            make_image(
                work / f"image-{i:02}.png",
                text=f"PUBLIC INVOICE {i+1000}\nTotal amount 4200",
            )
    before = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in work.iterdir()
    }
    log = (base / "backend.log").open("w")
    process = subprocess.Popen(
        [sys.executable, "-u", "run.py", "--demo", "--no-browser", "--port", "0"],
        stdout=log,
        stderr=subprocess.STDOUT,
    )
    checks = []
    errors = []
    requests = []
    try:
        deadline = time.monotonic() + 30
        while time.monotonic() < deadline:
            match = re.search(
                r"http://127\.0\.0\.1:\d+", (base / "backend.log").read_text()
            )
            if match:
                break
            time.sleep(0.1)
        else:
            raise TimeoutError("startup")
        url = match.group()
        with urllib.request.urlopen(url) as response:
            html = response.read().decode()
        token = re.search(r'name="local-session" content="([^"]+)"', html).group(1)

        def api(action, body=None):
            request = urllib.request.Request(
                url + "/api/" + action,
                data=None if body is None else json.dumps(body).encode(),
                headers={"X-Local-Token": token, "Content-Type": "application/json"},
            )
            with urllib.request.urlopen(request, timeout=20) as response:
                return json.load(response)

        if name == "LocalFlow-Studio":
            action = "run"
            body = {
                "workspace": str(work),
                "dry_run": False,
                "workflow": {
                    "id": "qa-cancel",
                    "name": "QA cancellation",
                    "nodes": [
                        {"id": "scan", "type": "scan", "config": {"pattern": "*.png"}},
                        {"id": "ocr", "type": "ocr", "config": {}},
                        {
                            "id": "csv",
                            "type": "csv",
                            "config": {"filename": "values.csv", "fields": ["text"]},
                        },
                    ],
                    "edges": [
                        {"from": "scan", "to": "ocr"},
                        {"from": "ocr", "to": "csv"},
                    ],
                },
            }
        elif name == "FileLens-Desktop":
            selected = api("roots/add", {"path": str(work), "ocr": True})
            action = "scan"
            body = {"id": selected["id"]}
        elif name == "ActivityGraph":
            api("roots/add", {"path": str(work), "project": "QA"})
            action = "scan"
            body = {}
        else:
            action = "inspect" if name == "RecoveryLab" else "scan"
            body = {"paths": [str(p) for p in work.iterdir()], "ocr": True}
        with sync_playwright() as pw:
            browser = pw.chromium.launch()
            page = browser.new_page(viewport={"width": 1280, "height": 900})
            page.on("pageerror", lambda e: errors.append(str(e)))
            page.on("request", lambda r: requests.append(r.url))
            page.goto(url, wait_until="networkidle")
            page.locator("#help-button").click()
            page.locator("#modal").wait_for(state="visible")
            page.keyboard.press("Escape")
            page.locator("#modal").wait_for(state="hidden")
            checks.append("Help dialog opens and closes with Escape")
            # Use the unmodified UI job module and real backend operation. This
            # starts the same progress/cancellation controls as project buttons.
            page.evaluate(
                """({action,body})=>{
                window.qaOperation={state:'starting'};
                import('/common.js').then(m=>m.runJob(action,body))
                .then(result=>window.qaOperation={state:'done',result})
                .catch(error=>window.qaOperation={state:'error',message:String(error)});
            }""",
                {"action": action, "body": body},
            )
            page.locator("#job-bar").wait_for(state="visible", timeout=15000)
            page.locator(".nav-link").last.click()
            checks.append("Navigation remains usable while a real job is running")
            page.locator("#cancel-job").click(timeout=15000)
            page.locator("#job-bar").wait_for(state="hidden", timeout=120000)
            state = page.evaluate("window.qaOperation")
            jobs = api("state")["jobs"]
            assert any(j["status"] == "cancelled" for j in jobs), jobs
            checks.append("Cancel reaches a persisted cancelled job state")
            assert before == {
                p.name: hashlib.sha256(p.read_bytes()).hexdigest()
                for p in work.iterdir()
            }
            assert not errors, errors
            assert all(r.startswith((url, "blob:", "data:")) for r in requests)
            checks.append("Sources unchanged and no browser error or external request")
            page.screenshot(path=str(base / "after-cancellation.png"), full_page=True)
            report = {
                "status": "PASS",
                "checks": checks,
                "job_outcome": state,
                "jobs": jobs,
                "source_sha256": before,
                "browser": browser.version,
            }
            browser.close()
    except Exception:
        import traceback

        report = {
            "status": "FAIL",
            "checks": checks,
            "error": traceback.format_exc(),
            "source_sha256": before,
        }
    finally:
        process.terminate()
        try:
            process.wait(timeout=10)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        log.close()
    (base / "interaction-report.json").write_text(
        json.dumps(report, indent=2), encoding="utf-8"
    )
    print(report["status"], checks)
    return int(report["status"] != "PASS")


if __name__ == "__main__":
    raise SystemExit(main())
