# Project maintenance

Keep all runtime processing local. Do not add API keys, telemetry, CDN assets, or automatic model downloads.
Preserve source files. Put outputs in the app export folder. Require explicit confirmation for desktop actions.
Do not remove validation or weaken tests to make a build pass. Add a regression test for a corrected defect.
Do not commit user files, credentials, vaults, extracted private text, model weights, or virtual environments.
Use simple English in the README. Do not use em dashes. Distinguish implemented behavior from untested platforms.
Capture real interface states for screenshots and GIFs. Do not label mockups as application evidence.

## Local acceptance handoff

Read HANDOFF.md, handoff.json, docs/LOCAL_TESTING.md, and docs/LOCAL_AGENT_PROMPT.md before local validation.
Use bootstrap.py for installation. Do not run release-preparation scripts as an installer.
Use --report-dir artifacts/local-qa for test and browser reports. Keep raw local evidence out of Git.
Test runtime-only installation before adding development packages. Add one regression test for each corrected defect.
A native service, OS keyring, or desktop adapter needs a real-session test before acceptance.
Never count a skipped or blocked test as passed. Preserve the exact source revision and command exit codes.
