"""Real loopback HTTP checks. No browser bridge is used in these tests."""

import http.client
import json
import threading
from localdesk.server import make_server
from tests.support import AppCase


class HttpTests(AppCase):
    def setUp(self):
        super().setUp()
        self.server, self.token = make_server(self.app, self.app.info(), 0)
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.02), daemon=True
        )
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        super().tearDown()

    def request(
        self, method="GET", path="/api/info", body=None, headers=None, auth=True
    ):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        h = {"X-Local-Token": self.token} if auth else {}
        if body is not None:
            h["Content-Type"] = "application/json"
        h.update(headers or {})
        c.request(method, path, body=body, headers=h)
        r = c.getresponse()
        result = (r.status, dict(r.getheaders()), r.read())
        c.close()
        return result

    def test_server_binds_only_loopback(self):
        self.assertEqual(self.server.server_address[0], "127.0.0.1")

    def test_html_has_session_token(self):
        code, h, data = self.request(path="/", auth=False)
        self.assertEqual(code, 200)
        self.assertIn(self.token.encode(), data)
        self.assertIn("frame-ancestors 'none'", h["Content-Security-Policy"])

    def test_static_javascript_is_served(self):
        code, h, data = self.request(path="/app.js", auth=False)
        self.assertEqual(code, 200)
        self.assertIn(b"common.js", data)

    def test_api_requires_token(self):
        self.assertEqual(self.request(auth=False)[0], 403)

    def test_wrong_token_is_rejected(self):
        self.assertEqual(self.request(headers={"X-Local-Token": "wrong"})[0], 403)

    def test_remote_origin_is_rejected(self):
        self.assertEqual(
            self.request(headers={"Origin": "https://other.example"})[0], 403
        )

    def test_host_rebinding_is_rejected(self):
        self.assertEqual(self.request(headers={"Host": "evil.example"})[0], 403)

    def test_unknown_api_returns_error(self):
        self.assertEqual(self.request(path="/api/no-such-operation")[0], 400)

    def test_static_path_cannot_escape(self):
        self.assertEqual(self.request(path="/../project.json", auth=False)[0], 404)

    def test_post_rejects_non_json(self):
        self.assertEqual(
            self.request("POST", "/api/upload", "abc", {"Content-Type": "text/plain"})[
                0
            ],
            415,
        )

    def test_post_rejects_list_body(self):
        self.assertEqual(self.request("POST", "/api/upload", "[]")[0], 400)

    def test_demo_backup_refuses_an_unrecoverable_key(self):
        status, h, raw = self.request("POST", "/api/backup", "{}")
        self.assertEqual(status, 400)
        self.assertIn("password-protected", json.loads(raw)["error"])

    def test_health_does_not_expose_paths(self):
        code, h, raw = self.request(path="/healthz", auth=False)
        self.assertEqual(code, 200)
        self.assertNotIn(str(self.app.data).encode(), raw)

    def test_duplicate_host_is_rejected(self):
        c = http.client.HTTPConnection("127.0.0.1", self.server.server_port, timeout=5)
        c.putrequest("GET", "/api/info", skip_host=True)
        c.putheader("Host", f"127.0.0.1:{self.server.server_port}")
        c.putheader("Host", "other.example")
        c.putheader("X-Local-Token", self.token)
        c.endheaders()
        response = c.getresponse()
        self.assertEqual(response.status, 403)
        response.read()
        c.close()

    def test_chunked_request_is_rejected(self):
        self.assertEqual(
            self.request("POST", "/api/backup", "{}", {"Transfer-Encoding": "chunked"})[
                0
            ],
            400,
        )

    def test_html_is_not_embeddable(self):
        code, headers, _ = self.request(path="/", auth=False)
        self.assertEqual(code, 200)
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
