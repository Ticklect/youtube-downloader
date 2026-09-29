import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


const popupHtml = new URL("../../extension/popup.html", import.meta.url);
const popupJs = new URL("../../extension/popup.js", import.meta.url);


test("popup is a compact launcher instead of the full downloader", async () => {
  const html = await readFile(popupHtml, "utf8");

  for (const id of ["openDownloader", "helperStatus", "helperMessage"]) {
    assert.match(html, new RegExp(`id=["']${id}["']`));
  }

  for (const removedId of ["channelUrl", "videoList", "startDownload"]) {
    assert.doesNotMatch(html, new RegExp(`id=["']${removedId}["']`));
  }

  assert.match(html, /<script[^>]+type=["']module["'][^>]+src=["']popup\.js["']/);
});


test("popup launcher uses shared downloader navigation", async () => {
  const source = await readFile(popupJs, "utf8");

  assert.match(source, /import\s*\{\s*openOrFocusDownloader\s*\}\s*from\s*["']\.\/navigation\.js["']/);
  assert.match(source, /openDownloader\.addEventListener\(["']click["']/);
  assert.match(source, /openOrFocusDownloader\(chrome\)/);
});


test("offline popup keeps the launcher usable and explains how to start the helper", async () => {
  const html = await readFile(popupHtml, "utf8");
  const source = await readFile(popupJs, "utf8");

  assert.doesNotMatch(html, /id=["']openDownloader["'][^>]*disabled/);
  assert.doesNotMatch(source, /openDownloader\.disabled\s*=\s*true/);
  assert.match(source, /Offline/);
  assert.match(source, /start-helper\.ps1/);
});
