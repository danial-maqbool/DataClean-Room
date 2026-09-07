# Security review

This report describes iterative source review and automated adversarial tests during version 0.2.0 development.
It is a self-review, not an independent penetration test or certification.

| Finding | Change | Regression evidence |
| :--- | :--- | :--- |
| Plaintext database and backups | In-memory SQLite with authenticated encrypted snapshots | Wrong key, altered bytes, zero-byte file, backup restore, plaintext absence |
| Partial SQL or failed snapshot write | Restore the last durable snapshot | Failed executescript and simulated disk-write failure |
| Concurrent writers | Nonblocking OS process lock | Second writer rejected; lock released on close |
| Host rebinding and cross-site requests | Exact Host, Origin, and session-token checks | Wrong origin, duplicate Host, missing token, chunked input rejected |
| Unbounded background work | Bounded HTTP workers and job queue | Queue, input, time, archive, and cancellation tests |
| Stale or replayed desktop consent | Short-lived, single-use, definition-bound confirmation | Default denial, expiry, changed definition, and replay tests |
| Lost watched changes during busy jobs | Advance trigger state only for an accepted run | Restart and trigger-state tests |
| Hidden private Office data | Remove unsupported parts and hidden values; rewrite supported content | Split runs, comments, notes, formulas, hidden sheets, and shared-string checks |
| Changed source during cleaning | Recheck the reviewed input hash before accepting output | Changed input produces no accepted clean copy |
| Unsafe archive contents | Reject traversal and links; process supported entries only | Nested archive, expansion, XML entity, and unsafe-name checks |

Shared checks run separately in each repository. Project-specific checks apply only to the relevant application.
Real OCR, PDF, image, and media tests use synthetic fixtures. Some OS-permission failures use mocks.
Real Linux desktop checks use a disposable X11 display. They do not establish Windows or macOS permission behavior.
See VERIFICATION.md and the CI results for the tested environments and any skipped checks.

Remaining trust boundaries include OS-user access, unlocked memory, native parser defects, OCR mistakes, missing input bytes, and desktop focus changes.
Do not remove these warnings merely because a test suite passes.
