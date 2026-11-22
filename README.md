# MediaFlow — Universal Media Downloader & Web Crawler

A powerful media crawler and streaming downloader that runs in your browser. It accepts any webpage or media link, crawls the page to uncover all embedded videos, audios, HLS/m3u8 streams, and high-res images, and downloads them directly to your device no matter how protected or obscured they are.

---

## ✨ Features

- **Automated Web Media Crawler (`crawler.py`)**:
  - Deep-crawls any URL to discover embedded media that standard downloads can't reach.
  - Inspects HTML5 `<video>`, `<audio>`, and `<source>` tags.
  - Parses OpenGraph meta tags (`og:video`, `og:audio`, `og:image`, `twitter:player`).
  - Scans JSON-LD metadata (`application/ld+json`) for Schema.org `VideoObject` and `AudioObject`.
  - Mines inlined JavaScript variables and player configs (e.g., VideoJS, JWPlayer, Clappr, Plyr) for `.mp4`, `.webm`, `.m3u8`, `.mpd`, `.mp3`.
  - Inspects embedded `<iframe>` video players with parent Referer negotiation.
- **HLS / m3u8 & DASH Stream Muxing**:
  - Automatically captures segmented streaming manifests (`.m3u8`, `.mpd`).
  - Converts live or VOD chunks into standard, playable `.mp4` video files via integrated FFmpeg copy muxing.
- **Anti-Hotlinking & 403 Bypass Engine**:
  - Maintains persistent `requests.Session()` with authentic browser headers (`Sec-Ch-Ua`, `Sec-Fetch-*`, `Referer`, `Origin`).
  - Automatically fetches the host page first to acquire required session cookies and tokens.
  - Delivers files directly to the browser with `Content-Disposition: attachment` headers, bypassing browser CORS restrictions.
- **Browser User Interface**:
  - **"🕷️ Crawl Page for Media" Button**: Analyzes any webpage and displays a filterable card listing all found media files with titles, source tags, and one-click download buttons.
  - **Single & Batch Modes**: Queue multiple links or download all discovered videos with one click.
  - **Live Preview & Tracking**: In-browser video/audio player preview, real-time download progress bar (MB/s, ETA, transferred MB).

---

## 🚀 Quick Start

### 1. Launch with PowerShell or Batch
- Double click or execute:
  ```powershell
  .\run.ps1
  ```
  *(or `run.bat` on Command Prompt)*

### 2. Or Run Directly with Python
```powershell
.\.venv\Scripts\python.exe server.py 8000
```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## 🧪 Testing

Run the test suite covering filename sanitization, header parsing, static assets, crawler extraction, and 403 fallback handling:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## 📁 Project Architecture

```
crawler/
├── crawler.py             # Web crawler, DOM/JS regex parser & HLS ffmpeg muxer
├── server.py              # Multi-threaded streaming server, crawler & download API
├── run.ps1                # PowerShell launcher (auto-launches browser)
├── run.bat                # Windows Batch launcher
├── README.md              # Documentation
├── static/
│   ├── index.html         # Web UI with Crawler Discovered Resources card
│   ├── style.css          # Glassmorphic dark theme stylesheet
│   └── app.js             # Client controller, crawler triggers & stream reader
└── tests/
    └── test_server.py     # Pytest automated test suite (17 tests)
```
