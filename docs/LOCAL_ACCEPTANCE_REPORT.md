# DataClean-Room: current local acceptance report

Status: BLOCKED. Required Windows permissions/session gates remain. This is not full local acceptance.

Run date: 2026-09-08, Asia/Karachi.
Tested current main commit: `978746e980c8658bac42dd7eca94cbb1e206ecd4`.
Starting state: main, clean, correct danial-maqbool origin. Fetch and fast-forward pull completed without discarding changes.
Working source diff at test time: empty; SHA-256 `e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855`.
Environment: Windows 11 Home build 26200, AMD64; project-local Python 3.14.3. Tesseract 5.4.0.20240606 with eng/osd; Poppler pdftoppm 26.07.0. Browser engine 143.0.7499.4.
Current evidence root: ignored `artifacts/local-qa/20260908-final-acceptance-01/`.
Earlier evidence root: ignored `artifacts/local-qa/20260907-acceptance-01/`.
The [previous acceptance report](history/LOCAL_ACCEPTANCE_20260907.md) is preserved verbatim. Earlier failures and blocked checks remain historical evidence.

## Current and retained checks

| Gate | Status | Executions and evidence |
| :--- | :--- | :--- |
| Starting Git state | PASS | `starting-state.json`, `fetch-pull.log`, `tested-source.txt`; main only is the final branch policy. |
| Windows source/vault symlinks | BLOCKED | Fresh disposable-directory creation probe returns WinError 1314. Exact existing tests: 2 run, 0 passed, 2 skipped, 0 failures/errors. `windows-symlinks/result.json`, `windows-symlinks/tests.log`. |
| Windows POSIX ciphertext mode | NOT APPLICABLE | POSIX mode assertions do not apply to Windows. It is not an application failure. |
| Full Windows regression suite | PASS | Fresh non-strict run: 174 executions, 171 passed, 0 failures/errors, 3 skipped. `full-suite/test-report.json`; command exit 0. The skipped native gates are reported separately as BLOCKED/NOT APPLICABLE. |
| Focused OCR regressions | PASS | 36 existing correction tests ran, 36 passed, no skips. `focused-ocr.log`, exit 0. |
| Existing browser suite | PASS | Fresh 20 checks, direct backend navigation, delayed API, recordings and actual downloads. `browser/`, exit 0. |
| OCR browser suite | PASS | Fresh 11 checks: candidate display, real near-match, downloaded bytes/pixels, backend review refusal/confirmation, unchanged source. `ocr-browser/`, exit 0. |
| Browser interaction | PASS | Fresh progress/cancellation/navigation/dialog check. `interaction/`, exit 0. |
| Acceptance runner | PASS | Fresh six grouped checks passed. `acceptance/results.json`, exit 0. |
| Independent Poppler checks | PASS | Six checks: recorded substitutions/insertions/deletions, real scanned/mixed rotated OCR, separate manual fallback. `ocr-pixels/`, exit 0. |
| Exact retained original failure | PASS | Real Tesseract still reports OA_SECRET_CANARY; automatic output masks the known source-truth secret region with zero manual rectangles. `retained-original/result.json`, exit 0. |
| Extra native-page/object/negative checks | PASS | Three checks: mixed native page, exact native and source objects, real near-but-unrelated scan with required review. `extra-pages-02/results.json`, exit 0. |
| Package consistency/preflight | PASS | `pip-check.log`, `preflight/`, `freeze.log`; exits 0. No installation repeated and no runtime dependency added. |

## Project acceptance cases

PASS cases carried from the previous report remain supported by their original dated evidence. DataClean DC-04/DC-08 below are newly retested. Native blockers were reassessed this run.

