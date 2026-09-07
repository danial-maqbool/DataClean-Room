# DataClean Room: local testing handoff

Handoff revision: 1. Prepared on 2026-09-07. Application version: 0.2.0.

## Status

The application source is published. This handoff prepares a repeatable local acceptance pass.
It does not certify the user PC, native permissions, every input file, or optional neural weights.
Do not remove documented processing boundaries to change the completion status.

The prior release evidence was recorded at `1c0f4a74f9dea7809afde677102f45a3483b4685`.
It reports 126 passing full Linux test executions and 16 browser checks.
Those counts are historical. Shared tests occur in each repository. Native-tool and OS-specific skips are recorded separately.
Use current GitHub Actions and new local reports to verify the handoff commit. Do not present the prior counts as a new run.

## Changes in this handoff

`bootstrap.py --dev` installs test tools into this project .venv.
`scripts/preflight.py` checks Python, direct package pins, SQLite FTS5, and applicable native-tool availability.
`--report-dir` keeps local test reports and media separate from committed release evidence.
Browser reports now distinguish started, failed, and completed runs. An interrupted run cannot keep a stale pass report.
Ten handoff regression tests check setup, requirement handling, and report isolation.
DataClean Office reconstruction dependencies now belong to requirements.txt. Validate runtime-only installation before adding test tools.

## Read order

Read `AGENTS.md`, this file, `handoff.json`, and `docs/LOCAL_TESTING.md` first.
Then read `docs/SETUP.md`, `docs/LIMITS.md`, `SECURITY.md`, and `docs/VERIFICATION.md`.
The full agent brief is in `docs/LOCAL_AGENT_PROMPT.md`.
Use `docs/LOCAL_TEST_RESULTS.template.md` for the sanitized final report.

## Start and verify

Windows PowerShell, from this repository root:

```powershell
py -3 bootstrap.py
.\.venv\Scripts\python.exe scripts/preflight.py --report-dir artifacts/local-qa/runtime
.\start.bat --demo
```

Stop the demo. Then follow the full runtime-only and development-install checks in `docs/LOCAL_TESTING.md`.
The default local port is `8765`. Use `--port 0 --no-browser` for a temporary server on an available port.
Use a unique `--data-dir` for persistence tests. `--demo` uses temporary data and does not prove persistent vault behavior.
Normal startup needs a vault passphrase. Do not put a real passphrase in a command, script, commit, or report.

## Project acceptance scope

| ID | Area | Required evidence |
| :--- | :--- | :--- |
| DC-01 | Runtime-only Office setup | In a fresh environment, install requirements.txt without requirements-dev.txt. Import docx, openpyxl, and pptx. Create and clean one synthetic file of each format. This checks the packaging defect fixed in this handoff. |
| DC-02 | Pattern review | Test each supported pattern and custom literal. Review false matches, missed matches, Unicode, selected categories, and labels. Never claim complete private-data detection. |
| DC-03 | Image redaction | Use known text and EXIF/GPS metadata in a synthetic image. Redact selected pixels, reopen the exported bytes, verify covered pixels, and inspect metadata independently. |
| DC-04 | PDF redaction | Test native-text, scanned, mixed-content, and rotated synthetic PDFs. Inspect every rendered output page. Search extracted text, annotations, attachments, forms, and metadata for known secrets. Black overlay appearance alone is not sufficient. |
| DC-05 | Office reconstruction | Test DOCX hidden runs, inherited hidden styles, tracked changes, comments, headers, and fields. Test XLSX hidden cells/sheets and formulas. Test PPTX notes and embedded content. Compare omissions and formatting changes with the report. |
| DC-06 | Archives | Test bounded ZIP cleaning, generic output names, unsupported entries, traversal, nested archives, and excessive expansion. Excluded entries must be listed, not silently passed through. |
| DC-07 | Changed source | Scan a fixture, change its bytes, then export. Export must refuse the changed source. Repeat with a source that changes size or disappears. |
| DC-08 | Independent output checks | Verify new outputs in another parser or viewer. Check canary secrets with binary/text searches where meaningful. Preserve original hashes. Keep test exports and raw reports out of Git. |

## Work that requires the local machine

Test the relevant native adapters on the actual target OS. Do not infer their behavior from mocked tests.
Install required native tools and language data. Check actual outputs with independent parsers or viewers.
Test a clean runtime-only environment, paths with spaces and Unicode, offline operation, and the existing app data migration path when applicable.
Measure local performance with synthetic fixtures. No universal hardware benchmark is claimed.
Use a disposable OS profile for service and credential-store checks. Do not alter the user active desktop without local consent.

## Evidence and Git rules

Keep raw logs, resolved dependency lists, screenshots, and temporary outputs under ignored `artifacts/`.
The committed `docs/test-report.json`, `docs/browser-report.json`, and `docs/platforms/` remain historical release evidence.
New local reports must identify their actual commit and environment. Review evidence before publishing it.
Never commit user documents, browser history, vaults, passwords, API tokens, model weights, or .venv.
Use a local-validation branch. Preserve existing changes. Never force-push or reset user work.

If a shared `localdesk/` defect is fixed, compare all five copies and apply only the relevant patch.
Run each affected repository suite. The apps must remain independently cloneable and runnable.
Do not run `scripts/prepare_release.py` as an installer. Use `bootstrap.py`.
Update source-manifest hashes only after reviewing changes. Preserve real tests and security controls.

## Acceptance decision

Local-machine acceptance: **NOT RUN HERE**.
Use PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE for each case.
Only state that local acceptance is complete when every applicable gate has evidence.
If a permission blocks one test, record that requirement and continue unrelated tests.
