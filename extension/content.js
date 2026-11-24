/**
 * MediaFlow - Content Script
 * Injected into active pages to scan DOM (<video>, <audio>, <source>, OpenGraph, JSON-LD)
 * and player configurations for embedded streams.
 */

(function () {
  "use strict";

  function scanDOMMedia() {
    const found = [];
    const seenUrls = new Set();

    function isHtmlOrPageUrl(url) {
      if (!url) return true;
      const lower = url.toLowerCase();
      // Filter out iframe embed player pages, html document pages, or non-media URLs
      if (
        lower.includes("youtube.com/embed/") ||
        lower.includes("youtube.com/v/") ||
        lower.includes("youtube.com/watch") ||
        lower.includes("player.vimeo.com/video/")
      ) {
        return true;
      }
      return false;
    }

    function addCandidate(url, type, format, title, source) {
      if (!url || typeof url !== "string") return;
      url = url.trim();
      if (!url || url.startsWith("blob:") || url.startsWith("data:") || url.startsWith("javascript:")) return;

      try {
        // Resolve relative URLs
        url = new URL(url, window.location.href).href;
      } catch (e) {
        return;
      }

      if (isHtmlOrPageUrl(url)) return;
      if (seenUrls.has(url)) return;
      seenUrls.add(url);

      found.push({
        url: url,
        title: title || document.title || "media",
        type: type,
        format: format,
        source: source
      });
    }

    // 1. HTML5 <video> elements
    document.querySelectorAll("video").forEach((vid) => {
      if (vid.src) {
        addCandidate(vid.src, "video", "MP4/Video", vid.title || "HTML5 Video", "DOM Video Tag");
      }
      if (vid.currentSrc && vid.currentSrc !== vid.src) {
        addCandidate(vid.currentSrc, "video", "MP4/Video", vid.title || "Active Video Stream", "DOM CurrentSrc");
      }
      vid.querySelectorAll("source").forEach((src) => {
        if (src.src) {
          const typeAttr = src.type || "";
          const fmt = typeAttr.includes("mpegurl") ? "HLS (.m3u8)" : (typeAttr.split("/")[1] || "Video").toUpperCase();
          addCandidate(src.src, "video", fmt, "Video Source", "DOM Source Tag");
        }
      });
    });

    // 2. HTML5 <audio> elements
    document.querySelectorAll("audio").forEach((aud) => {
      if (aud.src) {
        addCandidate(aud.src, "audio", "Audio", aud.title || "HTML5 Audio", "DOM Audio Tag");
      }
      aud.querySelectorAll("source").forEach((src) => {
        if (src.src) {
          addCandidate(src.src, "audio", "Audio", "Audio Source", "DOM Audio Source");
        }
      });
    });

    // 3. OpenGraph / Twitter meta tags (only if pointing to actual media files)
    document.querySelectorAll('meta[property="og:video"], meta[property="og:video:url"], meta[property="og:video:secure_url"], meta[name="twitter:player:stream"]').forEach((m) => {
      if (m.content && !isHtmlOrPageUrl(m.content)) {
        addCandidate(m.content, "video", "MP4/Video", document.title, "OpenGraph Meta");
      }
    });
    document.querySelectorAll('meta[property="og:audio"], meta[property="og:audio:secure_url"]').forEach((m) => {
      if (m.content && !isHtmlOrPageUrl(m.content)) {
        addCandidate(m.content, "audio", "Audio", document.title, "OpenGraph Meta");
      }
    });

    // 4. JSON-LD Structured Data
    document.querySelectorAll('script[type="application/ld+json"]').forEach((script) => {
      try {
        const data = JSON.parse(script.textContent);
        const scanObj = (obj) => {
          if (!obj || typeof obj !== "object") return;
          if (obj["@type"] === "VideoObject" || obj.contentUrl || obj.embedUrl) {
            if (obj.contentUrl && !isHtmlOrPageUrl(obj.contentUrl)) {
              addCandidate(obj.contentUrl, "video", "Video", obj.name || document.title, "JSON-LD");
            }
            // Only add embedUrl if it directly points to a media stream or video container, not a full HTML page
            if (obj.embedUrl && !isHtmlOrPageUrl(obj.embedUrl)) {
              addCandidate(obj.embedUrl, "video", "Stream", obj.name || document.title, "JSON-LD Embed");
            }
          }
          for (const k in obj) {
            if (typeof obj[k] === "object") scanObj(obj[k]);
          }
        };
        scanObj(data);
      } catch (e) {}
    });

    // 5. Inlined script regex mining (JWPlayer, VideoJS, HLS configs)
    const scriptTexts = Array.from(document.querySelectorAll("script:not([src])"))
      .map((s) => s.textContent)
      .join("\n");

    const hlsMatches = scriptTexts.match(/https?:\/\/[^\s"']+\.m3u8[^\s"']*/gi) || [];
    for (const m of hlsMatches) {
      addCandidate(m, "video", "HLS (.m3u8)", document.title, "Script Config");
    }

    const mp4Matches = scriptTexts.match(/https?:\/\/[^\s"']+\.(mp4|webm)[^\s"']*/gi) || [];
    for (const m of mp4Matches) {
      addCandidate(m, "video", "MP4", document.title, "Script Config");
    }

    return found;
  }

  // Scan immediately on idle and report to background
  const initialMedia = scanDOMMedia();
  if (initialMedia.length > 0) {
    chrome.runtime.sendMessage({
      action: "report_media",
      items: initialMedia
    });
  }

  // Also listen for scan triggers from the popup
  chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
    if (msg.action === "scan_page") {
      const results = scanDOMMedia();
      sendResponse({ items: results });
      return true;
    }
  });
})();
