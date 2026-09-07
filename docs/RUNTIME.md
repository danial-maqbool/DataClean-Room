# Runtime provenance

The vendored `localdesk/` runtime started from `danial-maqbool/LocalFlow-Studio` at commit `a42262279fef3a69f031fecfcdd54cabc78c682b`. Each application includes a complete copy. Runtime startup does not fetch this repository or contact GitHub.

The one-time release preparation copies an explicit list of shared files. It then runs this project's tests and records the prepared source commit. Later source changes must pass the local and CI checks again.
