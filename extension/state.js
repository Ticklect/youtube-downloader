export const MODES = ["video", "audio", "transcript", "everything"];
export const QUALITIES = ["360", "720", "1080", "best"];
export const THEMES = ["red", "mono"];

export function selectAllVideos(videos) {
  return new Set(videos.map((video) => video.video_id));
}

export function clearSelection() {
  return new Set();
}

export function canStartDownload({ folderPath, selectedIds, helperOnline, downloading, mode, dependencies }) {
  if (!Boolean(folderPath) || selectedIds.size === 0 || !helperOnline || downloading) return false;
  if (!dependencies?.yt_dlp) return false;
  if (mode === "transcript") return true;
  return Boolean(dependencies?.ffmpeg);
}

export function canRetryFailed(job, downloading) {
  if (downloading || job?.status !== "completed") return false;
  return summarizeProgress(job).failed > 0;
}

export function normalizeCurrentJobId(value) {
  if (typeof value !== "string") return null;
  const normalized = value.trim();
  return normalized || null;
}

export function normalizePreferences(raw = {}) {
  return {
    mode: MODES.includes(raw.mode) ? raw.mode : "video",
    quality: QUALITIES.includes(raw.quality) ? raw.quality : "best",
    autoStartHelper: raw.autoStartHelper === false ? false : true,
    theme: THEMES.includes(raw.theme) ? raw.theme : "red",
  };
}

export function normalizeChannelDraft(raw = {}) {
  const videos = Array.isArray(raw.videos)
    ? raw.videos.filter((video) => (
      video
      && typeof video.video_id === "string"
      && typeof video.title === "string"
      && typeof video.url === "string"
    ))
    : [];
  const loadedIds = new Set(videos.map((video) => video.video_id));
  const selectedIds = new Set();
  if (Array.isArray(raw.selectedIds)) {
    for (const id of raw.selectedIds) {
      if (typeof id === "string" && loadedIds.has(id)) selectedIds.add(id);
    }
  }

  return {
    channelUrl: typeof raw.channelUrl === "string" ? raw.channelUrl.trim() : "",
    channelName: typeof raw.channelName === "string" ? raw.channelName : "",
    videos,
    selectedIds,
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
