/**
 * MediaFlow - Universal Media Downloader & Page Crawler
 * Frontend Controller handling UI interactions, stream downloads, media preview,
 * crawler inspection, progress tracking, and batch processing.
 */

(function () {
  "use strict";

  // Elements
  const serverStatusPill = document.getElementById("server-status-pill");
  const serverStatusText = document.getElementById("server-status-text");
  
  const tabSingleBtn = document.getElementById("tab-single-btn");
  const tabBatchBtn = document.getElementById("tab-batch-btn");
  const panelSingle = document.getElementById("panel-single");
  const panelBatch = document.getElementById("panel-batch");

  const mediaUrlInput = document.getElementById("media-url-input");
  const pasteBtn = document.getElementById("paste-btn");
  const clearBtn = document.getElementById("clear-btn");
  const customFilenameInput = document.getElementById("custom-filename-input");
  const customRefererInput = document.getElementById("custom-referer-input");
  const crawlBtn = document.getElementById("crawl-btn");
  const inspectBtn = document.getElementById("inspect-btn");
  const downloadBtn = document.getElementById("download-btn");
  const sampleChips = document.querySelectorAll(".sample-chip");

  // Preview Card Elements
  const previewCard = document.getElementById("preview-card");
  const closePreviewBtn = document.getElementById("close-preview-btn");
  const mediaViewport = document.getElementById("media-viewport");
  const metaFilename = document.getElementById("meta-filename");
  const metaType = document.getElementById("meta-type");
  const metaSize = document.getElementById("meta-size");
  const metaRanges = document.getElementById("meta-ranges");
  const formatsContainer = document.getElementById("formats-selector-container");
  const formatSelect = document.getElementById("format-select");
  const previewDownloadBtn = document.getElementById("preview-download-btn");

  // Crawler Card Elements
  const crawlerCard = document.getElementById("crawler-card");
  const closeCrawlerBtn = document.getElementById("close-crawler-btn");
  const crawlerPageTitle = document.getElementById("crawler-page-title");
  const crawlerDownloadAllBtn = document.getElementById("crawler-download-all-btn");
  const crawlerResourcesList = document.getElementById("crawler-resources-list");
  const countAll = document.getElementById("count-all");
  const countVideo = document.getElementById("count-video");
  const countAudio = document.getElementById("count-audio");
  const countImage = document.getElementById("count-image");
  const filterChips = document.querySelectorAll(".filter-chip");

  // Progress Card Elements
  const progressCard = document.getElementById("progress-card");
  const progressFilename = document.getElementById("progress-filename");
  const progressPercent = document.getElementById("progress-percent");
  const progressBarFill = document.getElementById("progress-bar-fill");
  const progressTransferred = document.getElementById("progress-transferred");
  const progressSpeed = document.getElementById("progress-speed");
  const progressEta = document.getElementById("progress-eta");

  // Batch Elements
  const batchUrlsInput = document.getElementById("batch-urls-input");
  const batchCountBadge = document.getElementById("batch-count-badge");
  const batchClearBtn = document.getElementById("batch-clear-btn");
  const batchStartBtn = document.getElementById("batch-start-btn");

  // History Elements
  const historyEmpty = document.getElementById("history-empty");
  const historyList = document.getElementById("history-list");
  const historyCounter = document.getElementById("history-counter");
  const clearHistoryBtn = document.getElementById("clear-history-btn");
  const toastContainer = document.getElementById("toast-container");

  // State
  let currentInspection = null;
  let isDownloading = false;
  let downloadHistory = [];
  let crawledResources = [];
  let currentFilter = "all";

  // Initialize
  document.addEventListener("DOMContentLoaded", () => {
    checkServerHealth();
    loadHistory();
    setupEventListeners();
  });

  // Check Server Health
  async function checkServerHealth() {
    try {
      const res = await fetch("/api/health");
      if (res.ok) {
        const data = await res.json();
        serverStatusPill.className = "status-pill status-online";
        serverStatusText.textContent = data.yt_dlp ? "Engine & Crawler Ready" : "Crawler Ready";
      } else {
        throw new Error("Server responded with error");
      }
    } catch (e) {
      serverStatusPill.className = "status-pill status-offline";
      serverStatusText.textContent = "Offline (Standalone UI)";
    }
  }

  // Setup UI Event Listeners
  function setupEventListeners() {
    // Tabs
    tabSingleBtn.addEventListener("click", () => switchTab("single"));
    tabBatchBtn.addEventListener("click", () => switchTab("batch"));

    // Input handlers
    mediaUrlInput.addEventListener("input", () => {
      clearBtn.classList.toggle("hidden", !mediaUrlInput.value.trim());
    });

    mediaUrlInput.addEventListener("keydown", (e) => {
      if (e.key === "Enter") {
        e.preventDefault();
        startDownload();
      }
    });

    pasteBtn.addEventListener("click", async () => {
      try {
        const text = await navigator.clipboard.readText();
        if (text) {
          mediaUrlInput.value = text.trim();
          clearBtn.classList.remove("hidden");
          showToast("URL pasted from clipboard", "info");
        }
      } catch (err) {
        mediaUrlInput.focus();
        showToast("Please press Ctrl+V to paste", "info");
      }
    });

    clearBtn.addEventListener("click", () => {
      mediaUrlInput.value = "";
      clearBtn.classList.add("hidden");
      mediaUrlInput.focus();
    });

    // Sample clicks
    sampleChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        mediaUrlInput.value = chip.getAttribute("data-url");
        clearBtn.classList.remove("hidden");
        const defaultName = chip.getAttribute("data-name");
        if (defaultName) customFilenameInput.value = defaultName;
        inspectUrl();
      });
    });

    // Action buttons
    crawlBtn.addEventListener("click", () => crawlPage(mediaUrlInput.value.trim()));
    inspectBtn.addEventListener("click", inspectUrl);
    downloadBtn.addEventListener("click", startDownload);
    closePreviewBtn.addEventListener("click", () => previewCard.classList.add("hidden"));
    previewDownloadBtn.addEventListener("click", () => startDownload());

    // Crawler actions
    closeCrawlerBtn.addEventListener("click", () => crawlerCard.classList.add("hidden"));
    crawlerDownloadAllBtn.addEventListener("click", downloadAllCrawled);
    filterChips.forEach((chip) => {
      chip.addEventListener("click", () => {
        filterChips.forEach((c) => c.classList.remove("active"));
        chip.classList.add("active");
        currentFilter = chip.getAttribute("data-filter");
        renderCrawledResources();
      });
    });

    // Batch handlers
    batchUrlsInput.addEventListener("input", updateBatchCount);
    batchClearBtn.addEventListener("click", () => {
      batchUrlsInput.value = "";
      updateBatchCount();
    });
    batchStartBtn.addEventListener("click", startBatchDownload);

    // History
    clearHistoryBtn.addEventListener("click", () => {
      downloadHistory = [];
      saveHistory();
      renderHistory();
      showToast("Download history cleared", "info");
    });
  }

  function switchTab(tab) {
    if (tab === "single") {
      tabSingleBtn.classList.add("active");
      tabBatchBtn.classList.remove("active");
      panelSingle.classList.add("active");
      panelBatch.classList.remove("active");
    } else {
      tabBatchBtn.classList.add("active");
      tabSingleBtn.classList.remove("active");
      panelBatch.classList.add("active");
      panelSingle.classList.remove("active");
    }
  }

  function updateBatchCount() {
    const urls = getBatchUrls();
    batchCountBadge.textContent = `${urls.length} link${urls.length === 1 ? "" : "s"} detected`;
  }

  function getBatchUrls() {
    return batchUrlsInput.value
      .split("\n")
      .map((line) => line.trim())
      .filter((line) => line.startsWith("http://") || line.startsWith("https://"));
  }

  // Format bytes helper
  function formatBytes(bytes, decimals = 2) {
    if (bytes === null || bytes === undefined || isNaN(bytes) || bytes <= 0) return "Unknown size";
    const k = 1024;
    const dm = decimals < 0 ? 0 : decimals;
    const sizes = ["Bytes", "KB", "MB", "GB", "TB"];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(dm)) + " " + sizes[i];
  }

  // -------------------------------------------------------------
  // Crawl Page Functionality
  // -------------------------------------------------------------
  async function crawlPage(url) {
    if (!url) {
      showToast("Please enter a page or media link first.", "error");
      mediaUrlInput.focus();
      return;
    }

    crawlBtn.disabled = true;
    crawlBtn.innerHTML = '<span class="spinner-small"></span><span>Crawling page...</span>';
    showToast("Crawling page for videos, streams, and audio...", "info");

    try {
      const res = await fetch(`/api/crawl?url=${encodeURIComponent(url)}`);
      const data = await res.json();

      if (data.ok && data.resources && data.resources.length > 0) {
        crawledResources = data.resources;
        crawlerCard.classList.remove("hidden");
        crawlerPageTitle.textContent = `${data.page_title || "Page"} • ${data.page_url}`;

        // Update counts
        countAll.textContent = data.resources.length;
        countVideo.textContent = data.resources.filter((r) => r.type === "video" || r.type === "stream").length;
        countAudio.textContent = data.resources.filter((r) => r.type === "audio").length;
        countImage.textContent = data.resources.filter((r) => r.type === "image").length;

        renderCrawledResources();
        showToast(`Discovered ${data.resources.length} media resources!`, "success");

        // Scroll into view
        crawlerCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } else {
        showToast(data.error || "No media resources found on this page.", "warning");
      }
    } catch (e) {
      showToast("Crawl error: " + e.message, "error");
    } finally {
      crawlBtn.disabled = false;
      crawlBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="12" cy="12" r="3"></circle>
          <path d="M12 2v4m0 12v4M4.93 4.93l2.83 2.83m8.48 8.48l2.83 2.83M2 12h4m12 0h4M4.93 19.07l2.83-2.83m8.48-8.48l2.83-2.83"></path>
        </svg>
        <span>🕷️ Crawl Page for Media</span>`;
    }
  }

  function renderCrawledResources() {
    crawlerResourcesList.innerHTML = "";
    const filtered = crawledResources.filter((r) => {
      if (currentFilter === "all") return true;
      if (currentFilter === "video") return r.type === "video" || r.type === "stream";
      return r.type === currentFilter;
    });

    if (filtered.length === 0) {
      crawlerResourcesList.innerHTML = `<div class="history-empty"><p>No ${currentFilter} resources found in this category.</p></div>`;
      return;
    }

    filtered.forEach((res) => {
      const item = document.createElement("div");
      item.className = "crawler-item";

      const isVideo = res.type === "video" || res.type === "stream";
      const isAudio = res.type === "audio";
      const icon = isVideo ? "🎬" : isAudio ? "🎵" : "🖼️";
      const tagColor = res.is_stream ? "badge-warning" : "badge-type";

      const thumbEl = res.thumbnail
        ? `<img class="crawler-thumb" src="${escapeHtml(res.thumbnail)}" alt="thumb" onerror="this.style.display='none'">`
        : `<div class="crawler-type-icon">${icon}</div>`;

      item.innerHTML = `
        <div class="crawler-item-left">
          ${thumbEl}
          <div class="crawler-item-details">
            <div class="crawler-item-title" title="${escapeHtml(res.title || res.url)}">${escapeHtml(res.title || res.url)}</div>
            <div class="crawler-item-tags">
              <span class="badge ${tagColor}">${res.is_stream ? "HLS STREAM" : res.type.toUpperCase()}</span>
              <span class="badge font-mono">.${escapeHtml(res.format)}</span>
              <span class="badge font-mono" style="opacity:0.75">${escapeHtml(res.source_tag)}</span>
              ${res.size_bytes ? `<span class="badge">${formatBytes(res.size_bytes)}</span>` : ""}
            </div>
          </div>
        </div>
        <div class="crawler-item-actions">
          <button type="button" class="btn btn-secondary btn-sm crawler-preview-btn" title="Preview media">
            Preview
          </button>
          <button type="button" class="btn btn-primary btn-sm crawler-dl-btn" title="Download directly with session referer">
            Download
          </button>
        </div>
      `;

      // Preview click
      item.querySelector(".crawler-preview-btn").addEventListener("click", () => {
        mediaUrlInput.value = res.url;
        clearBtn.classList.remove("hidden");
        displayDirectPreview({
          filename: res.title,
          content_type: isVideo ? "video/mp4" : isAudio ? "audio/mpeg" : "image/jpeg",
          size_bytes: res.size_bytes,
          accept_ranges: true,
        }, res.url, res.referer);
        previewCard.scrollIntoView({ behavior: "smooth", block: "nearest" });
      });

      // Download click
      item.querySelector(".crawler-dl-btn").addEventListener("click", () => {
        downloadViaStreamingEngine(res.url, res.title, res.referer);
      });

      crawlerResourcesList.appendChild(item);
    });
  }

  async function downloadAllCrawled() {
    const downloadable = crawledResources.filter((r) => r.type === "video" || r.type === "stream" || r.type === "audio");
    if (downloadable.length === 0) {
      showToast("No downloadable videos or audio found.", "warning");
      return;
    }

    showToast(`Starting batch download of ${downloadable.length} discovered items...`, "info");
    for (let i = 0; i < downloadable.length; i++) {
      const item = downloadable[i];
      showToast(`Downloading (${i + 1}/${downloadable.length}): ${item.title}`, "info");
      await downloadViaStreamingEngine(item.url, item.title, item.referer);
    }
    showToast("All crawled media downloaded!", "success");
  }

  // Inspect URL
  async function inspectUrl() {
    const url = mediaUrlInput.value.trim();
    if (!url) {
      showToast("Please enter a media link first.", "error");
      mediaUrlInput.focus();
      return;
    }

    inspectBtn.disabled = true;
    inspectBtn.innerHTML = '<span class="spinner-small"></span><span>Inspecting...</span>';

    try {
      const res = await fetch(`/api/inspect?url=${encodeURIComponent(url)}`);
      const data = await res.json();

      if (data.ok) {
        currentInspection = data;
        if (data.content_type && data.content_type.includes("text/html")) {
          // It's a webpage! Trigger crawler
          crawlPage(url);
          return;
        }
        displayDirectPreview(data, url);
      } else {
        // If inspection failed with 403 or HTML, trigger crawler automatically!
        showToast("Direct inspect restricted. Crawling page for media...", "info");
        crawlPage(url);
      }
    } catch (e) {
      showToast("Connection failed: " + e.message, "error");
    } finally {
      inspectBtn.disabled = false;
      inspectBtn.innerHTML = `
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
          <circle cx="11" cy="11" r="8"></circle>
          <line x1="21" y1="21" x2="16.65" y2="16.65"></line>
        </svg>
        <span>Inspect & Preview</span>`;
    }
  }

  // Display direct media preview
  function displayDirectPreview(data, originalUrl, referer = "") {
    previewCard.classList.remove("hidden");
    formatsContainer.classList.add("hidden");

    metaFilename.textContent = data.filename || "file";
    metaType.textContent = data.content_type || "media";
    metaSize.textContent = formatBytes(data.size_bytes);
    metaRanges.textContent = data.accept_ranges ? "Yes (Resumable)" : "Standard";

    if (!customFilenameInput.value.trim() && data.filename) {
      customFilenameInput.value = data.filename;
    }

    mediaViewport.innerHTML = "";
    const type = (data.content_type || "").toLowerCase();
    const previewStreamUrl = `/api/download?url=${encodeURIComponent(originalUrl)}${referer ? `&referer=${encodeURIComponent(referer)}` : ""}`;

    if (type.startsWith("video/")) {
      const video = document.createElement("video");
      video.controls = true;
      video.src = previewStreamUrl;
      video.preload = "metadata";
      mediaViewport.appendChild(video);
    } else if (type.startsWith("audio/")) {
      const audio = document.createElement("audio");
      audio.controls = true;
      audio.src = previewStreamUrl;
      mediaViewport.appendChild(audio);
    } else if (type.startsWith("image/")) {
      const img = document.createElement("img");
      img.src = previewStreamUrl;
      img.alt = data.filename;
      mediaViewport.appendChild(img);
    } else {
      mediaViewport.innerHTML = `
        <div class="viewport-placeholder">
          <svg width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
          </svg>
          <span>Ready to download (${data.content_type})</span>
        </div>`;
    }

    showToast("Media preview ready!", "success");
  }

  // Start Download
  async function startDownload() {
    let url = mediaUrlInput.value.trim();
    if (!url) {
      showToast("Please enter a media URL to download.", "error");
      mediaUrlInput.focus();
      return;
    }

    if (currentInspection && currentInspection.is_platform && formatSelect.value) {
      url = formatSelect.value;
    }

    const customName = customFilenameInput.value.trim();
    const customReferer = customRefererInput ? customRefererInput.value.trim() : "";
    const downloadEngine = document.querySelector('input[name="download-engine"]:checked')?.value || "stream";

    if (downloadEngine === "direct") {
      downloadDirectBrowser(url, customName);
    } else {
      await downloadViaStreamingEngine(url, customName, customReferer);
    }
  }

  // Method 1: Direct Browser Fetch
  function downloadDirectBrowser(url, customName) {
    const a = document.createElement("a");
    a.href = url;
    if (customName) a.download = customName;
    a.target = "_blank";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    addHistoryItem(customName || getFilenameFromUrl(url), "Direct Browser Download", url, "completed");
    showToast("Download triggered in browser", "success");
  }

  // Method 2: High Performance Streaming Engine with Referer & Anti-Hotlinking
  async function downloadViaStreamingEngine(url, customName = "", referer = "") {
    if (isDownloading) {
      showToast("A download is already in progress.", "warning");
      return;
    }

    isDownloading = true;
    downloadBtn.disabled = true;
    previewDownloadBtn.disabled = true;

    // Show Progress UI
    progressCard.classList.remove("hidden");
    progressBarFill.style.width = "0%";
    progressPercent.textContent = "0%";
    progressSpeed.textContent = "-- MB/s";
    progressEta.textContent = "Connecting...";

    let resolvedReferer = referer;
    if (!resolvedReferer && customRefererInput && customRefererInput.value.trim()) {
      resolvedReferer = customRefererInput.value.trim();
    }

    let downloadEndpoint = `/api/download?url=${encodeURIComponent(url)}`;
    if (customName) downloadEndpoint += `&name=${encodeURIComponent(customName)}`;
    if (resolvedReferer) downloadEndpoint += `&referer=${encodeURIComponent(resolvedReferer)}`;

    progressFilename.textContent = customName || "Connecting to media resource...";

    const startTime = Date.now();
    let receivedBytes = 0;
    let totalBytes = 0;
    let lastTime = startTime;
    let lastBytes = 0;

    try {
      const response = await fetch(downloadEndpoint);

      if (!response.ok) {
        let errMessage = `Server error ${response.status}`;
        try {
          const errData = await response.json();
          if (errData.error) errMessage = errData.error;
        } catch (_) {}

        // If 403 Forbidden or HTML, offer to crawl the page
        if (response.status === 403 || errMessage.includes("403")) {
          showToast("Protected link detected. Initiating crawler...", "warning");
          crawlPage(url);
        }
        throw new Error(errMessage);
      }

      const contentLengthHeader = response.headers.get("Content-Length");
      if (contentLengthHeader) {
        totalBytes = parseInt(contentLengthHeader, 10);
      }

      const disposition = response.headers.get("Content-Disposition");
      let resolvedFilename = customName || "";
      if (!resolvedFilename && disposition) {
        const starMatch = disposition.match(/filename\*=(?:UTF-8''|utf-8'')([^;]+)/i);
        if (starMatch) {
          resolvedFilename = decodeURIComponent(starMatch[1].replace(/["']/g, ""));
        } else {
          const match = disposition.match(/filename="?([^";]+)"?/i);
          if (match) resolvedFilename = match[1];
        }
      }
      if (!resolvedFilename) resolvedFilename = getFilenameFromUrl(url);

      progressFilename.textContent = resolvedFilename;

      const reader = response.body.getReader();
      const chunks = [];

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        chunks.push(value);
        receivedBytes += value.length;

        const now = Date.now();
        if (now - lastTime >= 200 || receivedBytes === totalBytes) {
          const elapsedSec = (now - lastTime) / 1000;
          const currentSpeed = (receivedBytes - lastBytes) / elapsedSec;
          lastBytes = receivedBytes;
          lastTime = now;

          if (totalBytes > 0) {
            const percent = Math.min(100, Math.round((receivedBytes / totalBytes) * 100));
            progressBarFill.style.width = `${percent}%`;
            progressPercent.textContent = `${percent}%`;
            progressTransferred.textContent = `${formatBytes(receivedBytes)} / ${formatBytes(totalBytes)}`;

            if (currentSpeed > 0) {
              const remainingBytes = totalBytes - receivedBytes;
              const etaSec = Math.round(remainingBytes / currentSpeed);
              progressSpeed.textContent = `${(currentSpeed / (1024 * 1024)).toFixed(2)} MB/s`;
              progressEta.textContent = `ETA: ${etaSec}s`;
            }
          } else {
            progressBarFill.style.width = "100%";
            progressPercent.textContent = "Streaming...";
            progressTransferred.textContent = `${formatBytes(receivedBytes)} received`;
            if (currentSpeed > 0) {
              progressSpeed.textContent = `${(currentSpeed / (1024 * 1024)).toFixed(2)} MB/s`;
            }
          }
        }
      }

      const mime = response.headers.get("Content-Type") || "application/octet-stream";
      const blob = new Blob(chunks, { type: mime });
      const objectUrl = URL.createObjectURL(blob);

      const downloadLink = document.createElement("a");
      downloadLink.href = objectUrl;
      downloadLink.download = resolvedFilename;
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);

      setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);

      progressBarFill.style.width = "100%";
      progressPercent.textContent = "100%";
      progressEta.textContent = "Completed!";
      showToast(`Saved: ${resolvedFilename}`, "success");

      addHistoryItem(resolvedFilename, formatBytes(receivedBytes), url, "completed");

    } catch (err) {
      console.error("Download error:", err);
      showToast("Download failed: " + err.message, "error");
      progressBarFill.style.width = "0%";
      progressPercent.textContent = "Failed";
      progressEta.textContent = "Error";
      addHistoryItem(customName || getFilenameFromUrl(url), "Error", url, "failed");
    } finally {
      isDownloading = false;
      downloadBtn.disabled = false;
      previewDownloadBtn.disabled = false;
    }
  }

  // Batch Download Processor
  async function startBatchDownload() {
    const urls = getBatchUrls();
    if (urls.length === 0) {
      showToast("Please enter at least one valid HTTP/HTTPS URL in the batch area.", "error");
      return;
    }

    batchStartBtn.disabled = true;
    showToast(`Starting batch download of ${urls.length} files...`, "info");

    for (let i = 0; i < urls.length; i++) {
      const url = urls[i];
      showToast(`Downloading (${i + 1}/${urls.length}): ${getFilenameFromUrl(url)}`, "info");
      try {
        await downloadViaStreamingEngine(url, "");
      } catch (e) {
        console.error("Batch item error:", e);
      }
    }

    batchStartBtn.disabled = false;
    showToast(`Batch completed (${urls.length} items)!`, "success");
  }

  function getFilenameFromUrl(url) {
    try {
      const parsed = new URL(url);
      const parts = parsed.pathname.split("/").filter(Boolean);
      if (parts.length > 0) {
        return decodeURIComponent(parts[parts.length - 1]);
      }
    } catch (_) {}
    return "media_file";
  }

  // History Management
  function loadHistory() {
    try {
      const saved = localStorage.getItem("mediaflow_history");
      if (saved) {
        downloadHistory = JSON.parse(saved);
      }
    } catch (_) {
      downloadHistory = [];
    }
    renderHistory();
  }

  function saveHistory() {
    try {
      localStorage.setItem("mediaflow_history", JSON.stringify(downloadHistory.slice(0, 30)));
    } catch (_) {}
  }

  function addHistoryItem(name, size, url, status) {
    const item = {
      id: Date.now().toString(),
      name: name || "media",
      size: size || "unknown",
      url: url,
      status: status || "completed",
      date: new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    };
    downloadHistory.unshift(item);
    saveHistory();
    renderHistory();
  }

  function renderHistory() {
    historyCounter.textContent = `${downloadHistory.length} file${downloadHistory.length === 1 ? "" : "s"}`;

    if (downloadHistory.length === 0) {
      historyEmpty.classList.remove("hidden");
      historyList.classList.add("hidden");
      historyList.innerHTML = "";
      return;
    }

    historyEmpty.classList.add("hidden");
    historyList.classList.remove("hidden");
    historyList.innerHTML = "";

    downloadHistory.forEach((item) => {
      const el = document.createElement("div");
      el.className = "history-item";

      const isSuccess = item.status === "completed";
      const badgeClass = isSuccess ? "badge-success" : "badge-error";
      const icon = isSuccess
        ? `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="20 6 9 17 4 12"></polyline></svg>`
        : `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line></svg>`;

      el.innerHTML = `
        <div class="history-item-left">
          <div class="history-item-icon">${icon}</div>
          <div class="history-item-info">
            <div class="history-item-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</div>
            <div class="history-item-sub">
              <span>${escapeHtml(item.size)}</span>
              <span>&bull;</span>
              <span>${escapeHtml(item.date)}</span>
            </div>
          </div>
        </div>
        <div class="history-item-actions">
          <span class="badge ${badgeClass}">${escapeHtml(item.status)}</span>
          <button type="button" class="btn-icon redownload-btn" title="Re-download">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
              <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
              <polyline points="7 10 12 15 17 10"></polyline>
              <line x1="12" y1="15" x2="12" y2="3"></line>
            </svg>
          </button>
        </div>
      `;

      el.querySelector(".redownload-btn").addEventListener("click", () => {
        mediaUrlInput.value = item.url;
        clearBtn.classList.remove("hidden");
        switchTab("single");
        startDownload();
      });

      historyList.appendChild(el);
    });
  }

  // Toast Notifications
  function showToast(message, type = "info") {
    const toast = document.createElement("div");
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    toastContainer.appendChild(toast);

    setTimeout(() => {
      toast.style.opacity = "0";
      toast.style.transform = "translateX(100%)";
      toast.style.transition = "all 0.3s ease";
      setTimeout(() => {
        if (toast.parentNode) toast.parentNode.removeChild(toast);
      }, 300);
    }, 3500);
  }

  function escapeHtml(str) {
    if (!str) return "";
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#039;");
  }
})();
