# Local API

This API is for the running local app. It is not a hosted service or a stable public API contract.
The server listens on `127.0.0.1:8765` by default.

## Session checks

The index page supplies a random token for the current Python process.
The UI sends it in the `X-Local-Token` header. Every API request must use the current token.
POST requests must use `Content-Type: application/json`. The body limit is 36 MiB.
The server checks Host and Origin and does not enable cross-origin access.

Do not copy the token into a repository or enable network forwarding to the port.
Restarting the Python process changes the token.

## Common operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/info` | none | Name, version, paths, and local optional-tool availability. |
| GET | `/api/state` | none | Current application state and recent jobs. |
| GET | `/api/browse` | path, optional | Up to 1,500 visible folder entries. |
| GET | `/api/jobs/ID` | job ID in the path | Status, progress, result, or error. |
| POST | `/api/cancel` | id | Request cooperative job cancellation. |
| POST | `/api/upload` | name, base64 content | Save a new private inbox file. |
| POST | `/api/backup` | none | Write a database-only backup artifact. |

## Application operations

| Method | Path | Input | Result |
| :--- | :--- | :--- | :--- |
| GET | `/api/scan` | id; preview: 1, optional | Return a scan and optional extracted-text preview. |
| GET | `/api/image` | id | Return the review image as base64 PNG. |
| GET | `/api/examples` | none | List bundled synthetic inputs. |
| POST | `/api/scan` | paths or path; enabled, literals, ocr, optional | Start a scan job. |
| POST | `/api/paste` | text; enabled and literals, optional | Store pasted text locally and scan it. |
| POST | `/api/sanitize` | id; mode: labels or blocks; rectangles; accept_partial, optional | Create a supported clean copy in a job. |
| POST | `/api/export-report` | id | Export a report without matched values. |

### Example request body

Send this JSON to `POST /api/paste` with the current session token:

```json
{
  "text": "Contact demo@example.test for sample access.",
  "ocr": false
}
```

Use paths from the computer running Python. Change the example path before sending the request.
A job-start response contains `job_id`. Read `/api/jobs/ID` until its status is terminal.
Read the error field when the job fails. Do not treat a queued response as a completed operation.

An artifact response contains its name, relative output path, and size. The browser download helper requests only paths under the app output directory.
Use `web/common.js` as the reference client for the exact response envelope and download route.

## Version 0.2.0

All routes require the local session token. Use the user interface to review a job before an output operation. The source hash binds a review to the selected source bytes.

PDF scans return page dimensions. `image` accepts a 1-based `page` query. `sanitize` accepts `page_rectangles` as a list of `{ "page": 1, "rect": [x0, y0, x1, y1] }` in displayed pixel coordinates. Native Office outputs keep their format extension.
