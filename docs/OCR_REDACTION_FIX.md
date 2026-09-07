# OCR custom-value redaction

## Corrected failure

The Windows acceptance report records a real missed redaction. Tesseract read
`QA_SECRET_CANARY` as `OA_SECRET_CANARY`. Exact matching did not select that text.
The original exported pixels still contained the secret.

OCR image and PDF processing now includes bounded near-matches for custom values.
Native text, Office documents, and the existing pattern detectors retain exact behavior.
This change does not claim complete detection of private information.

## Matching rules

The matcher normalizes Unicode width, letter case, spaces, and punctuation for comparison.
It keeps positions in the original OCR text. It matches complete OCR tokens or adjacent
tokens on one line. It does not join separate columns, pages, or native-text runs.

| Normalized custom value | Additional OCR matching |
| :--- | :--- |
| Fewer than 8 letters or digits | Exact matching only. Review manually. |
| Fewer than 4 distinct characters | Exact matching only. Review manually. |
| 8 to 15 letters or digits | At most one insertion, deletion, or substitution. |
| 16 or more letters or digits | At most two insertions, deletions, or substitutions. |

These are fixed conservative bounds, not an accuracy score. Near-matches can select
harmless text. The application masks every selected candidate, including candidates
with low or unavailable OCR confidence. It does not discard a possible secret because
its recognition score is low. The report identifies these cases without adding private
literal values to the new candidate metadata.

A page without a custom-value candidate receives bounded orientation checks at 90,
180, and 270 degrees. The document can use at most six additional OCR passes. Returned
mask coordinates map to the original page. The original file is not rotated or changed.
The existing parser, image-size, page-count, and worker time limits still apply.
Matching also stops at its comparison, distance-work, and candidate limits. It reports
an error instead of returning an incomplete candidate list.

## Review and export

The page preview shows automatic mask outlines and candidate counts. These outlines
are not proof of a correct export. Inspect the exported file separately.

If a requested custom value was not located, or orientation review remains unresolved,
export requires the **I reviewed every page** checkbox. Add manual masks for missed
values, or verify that the values are absent. The backend independently checks this
boolean confirmation. Strings and numbers are not accepted as confirmation.

Near-matches are automatically included when located. Low-confidence and approximate
matches remain visible in warnings. Always review every page. Finding one occurrence
of a value does not prove that all occurrences were found. OCR errors outside the
matching bounds, handwriting, unrelated languages, and unidentified private objects
still require manual review. Manual-mask success is not automatic-redaction acceptance.

PDF output still contains newly rendered, masked pixels. It does not copy original
text objects, annotations, forms, metadata, or attachments. Source hashes and copy-only
export checks remain in force. Source files and exported files are not encrypted by
this feature.

## Regression checks

The new unit tests cover OCR substitutions, insertions, deletions, negative controls,
short values, Unicode positions, exact-match overlap, geometry, bounded work, and
boolean review confirmation. Integration tests inspect actual exported image bytes.
They cover native, scanned, rotated, and mixed-content PDFs, plus manual fallback.

The recorded-error regression injects the reported OCR text while keeping the source
pixels unchanged. It fails on the previous implementation and passes after the fix.
Separate tests use real Tesseract. They do not require Tesseract to make the identical
Windows recognition error on every platform.

Use these commands with this repository's virtual-environment Python:

```sh
python -m unittest tests.test_ocr_matching tests.test_ocr_redaction tests.test_ocr_api -v
python scripts/ocr_redaction_check.py --report-dir artifacts/local-qa/ocr-pixels-new
python scripts/ocr_browser_check.py --report-dir artifacts/local-qa/ocr-browser-new
python scripts/acceptance_check.py --report-dir artifacts/local-qa/acceptance-new
```

Use a new output directory each time. Existing directories are preserved.
`ocr_redaction_check.py` requires Tesseract and Poppler's `pdftoppm` executable.
It renders exported bytes with Poppler, independently of the production PDFium renderer.
It checks fixed source-truth pixel regions and retained public content, not just
whether a second OCR call missed the secret. It also checks source hashes and PDF objects.
`ocr_browser_check.py` requires the installed Playwright Chromium browser. It uses direct
loopback navigation, real API requests, review controls, and saved download bytes.

Run the complete suite and existing browser checks as well. New tests do not replace them.
On Linux, install `poppler-utils` through the OS package manager for the independent check.
No new Python runtime dependency, API key, or model download is required.

## Remaining local acceptance

The original Windows acceptance report remains historical evidence. Rerun its retained
failed fixture, DC-04, and DC-08 on the target PC after pulling the correction. Keep new
outputs and evidence separate. Also complete the outstanding Windows source/vault
symlink tests in a disposable session with the required permission. A passing Linux
or hosted CI run does not prove those local Windows conditions.
