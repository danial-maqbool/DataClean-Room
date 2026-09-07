# Daily use

## Start

Install Python 3.11 or later. Open the extracted project folder. Run `python bootstrap.py` once, then use `start.bat` on Windows or `sh start.sh` on Linux or macOS. Setup creates a private `.venv` folder. See [Setup](SETUP.md) for local tools and offline installation.

The normal app asks for a vault passphrase with at least 12 characters. Keep that passphrase. No server can reset it. Use `start.bat --demo` or `sh start.sh --demo` to try synthetic data without a persistent database.

The browser connects only to the local Python process. Closing the browser does not stop the worker. Press Ctrl+C in the terminal to stop a foreground worker. Use `run.py --port 0` to select a free port.

## Scan and review

Load the four synthetic examples. Select the contact file. Compare source text and the proposed clean text. Choose labels or replacement blocks. Add exact custom literals for values that the built-in patterns cannot identify.

Rule changes apply to new scans. The scanner can miss private data. Review names, addresses, faces, signatures, and unusual number formats yourself. Before each export, the app checks that the source still matches the reviewed source hash.

## PDF redaction

Select a PDF. Enable local OCR for scanned content before scanning. Select a page in the preview. Draw rectangles over any extra areas you need to remove. Rectangles stay attached to their selected page. Automatic text matches also produce pixel masks.

The app normalizes rotation and the visible crop box on a working copy. The scan, preview, and export use that same geometry. It excludes source annotations before rendering. It then paints selected pixels and constructs a new image-only PDF. Original text objects, links, forms, annotations, attachments, and metadata are not copied.

The result is no longer searchable text. Review every exported page, including cropped and rotated pages. Unselected faces and objects remain visible. Split documents above the stated page, pixel, or file limits.

## Office clean copies

| Format | Retained in a new file | Omitted |
| :--- | :--- | :--- |
| DOCX | Redacted body paragraphs and table-cell text | Headers, footers, hidden runs, tracked deletions, fields, links, comments, images, and embedded objects |
| XLSX | Redacted visible cell values with generic sheet names | Hidden sheets, rows and columns, formulas, comments, links, charts, images, and macros |
| PPTX | Redacted text and table text in original positions | Hidden slides, notes, links, comments, media, charts, and embedded objects |

Office reconstruction changes formatting. It favors a small inspectable copy over preservation of every source feature. Formula cells become `[FORMULA REMOVED]`, not calculated values. Keep the original separately. Check the clean file in Word, Excel, PowerPoint, or another compatible application before sharing.

## Images

Choose rectangles in the image preview. With local Tesseract installed, OCR matches can produce additional masks. The preview and export use the same image orientation. Export writes a new PNG and omits source EXIF metadata. Metadata removal alone does not remove visible private content.

## ZIP archives

Archive cleaning is bounded and uses generic output names. Read the manifest for every omitted entry. The archive path does not recursively process nested archives. Its supported text entries use text cleanup. Image entries receive metadata cleanup, not automatic pixel redaction. Extract and review documents or images individually when they need native redaction. Unsupported entries are omitted, not silently copied.

## Verify before sharing

Download the new output and its audit report. Check the actual output, not only the browser preview. The report identifies reconstruction losses and the need for human review. It does not certify legal compliance or complete privacy.

## Storage and support

The app stores its database in `.local-data/app.vault`. The database and its backups use authenticated encryption. Uploaded source copies and exported files are not encrypted by this app. Keep them in a protected folder.

Stop the app before copying its whole data folder. Keep the passphrase with a separate protected backup. Do not delete an original file until you have checked its output. Deleting a folder is not secure disk erasure.

When a source changes after review, scan it again. When a parser reports a size, page, or time limit, split the source. Do not publish private examples in a bug report. Include the exact error, app version, operating system, and a synthetic sample instead.
