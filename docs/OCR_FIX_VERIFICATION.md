# OCR correction verification

## Current target-PC result: 2026-09-08

DC-04 and DC-08: PASS on the target Windows 11 PC at main commit `978746e980c8658bac42dd7eca94cbb1e206ecd4`. The exact retained scanned-PDF failure was retested with real Tesseract, zero manual rectangles, and independent Poppler source-truth pixel checks. The original source hash remained unchanged, public content remained visible, and rebuilt output omitted text objects, forms, annotations, attachments and private metadata.

Current full suite: 174 run, 171 passed, 3 skipped, no failures or errors. Existing browser checks: 20 passed; OCR browser checks: 11 passed. The [current local report](LOCAL_ACCEPTANCE_REPORT.md) contains commands, hashes and evidence paths, including preserved failed evidence. Overall acceptance remains BLOCKED only by Windows symlink capability. No disposable Windows session is available; no personal desktop or service was used.

## Historical upstream decision

The reported OCR custom-value miss is corrected in the tested source. The retained
automatic scanned-PDF acceptance check passes with real OCR on hosted Windows,
macOS, and Linux. Target-PC acceptance is still partial. Do not replace the original
Windows failure report or mark its local case IDs passed without a new local run.

Runtime correction reviewed through commit `144142fa665726c587ce349aa0b33567785c6f8b`.
The runtime source is unchanged from `45f0139c09cf8085f3656bded76dfe40079d3a06`;
subsequent commits add the native OCR workflow and correct its installer discovery.

## Executed evidence

| Check | Result | Evidence |
| :--- | :--- | :--- |
| Recorded `OA_SECRET_CANARY` error with unchanged source pixels | Old implementation failed the pixel assertion. Corrected implementation passed. | New `test_recorded_substitution_masks_exported_pixels`; the failed local before-run is retained separately. |
| New regression tests | 36 tests added. | `tests/test_ocr_matching.py`, `tests/test_ocr_redaction.py`, `tests/test_ocr_api.py`. |
| Full Linux suite | 174 passed, no skips, failures, or errors. | Python 3.13 report in the core CI artifact. |
| Full native macOS suite | 174 passed, no skips, failures, or errors. | Python 3.13 native OCR artifact; Tesseract 5.5.3. |
| Full native Windows suite | 172 passed, 2 skipped, no failures or errors. | Python 3.13 native OCR artifact; Tesseract 5.4.0.20240606. |
| Direct-browser verification | Existing 20 checks and 11 new OCR review/download checks passed. | `local-qa/browser-report.json`, `ocr-browser/ocr-browser-report.json`. |
| Independent exported-pixel verification | Six checks passed. | `ocr-pixels/ocr-redaction-report.json`; Poppler renders production output independently of PDFium. |
| Retained acceptance runner | All six grouped checks passed. | `ocr-acceptance/results.json` or `native-acceptance/results.json`. Includes automatic and manual cases separately. |

Core source CI: https://github.com/danial-maqbool/DataClean-Room/actions/runs/34154365204

Expanded core CI: https://github.com/danial-maqbool/DataClean-Room/actions/runs/34154908712

Native OCR CI: https://github.com/danial-maqbool/DataClean-Room/actions/runs/34154908697

The core matrix covers Ubuntu, Windows, and macOS with Python 3.11 and 3.13.
The separate native OCR matrix covers Windows and macOS with both Python versions.
The first core-only Windows and macOS jobs skipped OCR because Tesseract was absent.
The added native jobs run those real OCR tests. Their results do not turn earlier
skips into passes. Counts above refer to individual Python 3.13 reports, not unique
tests across the matrix.

The Windows native artifact records one-edit OCR candidates with score 53.328255
in its scanned and mixed PDF acceptance exports. Those exports use zero manual
rectangles. They passed the retained output checks. This tests the original OCR
version, not only a newer Linux recognizer. The score is not a probability or a
security guarantee.

The two remaining hosted Windows suite skips are the POSIX ciphertext mode check
and vault-symlink creation. POSIX modes do not apply to Windows. The local user
report additionally records a blocked source-symlink test; hosted success does not
prove the target account has that permission.

Local Linux tests used different installed package versions from pinned CI.
Direct browser navigation in the chat execution environment was blocked by policy.
The reported browser passes come from GitHub runners using direct loopback navigation.
The original isolated offline run remains historical evidence; it was not relabelled
as a new network-isolation test for this correction.

## CI and safety changes

Linux native-package installation now has bounded network timeouts and retries.
Windows CI checks the historical installer SHA-256 against the recorded Microsoft
winget manifest before running it. It checks the installed version and English data.
Installer discovery initially assumed the requested destination; that setup failure
was corrected by checking known installer locations and requiring the exact version.
No application assertion was removed to address that setup failure.

The application still uses local processing, bounded parser workers, original-file
hash checks, authenticated local API calls, and copy-only exports. The correction
adds no Python runtime package, cloud service, API key, or model download.
Read [the matching and review policy](OCR_REDACTION_FIX.md) before using the feature.
The matching bounds do not guarantee that every possible secret is detected.

## Target-PC retest

Pull current `main`. Preserve the original ignored failure fixture and its output.
Use the project's virtual-environment Python. Keep every new run in a new directory.

```powershell
git pull --ff-only
.\.venv\Scripts\python.exe -m unittest tests.test_ocr_matching tests.test_ocr_redaction tests.test_ocr_api -v
.\.venv\Scripts\python.exe scripts/acceptance_check.py --report-dir artifacts/local-qa/ocr-fix-acceptance-new
.\.venv\Scripts\python.exe scripts/ocr_browser_check.py --report-dir artifacts/local-qa/ocr-fix-browser-new
```

Run `scripts/ocr_redaction_check.py` with another new report directory when Poppler's
`pdftoppm` is installed. The existing Tesseract and development packages are still
required. Do not copy a CI installer into the ordinary application startup process.

Rerun the exact retained Windows fixture with the same requested literal and no
manual rectangles. Independently inspect exported pixels. Repeat DC-04 and DC-08,
including scanned, rotated, mixed, and manual-fallback cases. A zero exact match in
second-pass OCR is not sufficient proof that the visible secret was removed.
Then run the complete suite and the existing browser/interaction checks.

Update local case statuses only from that evidence. Complete the shared Windows
symlink checks in a disposable session with the required privilege. Do not enable
machine-wide privileges or weaken application security to remove skips.

Other projects' service logout/login and desktop-consent gates are unchanged.
Their existing `HANDOFF.md`, `docs/LOCAL_TESTING.md`, and local acceptance reports
remain the instructions for those local checks. No user credentials belong in chat
or in Git.
