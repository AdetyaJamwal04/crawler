/**
 * MediaFlow - Extension Popup Controller
 * Queries detected media from background service worker, filters, previews,
 * and initiates direct or stitched HLS downloads.
 */

(function () {
  "use strict";

  let activeTabId = null;
  let allMedia = [];
  let currentFilter = "all";
  let isHlsDownloading = false;

  // Elements
  const mediaList = document.getElementById("media-list");
  const emptyState = document.getElementById("empty-state");
  const rescanBtn = document.getElementById("rescan-btn");
  const emptyRescanBtn = document.getElementById("empty-rescan-btn");
  const downloadAllBtn = document.getElementById("download-all-btn");
  const countAll = document.getElementById("count-all");
  const countVideo = document.getElementById("count-video");
  const countAudio = document.getElementById("count-audio");
  const filterChips = document.querySelectorAll(".filter-chip");

  // HLS Progress Elements
  const hlsCard = document.getElementById("hls-progress-card");
  const hlsMsg = document.getElementById("hls-msg");
  const hlsPct = document.getElementById("hls-pct");
  const hlsBarFill = document.getElementById("hls-bar-fill");

  // Direct Downloader
  const directUrlInput = document.getElementById("direct-url-input");
  const directDownloadBtn = document.getElementById("direct-download-btn");

  document.addEventListener("DOMContentLoaded", async () => {
    // Get active tab
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (tab) {
      activeTabId = tab.id;
      loadMedia();
    }
    setupEvents();
  });

  function setupEvents() {
    rescanBtn.addEventListener("click", scanPage);
    emptyRescanBtn.addEventListener("click", scanPage);

    filterChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        filterChips.forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        currentFilter = chip.getAttribute("data-filter");
        renderMedia();
      });
    });

    downloadAllBtn.addEventListener("click", async () => {
      const items = getFilteredItems();
      downloadAllBtn.disabled = true;
      for (const item of items) {
        await downloadMedia(item);
        // Small delay between downloads to prevent browser throttling
        await new Promise((r) => setTimeout(r, 400));
      }
      downloadAllBtn.disabled = false;
    });

    directDownloadBtn.addEventListener("click", () => {
      const url = directUrlInput.value.trim();
      if (!url) return;
      const isHls = url.includes(".m3u8");
      downloadMedia({
        url,
        title: "direct_download",
        format: isHls ? "HLS (.m3u8)" : "Media"
      });
      directUrlInput.value = "";
    });
  }

  // Load media from background service worker
  function loadMedia() {
    if (!activeTabId) return;
    chrome.runtime.sendMessage({ action: "get_tab_media", tabId: activeTabId }, (res) => {
      allMedia = (res && res.media) || [];
      updateCounts();
      renderMedia();
    });
  }

  // Actively trigger DOM scan in current tab
  function scanPage() {
    if (!activeTabId) return;
    rescanBtn.classList.add("spinning");
    chrome.tabs.sendMessage(activeTabId, { action: "scan_page" }, (res) => {
      rescanBtn.classList.remove("spinning");
      if (res && res.items) {
        chrome.runtime.sendMessage(
          { action: "report_media", tabId: activeTabId, items: res.items },
          () => loadMedia()
        );
      } else {
        loadMedia();
      }
    });
  }

  function updateCounts() {
    const vCount = allMedia.filter((m) => m.type === "video").length;
    const aCount = allMedia.filter((m) => m.type === "audio").length;
    countAll.textContent = allMedia.length;
    countVideo.textContent = vCount;
    countAudio.textContent = aCount;
    downloadAllBtn.classList.toggle("hidden", allMedia.length === 0);
  }

  function getFilteredItems() {
    if (currentFilter === "video") return allMedia.filter((m) => m.type === "video");
    if (currentFilter === "audio") return allMedia.filter((m) => m.type === "audio");
    return allMedia;
  }

  function formatBytes(bytes) {
    if (!bytes) return "";
    const k = 1024;
    const sizes = ["B", "KB", "MB", "GB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(1)} ${sizes[i]}`;
  }

  function escapeHtml(str) {
    if (!str) return "";
    return String(str)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }

  function renderMedia() {
    const items = getFilteredItems();
    mediaList.innerHTML = "";

    if (items.length === 0) {
      emptyState.classList.remove("hidden");
      return;
    }
    emptyState.classList.add("hidden");

    items.forEach((item) => {
      const card = document.createElement("div");
      card.className = "media-item";

      const isVideo = item.type === "video";
      const badgeClass = isVideo ? "badge-video" : "badge-audio";
      const sizeText = item.size ? formatBytes(item.size) : "";

      const safeTitle = escapeHtml(item.title || "media");
      const safeUrl = escapeHtml(item.url || "");
      const safeFormat = escapeHtml(item.format || "MEDIA");
      const safeSource = escapeHtml(item.source || "Network");

      card.innerHTML = `
        <div class="media-item-header">
          <div class="media-item-title" title="${safeUrl}">${safeTitle}</div>
          <span class="media-badge ${badgeClass}">${safeFormat}</span>
        </div>
        <div class="media-meta-row">
          <span>Source: ${safeSource}</span>
          <span>${sizeText}</span>
        </div>
        <div class="media-actions">
          <button class="btn-action btn-download" type="button">
            ⬇️ Download
          </button>
          <button class="btn-action btn-copy" type="button">
            📋 Copy Link
          </button>
        </div>
      `;

      card.querySelector(".btn-download").addEventListener("click", () => downloadMedia(item));
      card.querySelector(".btn-copy").addEventListener("click", (e) => {
        navigator.clipboard.writeText(item.url);
        const originalText = e.target.textContent;
        e.target.textContent = "Copied!";
        setTimeout(() => (e.target.textContent = originalText), 1500);
      });

      mediaList.appendChild(card);
    });
  }

  // Handle download dispatch
  async function downloadMedia(item) {
    const isHls = (item.format && item.format.includes("HLS")) || item.url.includes(".m3u8");

    if (isHls && window.HlsDownloader) {
      if (isHlsDownloading) {
        alert("An HLS stream download is already in progress. Please wait for it to complete.");
        return;
      }
      isHlsDownloading = true;
      hlsCard.classList.remove("hidden");
      try {
        await window.HlsDownloader.downloadHls(item.url, item.title, (p) => {
          hlsMsg.textContent = p.message;
          hlsPct.textContent = `${p.percent}%`;
          hlsBarFill.style.width = `${p.percent}%`;
          if (p.state === "complete") {
            setTimeout(() => {
              hlsCard.classList.add("hidden");
              isHlsDownloading = false;
            }, 3000);
          }
        });
      } catch (err) {
        hlsMsg.textContent = `Error: ${err.message || "Download failed"}`;
        hlsPct.textContent = "";
        isHlsDownloading = false;
      }
    } else {
      // Standard browser download
      chrome.runtime.sendMessage({
        action: "download_url",
        url: item.url,
        filename: item.title
      });
    }
  }
})();
