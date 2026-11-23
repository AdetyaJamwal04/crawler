/**
 * MediaFlow - Background Service Worker
 * Sniffs network traffic for video, audio, HLS (.m3u8), DASH (.mpd), and media streams.
 * Maintains a per-tab store of detected media resources with session storage persistence.
 */

const tabMediaStore = new Map();

// Helper to check if chrome.storage.session is available (MV3)
const storageSession = (typeof chrome !== "undefined" && chrome.storage && chrome.storage.session)
  ? chrome.storage.session
  : null;

// File extensions and mime types to capture
const MEDIA_EXTENSIONS = [
  /\.(mp4|webm|mkv|mov|avi|flv|m4v)(\?.*)?$/i, // 0: Video
  /\.(m3u8)(\?.*)?$/i,                          // 1: HLS
  /\.(mpd)(\?.*)?$/i,                           // 2: DASH
  /\.(mp3|wav|ogg|m4a|aac|flac)(\?.*)?$/i       // 3: Audio
];

const MEDIA_CONTENT_TYPES = [
  "video/",
  "audio/",
  "application/x-mpegurl",
  "application/vnd.apple.mpegurl",
  "application/dash+xml"
];

// Helper to determine media type
function classifyMediaType(url, contentType = "") {
  const cleanUrl = url.split("?")[0].toLowerCase();
  const cType = contentType.toLowerCase();

  if (cleanUrl.endsWith(".m3u8") || cType.includes("mpegurl")) {
    return { type: "video", format: "HLS (.m3u8)" };
  }
  if (cleanUrl.endsWith(".mpd") || cType.includes("dash+xml") || MEDIA_EXTENSIONS[2].test(url)) {
    return { type: "video", format: "DASH (.mpd)" };
  }
  if (MEDIA_EXTENSIONS[0].test(url) || cType.startsWith("video/")) {
    const ext = cleanUrl.split(".").pop() || "mp4";
    return { type: "video", format: ext.toUpperCase() };
  }
  if (MEDIA_EXTENSIONS[3].test(url) || cType.startsWith("audio/")) {
    const ext = cleanUrl.split(".").pop() || "mp3";
    return { type: "audio", format: ext.toUpperCase() };
  }
  return null;
}

// Extract clean filename from URL
function getFilenameFromUrl(url, defaultExt = "mp4") {
  try {
    const pathname = new URL(url).pathname;
    const segments = pathname.split("/").filter(Boolean);
    if (segments.length > 0) {
      const candidate = decodeURIComponent(segments[segments.length - 1]);
      if (candidate.includes(".")) return candidate;
    }
  } catch (e) {}
  return `media_${Date.now()}.${defaultExt}`;
}

// Persist tab media item
async function addMediaForTab(tabId, item) {
  if (!tabId || tabId < 0) return;

  if (!tabMediaStore.has(tabId)) {
    tabMediaStore.set(tabId, new Map());
  }
  const tabMap = tabMediaStore.get(tabId);

  if (!tabMap.has(item.url)) {
    const record = {
      id: Math.random().toString(36).substring(2, 9),
      url: item.url,
      title: item.title || getFilenameFromUrl(item.url, item.type === "audio" ? "mp3" : "mp4"),
      type: item.type,
      format: item.format,
      size: item.size || null,
      source: item.source || "network",
      timestamp: Date.now()
    };
    tabMap.set(item.url, record);
    updateBadge(tabId);

    // Sync to session storage if available
    if (storageSession) {
      const key = `tab_${tabId}`;
      const itemsArray = Array.from(tabMap.values());
      try {
        await storageSession.set({ [key]: itemsArray });
      } catch (_) {}
    }
  }
}

// Retrieve media list for a tab
async function getMediaForTab(tabId) {
  if (!tabId) return [];

  if (tabMediaStore.has(tabId) && tabMediaStore.get(tabId).size > 0) {
    return Array.from(tabMediaStore.get(tabId).values());
  }

  if (storageSession) {
    try {
      const key = `tab_${tabId}`;
      const data = await storageSession.get([key]);
      if (data && data[key]) {
        // Restore memory map
        const map = new Map();
        for (const item of data[key]) {
          map.set(item.url, item);
        }
        tabMediaStore.set(tabId, map);
        updateBadge(tabId);
        return data[key];
      }
    } catch (_) {}
  }

  return [];
}

// Update icon badge count
function updateBadge(tabId) {
  const count = tabMediaStore.has(tabId) ? tabMediaStore.get(tabId).size : 0;
  if (count > 0) {
    chrome.action.setBadgeText({ tabId, text: String(count) });
    chrome.action.setBadgeBackgroundColor({ tabId, color: "#6366f1" });
  } else {
    chrome.action.setBadgeText({ tabId, text: "" });
  }
}

// Listen to network response headers for media types
chrome.webRequest.onHeadersReceived.addListener(
  (details) => {
    // Only inspect top-level tabs
    if (details.tabId < 0) return;

    const url = details.url;
    // Skip small images, css, scripts, data urls
    if (url.startsWith("data:") || url.startsWith("blob:")) return;

    let contentType = "";
    let contentLength = null;

    if (details.responseHeaders) {
      for (const h of details.responseHeaders) {
        const name = h.name.toLowerCase();
        if (name === "content-type") contentType = h.value || "";
        if (name === "content-length") contentLength = parseInt(h.value, 10);
      }
    }

    const classification = classifyMediaType(url, contentType);
    if (classification) {
      addMediaForTab(details.tabId, {
        url: url,
        type: classification.type,
        format: classification.format,
        size: contentLength,
        source: "Network Sniffer"
      });
    }
  },
  { urls: ["<all_urls>"] },
  ["responseHeaders"]
);

// Clear media on tab navigation / reload
chrome.tabs.onUpdated.addListener((tabId, changeInfo) => {
  if (changeInfo.status === "loading") {
    tabMediaStore.delete(tabId);
    if (storageSession) {
      storageSession.remove(`tab_${tabId}`);
    }
    updateBadge(tabId);
  }
});

chrome.tabs.onRemoved.addListener((tabId) => {
  tabMediaStore.delete(tabId);
  if (storageSession) {
    storageSession.remove(`tab_${tabId}`);
  }
});

// Messaging with popup and content script
chrome.runtime.onMessage.addListener((message, sender, sendResponse) => {
  if (message.action === "get_tab_media") {
    const tabId = message.tabId;
    getMediaForTab(tabId).then((mediaList) => {
      sendResponse({ media: mediaList });
    });
    return true; // Keep message channel open for async response
  }

  if (message.action === "report_media") {
    const tabId = sender.tab ? sender.tab.id : message.tabId;
    if (tabId && message.items && Array.isArray(message.items)) {
      Promise.all(message.items.map((item) => addMediaForTab(tabId, item))).then(() => {
        sendResponse({ ok: true });
      });
      return true;
    }
    sendResponse({ ok: true });
    return true;
  }

  if (message.action === "download_url") {
    chrome.downloads.download({
      url: message.url,
      filename: message.filename || undefined,
      saveAs: false
    }, (downloadId) => {
      sendResponse({ downloadId: downloadId, error: chrome.runtime.lastError ? chrome.runtime.lastError.message : null });
    });
    return true;
  }

  if (message.action === "clear_tab_media") {
    if (message.tabId) {
      tabMediaStore.delete(message.tabId);
      if (storageSession) {
        storageSession.remove(`tab_${message.tabId}`);
      }
      updateBadge(message.tabId);
    }
    sendResponse({ ok: true });
    return true;
  }
});
