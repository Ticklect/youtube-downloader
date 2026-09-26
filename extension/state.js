export const MODES = ["video", "audio", "transcript", "everything"];
export const QUALITIES = ["360", "720", "1080", "best"];

export function selectAllVideos(videos) {
  return new Set(videos.map((video) => video.video_id));
}

export function clearSelection() {
  return new Set();
}

export function canStartDownload({ folderPath, selectedIds, helperOnline, downloading }) {
  return Boolean(folderPath) && selectedIds.size > 0 && helperOnline && !downloading;
}

export function normalizePreferences(raw = {}) {
  return {
    mode: MODES.includes(raw.mode) ? raw.mode : "video",
    quality: QUALITIES.includes(raw.quality) ? raw.quality : "best",
  };
}

export function summarizeProgress(job = {}) {
  const counts = { queued: 0, active: 0, completed: 0, skipped: 0, unavailable: 0, failed: 0 };
  for (const item of job.items || []) {
    if (Object.hasOwn(counts, item.state)) counts[item.state] += 1;
  }
  return {
    total: (job.items || []).length,
    done: counts.completed + counts.skipped + counts.unavailable + counts.failed,
    ...counts,
  };
}
