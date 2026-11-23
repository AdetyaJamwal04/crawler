/**
 * MediaFlow - In-Browser HLS Stream Downloader & Stitcher
 * Parses master and media .m3u8 playlists, concurrently fetches segment chunks,
 * decrypts AES-128 segments if encrypted, and stitches chunks into a downloadable .ts file.
 */

(function (global) {
  "use strict";

  class HlsDownloader {
    /**
     * Download and stitch an HLS stream in-browser.
     * @param {string} playlistUrl - The URL of the master or media .m3u8 playlist
     * @param {string} customTitle - Filename base
     * @param {Function} onProgress - Callback receiving { state, percent, message }
     */
    static async downloadHls(playlistUrl, customTitle = "video", onProgress = () => {}) {
      try {
        onProgress({ state: "init", percent: 0, message: "Fetching HLS manifest..." });

        const mediaPlaylistInfo = await HlsDownloader.resolveMediaPlaylist(playlistUrl);
        const { segments, keyInfo } = await HlsDownloader.parseMediaPlaylist(
          mediaPlaylistInfo.url,
          mediaPlaylistInfo.content
        );

        if (!segments || segments.length === 0) {
          throw new Error("No media segments found in HLS playlist.");
        }

        onProgress({
          state: "downloading",
          percent: 5,
          message: `Found ${segments.length} chunks. Downloading...`,
        });

        // If encrypted with AES-128, fetch decryption key
        let cryptoKey = null;
        if (keyInfo && keyInfo.method === "AES-128") {
          onProgress({ state: "key", percent: 7, message: "Fetching encryption key..." });
          cryptoKey = await HlsDownloader.fetchKey(keyInfo.uri);
        }

        // Concurrently fetch chunks with concurrency limit
        const concurrency = 4;
        const total = segments.length;
        let completed = 0;
        const downloadedBuffers = new Array(total);

        async function downloadWorker(indices) {
          for (const idx of indices) {
            const seg = segments[idx];
            let rawChunk = await HlsDownloader.fetchSegment(seg);

            // Decrypt if necessary
            if (cryptoKey) {
              const iv = seg.iv || keyInfo.iv || HlsDownloader.sequenceToIV(seg.seq);
              rawChunk = await HlsDownloader.decryptChunk(cryptoKey, iv, rawChunk);
            }

            downloadedBuffers[idx] = rawChunk;
            completed++;
            const pct = Math.min(95, Math.round(10 + (completed / total) * 85));
            onProgress({
              state: "downloading",
              percent: pct,
              message: `Downloading chunks (${completed}/${total})...`,
            });
          }
        }

        // Partition work across concurrent workers
        const tasks = Array.from({ length: total }, (_, i) => i);
        const workers = [];
        for (let w = 0; w < concurrency; w++) {
          const slice = tasks.filter((_, idx) => idx % concurrency === w);
          workers.push(downloadWorker(slice));
        }
        await Promise.all(workers);

        onProgress({ state: "stitching", percent: 96, message: "Stitching media chunks..." });

        // Concatenate buffers into single Blob
        const totalLength = downloadedBuffers.reduce((acc, b) => acc + (b ? b.byteLength : 0), 0);
        const mergedArray = new Uint8Array(totalLength);
        let offset = 0;
        for (const buf of downloadedBuffers) {
          if (buf) {
            mergedArray.set(new Uint8Array(buf), offset);
            offset += buf.byteLength;
          }
        }

        const blob = new Blob([mergedArray], { type: "video/mp2t" });
        const blobUrl = URL.createObjectURL(blob);

        let filename = (customTitle || "stream_video").replace(/[\/\\:*?"<>|]/g, "_").trim();
        if (!filename.toLowerCase().endsWith(".ts")) {
          filename += ".ts";
        }

        // Dispatch download
        if (typeof chrome !== "undefined" && chrome.downloads && chrome.downloads.download) {
          chrome.downloads.download(
            { url: blobUrl, filename: filename, saveAs: false },
            () => {
              setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
            }
          );
        } else {
          const a = document.createElement("a");
          a.href = blobUrl;
          a.download = filename;
          document.body.appendChild(a);
          a.click();
          document.body.removeChild(a);
          setTimeout(() => URL.revokeObjectURL(blobUrl), 120000);
        }

        onProgress({ state: "complete", percent: 100, message: "Download complete!" });
        return true;
      } catch (err) {
        onProgress({ state: "error", percent: 0, message: err.message || "Failed to download stream" });
        throw err;
      }
    }

    /**
     * Resolves master playlist to the highest-bandwidth media playlist.
     */
    static async resolveMediaPlaylist(playlistUrl) {
      const resp = await fetch(playlistUrl);
      if (!resp.ok) {
        throw new Error(`Failed to fetch playlist (HTTP ${resp.status})`);
      }
      const text = await resp.text();

      // Check if this is a master playlist containing variants
      if (text.includes("#EXT-X-STREAM-INF")) {
        const lines = text.split(/\r?\n/);
        let bestBandwidth = -1;
        let bestUri = null;

        for (let i = 0; i < lines.length; i++) {
          const line = lines[i].trim();
          if (line.startsWith("#EXT-X-STREAM-INF")) {
            const bwMatch = line.match(/BANDWIDTH=(\d+)/i);
            const bw = bwMatch ? parseInt(bwMatch[1], 10) : 0;
            // Next non-empty, non-comment line is the URI
            let j = i + 1;
            while (j < lines.length && (lines[j].trim().startsWith("#") || !lines[j].trim())) {
              j++;
            }
            if (j < lines.length && lines[j].trim()) {
              const uri = lines[j].trim();
              if (bw > bestBandwidth || !bestUri) {
                bestBandwidth = bw;
                bestUri = uri;
              }
            }
          }
        }

        if (bestUri) {
          const resolvedMediaUrl = new URL(bestUri, playlistUrl).href;
          const subResp = await fetch(resolvedMediaUrl);
          if (!subResp.ok) {
            throw new Error(`Failed to fetch media variant (HTTP ${subResp.status})`);
          }
          const subText = await subResp.text();
          return { url: resolvedMediaUrl, content: subText };
        }
      }

      return { url: playlistUrl, content: text };
    }

    /**
     * Parses segments, byte ranges, and encryption keys from a media playlist.
     */
    static async parseMediaPlaylist(playlistUrl, content) {
      const lines = content.split(/\r?\n/);
      const segments = [];
      let currentKeyInfo = null;
      let seqNum = 0;

      for (let i = 0; i < lines.length; i++) {
        const line = lines[i].trim();

        if (line.startsWith("#EXT-X-MEDIA-SEQUENCE")) {
          const seqMatch = line.match(/#EXT-X-MEDIA-SEQUENCE:(\d+)/);
          if (seqMatch) seqNum = parseInt(seqMatch[1], 10);
        } else if (line.startsWith("#EXT-X-KEY")) {
          currentKeyInfo = HlsDownloader.parseKeyTag(line, playlistUrl);
        } else if (line.startsWith("#EXTINF")) {
          // Look ahead for segment URL
          let j = i + 1;
          let byteRange = null;
          while (j < lines.length && (!lines[j].trim() || lines[j].trim().startsWith("#"))) {
            if (lines[j].trim().startsWith("#EXT-X-BYTERANGE")) {
              byteRange = lines[j].trim().replace("#EXT-X-BYTERANGE:", "");
            }
            j++;
          }
          if (j < lines.length && lines[j].trim()) {
            const rawUri = lines[j].trim();
            const segUrl = new URL(rawUri, playlistUrl).href;
            segments.push({
              url: segUrl,
              seq: seqNum++,
              byteRange: byteRange,
              key: currentKeyInfo,
            });
            i = j;
          }
        }
      }

      return { segments, keyInfo: currentKeyInfo };
    }

    static parseKeyTag(tagLine, baseUrl) {
      const methodMatch = tagLine.match(/METHOD=([^,\s]+)/);
      const method = methodMatch ? methodMatch[1].replace(/["']/g, "") : "NONE";
      if (method === "NONE") return null;

      const uriMatch = tagLine.match(/URI="([^"]+)"/) || tagLine.match(/URI=([^,\s]+)/);
      const rawUri = uriMatch ? uriMatch[1] : null;
      const keyUri = rawUri ? new URL(rawUri, baseUrl).href : null;

      let iv = null;
      const ivMatch = tagLine.match(/IV=0x([0-9a-fA-F]+)/i);
      if (ivMatch) {
        iv = HlsDownloader.hexStringToUint8Array(ivMatch[1]);
      }

      return { method, uri: keyUri, iv };
    }

    static async fetchKey(keyUrl) {
      const resp = await fetch(keyUrl);
      if (!resp.ok) throw new Error(`Failed to fetch encryption key (HTTP ${resp.status})`);
      const keyBuffer = await resp.arrayBuffer();
      return crypto.subtle.importKey("raw", keyBuffer, { name: "AES-CBC" }, false, ["decrypt"]);
    }

    static async fetchSegment(segment, retries = 3) {
      const headers = {};
      if (segment.byteRange) {
        const parts = segment.byteRange.split("@");
        const length = parseInt(parts[0], 10);
        const offset = parts[1] ? parseInt(parts[1], 10) : 0;
        headers["Range"] = `bytes=${offset}-${offset + length - 1}`;
      }

      for (let attempt = 0; attempt <= retries; attempt++) {
        try {
          const resp = await fetch(segment.url, { headers });
          if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
          return await resp.arrayBuffer();
        } catch (err) {
          if (attempt === retries) throw err;
          await new Promise((r) => setTimeout(r, 600 * (attempt + 1)));
        }
      }
    }

    static async decryptChunk(cryptoKey, iv, chunkBuffer) {
      try {
        return await crypto.subtle.decrypt({ name: "AES-CBC", iv: iv }, cryptoKey, chunkBuffer);
      } catch (e) {
        // Fallback: return raw chunk if decryption fails
        return chunkBuffer;
      }
    }

    static sequenceToIV(seq) {
      const iv = new Uint8Array(16);
      for (let i = 15; i >= 12; i--) {
        iv[i] = (seq >> ((15 - i) * 8)) & 0xff;
      }
      return iv;
    }

    static hexStringToUint8Array(hex) {
      const clean = hex.length % 2 !== 0 ? "0" + hex : hex;
      const arr = new Uint8Array(clean.length / 2);
      for (let i = 0; i < clean.length; i += 2) {
        arr[i / 2] = parseInt(clean.substring(i, i + 2), 16);
      }
      return arr;
    }
  }

  // Export to global scope
  global.HlsDownloader = HlsDownloader;
})(typeof window !== "undefined" ? window : this);
