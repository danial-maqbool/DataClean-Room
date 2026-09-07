# Verification

The release pipeline tests the application on Ubuntu, Windows, and macOS with Python 3.11 and 3.13. Read the exact results in `docs/platforms` and the linked GitHub Actions run. Do not infer that a queued or failed run passed.

Linux strict checks install Tesseract and FFmpeg. Windows and macOS checks can skip tests that need an unavailable local executable or POSIX file mode. Every skipped test is listed in its report.

The browser job starts the real application, exercises its interface, and records synthetic example states. It tests direct browser navigation with the application security policy enabled. Local development can use an explicitly labeled HTTP bridge on hosts that block loopback navigation.

The dependency audit checks declared runtime packages against its available advisory data. Passing tests or an audit does not prove that every file or desktop environment works. The security review is a source self-review with adversarial regression tests, not an independent audit.
