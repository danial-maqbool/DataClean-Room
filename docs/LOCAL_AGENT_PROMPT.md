# Local agent task

Complete a local acceptance pass for these five independent repositories under `danial-maqbool`:
LocalFlow-Studio, FileLens-Desktop, RecoveryLab, ActivityGraph, and DataClean-Room.
Use the current GitHub main branches. Do not use the earlier ZIP packages from the chat.
Work autonomously on safe local testing and code fixes. Do not ask for product-design choices.
Stop only the blocked test when an OS permission or credential needs human action. Continue the other tests.

## Read before changing files

In each repository, read AGENTS.md, HANDOFF.md, handoff.json, README.md, docs/LOCAL_TESTING.md,
docs/SETUP.md, docs/SECURITY.md if present, SECURITY.md, docs/LIMITS.md, and docs/VERIFICATION.md.
Read the existing test, browser, and platform reports as historical evidence, not as current local results.
Check the source, not just the README. Do not assume an earlier completion claim is accurate.

Find existing clones in the workspace. Confirm each origin. Clone missing public repositories only into new folders.
Keep the five repositories as siblings when practical. Do not nest one repository inside another.
Check Git status before pulling. Never discard, stash, reset, or overwrite user changes without explicit permission.
For clean clones, fetch main and use a fast-forward update. Create a separate local-validation branch in each repository.
Record the initial commit and any existing changes. Do not require GitHub credentials to run an application.

## Set up and preserve evidence

Use a separate project-local .venv for each repository. Validate Python version and architecture.
First run bootstrap.py without --dev. Check runtime-only dependencies and a normal sample operation.
DataClean Room must import docx, openpyxl, and pptx and clean synthetic Office files before development packages are installed.
Then run bootstrap.py --dev. Run preflight.py --tests --require-native and pip check.
Use the venv Python explicitly. Do not mix these apps with a global ML environment.

Read docs/LOCAL_TESTING.md for exact commands. Write all raw evidence under ignored artifacts/local-qa with a new run folder.
Use --report-dir for verify.py, browser_check.py, and LocalFlow worker_check.py.
Record commands, exit codes, source revisions, package versions, tool versions, skips, and output hashes.
Keep failed runs. Do not overwrite committed release reports with unreviewed local data.
Record the real OS and interpreter. Never report tests on a platform that you did not run.

Install required native tools only through approved sources. Do not lower OS security, enable unsafe keyring backends, or run as administrator.
Use Tesseract with English language data for the synthetic OCR tests. Use FFmpeg and ffprobe for RecoveryLab video checks.
Install the Playwright Chromium binary for browser testing. Install other language packs only for planned tests.
Do not automatically fetch neural weights. The built-in semantic backend must work without an external model.

## Test and repair loop

Run the complete existing unit, HTTP, integration, and adversarial suites. Run direct-browser checks with actual downloads.
Check light and dark themes, keyboard focus, screen sizes, dialogs, progress, errors, cancellation, navigation, and restart behavior.
Compare exported file contents with known fixture truth. A successful HTTP response or visible button is not sufficient.

For each failure: reproduce it, keep the failing fixture, identify the cause, add a regression test, apply a narrow fix,
rerun the focused test, then rerun the complete suite and browser checks for every affected repository.
Compare vendored localdesk copies before propagating a shared fix. Do not overwrite project-specific code or documentation.
Do not remove assertions, mock the feature being accepted, suppress errors, or relax security to make tests green.
Refresh source-manifest hashes only after reviewing the exact source changes. Do not run release-preparation scripts as an installer.

Execute every applicable project case in docs/LOCAL_TESTING.md. At minimum:
LocalFlow: invoice preview and output, all node types, OCR, mixed PDFs, tables, semantic filtering, source summaries, trigger restart,
interrupted jobs, encrypted storage, legacy migration, and gated desktop input.
FileLens: format coverage, OCR indexing, keyword/semantic/combined ranking, incremental updates, deletion, duplicates, tags, saved searches,
background rescans, encryption, and exclusions.
RecoveryLab: inspection, batch results, JSON/CSV/encoding, ZIP corruption, PDF/Office reconstruction, image decoding, SQLite recovery,
local FFmpeg remuxing, omission reports, and unchanged originals.
ActivityGraph: folder events, notes/tags/graph, retention, erase, source-content exclusion, consent-based title capture,
synthetic Chromium/Firefox history imports, timestamp handling, deduplication, and worker restart.
DataClean: selected patterns, literal rules, source-change refusal, opaque image redaction, EXIF removal, rebuilt PDFs,
hidden Office content, archive exclusions, and independent output inspection.

## Security and native acceptance

Use synthetic canary secrets. Test path traversal, archive expansion, XML entities, invalid Host and Origin headers,
wrong session tokens, bad passphrases, tampered vaults, interrupted writes, and a second writer.
Verify that redacted outputs do not retain selected canary secrets in supported text, metadata, hidden objects, or exported pixels.
Do not claim perfect detection of handwriting, faces, every language, or arbitrary private information.

Block outbound network access only inside the disposable test environment. Check browser and backend traffic.
Prove that already-installed built-in features work offline. Setup downloads are separate from runtime traffic.
Use unique temporary data directories for persistence tests. Record source hashes before and after processing.
Never use personal browser databases, clipboard contents, account passwords, or private documents as fixtures.

Native services, OS keyrings, desktop input, and window-title capture require separate real-session checks.
Run them in a disposable OS user profile or test desktop. Do not control the user active desktop or install a login task on the user profile
without explicit local consent. Test install, close terminal, logout/login, restart, pause, and uninstall. Clean up only test-created resources.
A process-restart test is not a logout/login service test. A configured adapter is not proof of permission or successful capture.
Record blocked permissions precisely and continue all independent work. Never request a secret in chat.

## Repository quality and delivery

Keep the README in simple English with no em dashes. Preserve screenshots and GIFs unless actual tested UI changes require new recordings.
Use synthetic content for new media. Verify links, file names, startup commands, requirement files, and examples.
Do not fabricate commits, benchmarks, authorship history, coverage, or verification results.
Before committing, scan staged content for secrets and private paths. Exclude .venv, vaults, private exports, raw logs, model weights, and caches.

Produce one sanitized local acceptance report per repository using the report template. Update HANDOFF.md with actual outcomes.
Add a suite summary that lists the tested commit, PASS/FAIL/BLOCKED/NOT RUN/NOT APPLICABLE cases, defects fixed,
remaining boundaries, skipped tests with reasons, and exact user actions still required.
Commit reviewed fixes and regression tests on each local-validation branch. Push through existing secure GitHub authentication when available.
Never reuse a token from chat, force-push, change repository visibility, or rewrite a release tag.
Wait for the affected CI checks during this session before calling a pushed change verified. Otherwise mark CI pending.

Do not describe all five systems as fully accepted unless every applicable acceptance gate actually passed.
Finish with the report paths, commit hashes, test counts separated from skips, and any specific local permission needed.
