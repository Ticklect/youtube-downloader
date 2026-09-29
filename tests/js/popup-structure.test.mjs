import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";


const popupHtml = new URL("../../extension/popup.html", import.meta.url);
const popupCss = new URL("../../extension/popup.css", import.meta.url);
const popupJs = new URL("../../extension/popup.js", import.meta.url);
const manifestJson = new URL("../../extension/manifest.json", import.meta.url);
const downloaderHtml = new URL("../../extension/downloader.html", import.meta.url);
const downloaderJs = new URL("../../extension/downloader.js", import.meta.url);
const navigationJs = new URL("../../extension/navigation.js", import.meta.url);

const requiredIds = [
  "helperStatus",
  "helperControl",
  "helperToggle",
  "autoStartHelper",
  "helperControlMessage",
  "themeRed",
  "themeMono",
  "channelUrl",
  "loadChannel",
  "channelMessage",
  "folderPath",
  "chooseFolder",
  "videoSection",
  "channelName",
  "selectionCount",
  "videoList",
  "selectAll",
  "clearAll",
  "mode",
  "quality",
  "startDownload",
  "retryFailed",
  "progressPanel",
  "progressSummary",
  "jobItems",
  "errorMessage",
];


test("popup contains the complete downloader workflow", async () => {
  const html = await readFile(popupHtml, "utf8");

  for (const id of requiredIds) {
    assert.match(html, new RegExp(`id=["']${id}["']`), `missing #${id}`);
  }

  assert.doesNotMatch(html, /id=["']openDownloader["']/);
  assert.match(html, /<script[^>]+type=["']module["'][^>]+src=["']popup\.js["']/);
});


test("popup keeps output and quality controls in the main flow", async () => {
  const html = await readFile(popupHtml, "utf8");

  for (const mode of ["video", "audio", "transcript", "everything"]) {
    assert.match(html, new RegExp(`<option\\s+value=["']${mode}["']`));
  }

  for (const quality of ["360", "720", "1080", "best"]) {
    assert.match(html, new RegExp(`<option\\s+value=["']${quality}["']`));
  }
});


test("popup layout is sized for browsing videos without becoming a full page", async () => {
  const css = await readFile(popupCss, "utf8");

  assert.match(css, /\.shell\s*\{[^}]*width\s*:\s*540px/i);
  assert.match(css, /\.shell\s*\{[^}]*max-height\s*:\s*580px/i);
  assert.match(css, /\.video-list\s*\{[^}]*max-height\s*:\s*340px[^}]*overflow-y\s*:\s*auto/i);
  assert.match(css, /\.download-bar\s*\{[^}]*position\s*:\s*sticky/i);
});


test("popup owns job persistence and stale-job recovery", async () => {
  const source = await readFile(popupJs, "utf8");

  assert.match(source, /getJobOrRecover/);
  assert.match(source, /retryJobOrRecover/);
  assert.match(source, /currentJobId/);
  assert.match(source, /chrome\.storage\.local\.get\(\[[^\]]*"currentJobId"[^\]]*\]\)/s);
  assert.doesNotMatch(source, /openOrFocusDownloader/);
});

test("popup persists the loaded channel and selection before opening the native folder picker", async () => {
  const source = await readFile(popupJs, "utf8");

  for (const field of ["channelUrl", "channelName", "videos", "selectedIds"]) {
    assert.match(source, new RegExp(`${field}:`), `missing persisted ${field}`);
  }

  assert.match(source, /await\s+savePreferences\(\);\s*\n\s*const\s+result\s*=\s*await\s+api\.pickFolder\(\)/);
  assert.match(source, /chrome\.storage\.local\.get\(\[[^\]]*"channelUrl"[^\]]*"videos"[^\]]*"selectedIds"[^\]]*\]\)/s);
  assert.match(source, /normalizeChannelDraft\(stored\)/);
});


