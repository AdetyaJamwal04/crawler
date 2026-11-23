"""
Media Crawler & Resource Extractor Engine
Crawls any webpage, discovers all embedded media files, streams, and protected links,
and handles anti-hotlink referers, cookies, and HLS/DASH streams.
"""

from __future__ import annotations

import ipaddress
import json
import mimetypes
import os
import re
import shutil
import socket
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

STREAM_MIME_TYPES = {
    "application/vnd.apple.mpegurl",
    "application/x-mpegurl",
    "application/dash+xml",
}

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)

# Block cloud metadata addresses and special restricted IPs
BLOCKED_IP_NETWORKS = [
    ipaddress.ip_network("169.254.169.254/32"),  # AWS/GCP/Azure instance metadata
    ipaddress.ip_network("169.254.0.0/16"),      # IPv4 Link-local
    ipaddress.ip_network("fe80::/10"),           # IPv6 Link-local
    ipaddress.ip_network("0.0.0.0/32"),
]


def is_safe_url(url: str, allow_local: bool = True) -> bool:
    """
    Validate that a URL uses http/https and does not target restricted
    cloud metadata or dangerous internal services.
    """
    try:
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False

        hostname = parsed.hostname
        if not hostname:
            return False

        # Check cloud metadata endpoint directly
        if hostname in ("169.254.169.254", "metadata.google.internal", "instance-data"):
            return False

        # Attempt to resolve IP to check against blocked ranges
        try:
            addr_info = socket.getaddrinfo(hostname, None)
            for item in addr_info:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                for blocked_net in BLOCKED_IP_NETWORKS:
                    if ip_obj in blocked_net:
                        return False
                if not allow_local and (ip_obj.is_loopback or ip_obj.is_private):
                    return False
        except (socket.gaierror, ValueError):
            pass

        return True
    except Exception:
        return False


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

    def __init__(self, timeout: int = 15, allow_local: bool = True):
        self.timeout = timeout
        self.allow_local = allow_local
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
        if not is_safe_url(page_url, allow_local=self.allow_local):
            return {"ok": False, "error": "Invalid or restricted URL scheme/target."}

        parsed = urllib.parse.urlparse(page_url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        req_headers = {"Referer": origin + "/", "Origin": origin}

        try:
            resp = self.session.get(page_url, headers=req_headers, timeout=self.timeout, allow_redirects=True)
        except requests.RequestException as e:
            return {"ok": False, "error": f"Failed to connect to page: {str(e)}"}

        final_url = resp.url
        content_type = resp.headers.get("content-type", "").lower()
        clean_content_type = content_type.split(";")[0].strip()
        parsed_final = urllib.parse.urlparse(final_url)
        final_path_lower = parsed_final.path.lower()

        # If URL directly points to an HLS or DASH stream
        is_direct_stream = (
            any(clean_content_type == sm for sm in STREAM_MIME_TYPES)
            or any(final_path_lower.endswith(ext) for ext in STREAM_EXTS)
        )
        if is_direct_stream:
            ext = os.path.splitext(final_path_lower)[1].lstrip(".") or "m3u8"
            filename = os.path.basename(parsed_final.path) or f"stream.{ext}"
            res = MediaResource(
                url=final_url,
                type="stream",
                format=ext,
                title=filename,
                source_tag="direct_stream_url",
                referer=page_url,
                is_stream=True,
            )
            return {
                "ok": True,
                "page_url": final_url,
                "page_title": filename,
                "count": 1,
                "resources": [res.to_dict()],
            }

        # If URL directly points to a media file, return it as a single discovered resource
        if any(clean_content_type.startswith(prefix) for prefix in ("video/", "audio/", "image/")):
            ext = mimetypes.guess_extension(clean_content_type) or ".media"
            filename = os.path.basename(parsed_final.path) or f"media{ext}"
            content_len = resp.headers.get("content-length")
            size = int(content_len) if content_len and content_len.isdigit() else None
            mtype = "video" if "video" in clean_content_type else "audio" if "audio" in clean_content_type else "image"
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
            base_url: str = "",
        ) -> None:
            if not url or not isinstance(url, str):
                return
            clean_input_url = url.strip()
            if clean_input_url.startswith(("data:", "javascript:", "blob:", "mailto:")):
                return

            # Unescape JS escaped slashes (e.g. https:\/\/...)
            clean_input_url = clean_input_url.replace(r"\/", "/")

            effective_base = base_url if base_url else final_url
            try:
                full_url = urllib.parse.urljoin(effective_base, clean_input_url)
            except Exception:
                return

            if full_url in seen_urls:
                return
            seen_urls.add(full_url)

            # Determine format based on URL path
            parsed_r = urllib.parse.urlparse(full_url)
            path_lower = parsed_r.path.lower()
            ext = os.path.splitext(path_lower)[1]
            fmt = ext.lstrip(".") if ext else mtype

            detected_stream = is_stream or ext in STREAM_EXTS

            if not title:
                base = os.path.basename(parsed_r.path)
                title = urllib.parse.unquote(base) if base else page_title

            discovered.append(MediaResource(
                url=full_url,
                type="stream" if detected_stream else mtype,
                format=fmt,
                title=title,
                source_tag=source_tag,
                referer=effective_base,
                thumbnail=thumb,
                is_stream=detected_stream,
            ))

        # 1. HTML5 <video> elements
        for video in soup.find_all("video"):
            v_src = video.get("src") or video.get("data-src") or video.get("data-url")
            poster = video.get("poster")
            if v_src:
                v_path = urllib.parse.urlparse(v_src).path.lower()
                is_str = any(v_path.endswith(ext) for ext in STREAM_EXTS)
                add_resource(v_src, "stream" if is_str else "video", "video_tag", thumb=poster, is_stream=is_str)
            for source in video.find_all("source"):
                s_src = source.get("src") or source.get("data-src")
                if s_src:
                    s_type = source.get("type", "").lower()
                    s_path = urllib.parse.urlparse(s_src).path.lower()
                    is_hls = "mpegurl" in s_type or "dash+xml" in s_type or any(s_path.endswith(ext) for ext in STREAM_EXTS)
                    mtype = "stream" if is_hls else "video"
                    add_resource(s_src, mtype, "video_source", thumb=poster, is_stream=is_hls)

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
        # Look for inlined .mp4, .m3u8, .mpd, .webm, .mp3 links (handling JS escaped slashes)
        unescaped_html = html_text.replace(r"\/", "/")
        media_regex = re.compile(
            r'https?://[^\s"\'<>]+\.(?:mp4|webm|mkv|m3u8|mpd|mp3|wav|ogg|flac)(?:\?[^\s"\'<>]*)?',
            re.IGNORECASE,
        )
        for match in media_regex.finditer(unescaped_html):
            found_url = match.group(0)
            url_clean_path = urllib.parse.urlparse(found_url).path.lower()
            if any(url_clean_path.endswith(ext) for ext in STREAM_EXTS):
                add_resource(found_url, "stream", "script_regex", is_stream=True)
            elif any(url_clean_path.endswith(ext) for ext in VIDEO_EXTS):
                add_resource(found_url, "video", "script_regex")
            elif any(url_clean_path.endswith(ext) for ext in AUDIO_EXTS):
                add_resource(found_url, "audio", "script_regex")

        # 6. Embedded Player Iframes (resolving relative URLs against iframe source URL)
        if depth > 0:
            for iframe in soup.find_all("iframe"):
                src = iframe.get("src") or iframe.get("data-src")
                if not src:
                    continue
                full_iframe = urllib.parse.urljoin(final_url, src.strip().replace(r"\/", "/"))
                if not is_safe_url(full_iframe, allow_local=self.allow_local):
                    continue
                if any(k in full_iframe.lower() for k in ("embed", "player", "video")):
                    try:
                        iframe_resp = self.session.get(full_iframe, headers={"Referer": final_url}, timeout=6)
                        if iframe_resp.ok:
                            iframe_base = iframe_resp.url
                            iframe_soup = BeautifulSoup(iframe_resp.text, "html.parser")
                            for v in iframe_soup.find_all(["video", "source"]):
                                isrc = v.get("src") or v.get("data-src")
                                if isrc:
                                    add_resource(isrc, "video", "iframe_crawler", base_url=iframe_base)
                            unescaped_iframe_text = iframe_resp.text.replace(r"\/", "/")
                            for match in media_regex.finditer(unescaped_iframe_text):
                                f_url = match.group(0)
                                is_str = any(urllib.parse.urlparse(f_url).path.lower().endswith(e) for e in STREAM_EXTS)
                                add_resource(f_url, "stream" if is_str else "video", "iframe_script_regex", is_stream=is_str, base_url=iframe_base)
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

    # Prevent header injection by stripping newlines
    clean_ua = DEFAULT_USER_AGENT.replace("\r", "").replace("\n", "")
    headers_str = f"User-Agent: {clean_ua}\r\n"
    if referer:
        clean_ref = referer.replace("\r", "").replace("\n", "").strip()
        headers_str += f"Referer: {clean_ref}\r\n"

    # Use -c copy -movflags +faststart without hardcoding -bsf:a aac_adtstoasc
    # so non-AAC audio codecs (MP3, Opus, AC3) do not crash FFmpeg
    cmd = [
        ffmpeg_bin,
        "-y",
        "-headers", headers_str,
        "-i", stream_url,
        "-c", "copy",
        "-movflags", "+faststart",
        output_path,
    ]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec)
        return proc.returncode == 0 and os.path.exists(output_path) and os.path.getsize(output_path) > 0
    except Exception:
        return False
