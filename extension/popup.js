import * as api from "./api.js";
import { getJobOrRecover, retryJobOrRecover } from "./job-lifecycle.js";
import {
  canRetryFailed,
  canStartDownload,
  clearSelection,
  normalizeCurrentJobId,
  normalizePreferences,
  selectAllVideos,
  summarizeProgress,
} from "./state.js";

const $ = (id) => document.getElementById(id);
const els = {
  helperStatus: $("helperStatus"),
  channelUrl: $("channelUrl"),
  loadChannel: $("loadChannel"),
  channelMessage: $("channelMessage"),
  folderPath: $("folderPath"),
  chooseFolder: $("chooseFolder"),
  videoSection: $("videoSection"),
  channelName: $("channelName"),
  selectionCount: $("selectionCount"),
  videoList: $("videoList"),
  selectAll: $("selectAll"),
  clearAll: $("clearAll"),
  mode: $("mode"),
  quality: $("quality"),
  startDownload: $("startDownload"),
  retryFailed: $("retryFailed"),
  progressPanel: $("progressPanel"),
  progressSummary: $("progressSummary"),
  jobItems: $("jobItems"),
  errorMessage: $("errorMessage"),
};

const state = {
  helperOnline: false,
  dependencies: { yt_dlp: false, ffmpeg: false },
  videos: [],
  channelName: "",
  selectedIds: new Set(),
  folderPath: "",
  downloading: false,
  currentJobId: null,
  pollTimer: null,
};

function showError(message) {
  const value = message || "";
  els.errorMessage.textContent = value;
  els.errorMessage.classList.toggle("hidden", !value);
}

function setHelperStatus(kind) {
  const label = kind === "online" ? "Connected" : kind === "limited" ? "Limited" : "Offline";
  els.helperStatus.textContent = label;
  els.helperStatus.className = `status status-${kind}`;
}

function formatDuration(seconds) {
  if (!Number.isFinite(seconds)) return "";
  const totalSeconds = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(totalSeconds / 3600);
  const mins = Math.floor((totalSeconds % 3600) / 60);
  const secs = String(totalSeconds % 60).padStart(2, "0");
  return hours > 0
    ? `${hours}:${String(mins).padStart(2, "0")}:${secs}`
    : `${mins}:${secs}`;
}

function refreshControls() {
  els.folderPath.textContent = state.folderPath || "No folder selected";
  els.selectionCount.textContent = `${state.selectedIds.size} selected`;
  els.startDownload.disabled = !canStartDownload({ ...state, mode: els.mode.value });
  els.startDownload.textContent = state.downloading ? "Downloading..." : "Download Selected";
  els.quality.disabled = !["video", "everything"].includes(els.mode.value);
  els.loadChannel.disabled = !state.helperOnline || !state.dependencies.yt_dlp;
  els.chooseFolder.disabled = !state.helperOnline;
}

function renderVideos() {
  els.videoList.textContent = "";
  const fragment = document.createDocumentFragment();

  for (const video of state.videos) {
    const row = document.createElement("label");
    row.className = "video-card";

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = state.selectedIds.has(video.video_id);
    checkbox.addEventListener("change", () => {
      if (checkbox.checked) state.selectedIds.add(video.video_id);
      else state.selectedIds.delete(video.video_id);
      refreshControls();
    });

    const image = document.createElement("img");
    image.className = "thumb";
    image.alt = "";
    image.loading = "lazy";
    if (video.thumbnail) image.src = video.thumbnail;

    const copy = document.createElement("div");
    copy.className = "video-copy";

    const title = document.createElement("div");
    title.className = "video-title";
    title.textContent = video.title;
    title.title = video.title;

    const meta = document.createElement("div");
    meta.className = "video-meta";
    meta.textContent = [formatDuration(video.duration), video.video_id].filter(Boolean).join(" · ");

    copy.append(title, meta);
    row.append(checkbox, image, copy);
    fragment.append(row);
  }

  els.videoList.append(fragment);
  refreshControls();
}

function renderJob(job) {
  const summary = summarizeProgress(job);
  els.progressPanel.classList.remove("hidden");
  els.progressSummary.textContent = `${summary.done}/${summary.total} done · ${summary.failed} failed`;
  els.jobItems.textContent = "";

  for (const item of job.items || []) {
    const row = document.createElement("div");
    row.className = "job-item";

    const title = document.createElement("div");
    title.className = "job-item-title";
    title.textContent = item.title;

    const status = document.createElement("div");
    status.className = "job-state";
    const percent = item.state === "active" && Number.isFinite(item.percent)
      ? ` ${Math.round(item.percent)}%`
      : "";
    status.textContent = item.state + percent;
    status.title = item.message || "";

    row.append(title, status);
    els.jobItems.append(row);
  }

  els.retryFailed.classList.toggle("hidden", !canRetryFailed(job, state.downloading));
}

async function savePreferences() {
  await chrome.storage.local.set({
    mode: els.mode.value,
    quality: els.quality.value,
    folderPath: state.folderPath,
    currentJobId: state.currentJobId,
  });
}

