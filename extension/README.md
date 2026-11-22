# MediaFlow Browser Extension (Manifest V3)

A fast, zero-server browser extension that sniffs and downloads media (MP4, WebM, MP3, HLS `.m3u8` streams) directly inside Chrome, Edge, and Brave.

---

## ✨ Features
- **Passive Network Sniffing**: Sniffs video/audio requests (`.mp4`, `.webm`, `.m3u8`, `.mpd`, `.mp3`) directly as pages load.
- **Active DOM & Player Inspector**: Scans `<video>`, `<audio>`, `<source>`, OpenGraph tags, JSON-LD, and embedded player configs.
- **In-Browser HLS Stitcher**: Sequentially downloads `.m3u8` segment chunks with concurrency and stitches them into a `.ts` file entirely in memory with no backend server.
- **$0 Hosting**: Runs 100% locally in the browser with zero cloud costs or infrastructure maintenance.

---

## 🚀 How to Load in Chrome / Edge / Brave

1. Open **Chrome** and navigate to:
   ```
   chrome://extensions/
   ```
   *(or `edge://extensions/` in Microsoft Edge)*
2. In the top-right corner, toggle **Developer mode** to **ON**.
3. Click the **"Load unpacked"** button in the top-left.
4. Select the `extension` folder located inside this project:
   ```
   C:\Users\Adetya\Desktop\crawler\extension
   ```
5. Click **Select Folder**.
6. Pin **MediaFlow** to your browser toolbar!

---

## 💡 How to Use
1. Navigate to any webpage with video or audio (e.g., news, streaming, or media sites).
2. Play the media. The extension badge icon will update with the count of detected streams.
3. Click the MediaFlow extension icon:
   - Preview discovered streams.
   - Click **Download** to save standard video/audio or stream `.m3u8` directly.
   - Use **Copy Link** to share or inspect raw URLs.
