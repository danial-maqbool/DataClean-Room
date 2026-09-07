"""Loopback-only HTTP transport with same-origin and per-session token checks.

Do not expose this server through a reverse proxy, port forward, or LAN bind.
It is a single-user desktop transport, not a production Internet server.
"""

from __future__ import annotations
import hmac
import json
import mimetypes
import secrets
import shutil
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from .safety import InputError, within

MAX_REQUEST = 36 * 1024 * 1024


def make_server(app, config: dict, port: int = 0):
    token = secrets.token_urlsafe(32)
    static = app.root / "web"

    class Handler(BaseHTTPRequestHandler):
        server_version = "LocalDesk/0.2"
        sys_version = ""

        def log_message(self, *_):
            pass  # Do not write file paths, private text, or session tokens to logs.

        def setup(self):
            super().setup()
            self.connection.settimeout(15)

        def _host_ok(self) -> bool:
            allowed = {
                f"127.0.0.1:{self.server.server_port}",
                f"localhost:{self.server.server_port}",
            }
            return (
                len(self.headers.get_all("Host", [])) == 1
                and self.headers.get("Host", "") in allowed
            )

        def _origin_ok(self) -> bool:
            origin = self.headers.get("Origin")
            return origin is None or origin in {
                f"http://127.0.0.1:{self.server.server_port}",
                f"http://localhost:{self.server.server_port}",
            }

        def _authorized(self) -> bool:
            supplied = self.headers.get("X-Local-Token", "")
            return (
                self._host_ok()
                and self._origin_ok()
                and hmac.compare_digest(supplied, token)
            )

        def _send(
            self,
            code: int,
            raw: bytes,
            kind: str = "application/json; charset=utf-8",
            filename: str | None = None,
        ):
            self.send_response(code)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(raw)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("X-Frame-Options", "DENY")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: blob:; "
                "connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'",
            )
            if filename:
                from urllib.parse import quote

                self.send_header(
                    "Content-Disposition",
                    f"attachment; filename*=UTF-8''{quote(filename)}",
                )
            self.end_headers()
            try:
                self.wfile.write(raw)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _file(self, path: Path):
            from urllib.parse import quote

            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(path.stat().st_size))
            self.send_header(
                "Content-Disposition",
                f"attachment; filename*=UTF-8''{quote(path.name)}",
            )
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Cross-Origin-Resource-Policy", "same-origin")
            self.send_header("Content-Security-Policy", "default-src 'none'; sandbox")
            self.end_headers()
            try:
                with path.open("rb") as stream:
                    shutil.copyfileobj(stream, self.wfile, 1024 * 1024)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def _json(self, code: int, value: dict):
            self._send(code, json.dumps(value, ensure_ascii=False).encode("utf-8"))

        def do_GET(self):
            if not self._host_ok() or not self._origin_ok():
                return self._json(
                    403, {"error": "Only this local app origin is allowed."}
                )
            request = urlsplit(self.path)
            if request.path == "/healthz":
                return self._json(200, {"status": "ok", "name": config["name"]})
            if request.path.startswith("/api/"):
                if not self._authorized():
                    return self._json(
                        403, {"error": "The local session token is missing or invalid."}
                    )
                action = request.path[5:]
                args = {k: v[0] for k, v in parse_qs(request.query).items()}
                try:
                    if action == "download":
                        p = app.download(args.get("path", ""))
                        return self._file(p)
                    return self._json(200, app.common_get(action, args))
                except (InputError, ValueError, FileNotFoundError) as exc:
                    return self._json(400, {"error": str(exc)})
                except Exception:
                    return self._json(
                        500,
                        {
                            "error": "The operation failed. Check the app input and try again."
                        },
                    )
            name = request.path.lstrip("/") or "index.html"
            path = (static / name).resolve()
            if (
                not within(path, static)
                or not path.is_file()
                or path.suffix
                not in {".html", ".css", ".js", ".svg", ".png", ".gif", ".ico"}
            ):
                return self._json(404, {"error": "This page does not exist."})
            raw = path.read_bytes()
            if name == "index.html":
                raw = raw.replace(b"@@TOKEN@@", token.encode("ascii"))
            return self._send(
                200,
                raw,
                mimetypes.guess_type(str(path))[0] or "application/octet-stream",
            )

        def do_POST(self):
            if not self._authorized():
                return self._json(
                    403, {"error": "This request is not authorized by the local app."}
                )
            if len(self.headers.get_all("Content-Length", [])) != 1:
                return self._json(
                    400, {"error": "Use exactly one Content-Length header."}
                )
            if self.headers.get("Transfer-Encoding"):
                return self._json(400, {"error": "Chunked requests are not supported."})
            if self.headers.get_content_type() != "application/json":
                return self._json(415, {"error": "Use a JSON request."})
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_REQUEST:
                    return self._json(
                        413, {"error": "The request exceeds the local size limit."}
                    )
                raw = self.rfile.read(length)
                if len(raw) != length:
                    raise InputError("The request is incomplete.")
                body = json.loads(raw)
                if not isinstance(body, dict):
                    raise InputError("The request must be a JSON object.")
                path = urlsplit(self.path).path
                if not path.startswith("/api/"):
                    return self._json(404, {"error": "This operation does not exist."})
                result = app.common_post(path[5:], body)
                return self._json(200, result)
            except (InputError, ValueError, KeyError, TypeError, OSError) as exc:
                return self._json(400, {"error": str(exc)[:500]})
            except Exception:
                return self._json(
                    500,
                    {
                        "error": "The operation failed. Check the app input and try again."
                    },
                )

    class BoundedServer(ThreadingHTTPServer):
        # Reject excess sockets instead of spawning unlimited request threads.
        slots = threading.BoundedSemaphore(16)

        def process_request(self, request, address):
            if not self.slots.acquire(blocking=False):
                self.shutdown_request(request)
                return
            try:
                super().process_request(request, address)
            except BaseException:
                self.slots.release()
                raise

        def process_request_thread(self, request, address):
            try:
                super().process_request_thread(request, address)
            finally:
                self.slots.release()

    server = BoundedServer(("127.0.0.1", port), Handler)
    server.daemon_threads = True
    return server, token


def serve(app, config: dict, port: int, open_browser: bool):
    server, _ = make_server(app, config, port)
    url = f"http://127.0.0.1:{server.server_port}"
    print(f"{config['name']} is running at {url}", flush=True)
    print(
        "Press Ctrl+C to stop. No files are scanned until you start an operation.",
        flush=True,
    )
    if open_browser:
        threading.Timer(0.5, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever(poll_interval=0.2)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        app.close()
