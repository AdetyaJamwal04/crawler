# MediaFlow — Universal Media Downloader, Web Crawler & Browser Extension

A powerful media crawler, streaming downloader, and browser extension. It accepts any webpage or media link, sniffs and crawls to uncover all embedded videos, audios, HLS/m3u8 streams, and high-res images, and downloads them directly to your device no matter how protected or obscured they are.

---

## ⚡ Two Ways to Run

MediaFlow can be used in two modes:
1. **Browser Extension (Manifest V3)**: 100% client-side, zero installation of Python or FFmpeg required, runs in Chrome / Edge / Brave with $0 server cost.
2. **Local Python Server**: Full-stack backend crawler with native FFmpeg HLS muxing and `yt-dlp` fallback engine.

---

## 🧩 Option 1: Browser Extension (Quickest Setup)

Runs directly in your browser with passive media network sniffing and in-browser HLS (.m3u8) stream segment stitching.

### Installation in Chrome / Edge / Brave
1. Open your browser and navigate to:
   - Chrome: `chrome://extensions/`
   - Edge: `edge://extensions/`
   - Brave: `brave://extensions/`
2. Toggle **Developer mode** to **ON** (top-right corner).
3. Click **Load unpacked** (top-left).
4. Select the `extension/` directory inside this repository:
   ```
   C:\Users\Adetya\Desktop\crawler\extension
   ```
5. Pin **MediaFlow** to your browser toolbar.
6. Open any page with video or audio, play the media, and click the MediaFlow icon to download.

---

## 🖥️ Option 2: Local Python Server

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

## ✨ Features

- **Passive Network Sniffing (Extension)**:
  - Intercepts live media stream requests (`.m3u8`, `.mpd`, `.mp4`, `.mp3`) as they load in your active browser tabs.
  - Automatically updates icon badge counts with detected media.
- **In-Browser HLS Stitcher (Extension)**:
  - Fetches segmented `.m3u8` playlists and chunks concurrently.
  - Assembles chunks directly in browser memory into downloadable media files with zero server overhead.
- **Automated Web Media Crawler (`crawler.py`)**:
  - Deep-crawls any URL to discover embedded media that standard downloads can't reach.
  - Inspects HTML5 `<video>`, `<audio>`, and `<source>` tags.
  - Parses OpenGraph meta tags (`og:video`, `og:audio`, `og:image`, `twitter:player`).
  - Scans JSON-LD metadata (`application/ld+json`) for Schema.org `VideoObject` and `AudioObject`.
  - Mines inlined JavaScript variables and player configs (e.g., VideoJS, JWPlayer, Clappr, Plyr) for `.mp4`, `.webm`, `.m3u8`, `.mpd`, `.mp3`.
  - Inspects embedded `<iframe>` video players with parent Referer negotiation.
- **HLS / m3u8 & DASH Stream Muxing (Server)**:
  - Captures segmented streaming manifests (`.m3u8`, `.mpd`).
  - Converts live or VOD chunks into standard, playable `.mp4` video files via integrated FFmpeg copy muxing.
- **Anti-Hotlinking & 403 Bypass Engine**:
  - Maintains persistent `requests.Session()` with authentic browser headers (`Sec-Ch-Ua`, `Sec-Fetch-*`, `Referer`, `Origin`).
  - Automatically fetches host pages to acquire required session cookies and tokens.
- **Glassmorphic Web UI**:
  - Live preview and progress tracking (MB/s, ETA, transferred MB).
  - Single and batch URL queue modes.

---

## 🧪 Testing

Run the test suite covering filename sanitization, header parsing, static assets, crawler extraction, and fallback handling:
```powershell
.\.venv\Scripts\python.exe -m pytest -v
```

---

## 📁 Project Architecture

```
crawler/
├── extension/                 # Manifest V3 Browser Extension (Client-Side)
│   ├── manifest.json          # Extension config & permissions
│   ├── background.js          # Service worker: network stream sniffing
│   ├── content.js             # Injected script: DOM & player inspection
│   ├── lib/
│   │   └── hls-downloader.js  # In-browser chunk downloader & stitcher
│   ├── popup/
│   │   ├── popup.html         # Extension popup interface
│   │   ├── popup.css          # Dark glassmorphic styling
│   │   └── popup.js           # Media list controller & download triggers
│   ├── icons/                 # Extension toolbar icons (16, 48, 128)
│   └── README.md              # Extension standalone guide
├── crawler.py                 # Python web crawler, DOM/JS regex parser & HLS muxer
├── server.py                  # Multi-threaded streaming server, crawler & download API
├── run.ps1                    # PowerShell launcher
├── run.bat                    # Windows Batch launcher
├── README.md                  # Project documentation
├── static/
│   ├── index.html             # Web UI with Crawler Discovered Resources card
│   ├── style.css              # Glassmorphic dark theme stylesheet
│   └── app.js                 # Client controller & stream reader
└── tests/
    └── test_server.py         # Pytest automated test suite
```
