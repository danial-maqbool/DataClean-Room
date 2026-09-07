# Security

## Trust model

This is a single-user local application. It binds only to loopback.
The HTTP API checks its Host, Origin, and per-process session token. The UI has no remote scripts or CDN assets.
Do not expose the port to a network, public tunnel, or untrusted reverse proxy.
Another process with the same OS identity can access your files or unlocked process memory. This app does not defend against that process.

## Database and credentials

SQLite runs in memory. Authenticated AES-256-GCM snapshots are the only database bytes written to the vault path.
The key uses scrypt with a random 16-byte salt, N=131072, r=8, and p=1.
Each encrypted snapshot uses a new random 12-byte nonce. A process lock prevents concurrent writers.
Atomic replacement prevents a partial snapshot from replacing the last complete file during a normal write failure.
Wrong passwords and failed authentication never trigger a plaintext fallback.

The passphrase is requested interactively. Automatic startup needs explicit storage in a supported OS credential store.
Database encryption does not cover source documents, exported files, uploaded files, swap, crash dumps, or temporary parser files.
Use OS disk encryption, private file permissions, and a trusted user session. There is no password-reset server.

## Untrusted files

The app limits file bytes, expanded archives, entry counts, PDF pages, pixels, text, queue size, and processing time.
It rejects linked paths, traversal entries, XML entities, and unsupported executable workflow nodes.
Native document work runs in a separate process with a deadline. This is fault isolation, not a complete OS security sandbox.
Keep native dependencies current. Do not use these apps to execute or certify malicious software.
Recovery creates new files. Privacy cleaning never treats a metadata change alone as proof of full content removal.

## Desktop actions

Only an interactive LocalFlow process started with --allow-desktop can arm actions.
The confirmation is short-lived, bound to the exact workflow and folder, and consumed once.
The input backend keeps its corner fail-safe enabled. Background triggers cannot arm desktop input.
A confirmed macro can still type into the wrong window or change source files through another application.
Review every action. Do not import and confirm an untrusted macro.

## Reports and disclosure

Use synthetic samples in public issues. Do not attach real private documents, vaults, passphrases, or tokens.
Read docs/SECURITY_REVIEW.md for the self-review findings and regression tests.
The project has not received an independent security audit or a guarantee that every private value can be detected.
