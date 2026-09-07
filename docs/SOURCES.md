# Sources and third-party components

Runtime code in this repository uses these primary references. No third-party model weights or font files are included.

| Component | Reference | Purpose |
| :--- | :--- | :--- |
| Python | https://docs.python.org/3/library/sqlite3.html | SQLite backup, serialization, transactions |
| cryptography | https://cryptography.io/en/latest/hazmat/primitives/aead/ | AES-GCM authenticated encryption |
| cryptography | https://cryptography.io/en/latest/hazmat/primitives/key-derivation-functions/ | scrypt key derivation |
| Tesseract | https://tesseract-ocr.github.io/tessdoc/Installation.html | Local OCR installation and language data |
| pdfplumber | https://github.com/jsvine/pdfplumber | Native PDF words and tables |
| pypdf | https://pypdf.readthedocs.io/ | PDF rebuilding and validation |
| pypdfium2 | https://pypdfium2.readthedocs.io/ | Local PDF rendering |
| Pillow | https://pillow.readthedocs.io/ | Pixel operations and image output |
| scikit-learn | https://scikit-learn.org/stable/modules/decomposition.html#lsa | Latent semantic analysis |
| Sentence Transformers | https://www.sbert.net/docs/package_reference/sentence_transformer/SentenceTransformer.html | Optional local model loading |
| PyAutoGUI | https://pyautogui.readthedocs.io/en/latest/ | Interactive desktop actions and fail-safe |
| keyring | https://keyring.readthedocs.io/en/latest/ | OS credential stores |
| FFmpeg | https://ffmpeg.org/documentation.html | Local media remuxing |

Dependencies retain their own licenses. Review those licenses before redistributing an installed environment or a model folder.
The application source uses MIT. No font files are distributed by this repository.
