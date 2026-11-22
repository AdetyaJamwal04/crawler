"""
Media Downloader Web Application - Local Streaming Server
Provides static file serving and API endpoints for inspecting and downloading media.
"""

from __future__ import annotations

import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import urllib.parse
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import requests

from crawler import MediaCrawler, download_stream_with_ffmpeg, STREAM_EXTS

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"

# Chunk size for streaming media (64KB)
CHUNK_SIZE = 65536

# Common media MIME types mapping
EXTRA_MIME_TYPES = {
    ".mp4": "video/mp4",
    ".mkv": "video/x-matroska",
    ".webm": "video/webm",
    ".mov": "video/quicktime",
    ".avi": "video/x-msvideo",
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".m4a": "audio/mp4",
    ".aac": "audio/aac",
    ".opus": "audio/opus",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".svg": "image/svg+xml",
    ".bmp": "image/bmp",
}

for ext, mime in EXTRA_MIME_TYPES.items():
    mimetypes.add_type(mime, ext)


def sanitize_filename(name: str) -> str:
    """Sanitize a filename for safe download headers and filesystem safety."""
    if not name:
        return "downloaded_media"
    # If query or fragment is appended after an extension (e.g. video.mp4?token=123), strip it
    name = re.sub(r'(\.[a-zA-Z0-9]{2,5})\?.*$', r'\1', name)
    name = re.sub(r'(\.[a-zA-Z0-9]{2,5})#.*$', r'\1', name)
    # Replace illegal filesystem and header characters: <>:"/\|?*
    clean = re.sub(r'[<>:"/\\|?*\x00-\x1f]', "_", name).strip()
    # Strip leading/trailing dots or spaces
    clean = clean.strip(". ")
    if not clean:
        clean = "downloaded_media"
    return clean[:200]


def extract_filename_from_headers_or_url(url: str, headers: Dict[str, str]) -> str:
    """Extract or deduce appropriate filename from HTTP headers or URL."""
    # 1. Check Content-Disposition
    cd = headers.get("content-disposition", "")
    if cd:
        # Check filename* (RFC 5987 / 6266)
        match_star = re.search(r"filename\*\s*=\s*(?:UTF-8''|utf-8'')([^;]+)", cd, re.IGNORECASE)
        if match_star:
            raw_name = urllib.parse.unquote(match_star.group(1).strip("\"'"))
            return sanitize_filename(raw_name)
        # Check standard filename=
        match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', cd, re.IGNORECASE)
        if match:
            raw_name = match.group(1) or match.group(2)
            return sanitize_filename(raw_name.strip("\"'"))

    # 2. Try URL path
    parsed = urllib.parse.urlparse(url)
    path = parsed.path
    if path:
        base = os.path.basename(path.rstrip("/"))
        if base and "." in base:
            return sanitize_filename(urllib.parse.unquote(base))

    # 3. Fallback based on content-type
    content_type = headers.get("content-type", "").split(";")[0].strip().lower()
    ext = mimetypes.guess_extension(content_type) or ""
    if not ext:
        if "video" in content_type:
            ext = ".mp4"
        elif "audio" in content_type:
            ext = ".mp3"
        elif "image" in content_type:
            ext = ".jpg"
        else:
            ext = ".bin"

    fallback_base = sanitize_filename(os.path.basename(path.rstrip("/")) or "media_file")
    if not fallback_base.endswith(ext):
        fallback_base += ext
    return fallback_base


