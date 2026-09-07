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
Work on main and push only main. Preserve existing changes. Never force-push or reset user work. Keep exactly one remote branch, main; preserve tags.

If a shared `localdesk/` defect is fixed, compare all five copies and apply only the relevant patch.
Run each affected repository suite. The apps must remain independently cloneable and runnable.
Do not run `scripts/prepare_release.py` as an installer. Use `bootstrap.py`.
Update source-manifest hashes only after reviewing changes. Preserve real tests and security controls.

## Acceptance decision

Local-machine acceptance: **NOT RUN HERE**.
Use PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE for each case.
Only state that local acceptance is complete when every applicable gate has evidence.
If a permission blocks one test, record that requirement and continue unrelated tests.

## Local PC acceptance: 2026-09-07

Decision: REJECTED for automatic scanned-PDF secret removal; PARTIAL overall. See [the current local acceptance report](docs/LOCAL_ACCEPTANCE_REPORT.md).

Tested source `6cf65c4eca8d161281159cf66b88148b98efded8` on Windows 11 AMD64, Python 3.14.3. Runtime-only setup and real samples completed before dev installation. Windows suite: 138 run, 135 passed, 3 skipped, no failures/errors; strict exits 1. Direct-browser checks: 20 passed with actual downloads. Network-disabled Linux container on this PC: 138 tests, no skips, 20 browser checks.

Windows manifest and browser synchronization checks were repaired with retained regressions. Evidence is ignored under `artifacts/local-qa/20260907-acceptance-01/`. Historical release reports remain historical. Native-session and symlink limits are detailed in the report. Automatic scanned-PDF literal redaction FAILED an exported-pixel canary; manual masks passed separately.

## OCR correction for the local acceptance retest

The custom OCR matcher now includes bounded near-matches and orientation checks.
Missing custom values require explicit review confirmation before export.
See [OCR correction and retest commands](docs/OCR_REDACTION_FIX.md).
The original Windows FAIL results above remain historical. Rerun the retained
fixture and DC-04/DC-08 on the target PC before changing local acceptance.
The native Windows symlink permission checks remain blocked until run locally.

## Current target-PC follow-up: 2026-09-08

Status: BLOCKED. Current report: [local acceptance](docs/LOCAL_ACCEPTANCE_REPORT.md). Tested main `978746e980c8658bac42dd7eca94cbb1e206ecd4`. Fresh source/vault symlink probe failed with WinError 1314; exact tests remain two skips. The user confirmed no disposable Windows session is available. No native service or desktop controls were used in the personal profile.

DataClean DC-04 and DC-08 now PASS on this PC. The exact retained OCR failure was automatically masked with zero manual rectangles and independent Poppler source-truth pixel checks. Fresh suite: 174 run, 171 passed, 3 skipped, no failures/errors; 36 focused OCR tests, 20 existing browser checks and 11 OCR browser checks passed. Original failures remain historical.

Current ignored evidence: `artifacts/local-qa/20260908-final-acceptance-01/`. No new application fix or regression test was needed in this run. Git policy: main only locally/remotely, no temporary remote branches, no force-push or tag rewrite.
