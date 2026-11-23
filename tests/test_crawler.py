"""
Unit tests for MediaCrawler and stream extraction engine.
Supports execution via both pytest and python3 -m unittest.
"""

from __future__ import annotations

import unittest
from unittest.mock import MagicMock, patch
from crawler import MediaCrawler, is_safe_url


class TestMediaCrawler(unittest.TestCase):
    """Test suite for crawler logic and extraction."""

    def setUp(self) -> None:
        self.crawler = MediaCrawler(timeout=5)

    @patch("crawler.requests.Session.get")
    def test_crawl_direct_m3u8_stream(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://cdn.example.com/live/playlist.m3u8"
        mock_resp.headers = {"content-type": "application/vnd.apple.mpegurl"}
        mock_get.return_value = mock_resp

        result = self.crawler.crawl("https://cdn.example.com/live/playlist.m3u8")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        res = result["resources"][0]
        self.assertEqual(res["type"], "stream")
        self.assertTrue(res["is_stream"])
        self.assertEqual(res["format"], "m3u8")

    @patch("crawler.requests.Session.get")
    def test_crawl_direct_mp4_video(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://cdn.example.com/sample.mp4"
        mock_resp.headers = {"content-type": "video/mp4", "content-length": "2048"}
        mock_get.return_value = mock_resp

        result = self.crawler.crawl("https://cdn.example.com/sample.mp4")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        res = result["resources"][0]
        self.assertEqual(res["type"], "video")
        self.assertEqual(res["format"], "mp4")
        self.assertEqual(res["size_bytes"], 2048)

    @patch("crawler.requests.Session.get")
    def test_crawl_html_with_m3u8_query_params(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/player"
        mock_resp.headers = {"content-type": "text/html; charset=utf-8"}
        mock_resp.text = """
        <html>
          <head><title>Video Page</title></head>
          <body>
            <video controls>
              <source src="/hls/stream.m3u8?token=xyz123&expires=999999" type="application/x-mpegURL">
            </video>
          </body>
        </html>
        """
        mock_get.return_value = mock_resp

        result = self.crawler.crawl("https://example.com/player")
        self.assertTrue(result["ok"])
        self.assertEqual(result["count"], 1)
        res = result["resources"][0]
        self.assertEqual(res["type"], "stream")
        self.assertTrue(res["is_stream"])
        self.assertEqual(res["url"], "https://example.com/hls/stream.m3u8?token=xyz123&expires=999999")

    @patch("crawler.requests.Session.get")
    def test_crawl_html_with_escaped_js_slashes(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://example.com/watch"
        mock_resp.headers = {"content-type": "text/html"}
        mock_resp.text = r"""
        <html>
          <head><title>Watch</title></head>
          <body>
            <script>
              var playerConfig = {
                file: "https:\/\/cdn.stream.com\/videos\/clip.mp4?auth=abc",
                hls: "https:\/\/cdn.stream.com\/live\/index.m3u8"
              };
            </script>
          </body>
        </html>
        """
        mock_get.return_value = mock_resp

        result = self.crawler.crawl("https://example.com/watch")
        self.assertTrue(result["ok"])
        urls = [r["url"] for r in result["resources"]]
        # Verify backslashes are properly unescaped
        self.assertIn("https://cdn.stream.com/videos/clip.mp4?auth=abc", urls)
        self.assertIn("https://cdn.stream.com/live/index.m3u8", urls)

    @patch("crawler.requests.Session.get")
    def test_crawl_iframe_relative_urls_resolved_to_iframe_origin(self, mock_get: MagicMock) -> None:
        # Mock parent page
        parent_resp = MagicMock()
        parent_resp.url = "https://mainpage.com/watch"
        parent_resp.headers = {"content-type": "text/html"}
        parent_resp.text = """
        <html>
          <body>
            <iframe src="https://embedplayer.cdn.com/embed/player123"></iframe>
          </body>
        </html>
        """

        # Mock iframe page
        iframe_resp = MagicMock()
        iframe_resp.url = "https://embedplayer.cdn.com/embed/player123"
        iframe_resp.ok = True
        iframe_resp.headers = {"content-type": "text/html"}
        iframe_resp.text = """
        <html>
          <body>
            <video src="/media/video_source.mp4"></video>
          </body>
        </html>
        """

        mock_get.side_effect = [parent_resp, iframe_resp]

        result = self.crawler.crawl("https://mainpage.com/watch", depth=1)
        self.assertTrue(result["ok"])
        urls = [r["url"] for r in result["resources"]]
        # Must resolve to iframe domain, NOT mainpage.com
        self.assertIn("https://embedplayer.cdn.com/media/video_source.mp4", urls)
        self.assertNotIn("https://mainpage.com/media/video_source.mp4", urls)

    @patch("crawler.requests.Session.get")
    def test_crawl_cloudflare_challenge_detected(self, mock_get: MagicMock) -> None:
        mock_resp = MagicMock()
        mock_resp.url = "https://protected-site.com/"
        mock_resp.headers = {"content-type": "text/html", "cf-mitigated": "challenge"}
        mock_resp.text = "<html><body>Just a moment...</body></html>"
        mock_get.return_value = mock_resp

        result = self.crawler.crawl("https://protected-site.com/")
        self.assertFalse(result["ok"])
        self.assertIn("Cloudflare", result["error"])

    def test_json_ld_extraction(self) -> None:
        json_data = {
            "@context": "https://schema.org",
            "@type": "VideoObject",
            "name": "Sample JSON-LD Video",
            "contentUrl": "https://cdn.example.com/json_ld_video.mp4",
            "thumbnailUrl": "https://cdn.example.com/thumb.jpg",
        }
        extracted = []

        def dummy_add(url, mtype, tag, title="", thumb=None):
            extracted.append({"url": url, "type": mtype, "tag": tag, "title": title, "thumb": thumb})

        self.crawler._extract_from_json(json_data, dummy_add)
        self.assertEqual(len(extracted), 1)
        self.assertEqual(extracted[0]["url"], "https://cdn.example.com/json_ld_video.mp4")
        self.assertEqual(extracted[0]["title"], "Sample JSON-LD Video")


if __name__ == "__main__":
    unittest.main()
