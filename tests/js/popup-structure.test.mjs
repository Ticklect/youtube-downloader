import test from "node:test";
import assert from "node:assert/strict";
import { access, readFile } from "node:fs/promises";


const popupHtml = new URL("../../extension/popup.html", import.meta.url);
const popupCss = new URL("../../extension/popup.css", import.meta.url);
const popupJs = new URL("../../extension/popup.js", import.meta.url);
const downloaderHtml = new URL("../../extension/downloader.html", import.meta.url);
const downloaderJs = new URL("../../extension/downloader.js", import.meta.url);
const navigationJs = new URL("../../extension/navigation.js", import.meta.url);

const requiredIds = [
  "helperStatus",
  "helperControl",
  "helperToggle",
  "autoStartHelper",
  "helperControlMessage",
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