| Case | Status | Findings | Evidence |
| :--- | :--- | :--- | :--- |
| DC-01 | PASS | Runtime-only imports docx/openpyxl/pptx and creates/cleans each before dev tools. | Earlier report/evidence: `runtime-early; runtime-extended/results.json` |
| DC-02 | PASS | Patterns, checksums, false matches, unlabeled missed names, literal rules, Unicode, selected categories and stable labels. | Earlier report/evidence: `final-suite/verify.log` |
| DC-03 | PASS | Exported pixels independently checked; selected region black and EXIF/GPS absent. | Earlier report/evidence: `final-acceptance/results.json` |
| DC-04 | PASS | Original retained failure, real substitution, exact/native/scanned/mixed/rotated cases, zero automatic manual rectangles, independent source-truth pixel checks and separate manual fallback. | Current: `retained-original/result.json; ocr-pixels/ocr-redaction-report.json; extra-pages-02/results.json` |
| DC-05 | PASS | Hidden/inherited Word styles, tracked deletions, fields/comments/headers, hidden spreadsheet cells/sheets, formulas, slide notes and synthetic embedded parts checked. Office 16 independently renders outputs; rebuilding changes formatting and omits objects. | Earlier report/evidence: `final-suite; supplemental-hidden; runtime-extended/office-independent-render-02` |
| DC-06 | PASS | ZIP bounds, generic output names, traversal/nesting/unsupported exclusions and expansion; omissions reported. | Earlier report/evidence: `final-suite/verify.log` |
| DC-07 | PASS | Same-size content change, size change and disappearance each refuse export. | Earlier report/evidence: `final-acceptance/results.json` |
| DC-08 | PASS | Poppler output rendering, known secret/public pixel regions, actual forms/annotations/attachments/metadata removed, source hashes unchanged. Original Windows automatic failure is resolved on this exact PC. | Current: `retained-original; ocr-pixels; extra-pages-02; full-suite` |

## Defects, regression tests and verification scope

No application defect required a source-code change during this run. No application regression test was added by this run. No assertion, encryption, consent, source protection or parser limit was weakened. No shared localdesk file changed.

The fetched correction already included 36 OCR regression tests. They are upstream correction tests, not newly authored tests from this run. Matching tests cover exact, substitution/insertion/deletion, negative controls, Unicode, short rules, geometry and bounds. Review checks cover refusal without boolean confirmation and real UI confirmation.

Original retained source SHA-256: `76d6619c319c561c0f9d5afba94fc9358b3b2834b1276d2310619f625a815951`.
New automatic output SHA-256: `a80bc34eaad4282b9abbf3b8b95c4b836024830656521f18c18968b84974a60b`.
The source remained unchanged. Installed Tesseract reproduced the same OA_SECRET_CANARY recognition. The new output has one automatic painted region, zero selected/manual regions and no bypass confirmation. Poppler-rendered fixed source-truth secret pixels were all zero. Public number 42 remained visible and was independently read. Second OCR was supplementary, not the sole redaction proof.
For recorded insertion/deletion regressions, only recognized OCR text was injected; source pixels stayed unchanged. These are distinct from real Tesseract checks. Both pages of the mixed/rotated output were independently inspected. Actual synthetic PDF fields, annotations, attachments and private metadata were present in a source fixture and absent from its output.
One extra local harness initially required close per-pixel gray values between Poppler vector text and PDFium-rasterized text. It reported a false failure from edge antialiasing. The failed run and its runner are preserved in `extra-pages/`. The corrected content check retains the fixed all-black secret assertion, verifies public glyph support within two pixels at >=99% in both directions, and preserves measured shade differences. Source glyph retention was 100%; output glyph support exceeded 99.9%. No application test was removed or modified.
The former automatic-redaction failure is resolved for the retained fixture and tested cases on this Windows machine. OCR remains bounded and can miss other text. Manual review and documented fallback remain necessary; this is not a universal removal guarantee.

## Native Windows blockers

The user explicitly confirmed that no disposable Windows session is available. No login task, credential-store write, desktop input or window-title capture was attempted on the personal session. Process-restart evidence from the earlier run is not logout/login evidence.
A fresh symlink probe ran only inside disposable synthetic directories. Windows returned error 1314, a required privilege is not held. Both existing source/vault tests were invoked; their skips remain BLOCKED, not PASS. No machine-wide security configuration was changed.

## Commands and evidence

Exact command arguments, start times, exits and durations are in `*.command.json`; native/interpreter versions are in `environment.log`. Raw paths, logs, vaults and synthetic outputs stay ignored. No personal documents, browser databases, credentials or screenshots were used. Only owned test processes were stopped.

Source-manifest verification follows review of report-only changes and is recorded in `final-manifest.log`. Runtime-only installation and prior offline runs are retained evidence and were not repeated. No new network-isolation result is claimed for this run.

GitHub final main workflow results are recorded after the report push in the workspace five-project summary and ignored `final-ci.json`; remote CI does not replace local Windows permissions. No queued or running job is called a pass.

## Exact remaining user actions

1. Supply a disposable Windows environment with symbolic-link creation capability, then run the existing source and vault symlink rejection tests there. No global security setting was changed to obtain that capability.

## Decision

Overall: BLOCKED by the native Windows capability/session requirements listed above. DC-04 and DC-08: PASS for this machine and the tested fixtures; the old FAIL history is retained.
