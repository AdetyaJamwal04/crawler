"""
Unit and integration tests for Media Downloader server.
"""

from __future__ import annotations

import json
import threading
import time
from http.server import HTTPServer
from unittest.mock import MagicMock, patch
import pytest
import requests

from server import (
    MediaServerHandler,
    extract_filename_from_headers_or_url,
    inspect_media_url,
    sanitize_filename,
)


class TestHelpers:
    """Test filename extraction and sanitization helpers."""

    def test_sanitize_filename_basic(self) -> None:
        assert sanitize_filename("test_video.mp4") == "test_video.mp4"
        assert sanitize_filename("file:name/with?invalid*chars<.mp3") == "file_name_with_invalid_chars_.mp3"

    def test_sanitize_filename_strip_query_and_hash(self) -> None:
        assert sanitize_filename("video.mp4?token=123&expire=456") == "video.mp4"
        assert sanitize_filename("audio.mp3#t=10") == "audio.mp3"

    def test_sanitize_filename_fallback_empty(self) -> None:
        assert sanitize_filename("") == "downloaded_media"
        assert sanitize_filename("...   ...") == "downloaded_media"

    def test_extract_filename_content_disposition_standard(self) -> None:
        headers = {"content-disposition": 'attachment; filename="cool_movie.mp4"'}
        name = extract_filename_from_headers_or_url("https://example.com/download", headers)
        assert name == "cool_movie.mp4"

    def test_extract_filename_content_disposition_utf8_star(self) -> None:
        headers = {"content-disposition": "attachment; filename*=UTF-8''%E6%AD%8C%E6%9B%B2.mp3"}
        name = extract_filename_from_headers_or_url("https://example.com/download", headers)
        assert name == "歌曲.mp3"

    def test_extract_filename_from_url_path(self) -> None:
        headers = {"content-type": "video/mp4"}
        url = "https://cdn.example.org/videos/clip_2026.webm?auth=abc"
        name = extract_filename_from_headers_or_url(url, headers)
        assert name == "clip_2026.webm"

    def test_extract_filename_fallback_mimetype(self) -> None:
        headers = {"content-type": "video/mp4"}
        url = "https://example.com/stream"
        name = extract_filename_from_headers_or_url(url, headers)
        assert name == "stream.mp4"


class TestServerEndpoints:
    """Integration test suite spinning up a local test server instance."""

    server: HTTPServer
    server_thread: threading.Thread
    base_url: str

    @classmethod
    def setup_class(cls) -> None:
        # Bind to port 0 (OS picks available free port)
        cls.server = HTTPServer(("127.0.0.1", 0), MediaServerHandler)
        cls.port = cls.server.server_port
        cls.base_url = f"http://127.0.0.1:{cls.port}"
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def teardown_class(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def test_health_check(self) -> None:
        resp = requests.get(f"{self.base_url}/api/health", timeout=5)
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"
        assert "yt_dlp" in data

    def test_serve_static_index(self) -> None:
        resp = requests.get(f"{self.base_url}/", timeout=5)
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("Content-Type", "")
        assert "MediaFlow" in resp.text

    def test_serve_static_css(self) -> None:
        resp = requests.get(f"{self.base_url}/style.css", timeout=5)
        assert resp.status_code == 200
        assert "text/css" in resp.headers.get("Content-Type", "")

    def test_serve_static_js(self) -> None:
        resp = requests.get(f"{self.base_url}/app.js", timeout=5)
        assert resp.status_code == 200
        assert "javascript" in resp.headers.get("Content-Type", "")

    def test_inspect_invalid_url(self) -> None:
        resp = requests.get(f"{self.base_url}/api/inspect?url=ftp://not-supported", timeout=5)
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False

    def test_inspect_missing_url(self) -> None:
        resp = requests.get(f"{self.base_url}/api/inspect", timeout=5)
        assert resp.status_code == 400
        data = resp.json()
        assert data["ok"] is False

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
        assert result["ok"] is True
        assert result["filename"] == "sample.mp4"
        assert result["content_type"] == "video/mp4"
        assert result["size_bytes"] == 1048576
        assert result["is_media"] is True
        assert result["accept_ranges"] is True

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
            assert client_resp.status == 200
            assert body == b"chunk1chunk2"
            disposition = client_resp.headers.get("Content-Disposition", "")
            assert "attachment" in disposition
            assert client_resp.headers.get("Content-Type") == "audio/mpeg"

    @patch("server.MediaServerHandler.crawl_and_stream", return_value=False)
    @patch("server.MediaServerHandler.stream_via_ytdlp")
    @patch("server.requests.get")
    def test_stream_download_403_triggers_ytdlp_fallback(
        self, mock_get: MagicMock, mock_ytdlp: MagicMock, mock_crawl: MagicMock
    ) -> None:
        import urllib.request

        # Simulate upstream returning 403 Forbidden
        mock_resp = MagicMock()
        mock_resp.status_code = 403
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.__enter__.return_value = mock_resp
        mock_resp.__exit__.return_value = None
        mock_get.return_value = mock_resp

        def fake_stream(handler_self, url: str, custom_name: str = "") -> bool:
            handler_self.send_response(200)
            handler_self.send_header("Content-Type", "video/mp4")
            handler_self.end_headers()
            handler_self.wfile.write(b"fallback_video")
            return True

        mock_ytdlp.side_effect = lambda url, custom_name="": True

        try:
            req = urllib.request.Request(f"{self.base_url}/api/download?url=https://example.com/protected-video")
            with urllib.request.urlopen(req, timeout=5) as client_resp:
                pass
        except Exception:
            pass

        assert mock_ytdlp.called

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
        assert resp.status_code == 200
        data = resp.json()
        assert data["ok"] is True
        assert data["count"] >= 2
        types = [r["type"] for r in data["resources"]]
        assert "video" in types or "stream" in types
