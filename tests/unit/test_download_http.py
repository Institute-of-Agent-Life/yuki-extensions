"""Real loopback GET retries keep the fixed asset and integrity boundary intact."""
from contextlib import contextmanager
import hashlib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import ssl
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError
from urllib.request import Request

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "ci"))
import download_http

spec = importlib.util.spec_from_file_location("fetch_contract_retry_test", ROOT / "ci/fetch-contract.py")
fetch = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fetch)


@contextmanager
def endpoint(responses):
    requests = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_GET(self):
            requests.append({"method": self.command, "path": self.path,
                             "header": self.headers.get("X-Fixture")})
            status, body, headers = responses[min(len(requests) - 1, len(responses) - 1)]
            self.send_response(status)
            self.send_header("Content-Length", str(len(body)))
            for key, value in headers.items():
                self.send_header(key, value)
            self.end_headers()
            self.wfile.write(body)

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}/fixed-asset", requests
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


class AssetTransport(unittest.TestCase):
    def test_transient_errors_keep_original_get_headers_and_fixed_bundle(self):
        payload = (ROOT / "compat/core-031/yuki-handshake-preview.zip").read_bytes()
        with endpoint([(502, b"upstream", {}), (504, b"gateway", {}),
                       (200, payload, {})]) as (url, requests), \
                patch.object(download_http, "sleep") as sleep:
            data = download_http.read_get(Request(url, headers={"X-Fixture": "fixed"}))
            self.assertEqual(data, payload)
            self.assertEqual(requests, [{"method": "GET", "path": "/fixed-asset", "header": "fixed"}] * 3)
            self.assertEqual([c.args for c in sleep.call_args_list], [(1,), (2,)])
        lock = json.loads((ROOT / "contracts.lock").read_bytes())
        self.assertEqual(hashlib.sha256(data).hexdigest(), lock["files"]["yuki-handshake-preview.zip"])
        with tempfile.TemporaryDirectory() as tmp:
            archive = Path(tmp) / "fixed.zip"
            archive.write_bytes(data)
            meta, _ = fetch.materialize(ROOT, Path(tmp) / "verified", archive)
            self.assertEqual(meta["source_commit"], lock["source_commit"])
            self.assertEqual(meta["capabilities"], lock["capabilities"])

    def test_continuous_504_stops_after_three_requests(self):
        with endpoint([(504, b"gateway", {})] * 3 + [(200, b"too late", {})]) as (url, requests), \
                patch.object(download_http, "sleep") as sleep:
            with self.assertRaises(HTTPError) as error:
                download_http.read_get(url)
            self.assertEqual(error.exception.code, 504)
            self.assertEqual(len(requests), 3)
            self.assertEqual(sleep.call_count, 2)

    def test_permanent_http_errors_are_not_retried(self):
        for status in (403, 404):
            with self.subTest(status=status), endpoint([(status, b"denied", {})]) as (url, requests), \
                    patch.object(download_http, "sleep") as sleep:
                with self.assertRaises(HTTPError):
                    download_http.read_get(url)
                self.assertEqual(len(requests), 1)
                sleep.assert_not_called()

    def test_retry_after_is_not_overridden_by_local_backoff(self):
        with endpoint([(503, b"wait", {"Retry-After": "120"})]) as (url, requests), \
                patch.object(download_http, "sleep") as sleep:
            with self.assertRaises(HTTPError):
                download_http.read_get(url)
            self.assertEqual(len(requests), 1)
            sleep.assert_not_called()

    def test_tls_verification_failure_is_not_retried(self):
        error = URLError(ssl.SSLCertVerificationError("untrusted certificate"))
        with patch.object(download_http, "urlopen", side_effect=error) as request, \
                patch.object(download_http, "sleep") as sleep:
            with self.assertRaises(URLError):
                download_http.read_get("https://fixture.invalid/asset")
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()

    def test_post_is_rejected_before_network_io(self):
        for method in ("POST", "GET"):
            with self.subTest(method=method), patch.object(download_http, "urlopen") as request:
                with self.assertRaisesRegex(ValueError, "require GET"):
                    download_http.read_get(Request("https://fixture.invalid/asset", data=b"write", method=method))
                request.assert_not_called()

    def test_success_with_wrong_digest_is_not_retried_or_written(self):
        with endpoint([(200, b"corrupt archive", {})]) as (url, requests), \
                patch.object(download_http, "sleep") as sleep, tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            original = (ROOT / "compat/core-031/yuki-handshake-preview.zip").read_bytes()
            (root / "contracts.lock").write_text(json.dumps({"release": {"assets": {
                "yuki-handshake-preview.zip": {"url": url, "sha256": hashlib.sha256(original).hexdigest()}
            }}}))
            with patch.dict(os.environ):
                os.environ.pop("YUKI_CORE031_RELEASE_DIR", None)
                with self.assertRaisesRegex(ValueError, "asset digest mismatch"):
                    fetch.obtain_release(root, root / "download")
            self.assertEqual(len(requests), 1)
            self.assertEqual(list((root / "download").iterdir()), [])
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
