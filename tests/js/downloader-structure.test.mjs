import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


const downloaderHtml = new URL("../../extension/downloader.html", import.meta.url);
const downloaderCss = new URL("../../extension/downloader.css", import.meta.url);
const downloaderJs = new URL("../../extension/downloader.js", import.meta.url);

const requiredIds = [
  "helperStatus",
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


test("full downloader page retains every workflow control", async () => {
  const html = await readFile(downloaderHtml, "utf8");

  for (const id of requiredIds) {
    assert.match(html, new RegExp(`id=["']${id}["']`), `missing #${id}`);
  }

  assert.match(html, /<label[^>]+for=["']channelUrl["'][^>]*>[^<]*YouTube channel/i);
  assert.match(html, /<script[^>]+type=["']module["'][^>]+src=["']downloader\.js["']/);
});


test("full downloader page preserves output and quality choices", async () => {
  const html = await readFile(downloaderHtml, "utf8");

  for (const mode of ["video", "audio", "transcript", "everything"]) {
    assert.match(html, new RegExp(`<option\\s+value=["']${mode}["']`));
  }

  for (const quality of ["360", "720", "1080", "best"]) {
    assert.match(html, new RegExp(`<option\\s+value=["']${quality}["']`));
  }
});


test("full downloader layout becomes single-column on narrow windows", async () => {
  const css = await readFile(downloaderCss, "utf8");

  assert.match(css, /@media\s*\([^)]*max-width[^)]*\)/);
  assert.match(css, /grid-template-columns\s*:\s*1fr\s*;/);
  assert.doesNotMatch(css, /max-height\s*:\s*260px/);
});


test("full downloader routes polling and retry through shared stale-job recovery", async () => {
  const source = await readFile(downloaderJs, "utf8");

  assert.match(source, /getJobOrRecover/);
  assert.match(source, /retryJobOrRecover/);
  assert.match(source, /helper was restarted/i);
});
