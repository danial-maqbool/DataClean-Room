# Local installation and acceptance testing

## Requirements

Use a 64-bit Windows, macOS, or Linux computer. Install Python 3.11 or newer and a modern browser.
Python 3.11 and 3.13 are the release CI targets. A newer interpreter needs its own validation.
No API key, cloud account, paid service, or GPU is required for the built-in features.
There is no claim of support for every PC, every file, or unlimited input size.

| File or tool | Purpose |
| :--- | :--- |
| `requirements.txt` | Pinned direct runtime packages. |
| `requirements-dev.txt` | Runtime packages plus tests, browser checks, audit, and formatting tools. |
| `requirements-desktop.txt` | Optional PyAutoGUI input support. Installing it does not grant consent. |
| `requirements-neural.txt` | Optional neural backend. Supply trusted local model files. It is not part of the built-in acceptance claim. |
| Tesseract and `eng` data | OCR features and the shared OCR integration tests. Add other languages only when needed. |
| FFmpeg and ffprobe | RecoveryLab local video remuxing. |
| Git | Revision tracking. A source ZIP runs without Git, but it has no local commit history. |

Direct runtime packages are pinned. Transitive resolution can still differ by OS and interpreter.
Record `pip freeze` from each accepted environment. Do not copy a Linux environment or wheel set to Windows.
Use `docs/SETUP.md` and `docs/SOURCES.md` for native-tool sources. Use official installers.
Do not weaken OS security settings, run the apps as administrator, or store credentials in command arguments.

## Clean installation

Work from the repository root. Preserve existing local changes and app data first.
The normal installer does not install native tools, model weights, a service, or a browser binary.

Windows PowerShell:

```powershell
py -3 bootstrap.py
.\.venv\Scripts\python.exe scripts/preflight.py --report-dir artifacts/local-qa/runtime
.\.venv\Scripts\python.exe -m pip check
.\start.bat --demo
```

Linux or macOS:

```sh
python3 bootstrap.py
.venv/bin/python scripts/preflight.py --report-dir artifacts/local-qa/runtime
.venv/bin/python -m pip check
sh start.sh --demo
```

Test runtime-only setup before adding development packages. Development packages can hide packaging defects.
Stop demo mode with Ctrl+C. Start without `--demo` only after reviewing the examples.
Normal mode asks for a vault passphrase with at least 12 characters. Use a disposable passphrase for QA.
Never reuse a GitHub token or a personal password as a test passphrase.

## Automated checks

Windows PowerShell:

```powershell
py -3 bootstrap.py --dev
.\.venv\Scripts\python.exe scripts/preflight.py --tests --require-native --report-dir artifacts/local-qa
.\.venv\Scripts\python.exe -m pip check
.\.venv\Scripts\python.exe scripts/verify.py --report-dir artifacts/local-qa
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe scripts/browser_check.py --record --report-dir artifacts/local-qa
.\.venv\Scripts\python.exe -m pip freeze > artifacts/local-qa/requirements-resolved.txt
git rev-parse HEAD > artifacts/local-qa/source-commit.txt
```

Linux or macOS:

```sh
python3 bootstrap.py --dev
.venv/bin/python scripts/preflight.py --tests --require-native --report-dir artifacts/local-qa
.venv/bin/python -m pip check
.venv/bin/python scripts/verify.py --report-dir artifacts/local-qa
.venv/bin/python -m playwright install chromium
.venv/bin/python scripts/browser_check.py --record --report-dir artifacts/local-qa
.venv/bin/python -m pip freeze > artifacts/local-qa/requirements-resolved.txt
git rev-parse HEAD > artifacts/local-qa/source-commit.txt
```

On Linux CI or a Linux test machine with all native dependencies, add `--strict` to `scripts/verify.py`.
Strict mode requires zero skips. Windows-only or POSIX-only skip reasons must not be converted into passes.
Install missing applicable tools and rerun their tests. Record genuine platform exclusions separately.
Use direct browser navigation for local acceptance. `--bridge` does not prove normal browser policy behavior.
Check every exit code. PowerShell does not automatically stop after every failed native command.
After each command, inspect `$LASTEXITCODE`. Preserve failed-run evidence in a separate timestamped folder.

The new `--report-dir` option keeps committed release reports and media unchanged.
Raw logs and local reports belong under ignored `artifacts/`. Review files before copying any evidence into Git.
Do not regenerate public GIFs from personal folders, personal browser profiles, or a password prompt.

## Offline installation and runtime

On a compatible connected computer, build wheels for the exact destination OS, architecture, and Python version:

```sh
python -m pip wheel -r requirements-dev.txt --wheel-dir wheelhouse
python bootstrap.py --dev --offline --wheelhouse wheelhouse
```

`pip wheel` includes distributions that need a build step. Test installation with network access disabled.
Transfer native-tool installers and language data separately. Transfer the matching Playwright browser cache for browser tests.
The application does not need Playwright for ordinary use. Never silently download a model during a runtime test.

After setup, test the apps with outbound network access blocked in a disposable environment.
Check backend traffic as well as browser traffic. A browser-only check cannot establish backend network behavior.
Use a test firewall rule or network namespace that affects only the test environment. Do not alter the user global firewall.

## Shared acceptance checks

Use synthetic files and temporary data directories. Hash source files before and after each operation.
Test paths with spaces and Unicode, empty input, corrupt input, size limits, cancellation, restart, and occupied ports.
Test the same fixture twice. Check that repeated execution does not corrupt state or replace original files.
Test wrong passwords, altered vault bytes, failed writes, backup restoration, and concurrent writers.
Test loopback binding, wrong session tokens, hostile Origin/Host headers, traversal, symlinks, archive expansion, and XML entities.
Do not remove safety limits, confirmation requirements, encryption, or failing assertions to produce a pass.

A native login service needs an actual OS user session and credential store. A mocked service test is not enough.
Use a disposable OS user profile. Test installation, terminal close, logout/login, disabled state, and removal.
Do not install services on the user normal profile or enable desktop input without explicit local consent.
Do not run LocalFlow desktop tests while the user is working. Use a disposable desktop with a synthetic target.

Keep a separate result for each feature: PASS, FAIL, BLOCKED, NOT RUN, or NOT APPLICABLE.
A skip is not PASS. A configured feature is not a tested feature. A screenshot is not a correctness test.

## Project acceptance cases

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

## Completion criteria

The local acceptance pass is complete only when the applicable checklist passes with evidence.
Record the exact source commit, local modifications, interpreter, OS, package versions, commands, exit codes, skips, and output hashes.
Measure startup, representative job duration, and peak memory on this machine. Do not invent universal minimum hardware requirements.
Review recovered and redacted outputs in independent viewers. Keep known format and OS boundaries explicit.
Update `HANDOFF.md` with a reviewed result summary. Use `docs/LOCAL_TEST_RESULTS.template.md` as the report structure.
Commit source fixes and regression tests separately from sanitized evidence. Do not force-push or rewrite release history.
