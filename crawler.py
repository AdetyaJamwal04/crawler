"""
Media Crawler & Resource Extractor Engine
Crawls any webpage, discovers all embedded media files, streams, and protected links,
and handles anti-hotlink referers, cookies, and HLS/DASH streams.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import urllib.parse
from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional, Set
import requests
from bs4 import BeautifulSoup

# Extended media extensions
VIDEO_EXTS = {".mp4", ".webm", ".mkv", ".mov", ".avi", ".flv", ".wmv", ".m4v"}
AUDIO_EXTS = {".mp3", ".wav", ".ogg", ".flac", ".m4a", ".aac", ".opus", ".wma"}
STREAM_EXTS = {".m3u8", ".mpd"}
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg", ".bmp", ".avif"}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


@dataclass
class MediaResource:
    """Represents a discovered media resource on a crawled page."""
    url: str
    type: str  # "video", "audio", "stream", "image"
    format: str  # "mp4", "m3u8", "mp3", etc.
    title: str
    source_tag: str  # "video_tag", "og_meta", "json_ld", "script_regex", "iframe"
    referer: str
    thumbnail: Optional[str] = None
    size_bytes: Optional[int] = None
    is_stream: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class MediaCrawler:
    """Intelligent web crawler that analyzes pages for media resources."""

    def __init__(self, timeout: int = 15):
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": DEFAULT_USER_AGENT,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
            "Upgrade-Insecure-Requests": "1",
        })

    def crawl(self, page_url: str, depth: int = 1) -> Dict[str, Any]:
        """Crawl a webpage and discover all media files and streams."""
        parsed = urllib.parse.urlparse(page_url)
        if parsed.scheme not in ("http", "https"):
            return {"ok": False, "error": "Invalid URL scheme. Must be http or https."}

        origin = f"{parsed.scheme}://{parsed.netloc}"
        self.session.headers.update({"Referer": origin + "/", "Origin": origin})

        try:
            resp = self.session.get(page_url, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as e:
            return {"ok": False, "error": f"Failed to connect to page: {str(e)}"}

        final_url = resp.url
        content_type = resp.headers.get("content-type", "").lower()

        # If the URL directly points to a media file, return it as a single discovered resource
        if any(content_type.startswith(prefix) for prefix in ("video/", "audio/", "image/")):
            ext = mimetypes.guess_extension(content_type.split(";")[0]) or ".media"
            filename = os.path.basename(urllib.parse.urlparse(final_url).path) or f"media{ext}"
            content_len = resp.headers.get("content-length")
            size = int(content_len) if content_len and content_len.isdigit() else None
            mtype = "video" if "video" in content_type else "audio" if "audio" in content_type else "image"
            res = MediaResource(
                url=final_url,
                type=mtype,
                format=ext.lstrip("."),
                title=filename,
                source_tag="direct_media_url",
                referer=page_url,
                size_bytes=size,
            )
            return {
                "ok": True,
                "page_url": final_url,
                "page_title": filename,
                "count": 1,
                "resources": [res.to_dict()],
            }

        # Otherwise parse HTML content
        html_text = resp.text

        # Check for Cloudflare Turnstile / Managed Challenge
        if resp.headers.get("cf-mitigated") == "challenge" or "challenges.cloudflare.com" in html_text or "Just a moment..." in html_text:
            return {
                "ok": False,
                "error": f"The page at {parsed.netloc} is protected by a Cloudflare 'Verify you are human' challenge. "
                         f"Please open the page directly in your browser, copy the media link from the player or network tab, "
                         f"and download it using Referer: https://{parsed.netloc}/.",
            }

        soup = BeautifulSoup(html_text, "html.parser")

        page_title = "Crawled Media"
        if soup.title and soup.title.string:
            page_title = soup.title.string.strip()

        discovered: List[MediaResource] = []
        seen_urls: Set[str] = set()

        def add_resource(
            url: str,
            mtype: str,
            source_tag: str,
            title: str = "",
            thumb: Optional[str] = None,
            is_stream: bool = False,
        ) -> None:
            if not url or url.startswith("data:") or url.startswith("javascript:"):
                return
            full_url = urllib.parse.urljoin(final_url, url.strip())
            if full_url in seen_urls:
                return
            seen_urls.add(full_url)

            # Determine format
            parsed_r = urllib.parse.urlparse(full_url)
            path_lower = parsed_r.path.lower()
            ext = os.path.splitext(path_lower)[1]
            fmt = ext.lstrip(".") if ext else mtype

            if not title:
                base = os.path.basename(parsed_r.path)
                title = urllib.parse.unquote(base) if base else page_title

            discovered.append(MediaResource(
                url=full_url,
                type=mtype,
                format=fmt,
                title=title,
                source_tag=source_tag,
                referer=final_url,
                thumbnail=thumb,
                is_stream=is_stream or ext in STREAM_EXTS,
            ))

        # 1. HTML5 <video> elements
        for video in soup.find_all("video"):
            v_src = video.get("src") or video.get("data-src") or video.get("data-url")
            poster = video.get("poster")
            if v_src:
                add_resource(v_src, "video", "video_tag", thumb=poster)
            for source in video.find_all("source"):
                s_src = source.get("src") or source.get("data-src")
                if s_src:
                    s_type = source.get("type", "")
                    mtype = "stream" if "x-mpegurl" in s_type or s_src.endswith(".m3u8") else "video"
                    add_resource(s_src, mtype, "video_source", thumb=poster, is_stream=(mtype == "stream"))

        # 2. HTML5 <audio> elements
        for audio in soup.find_all("audio"):
            a_src = audio.get("src") or audio.get("data-src")
            if a_src:
                add_resource(a_src, "audio", "audio_tag")
            for source in audio.find_all("source"):
                s_src = source.get("src") or source.get("data-src")
                if s_src:
                    add_resource(s_src, "audio", "audio_source")

        # 3. OpenGraph & Twitter Meta Tags
        for meta in soup.find_all("meta"):
            prop = meta.get("property") or meta.get("name") or ""
            content = meta.get("content")
            if not content:
                continue
            prop_l = prop.lower()
            if prop_l in ("og:video", "og:video:url", "og:video:secure_url", "twitter:player:stream"):
                add_resource(content, "video", "meta_og_video")
            elif prop_l in ("og:audio", "og:audio:secure_url"):
                add_resource(content, "audio", "meta_og_audio")
            elif prop_l in ("og:image", "twitter:image") and not prop_l.endswith(":alt"):
                add_resource(content, "image", "meta_og_image")

        # 4. JSON-LD scripts (<script type="application/ld+json">)
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                if not script.string:
                    continue
                data = json.loads(script.string)
                self._extract_from_json(data, add_resource)
            except Exception:
                pass

        # 5. Regex Deep Mining in Script Tags & HTML
        # Look for inlined .mp4, .m3u8, .mpd, .webm, .mp3 links
        media_regex = re.compile(
            r'https?://[^\s"\'<>]+\.(?:mp4|webm|mkv|m3u8|mpd|mp3|wav|ogg|flac)(?:\?[^\s"\'<>]*)?',
            re.IGNORECASE,
        )
        for match in media_regex.finditer(html_text):
            found_url = match.group(0)
            url_clean = found_url.split("?")[0].lower()
            if any(url_clean.endswith(ext) for ext in STREAM_EXTS):
                add_resource(found_url, "stream", "script_regex", is_stream=True)
            elif any(url_clean.endswith(ext) for ext in VIDEO_EXTS):
                add_resource(found_url, "video", "script_regex")
            elif any(url_clean.endswith(ext) for ext in AUDIO_EXTS):
                add_resource(found_url, "audio", "script_regex")

        # 6. Embedded Player Iframes (e.g. Vimeo, YouTube, Player embeds)
        if depth > 0:
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src") or iframe.get("data-src")
                if not src:
                    continue
                full_iframe = urllib.parse.urljoin(final_url, src)
                # If iframe is a video embed, optionally crawl iframe page
                if any(k in full_iframe.lower() for k in ("embed", "player", "video")):
                    try:
                        iframe_resp = self.session.get(full_iframe, headers={"Referer": final_url}, timeout=6)
                        if iframe_resp.ok:
                            iframe_soup = BeautifulSoup(iframe_resp.text, "html.parser")
                            for v in iframe_soup.find_all(["video", "source"]):
                                isrc = v.get("src") or v.get("data-src")
                                if isrc:
                                    add_resource(isrc, "video", "iframe_crawler")
                            for match in media_regex.finditer(iframe_resp.text):
                                add_resource(match.group(0), "video", "iframe_script_regex")
                    except Exception:
                        pass

        # 7. Images on page (if no video/audio found, or high-res images)
        for img in soup.find_all("img"):
            i_src = img.get("src") or img.get("data-src") or img.get("data-original")
            if i_src:
                add_resource(i_src, "image", "img_tag", thumb=i_src)

        # Sort resources so videos & streams appear first
        priority = {"video": 1, "stream": 2, "audio": 3, "image": 4}
        discovered.sort(key=lambda r: priority.get(r.type, 9))

        return {
            "ok": True,
            "page_url": final_url,
            "page_title": page_title,
            "count": len(discovered),
            "resources": [r.to_dict() for r in discovered],
        }

    def _extract_from_json(self, data: Any, add_cb: Any) -> None:
        """Recursively search JSON structures for video/audio/image URLs."""
        if isinstance(data, dict):
            content_url = data.get("contentUrl")
            embed_url = data.get("embedUrl")
            name = data.get("name") or data.get("headline") or ""
            thumb = data.get("thumbnailUrl")
            if isinstance(thumb, list) and thumb:
                thumb = thumb[0]

            if content_url and isinstance(content_url, str):
                mtype = "video" if "video" in str(data.get("@type", "")).lower() else "audio"
                add_cb(content_url, mtype, "json_ld", title=name, thumb=thumb)
            if embed_url and isinstance(embed_url, str):
                add_cb(embed_url, "video", "json_ld_embed", title=name, thumb=thumb)

            for val in data.values():
                self._extract_from_json(val, add_cb)
        elif isinstance(data, list):
            for item in data:
                self._extract_from_json(item, add_cb)


def download_stream_with_ffmpeg(
    stream_url: str,
    output_path: str,
    referer: str = "",
    timeout_sec: int = 300,
) -> bool:
    """Download HLS/m3u8 or DASH stream and save as standard MP4 via ffmpeg."""
    ffmpeg_bin = shutil.which("ffmpeg")
    if not ffmpeg_bin:
        return False

    headers_str = f"User-Agent: {DEFAULT_USER_AGENT}\r\n"
    if referer:
        headers_str += f"Referer: {referer}\r\n"

    cmd = [
        ffmpeg_bin,
        "-y",
        "-headers", headers_str,
        "-i", stream_url,
        "-c", "copy",
        "-bsf:a", "aac_adtstoasc",
        output_path,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        return proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False