test("popup uses a flat utility visual system instead of decorative AI-dashboard effects", async () => {
  const html = await readFile(popupHtml, "utf8");
  const css = await readFile(popupCss, "utf8");

  assert.match(html, /id=["']themeRed["']/);
  assert.match(html, /id=["']themeMono["']/);
  assert.match(css, /html\[data-theme=["']red["']\]/);
  assert.match(css, /html\[data-theme=["']mono["']\]/);
  assert.doesNotMatch(css, /linear-gradient|radial-gradient|backdrop-filter/i);
  assert.doesNotMatch(css, /border-radius\s*:\s*999px/i);
  assert.doesNotMatch(html, /class=["'][^"']*brand-mark/);
});


test("extension declares real icon assets for Chrome surfaces", async () => {
  const manifest = JSON.parse(await readFile(manifestJson, "utf8"));
  const expected = {
    "16": "icons/icon16.png",
    "32": "icons/icon32.png",
    "48": "icons/icon48.png",
    "128": "icons/icon128.png",
  };

  assert.deepEqual(manifest.icons, expected);
  assert.deepEqual(manifest.action?.default_icon, expected);

  for (const path of Object.values(expected)) {
    await access(new URL(`../../extension/${path}`, import.meta.url));
  }
});


function relativeLuminance(hex) {
  const value = hex.replace("#", "");
  const full = value.length === 3 ? value.split("").map((part) => part + part).join("") : value;
  const channels = [0, 2, 4].map((offset) => Number.parseInt(full.slice(offset, offset + 2), 16) / 255);
  const linear = channels.map((channel) => (
    channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4
  ));
  return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrastRatio(first, second) {
  const [bright, dark] = [relativeLuminance(first), relativeLuminance(second)].sort((a, b) => b - a);
  return (bright + 0.05) / (dark + 0.05);
}

test("red theme primary button text meets normal-text contrast", async () => {
  const css = await readFile(popupCss, "utf8");
  const redTheme = css.match(/html\[data-theme=["']red["']\]\s*\{([^}]*)\}/i)?.[1] || "";
  const accent = redTheme.match(/--accent\s*:\s*(#[0-9a-f]{3,6})/i)?.[1];
  const ink = redTheme.match(/--accent-ink\s*:\s*(#[0-9a-f]{3,6})/i)?.[1];

  assert.ok(accent, "red theme must define --accent as a hex color");
  assert.ok(ink, "red theme must define --accent-ink as a hex color");
  assert.ok(contrastRatio(accent, ink) >= 4.5, `red primary contrast is ${contrastRatio(accent, ink).toFixed(2)}:1`);
});


test("popup persists and restores the selected appearance theme", async () => {
  const source = await readFile(popupJs, "utf8");

  assert.match(source, /theme:\s*state\.theme/);
  assert.match(source, /"theme"/);
  assert.match(source, /document\.documentElement\.dataset\.theme\s*=\s*theme/);
  assert.match(source, /themeRed\.addEventListener\(["']click["']/);
  assert.match(source, /themeMono\.addEventListener\(["']click["']/);
});


test("sticky download bar summarizes the real selection and destination", async () => {
  const source = await readFile(popupJs, "utf8");

  assert.match(source, /downloadSummary:\s*\$\(["']downloadSummary["']\)/);
  assert.match(source, /selectedCount.*selected.*folderPath/s);
  assert.match(source, /els\.downloadSummary\.textContent/);
});

test("popup exposes manual helper control and auto-start preference", async () => {
  const html = await readFile(popupHtml, "utf8");
  const source = await readFile(popupJs, "utf8");

  assert.match(html, /Auto-start when needed/);
  assert.match(html, /id=["']helperToggle["']/);
  assert.match(html, /id=["']autoStartHelper["']/);
  assert.match(source, /autoStartHelper:\s*state\.autoStartHelper/);
  assert.match(source, /"autoStartHelper"/);
  assert.match(source, /sendControlCommand\(chrome,\s*["']start["']\)/);
  assert.match(source, /sendControlCommand\(chrome,\s*["']stop["']\)/);
});


test("full-page downloader and launcher navigation are removed", async () => {
  await assert.rejects(access(downloaderHtml));
  await assert.rejects(access(downloaderJs));
  await assert.rejects(access(navigationJs));
});
