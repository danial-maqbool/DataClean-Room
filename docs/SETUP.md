# Setup

Use a 64-bit Windows, macOS, or Linux computer with Python 3.11 or newer and a modern browser.
No GPU is required. Large OCR batches and semantic indexes use more RAM than text-only tasks.
Select smaller folders or split large documents when a processing limit is reached.

## Python packages

Run `python bootstrap.py` from the project folder. On Windows, `py -3 bootstrap.py` selects Python 3.
The command creates `.venv` and installs requirements.txt. Runtime direct dependencies are pinned.
The test report records the exact tested package versions. Do not mix the app with a system-wide ML environment.

For a disconnected PC, prepare a wheel folder on a compatible online PC:

```sh
python -m pip download -r requirements.txt -d wheelhouse
python bootstrap.py --offline --wheelhouse wheelhouse
```

The Python version, OS, and processor architecture must match the destination.
Also transfer the required Tesseract language data and native tools through their official installers.
The app does not download these automatically.

## Tesseract OCR

Install Tesseract and add its executable folder to PATH. Install the languages that you will use.
The default language is `eng`. LocalFlow accepts a local language identifier such as `eng+urd`.
Check the installation with `tesseract --list-langs` and `python run.py doctor`.

Ubuntu/Debian:

```sh
sudo apt-get install tesseract-ocr tesseract-ocr-eng python3-venv
```

macOS with Homebrew:

```sh
brew install tesseract
```

For Windows installers, use the Windows section of the Tesseract installation guide listed in SOURCES.md.
Restart the terminal after changing PATH. The application does not install OS packages or change PATH itself.

## Desktop and foreground-window access

Run `python bootstrap.py --desktop` for LocalFlow mouse and keyboard input.
Start LocalFlow with `--allow-desktop`. Review and confirm the exact action list before each real run.
Move the pointer to a primary-screen corner to stop PyAutoGUI input.
Desktop actions can affect any foreground application, including a terminal. Never confirm an untrusted macro.

Windows needs an unlocked interactive session. The app cannot control an elevated window from a lower-integrity process.
macOS needs Accessibility permission for input. Screen Recording permission can be needed for screenshots.
Linux desktop input and window-title capture use X11. A Wayland compositor can block these operations.
File workflows, OCR, search, and document tools do not need desktop-control permission.

ActivityGraph has a separate title-capture consent control. It does not capture keys or automatic screenshots.

## Video operations

RecoveryLab needs both `ffmpeg` and `ffprobe` on PATH for media remuxing.
Use the official FFmpeg download information listed in SOURCES.md.
The app rejects playlist inputs and does not allow network media protocols.

## Troubleshooting

Run `python run.py doctor` with the virtual-environment Python to inspect dependency availability.
A locked vault means another app instance uses the same data folder. Open the existing worker or stop it first.
A wrong passphrase or altered vault fails closed. Restore a verified backup. Do not delete the only copy.
A service cannot unlock a locked or unsupported OS credential store. Use an interactive password in that case.
No confirmation or service error is silently converted into an unencrypted database.