async function recoverMissingJob() {
  if (state.pollTimer) clearTimeout(state.pollTimer);
  state.currentJobId = null;
  state.downloading = false;
  state.pollTimer = null;
  await savePreferences();
  showError("The previous job is no longer available because the helper was restarted.");
  refreshControls();
}

async function pollJob() {
  if (!state.currentJobId) return;

  try {
    const job = await getJobOrRecover(api, state.currentJobId, recoverMissingJob);
    if (!job) return;
    renderJob(job);

    if (job.status === "completed") {
      state.downloading = false;
      state.pollTimer = null;
      refreshControls();
      renderJob(job);
      return;
    }

    state.pollTimer = setTimeout(pollJob, 1000);
  } catch (error) {
    state.helperOnline = false;
    state.downloading = false;
    state.pollTimer = null;
    setHelperStatus("offline");
    showError(error.message);
    refreshControls();
  }
}

els.loadChannel.addEventListener("click", async () => {
  showError();
  const url = els.channelUrl.value.trim();
  if (!url) {
    showError("Paste a YouTube channel URL first.");
    return;
  }

  els.loadChannel.disabled = true;
  els.channelMessage.textContent = "Loading channel…";

  try {
    const result = await api.loadChannel(url);
    state.videos = result.videos;
    state.channelName = result.channel_name;
    state.selectedIds = clearSelection();
    els.channelName.textContent = result.channel_name;
    els.videoSection.classList.remove("hidden");
    els.channelMessage.textContent = `${result.videos.length} public videos loaded.`;
    renderVideos();
  } catch (error) {
    els.channelMessage.textContent = "";
    showError(error.message);
  } finally {
    refreshControls();
  }
});

els.channelUrl.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !els.loadChannel.disabled) els.loadChannel.click();
});

els.chooseFolder.addEventListener("click", async () => {
  showError();
  try {
    const result = await api.pickFolder();
    if (!result.cancelled && result.path) state.folderPath = result.path;
    await savePreferences();
    refreshControls();
  } catch (error) {
    showError(error.message);
  }
});

els.selectAll.addEventListener("click", () => {
  state.selectedIds = selectAllVideos(state.videos);
  renderVideos();
});

els.clearAll.addEventListener("click", () => {
  state.selectedIds = clearSelection();
  renderVideos();
});

for (const select of [els.mode, els.quality]) {
  select.addEventListener("change", async () => {
    refreshControls();
    await savePreferences();
  });
}

els.startDownload.addEventListener("click", async () => {
  if (!canStartDownload({ ...state, mode: els.mode.value })) return;
  showError();

  const videos = state.videos
    .filter((video) => state.selectedIds.has(video.video_id))
    .map((video) => ({
      video_id: video.video_id,
      url: video.url,
      title: video.title,
      channel_name: state.channelName,
    }));

  try {
    state.downloading = true;
    refreshControls();
    const result = await api.createJob({
      videos,
      mode: els.mode.value,
      quality: els.quality.value,
    });
    state.currentJobId = result.job_id;
    await savePreferences();
    await pollJob();
  } catch (error) {
    state.downloading = false;
    showError(error.message);
    refreshControls();
  }
});

els.retryFailed.addEventListener("click", async () => {
  if (!state.currentJobId) return;

  try {
    state.downloading = true;
    refreshControls();
    const result = await retryJobOrRecover(api, state.currentJobId, recoverMissingJob);
    if (!result) return;
    state.currentJobId = result.job_id;
    await savePreferences();
    await pollJob();
  } catch (error) {
    state.downloading = false;
    showError(error.message);
    refreshControls();
  }
});

async function initialize() {
  const stored = await chrome.storage.local.get(["mode", "quality", "folderPath", "currentJobId"]);
  const prefs = normalizePreferences(stored);
  els.mode.value = prefs.mode;
  els.quality.value = prefs.quality;
  state.folderPath = typeof stored.folderPath === "string" ? stored.folderPath : "";
  state.currentJobId = normalizeCurrentJobId(stored.currentJobId);
  refreshControls();

  try {
    const health = await api.health();
    state.helperOnline = true;
    state.dependencies = {
      yt_dlp: Boolean(health.dependencies?.yt_dlp),
      ffmpeg: Boolean(health.dependencies?.ffmpeg),
    };
    setHelperStatus(health.ok ? "online" : "limited");

    if (!health.ok && health.dependencies?.messages?.length) {
      showError(health.dependencies.messages.join(" "));
    }

    const folder = await api.getFolder();
    state.folderPath = folder.path || "";

    if (state.currentJobId) {
      const job = await getJobOrRecover(api, state.currentJobId, recoverMissingJob);
      if (job) {
        renderJob(job);
        state.downloading = job.status !== "completed";
        if (state.downloading) state.pollTimer = setTimeout(pollJob, 250);
      }
    }

    await savePreferences();
  } catch (error) {
    state.helperOnline = false;
    state.dependencies = { yt_dlp: false, ffmpeg: false };
    setHelperStatus("offline");
    showError(error.message);
  }

  refreshControls();
}

window.addEventListener("unload", () => {
  if (state.pollTimer) clearTimeout(state.pollTimer);
});

initialize();
