import test from "node:test";
import assert from "node:assert/strict";

import {
  canRetryFailed,
  canStartDownload,
  clearSelection,
  normalizeCurrentJobId,
  normalizePreferences,
  selectAllVideos,
  summarizeProgress,
} from "../../extension/state.js";


test("select all and clear selection use video ids", () => {
  const videos = [{ video_id: "a" }, { video_id: "b" }];
  assert.deepEqual([...selectAllVideos(videos)], ["a", "b"]);
  assert.deepEqual([...clearSelection()], []);
});

test("download stays disabled without folder selection or helper connectivity", () => {
  const base = {
    folderPath: "C:/Downloads",
    selectedIds: new Set(["a"]),
    helperOnline: true,
    downloading: false,
    mode: "video",
    dependencies: { yt_dlp: true, ffmpeg: true },
  };
  assert.equal(canStartDownload(base), true);
  assert.equal(canStartDownload({ ...base, folderPath: "" }), false);
  assert.equal(canStartDownload({ ...base, selectedIds: new Set() }), false);
  assert.equal(canStartDownload({ ...base, helperOnline: false }), false);
  assert.equal(canStartDownload({ ...base, downloading: true }), false);
});

test("dependency capabilities allow transcript without ffmpeg but block media", () => {
  const base = {
    folderPath: "C:/Downloads",
    selectedIds: new Set(["a"]),
    helperOnline: true,
    downloading: false,
    dependencies: { yt_dlp: true, ffmpeg: false },
  };
  assert.equal(canStartDownload({ ...base, mode: "transcript" }), true);
  assert.equal(canStartDownload({ ...base, mode: "video" }), false);
  assert.equal(canStartDownload({ ...base, mode: "audio" }), false);
  assert.equal(canStartDownload({ ...base, mode: "everything" }), false);
  assert.equal(canStartDownload({ ...base, mode: "transcript", dependencies: { yt_dlp: false, ffmpeg: true } }), false);
});

test("current job id normalization keeps only non-empty strings", () => {
  assert.equal(normalizeCurrentJobId(" job-123 "), "job-123");
  assert.equal(normalizeCurrentJobId(""), null);
  assert.equal(normalizeCurrentJobId(123), null);
});

test("remembered preferences are normalized to supported values", () => {
  assert.deepEqual(normalizePreferences({ mode: "audio", quality: "1080" }), { mode: "audio", quality: "1080" });
  assert.deepEqual(normalizePreferences({ mode: "wat", quality: "4k" }), { mode: "video", quality: "best" });
});

test("progress summary covers every terminal and active state", () => {
  const summary = summarizeProgress({
    items: [
      { state: "queued" },
      { state: "active" },
      { state: "completed" },
      { state: "skipped" },
      { state: "unavailable" },
      { state: "failed" },
    ],
  });
  assert.deepEqual(summary, { total: 6, done: 4, queued: 1, active: 1, completed: 1, skipped: 1, unavailable: 1, failed: 1 });
});

test("retry failed is only available after the job has completed", () => {
  const runningWithFailure = {
    status: "running",
    items: [{ state: "failed" }, { state: "active" }],
  };
  const completedWithFailure = {
    status: "completed",
    items: [{ state: "failed" }, { state: "completed" }],
  };

  assert.equal(canRetryFailed(runningWithFailure, false), false);
  assert.equal(canRetryFailed(completedWithFailure, true), false);
  assert.equal(canRetryFailed(completedWithFailure, false), true);
  assert.equal(canRetryFailed({ status: "completed", items: [{ state: "completed" }] }, false), false);
});
