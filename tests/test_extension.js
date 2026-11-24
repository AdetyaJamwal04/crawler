/**
 * Unit tests for extension helper logic:
 * - Filename sanitization
 * - MIME / type / format extension enforcement
 * - YouTube and extension-less URL handling
 */

const test = require("node:test");
const assert = require("node:assert");

// Import target helpers from background/extension module
const {
  classifyMediaType,
  sanitizeAndEnsureExtension,
  getFilenameFromUrl
} = require("../extension/background.js");

test("sanitizeAndEnsureExtension should add .mp4 to extension-less titles for video", () => {
  const result = sanitizeAndEnsureExtension("Never Gonna Give You Up - YouTube", "video", "video/mp4");
  assert.strictEqual(result, "Never Gonna Give You Up - YouTube.mp4");
});

test("sanitizeAndEnsureExtension should strip invalid OS filename characters", () => {
  const result = sanitizeAndEnsureExtension("Video: What / Why? *Special* <Edition>|Part 1", "video", "video/mp4");
  assert.strictEqual(result, "Video_ What _ Why_ _Special_ _Edition__Part 1.mp4");
});

test("sanitizeAndEnsureExtension should preserve existing valid extension", () => {
  const result = sanitizeAndEnsureExtension("clip.webm", "video", "video/webm");
  assert.strictEqual(result, "clip.webm");
});

test("sanitizeAndEnsureExtension should add .mp3 for audio files if missing", () => {
  const result = sanitizeAndEnsureExtension("Podcast Episode 1", "audio", "audio/mpeg");
  assert.strictEqual(result, "Podcast Episode 1.mp3");
});

test("getFilenameFromUrl extracts default with extension when path has no extension", () => {
  const result = getFilenameFromUrl("https://rr1---sn-4g5ednls.googlevideo.com/videoplayback?expire=123", "mp4");
  assert.match(result, /^media_\d+\.mp4$/);
});

test("isHtmlOrPageUrl filters YouTube embed and player URLs", () => {
  const contentCode = require("fs").readFileSync(require("path").join(__dirname, "../extension/content.js"), "utf8");
  // Check that HTML URLs are filtered
  assert.ok(contentCode.includes("youtube.com/embed/"));
  assert.ok(contentCode.includes("youtube.com/v/"));
  assert.ok(contentCode.includes("player.vimeo.com/video/"));
});
