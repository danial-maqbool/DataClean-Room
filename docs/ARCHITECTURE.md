# Architecture

The browser uses local HTML, CSS, and JavaScript. A loopback-only HTTP server validates the host, request origin, content type, size, and session token. The API sends bounded work to the local job queue.

Project-specific code lives in `app`. Shared runtime code lives in `localdesk`. Every repository includes those files. Runtime startup does not fetch another repository.

SQLite operates in memory. The vault writes authenticated encrypted snapshots and encrypted database backups. Source inputs and exported copies are separate ordinary files. Jobs preserve originals and write new output names.

Document parsing uses bounded child processes. The operating system enforces additional process limits where supported. Browser checks use synthetic examples. Platform reports identify any skipped operating-system checks.

See [User guide](USER_GUIDE.md) for format-specific processing and [Security](../SECURITY.md) for the threat model.
