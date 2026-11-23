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
4. Select the `extension/` directory inside this repository.
5. Pin **MediaFlow** to your browser toolbar.
6. Open any page with video or audio, play the media, and click the MediaFlow icon to download.

---

## 🖥️ Option 2: Local Python Server

### 1. Install Dependencies
```bash
pip install -r requirements.txt
```

### 2. Launch
- **Linux / macOS**:
  ```bash
  chmod +x run.sh
  ./run.sh
  ```
- **Windows (PowerShell)**:
  ```powershell
  .\run.ps1
  ```
- **Windows (Command Prompt)**:
  ```cmd
  run.bat
  ```
- **Direct Python**:
  ```bash
  python server.py 8000
  ```
Open **[http://localhost:8000](http://localhost:8000)** in your browser.

---

## ✨ Features

- **Passive Network Sniffing (Extension)**:
  - Intercepts live media stream requests (`.m3u8`, `.mpd`, `.mp4`, `.mp3`) as they load in your active browser tabs.
  - Automatically updates icon badge counts with detected media.
  - Persists detected media across service worker lifecycles via `chrome.storage.session`.
- **In-Browser HLS Stitcher (Extension)**:
  - Client-side master and media playlist parser (`extension/lib/hls-downloader.js`).
  - Fetches segmented `.m3u8` playlists and chunks concurrently with automatic retries.
  - Supports AES-128 decryption via Web Crypto API.
  - Assembles chunks directly in browser memory into downloadable media files with zero server overhead.
- **Automated Web Media Crawler (`crawler.py`)**:
  - Deep-crawls any URL to discover embedded media that standard downloads can't reach.
  - Inspects HTML5 `<video>`, `<audio>`, and `<source>` tags (with query string awareness).
  - Parses OpenGraph meta tags (`og:video`, `og:audio`, `og:image`, `twitter:player`).
  - Scans JSON-LD metadata (`application/ld+json`) for Schema.org `VideoObject` and `AudioObject`.
  - Mines inlined JavaScript variables and player configs (e.g., VideoJS, JWPlayer, Clappr, Plyr) for `.mp4`, `.webm`, `.m3u8`, `.mpd`, `.mp3` with JS slash unescaping.
  - Inspects embedded `<iframe>` video players with proper origin base URL resolution and parent Referer negotiation.
  - SSRF protection against private network / cloud metadata access.
- **HLS / m3u8 & DASH Stream Muxing (Server)**:
  - Captures segmented streaming manifests (`.m3u8`, `.mpd`).
  - Converts live or VOD chunks into standard, playable `.mp4` video files via integrated FFmpeg copy muxing.
- **Anti-Hotlinking & 403 Bypass Engine**:
  - Maintains persistent `requests.Session()` with authentic browser headers (`Sec-Ch-Ua`, `Sec-Fetch-*`, `Referer`, `Origin`).
  - Automatically fetches host pages to acquire required session cookies and tokens.
  - RFC 6266 / RFC 5987 compliant Content-Disposition handling for international/UTF-8 filenames.
- **Glassmorphic Web UI**:
  - Live preview and progress tracking (MB/s, ETA, transferred MB).
  - Single and batch URL queue modes.
  - Available quality/format selector for platform streams.

---

## 🧪 Testing

Run the test suite covering filename sanitization, UTF-8 header formatting, static assets, crawler extraction, iframe handling, and fallback handling:

```bash
# Using pytest
pytest -v

# Or using Python's built-in unittest runner
python3 -m unittest discover tests -v
```

---

## 📁 Project Architecture

```
crawler/
├── extension/                 # Manifest V3 Browser Extension (Client-Side)
│   ├── manifest.json          # Extension config & permissions
│   ├── background.js          # Service worker: network stream sniffing & session storage
│   ├── content.js             # Injected script: DOM & player inspection
│   ├── lib/
│   │   └── hls-downloader.js  # In-browser chunk downloader, AES decryptor & stitcher
│   ├── popup/
│   │   ├── popup.html         # Extension popup interface
│   │   ├── popup.css          # Dark glassmorphic styling
│   │   └── popup.js           # Media list controller & download triggers (XSS-safe)
│   ├── icons/                 # Extension toolbar icons (16, 48, 128)
│   └── README.md              # Extension standalone guide
├── crawler.py                 # Python web crawler, DOM/JS regex parser & HLS muxer
├── server.py                  # Multi-threaded streaming server, crawler & download API
├── requirements.txt           # Python dependencies
├── LICENSE                    # MIT License
├── run.sh                     # Linux / macOS launcher script
├── run.ps1                    # Windows PowerShell launcher
├── run.bat                    # Windows Batch launcher
├── README.md                  # Project documentation
├── static/
│   ├── index.html             # Web UI with Crawler Discovered Resources card
│   ├── style.css              # Glassmorphic dark theme stylesheet
│   └── app.js                 # Client controller & stream reader
└── tests/
    ├── test_server.py         # Pytest & unittest server test suite
    └── test_crawler.py        # Crawler & extraction test suite
```

---

## 📄 License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