def inspect_media_url(url: str, timeout: int = 10) -> Dict[str, Any]:
    """Inspect a media URL using HEAD or partial GET request to extract metadata."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return {"ok": False, "error": "Invalid URL scheme. Only HTTP and HTTPS are supported."}

    origin = f"{parsed.scheme}://{parsed.netloc}"
    req_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept": "*/*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": origin + "/",
        "Origin": origin,
    }

    try:
        # Try HEAD first
        resp = requests.head(url, headers=req_headers, allow_redirects=True, timeout=timeout)
        # Some servers return 405 Method Not Allowed or 403 for HEAD
        if resp.status_code >= 400:
            # Fallback to GET with Range 0-0
            range_headers = dict(req_headers)
            range_headers["Range"] = "bytes=0-0"
            resp = requests.get(url, headers=range_headers, stream=True, allow_redirects=True, timeout=timeout)
            resp.close()

        final_url = resp.url
        headers = {k.lower(): v for k, v in resp.headers.items()}
        content_type = headers.get("content-type", "application/octet-stream").split(";")[0].strip()

        # If HTTP error (like 403 Forbidden) or HTML page, check candidate referers first
        if resp.status_code >= 400 or content_type.startswith("text/html"):
            candidate_referers = []
            if "pvtcdn.com" in parsed.netloc:
                candidate_referers.append("https://vid65.net/")

            for cand_ref in candidate_referers:
                cand_headers = dict(req_headers)
                cand_headers["Referer"] = cand_ref
                cand_headers["Origin"] = cand_ref.rstrip("/")
                try:
                    r_cand = requests.head(url, headers=cand_headers, allow_redirects=True, timeout=timeout)
                    if r_cand.status_code == 200:
                        resp = r_cand
                        final_url = resp.url
                        headers = {k.lower(): v for k, v in resp.headers.items()}
                        content_type = headers.get("content-type", "application/octet-stream").split(";")[0].strip()
                        break
                except Exception:
                    pass

        # If still error, check if yt-dlp can extract platform media
        if resp.status_code >= 400 or content_type.startswith("text/html"):
            if check_yt_dlp_available():
                platform_info = extract_platform_media(url)
                if platform_info.get("ok"):
                    return platform_info

            # If yt-dlp couldn't extract or not available, return error
            if resp.status_code >= 400:
                reason = getattr(resp, "reason", "") or "Forbidden / Not Found"
                return {"ok": False, "error": f"Remote host returned HTTP {resp.status_code}: {reason}"}

        content_length = headers.get("content-length")

        # If partial content, parse Content-Range for full size
        if "content-range" in headers:
            range_match = re.search(r"/(\d+|\*)", headers["content-range"])
            if range_match and range_match.group(1) != "*":
                content_length = int(range_match.group(1))

        size_bytes = int(content_length) if content_length and str(content_length).isdigit() else None
        filename = extract_filename_from_headers_or_url(final_url, headers)

        is_media = (
            content_type.startswith("video/")
            or content_type.startswith("audio/")
            or content_type.startswith("image/")
            or content_type in ("application/ogg", "application/vnd.apple.mpegurl")
            or any(filename.lower().endswith(ext) for ext in EXTRA_MIME_TYPES)
        )

        return {
            "ok": True,
            "url": final_url,
            "filename": filename,
            "content_type": content_type,
            "size_bytes": size_bytes,
            "is_media": is_media,
            "accept_ranges": "bytes" in headers.get("accept-ranges", "").lower(),
        }
    except requests.RequestException as e:
        if check_yt_dlp_available():
            platform_info = extract_platform_media(url)
            if platform_info.get("ok"):
                return platform_info
        return {"ok": False, "error": f"Failed to connect to media host: {str(e)}"}


def get_ytdlp_bin() -> Optional[str]:
    """Get the path to the best available yt-dlp binary (preferring project venv)."""
    local_ytdlp = BASE_DIR / ".venv" / "Scripts" / "yt-dlp.exe"
    if local_ytdlp.is_file():
        return str(local_ytdlp)
    local_ytdlp_nix = BASE_DIR / ".venv" / "bin" / "yt-dlp"
    if local_ytdlp_nix.is_file():
        return str(local_ytdlp_nix)
    return shutil.which("yt-dlp")


def check_yt_dlp_available() -> bool:
    """Check if yt-dlp is available in PATH or project venv."""
    return get_ytdlp_bin() is not None


def extract_platform_media(url: str) -> Dict[str, Any]:
    """Use yt-dlp to inspect or extract media formats from media platforms."""
    ytdlp_bin = get_ytdlp_bin()
    if not ytdlp_bin:
        return {"ok": False, "error": "yt-dlp is not installed on the system."}

    cmd = [
        ytdlp_bin,
        "--dump-single-json",
        "--no-playlist",
        "--no-warnings",
        "--no-update",
        "--skip-download",
        url,
    ]
    if shutil.which("node"):
        cmd.extend(["--js-runtimes", "node"])

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=35)
        if result.returncode != 0:
            err = result.stderr.strip() or "Failed to extract media information from this URL."
            return {"ok": False, "error": err}

        info = json.loads(result.stdout)
        title = info.get("title", "media")
        ext = info.get("ext", "mp4")
        duration = info.get("duration")
        thumbnail = info.get("thumbnail")
        formats = []

        # Find best direct video/audio download link if available
        direct_url = info.get("url")

        # Pick simplified clean format options
        raw_formats = info.get("formats", [])
        for f in raw_formats:
            f_url = f.get("url")
            if not f_url:
                continue
            vcodec = f.get("vcodec", "none")
            acodec = f.get("acodec", "none")
            f_note = f.get("format_note") or f.get("resolution") or ""
            f_ext = f.get("ext", "")
            f_size = f.get("filesize") or f.get("filesize_approx")
            has_video = vcodec != "none"
            has_audio = acodec != "none"

            formats.append({
                "format_id": f.get("format_id"),
                "format_note": f_note,
                "ext": f_ext,
                "has_video": has_video,
                "has_audio": has_audio,
                "direct_url": f_url,
                "filesize": f_size,
            })

        return {
            "ok": True,
            "title": title,
            "filename": sanitize_filename(f"{title}.{ext}"),
            "ext": ext,
            "duration": duration,
            "thumbnail": thumbnail,
            "direct_url": direct_url,
            "formats": formats[:15],  # top 15 formats
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "Extraction timed out after 35 seconds."}
    except Exception as e:
        return {"ok": False, "error": f"Extraction error: {str(e)}"}


class MediaServerHandler(BaseHTTPRequestHandler):
    """HTTP Request Handler serving static frontend assets and API endpoints."""

    def send_json(self, data: Any, status: int = 200) -> None:
        """Send a JSON HTTP response with proper headers."""
        body = json.dumps(data).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.end_headers()
        self.wfile.write(body)

    def do_OPTIONS(self) -> None:
        """Handle CORS pre-flight requests."""
        self.send_response(HTTPStatus.NO_CONTENT)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Range")
        self.end_headers()

    def do_GET(self) -> None:
        """Handle HTTP GET requests."""
        parsed_url = urllib.parse.urlparse(self.path)
        path = parsed_url.path
        query = urllib.parse.parse_qs(parsed_url.query)

        # 1. API: Healthcheck
        if path == "/api/health":
            self.send_json({"status": "ok", "yt_dlp": check_yt_dlp_available()})
            return

        # 2. API: Crawl Page for Media Resources
        if path == "/api/crawl":
            url = query.get("url", [""])[0].strip()
            if not url:
                self.send_json({"ok": False, "error": "Missing 'url' query parameter."}, 400)
                return
            crawler = MediaCrawler()
            result = crawler.crawl(url)
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        # 3. API: Inspect URL
        if path == "/api/inspect":
            url = query.get("url", [""])[0].strip()
            if not url:
                self.send_json({"ok": False, "error": "Missing 'url' query parameter."}, 400)
                return
            result = inspect_media_url(url)
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        # 3. API: Platform Extraction (yt-dlp)
        if path == "/api/extract":
            url = query.get("url", [""])[0].strip()
            if not url:
                self.send_json({"ok": False, "error": "Missing 'url' query parameter."}, 400)
                return
            result = extract_platform_media(url)
            self.send_json(result, 200 if result.get("ok") else 400)
            return

        # 4. API: Stream Download
        if path == "/api/download":
            url = query.get("url", [""])[0].strip()
            custom_name = query.get("name", [""])[0].strip()
            referer = query.get("referer", [""])[0].strip()
            if not url:
                self.send_json({"ok": False, "error": "Missing 'url' query parameter."}, 400)
                return
            self.stream_download(url, custom_name, referer)
            return

        # 5. Static Files Serving
        self.serve_static(path)

    def serve_static(self, path: str) -> None:
        """Serve files from the static directory safely."""
        if path in ("", "/"):
            req_file = "index.html"
        else:
            req_file = path.lstrip("/")

        target_file = (STATIC_DIR / req_file).resolve()

        # Prevent directory traversal
        try:
            target_file.relative_to(STATIC_DIR.resolve())
        except ValueError:
            self.send_error(HTTPStatus.FORBIDDEN, "Access denied")
            return

        if not target_file.is_file():
            # If not found and looking for root/html, default to index.html
            target_file = STATIC_DIR / "index.html"
            if not target_file.is_file():
                self.send_error(HTTPStatus.NOT_FOUND, "File not found")
                return

        mime_type, _ = mimetypes.guess_type(str(target_file))
        if not mime_type:
            mime_type = "application/octet-stream"

        try:
            content = target_file.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", f"{mime_type}; charset=utf-8" if "text" in mime_type or "javascript" in mime_type else mime_type)
            self.send_header("Content-Length", str(len(content)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(HTTPStatus.INTERNAL_SERVER_ERROR, f"Error reading file: {str(e)}")

    def stream_ffmpeg(self, stream_url: str, custom_name: str = "", referer: str = "") -> bool:
        """Download and remux an m3u8/mpd stream to MP4 via ffmpeg, streaming to client."""
        import tempfile
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                tmp_mp4 = os.path.join(tmpdir, "stream_output.mp4")
                ok = download_stream_with_ffmpeg(stream_url, tmp_mp4, referer=referer)
                if not ok or not os.path.exists(tmp_mp4):
                    return False

                file_size = os.path.getsize(tmp_mp4)
                filename = sanitize_filename(custom_name) if custom_name else "streamed_video.mp4"
                if not filename.endswith(".mp4"):
                    filename += ".mp4"

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", "video/mp4")
                self.send_header("Content-Length", str(file_size))
                encoded_filename = urllib.parse.quote(filename)
                disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}'
                self.send_header("Content-Disposition", disposition)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")
                self.end_headers()

                with open(tmp_mp4, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            break

                return True
        except Exception:
            return False

    def crawl_and_stream(self, page_url: str, custom_name: str = "") -> bool:
        """Crawl the webpage, uncover embedded media resources, and stream the best candidate."""
        try:
            crawler = MediaCrawler()
            crawl_res = crawler.crawl(page_url)
            if not crawl_res.get("ok") or not crawl_res.get("resources"):
                return False

            resources = crawl_res["resources"]
            # Look for video or stream first
            media_candidates = [r for r in resources if r.get("type") in ("video", "stream", "audio")]
            if not media_candidates:
                media_candidates = resources

            for cand in media_candidates:
                cand_url = cand["url"]
                cand_ref = cand.get("referer") or page_url
                cand_title = cand.get("title") or custom_name

                # If it's an HLS / DASH stream
                if cand.get("is_stream") or any(cand_url.lower().endswith(ext) for ext in (".m3u8", ".mpd")):
                    if self.stream_ffmpeg(cand_url, custom_name=cand_title, referer=cand_ref):
                        return True

                # If it's a direct media link, stream with the crawler's session & referer
                try:
                    headers = dict(crawler.session.headers)
                    headers["Referer"] = cand_ref
                    parsed_c = urllib.parse.urlparse(cand_url)
                    headers["Origin"] = f"{parsed_c.scheme}://{parsed_c.netloc}"

                    with crawler.session.get(cand_url, headers=headers, stream=True, timeout=20) as r:
                        if r.status_code == 200:
                            content_type = r.headers.get("content-type", "application/octet-stream")
                            if not content_type.startswith("text/html"):
                                self.send_response(HTTPStatus.OK)
                                self.send_header("Content-Type", content_type)
                                if "content-length" in r.headers:
                                    self.send_header("Content-Length", r.headers["content-length"])
                                fn = sanitize_filename(cand_title) or "downloaded_media"
                                disposition = f'attachment; filename="{fn}"; filename*=UTF-8\'\'{urllib.parse.quote(fn)}'
                                self.send_header("Content-Disposition", disposition)
                                self.send_header("Access-Control-Allow-Origin", "*")
                                self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")
                                self.end_headers()
                                for chunk in r.iter_content(chunk_size=CHUNK_SIZE):
                                    if chunk:
                                        try:
                                            self.wfile.write(chunk)
                                        except (BrokenPipeError, ConnectionResetError):
                                            break
                                return True
                except Exception:
                    continue

            return False
        except Exception:
            return False

    def stream_via_ytdlp(self, url: str, custom_name: str = "") -> bool:
        """Stream media using yt-dlp to handle platform links, signed tokens, or anti-hotlinking."""
        ytdlp_bin = get_ytdlp_bin()
        if not ytdlp_bin:
            return False

        import tempfile
        try:
            with tempfile.TemporaryDirectory() as tmpdir:
                out_tmpl = os.path.join(tmpdir, "%(title)s.%(ext)s")
                cmd = [
                    ytdlp_bin,
                    "--no-playlist",
                    "--no-warnings",
                    "--no-update",
                    "-f", "b/bv*+ba/b",
                    "-o", out_tmpl,
                    url,
                ]
                if shutil.which("node"):
                    cmd.extend(["--js-runtimes", "node"])

                result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
                if result.returncode != 0:
                    return False

                files = os.listdir(tmpdir)
                if not files:
                    return False

                downloaded_file = os.path.join(tmpdir, files[0])
                file_size = os.path.getsize(downloaded_file)
                ext = os.path.splitext(downloaded_file)[1].lower()
                content_type = EXTRA_MIME_TYPES.get(ext) or mimetypes.guess_type(downloaded_file)[0] or "application/octet-stream"

                filename = sanitize_filename(custom_name) if custom_name else sanitize_filename(files[0])
                if not os.path.splitext(filename)[1] and ext:
                    filename += ext

                self.send_response(HTTPStatus.OK)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(file_size))
                encoded_filename = urllib.parse.quote(filename)
                disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}'
                self.send_header("Content-Disposition", disposition)
                self.send_header("Access-Control-Allow-Origin", "*")
                self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length")
                self.end_headers()

                with open(downloaded_file, "rb") as f:
                    while True:
                        chunk = f.read(CHUNK_SIZE)
                        if not chunk:
                            break
                        try:
                            self.wfile.write(chunk)
                        except (BrokenPipeError, ConnectionResetError):
                            break

                return True
        except Exception:
            return False

    def _stream_response(self, upstream: requests.Response, custom_name: str = "") -> None:
        """Stream an active requests response to client with attachment headers."""
        headers = {k.lower(): v for k, v in upstream.headers.items()}
        content_type = headers.get("content-type", "application/octet-stream")
        content_length = headers.get("content-length")

        if custom_name:
            filename = sanitize_filename(custom_name)
        else:
            filename = extract_filename_from_headers_or_url(upstream.url, headers)

        status_code = HTTPStatus.PARTIAL_CONTENT if upstream.status_code == 206 else HTTPStatus.OK
        self.send_response(status_code)
        self.send_header("Content-Type", content_type)
        if content_length:
            self.send_header("Content-Length", content_length)

        if "content-range" in headers:
            self.send_header("Content-Range", headers["content-range"])
        if "accept-ranges" in headers:
            self.send_header("Accept-Ranges", headers["accept-ranges"])

        encoded_filename = urllib.parse.quote(filename)
        disposition = f'attachment; filename="{filename}"; filename*=UTF-8\'\'{encoded_filename}'
        self.send_header("Content-Disposition", disposition)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Expose-Headers", "Content-Disposition, Content-Length, Content-Range")
        self.end_headers()

        for chunk in upstream.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                try:
                    self.wfile.write(chunk)
                except (BrokenPipeError, ConnectionResetError):
                    break

    def stream_download(self, url: str, custom_name: str = "", referer: str = "") -> None:
        """Stream remote media file directly to client with attachment header."""
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme not in ("http", "https"):
            self.send_json({"ok": False, "error": "Invalid URL scheme"}, 400)
            return

        # Check if URL is an HLS or DASH stream
        path_lower = parsed.path.lower()
        if any(path_lower.endswith(ext) for ext in (".m3u8", ".mpd")) or ".m3u8?" in url.lower():
            if self.stream_ffmpeg(url, custom_name=custom_name, referer=referer):
                return

        origin = f"{parsed.scheme}://{parsed.netloc}"
        req_headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Accept": "*/*",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": referer if referer else (origin + "/"),
            "Origin": origin,
            "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
            "Sec-Ch-Ua-Mobile": "?0",
            "Sec-Ch-Ua-Platform": '"Windows"',
            "Sec-Fetch-Dest": "video",
            "Sec-Fetch-Mode": "no-cors",
            "Sec-Fetch-Site": "cross-site",
        }

        # Forward client Range header if requested (for resume/seeking)
        client_range = self.headers.get("Range")
        if client_range:
            req_headers["Range"] = client_range

        try:
            with requests.get(url, headers=req_headers, stream=True, timeout=20) as upstream:
                content_type = upstream.headers.get("content-type", "").lower()

                # If upstream returned error (e.g. 403 Forbidden) or HTML, activate fallbacks
                if upstream.status_code >= 400 or content_type.startswith("text/html"):
                    # 1. Try candidate referers for CDNs requiring specific origin
                    candidate_referers = []
                    if not referer and "pvtcdn.com" in parsed.netloc:
                        candidate_referers.append("https://vid65.net/")

                    for cand_ref in candidate_referers:
                        cand_headers = dict(req_headers)
                        cand_headers["Referer"] = cand_ref
                        cand_headers["Origin"] = cand_ref.rstrip("/")
                        try:
                            cand_resp = requests.get(url, headers=cand_headers, stream=True, timeout=20)
                            if cand_resp.status_code == 200 and not cand_resp.headers.get("content-type", "").startswith("text/html"):
                                self._stream_response(cand_resp, custom_name)
                                return
                        except Exception:
                            pass

                    # 2. Try crawler to extract media from the page / parent
                    if self.crawl_and_stream(url, custom_name):
                        return

                    # 3. Try yt-dlp fallback
                    if check_yt_dlp_available() and self.stream_via_ytdlp(url, custom_name):
                        return

                    self.send_json({
                        "ok": False,
                        "error": f"Upstream media host returned status code {upstream.status_code}. The media link may be protected or expired.",
                    }, upstream.status_code)
                    return

                self._stream_response(upstream, custom_name)

        except requests.RequestException as e:
            if self.crawl_and_stream(url, custom_name):
                return
            if check_yt_dlp_available() and self.stream_via_ytdlp(url, custom_name):
                return
            try:
                self.send_json({"ok": False, "error": f"Stream error: {str(e)}"}, 502)
            except Exception:
                pass


def run_server(port: int = 8000, host: str = "127.0.0.1") -> None:
    """Start the media downloader server."""
    server_address = (host, port)
    httpd = ThreadingHTTPServer(server_address, MediaServerHandler)
    print(f"🚀 Media Downloader running at http://{host}:{port}/")
    print("Press Ctrl+C to stop the server.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping server...")
    finally:
        httpd.server_close()


if __name__ == "__main__":
    port = 8000
    if len(sys.argv) > 1 and sys.argv[1].isdigit():
        port = int(sys.argv[1])
    run_server(port=port)
