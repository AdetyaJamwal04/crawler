"""
Unit and integration tests for Media Downloader server.
Supports execution via both pytest and python3 -m unittest.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
from http.server import HTTPServer
from unittest.mock import MagicMock, patch
import requests

from server import (
    MediaServerHandler,
    extract_filename_from_headers_or_url,
    format_content_disposition,
    inspect_media_url,
    sanitize_filename,
)
from crawler import is_safe_url


class TestHelpers(unittest.TestCase):
    """Test filename extraction, formatting, and sanitization helpers."""

    def test_sanitize_filename_basic(self) -> None:
        self.assertEqual(sanitize_filename("test_video.mp4"), "test_video.mp4")
        self.assertEqual(
            sanitize_filename("file:name/with?invalid*chars<.mp3"),
            "file_name_with_invalid_chars_.mp3",
        )

    def test_sanitize_filename_strip_query_and_hash(self) -> None:
        self.assertEqual(sanitize_filename("video.mp4?token=123&expire=456"), "video.mp4")
        self.assertEqual(sanitize_filename("audio.mp3#t=10"), "audio.mp3")

    def test_sanitize_filename_fallback_empty(self) -> None:
        self.assertEqual(sanitize_filename(""), "downloaded_media")
        self.assertEqual(sanitize_filename("...   ..."), "downloaded_media")

    def test_format_content_disposition_ascii(self) -> None:
        disposition = format_content_disposition("movie.mp4")
        self.assertIn('filename="movie.mp4"', disposition)
        self.assertIn("filename*=UTF-8''movie.mp4", disposition)
        # Verify it encodes in latin-1 without exception
        disposition.encode("latin-1")

    def test_format_content_disposition_unicode_safe(self) -> None:
        # Non-ASCII filename that would otherwise crash latin-1 HTTP headers
        disposition = format_content_disposition("歌曲_clip_🎬.mp4")
        # Ensure latin-1 encoding succeeds (no UnicodeEncodeError)
        encoded_header = disposition.encode("latin-1")
        self.assertTrue(len(encoded_header) > 0)
        # Ensure UTF-8 parameter holds full encoded string
        self.assertIn("filename*=UTF-8''", disposition)
        self.assertIn("%E6%AD%8C%E6%9B%B2", disposition)

    def test_extract_filename_content_disposition_standard(self) -> None:
        headers = {"content-disposition": 'attachment; filename="cool_movie.mp4"'}
        name = extract_filename_from_headers_or_url("https://example.com/download", headers)
        self.assertEqual(name, "cool_movie.mp4")

    def test_extract_filename_content_disposition_utf8_star(self) -> None:
        headers = {"content-disposition": "attachment; filename*=UTF-8''%E6%AD%8C%E6%9B%B2.mp3"}
        name = extract_filename_from_headers_or_url("https://example.com/download", headers)
        self.assertEqual(name, "歌曲.mp3")

    def test_extract_filename_from_url_path(self) -> None:
        headers = {"content-type": "video/mp4"}
        url = "https://cdn.example.org/videos/clip_2026.webm?auth=abc"
        name = extract_filename_from_headers_or_url(url, headers)
        self.assertEqual(name, "clip_2026.webm")

    def test_extract_filename_fallback_mimetype(self) -> None:
        headers = {"content-type": "video/mp4"}
        url = "https://example.com/stream"
        name = extract_filename_from_headers_or_url(url, headers)
        self.assertEqual(name, "stream.mp4")

    def test_is_safe_url(self) -> None:
        self.assertTrue(is_safe_url("https://example.com/video.mp4"))
        self.assertFalse(is_safe_url("ftp://example.com/video.mp4"))
        self.assertFalse(is_safe_url("file:///etc/passwd"))
        self.assertFalse(is_safe_url("http://169.254.169.254/latest/meta-data/"))


class TestServerEndpoints(unittest.TestCase):
    """Integration test suite spinning up a local test server instance."""

    server: HTTPServer
    server_thread: threading.Thread
    base_url: str

    @classmethod
    def setUpClass(cls) -> None:
        # Bind to port 0 (OS picks available free port)
        cls.server = HTTPServer(("127.0.0.1", 0), MediaServerHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_check(self) -> None:
        resp = requests.get(f"{self.base_url}/api/health", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertEqual(data["status"], "ok")
        self.assertIn("yt_dlp", data)

    def test_serve_static_index(self) -> None:
        resp = requests.get(f"{self.base_url}/", timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/html", resp.headers.get("Content-Type", ""))
        self.assertIn("MediaFlow", resp.text)

    def test_serve_static_css(self) -> None:
        resp = requests.get(f"{self.base_url}/style.css", timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("text/css", resp.headers.get("Content-Type", ""))

    def test_serve_static_js(self) -> None:
        resp = requests.get(f"{self.base_url}/app.js", timeout=5)
        self.assertEqual(resp.status_code, 200)
        self.assertIn("javascript", resp.headers.get("Content-Type", ""))

    def test_unmatched_api_returns_404(self) -> None:
        resp = requests.get(f"{self.base_url}/api/unknown_route", timeout=5)
        self.assertEqual(resp.status_code, 404)
        data = resp.json()
        self.assertFalse(data["ok"])

    def test_inspect_invalid_url(self) -> None:
        resp = requests.get(f"{self.base_url}/api/inspect?url=ftp://not-supported", timeout=5)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])

    def test_inspect_missing_url(self) -> None:
        resp = requests.get(f"{self.base_url}/api/inspect", timeout=5)
        self.assertEqual(resp.status_code, 400)
        data = resp.json()
        self.assertFalse(data["ok"])

    @patch("server.requests.head")
    def test_inspect_mocked_success(self, mock_head: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/sample.mp4"
        mock_resp.headers = {
            "content-type": "video/mp4",
            "content-length": "1048576",
            "accept-ranges": "bytes",
        }
        mock_head.return_value = mock_resp

        result = inspect_media_url("https://example.com/sample.mp4")
        self.assertTrue(result["ok"])
        self.assertEqual(result["filename"], "sample.mp4")
        self.assertEqual(result["content_type"], "video/mp4")
        self.assertEqual(result["size_bytes"], 1048576)
        self.assertTrue(result["is_media"])
        self.assertTrue(result["accept_ranges"])

    @patch("server.requests.get")
    def test_stream_download_mocked(self, mock_get: MagicMock) -> None:
        import urllib.request

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/music.mp3"
        mock_resp.headers = {
            "content-type": "audio/mpeg",
            "content-length": "12",
        }
        mock_resp.iter_content.return_value = [b"chunk1", b"chunk2"]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        req = urllib.request.Request(f"{self.base_url}/api/download?url=https://example.com/music.mp3")
        with urllib.request.urlopen(req, timeout=5) as client_resp:
            body = client_resp.read()
            self.assertEqual(client_resp.status, 200)
            self.assertEqual(body, b"chunk1chunk2")
            disposition = client_resp.headers.get("Content-Disposition", "")
            self.assertIn("attachment", disposition)
            self.assertEqual(client_resp.headers.get("Content-Type"), "audio/mpeg")

    @patch("server.requests.get")
    def test_stream_download_unicode_filename_safe(self, mock_get: MagicMock) -> None:
        import urllib.request

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.url = "https://example.com/unicode.mp4"
        mock_resp.headers = {
            "content-type": "video/mp4",
            "content-length": "6",
        }
        mock_resp.iter_content.return_value = [b"stream"]
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        # Request download with international name (Chinese + Emoji)
        url_encoded_name = urllib.parse.quote("电影_movie_🎥.mp4")
        req = urllib.request.Request(f"{self.base_url}/api/download?url=https://example.com/unicode.mp4&name={url_encoded_name}")
        with urllib.request.urlopen(req, timeout=5) as client_resp:
            self.assertEqual(client_resp.status, 200)
            disposition = client_resp.headers.get("Content-Disposition", "")
            self.assertIn("filename*=UTF-8''", disposition)

    @patch("server.MediaServerHandler.crawl_and_stream", return_value=False)
    @patch("server.MediaServerHandler.stream_via_ytdlp")
    @patch("server.requests.get")
    def test_stream_download_403_triggers_ytdlp_fallback(
        self, mock_get: MagicMock, mock_ytdlp: MagicMock, mock_crawl: MagicMock
    ) -> None:
        import urllib.request

        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        mock_ytdlp.side_effect = lambda url, custom_name="": True

        try:
            req = urllib.request.Request(f"{self.base_url}/api/download?url=https://example.com/protected-video")
            with urllib.request.urlopen(req, timeout=5) as client_resp:
                pass
        except Exception:
            pass

        self.assertTrue(mock_ytdlp.called)

    @patch("crawler.requests.Session.get")
    def test_crawl_endpoint(self, mock_sess_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/watch"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = """
        <html>
          <head><title>Test Video Page</title></head>
          <body>
            <video src="/videos/cool.mp4" poster="/thumbs/cool.jpg"></video>
            <script>var stream = "https://cdn.example.com/hls/live.m3u8";</script>
          </body>
        </html>
        """
        mock_sess_get.return_value = mock_resp

        resp = requests.get(f"{self.base_url}/api/crawl?url=https://example.com/watch", timeout=5)
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertGreaterEqual(data["count"], 2)
        types = [r["type"] for r in data["resources"]]
        self.assertTrue("video" in types or "stream" in types)


if __name__ == "__main__":
    unittest.main()
