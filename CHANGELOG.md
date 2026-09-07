# Changes

## 0.2.0

- Private-data patterns: Find email, phone, identifier, card, IP, and custom literal matches. Review each match.
- Local OCR: Inspect image and scanned-PDF text with local Tesseract. Keep review notes and word positions.
- PDF clean copies: Replace selected regions in rendered pixels. Rebuild a PDF without original hidden objects.
- Image redaction: Draw opaque regions over sensitive pixels. Export a new image without source metadata.
- Office clean copies: Reconstruct supported DOCX, XLSX, and PPTX content. Remove comments, properties, and unsafe embedded content.
- Archive review: Process bounded top-level ZIP entries. Report exclusions and use generic output names.
- Source protection: Refuse exports after a source changes. Create new files and keep the input unchanged.
- Encrypted records: Store scan records in an encrypted vault. Keep each export with an audit report.

The release also includes encrypted storage, request checks, portable output paths, synthetic examples, test reports, and recorded interface media.
