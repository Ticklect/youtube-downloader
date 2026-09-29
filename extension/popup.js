import * as api from "./api.js";
import { getJobOrRecover, retryJobOrRecover } from "./job-lifecycle.js";
import { ensureHelperReady, requireHelperStopped, sendControlCommand, waitForHelper } from "./helper-control.js";
import {
  canRetryFailed,
  canStartDownload,
  clearSelection,
  normalizeChannelDraft,
  normalizeCurrentJobId,
  normalizePreferences,
  selectAllVideos,
  summarizeProgress,
} from "./state.js";

const $ = (id) => document.getElementById(id);
const els = {
  helperStatus: $("helperStatus"),
  helperControl: $("helperControl"),
  helperToggle: $("helperToggle"),
  autoStartHelper: $("autoStartHelper"),
  helperControlMessage: $("helperControlMessage"),
  themeRed: $("themeRed"),
  themeMono: $("themeMono"),
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
  downloadSummary: $("downloadSummary"),
  progressPanel: $("progressPanel"),
  progressSummary: $("progressSummary"),
  jobItems: $("jobItems"),
  errorMessage: $("errorMessage"),
};

const state = {
  helperOnline: false,
  helperControlAvailable: true,
  helperOwned: false,
  helperTransition: null,
  autoStartHelper: true,
  theme: "red",
  dependencies: { yt_dlp: false, ffmpeg: false },
  channelUrl: "",
  videos: [],
  channelName: "",
  selectedIds: new Set(),
  folderPath: "",
  downloading: false,
  currentJobId: null,
  pollTimer: null,
};

function applyTheme(theme) {
  state.theme = theme;
  document.documentElement.dataset.theme = theme;
  els.themeRed.setAttribute("aria-pressed", String(theme === "red"));
  els.themeMono.setAttribute("aria-pressed", String(theme === "mono"));
}

function showError(message) {
  const value = message || "";
  els.errorMessage.textContent = value;
  els.errorMessage.classList.toggle("hidden", !value);
}

function setHelperStatus(kind) {
  const labels = {
    online: "Connected",
    limited: "Limited",
    offline: "Helper Off",
    starting: "Starting…",
    stopping: "Stopping…",
    "control-missing": "Control not installed",
  };
  const label = labels[kind] || "Helper Off";
  els.helperStatus.textContent = label;
  els.helperStatus.className = `status status-${kind}`;
}

function applyHealth(health) {
  if (health?.service !== "youtube-channel-downloader") return false;
  state.helperOnline = true;
  state.dependencies = {
    yt_dlp: Boolean(health.dependencies?.yt_dlp),
    ffmpeg: Boolean(health.dependencies?.ffmpeg),
  };
  setHelperStatus(health.ok ? "online" : "limited");
  return true;
}

function markHelperOff() {
  state.helperOnline = false;
  state.dependencies = { yt_dlp: false, ffmpeg: false };
  setHelperStatus(state.helperControlAvailable ? "offline" : "control-missing");
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
  const autoStartAvailable = state.autoStartHelper && state.helperControlAvailable && !state.helperTransition;
  const helperCanStart = state.helperOnline || autoStartAvailable;
  const baseDownloadReady = Boolean(state.folderPath) && state.selectedIds.size > 0 && !state.downloading;
  els.startDownload.disabled = state.helperOnline
    ? !canStartDownload({ ...state, mode: els.mode.value })
    : !(baseDownloadReady && autoStartAvailable);
  const selectedCount = state.selectedIds.size;
  const destination = state.folderPath || "Choose a folder";
  els.downloadSummary.textContent = `${selectedCount} selected · ${destination}`;
  els.downloadSummary.title = els.downloadSummary.textContent;
  els.startDownload.textContent = state.downloading
    ? "Downloading…"
    : selectedCount > 0
      ? `Download ${selectedCount} video${selectedCount === 1 ? "" : "s"}`
      : "Download selected";
  els.quality.disabled = !["video", "everything"].includes(els.mode.value);
  els.loadChannel.disabled = Boolean(state.helperTransition) || !helperCanStart || (state.helperOnline && !state.dependencies.yt_dlp);
  els.chooseFolder.disabled = Boolean(state.helperTransition) || !helperCanStart;
  els.autoStartHelper.checked = state.autoStartHelper;
  els.helperToggle.disabled = Boolean(state.helperTransition) || state.downloading || !state.helperControlAvailable;
  els.helperToggle.textContent = state.helperTransition === "starting"
    ? "Starting…"
    : state.helperTransition === "stopping"
      ? "Stopping…"
      : state.helperOnline
        ? "Turn Off"
        : "Turn On";

  if (!state.helperControlAvailable) {
    els.helperControlMessage.textContent = "Helper control not installed. Run scripts/setup.ps1 once.";
  } else if (state.helperOnline) {
    els.helperControlMessage.textContent = state.autoStartHelper
      ? "Connected. Auto-start is enabled for future use."
      : "Connected. Manual mode is enabled.";
  } else if (state.autoStartHelper) {
    els.helperControlMessage.textContent = "Helper is off. It will start automatically when needed.";
  } else {
    els.helperControlMessage.textContent = "Helper is off. Press Turn On to use the downloader.";
  }
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
    checkbox.addEventListener("change", async () => {
      if (checkbox.checked) state.selectedIds.add(video.video_id);
      else state.selectedIds.delete(video.video_id);
      refreshControls();
      await savePreferences();
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
    autoStartHelper: state.autoStartHelper,
    theme: state.theme,
    folderPath: state.folderPath,
    currentJobId: state.currentJobId,
    channelUrl: state.channelUrl,
    channelName: state.channelName,
    videos: state.videos,
    selectedIds: [...state.selectedIds],
  });
}

async function requireHelper(actionName) {
  const shouldShowStarting = !state.helperOnline && state.autoStartHelper;
  if (shouldShowStarting) {
    state.helperTransition = "starting";
    setHelperStatus("starting");
    refreshControls();
  }
  try {
    const result = await ensureHelperReady({
      api,
      chromeApi: chrome,
      autoStart: state.autoStartHelper,
    });
    if (!applyHealth(result.health)) throw new Error("Unexpected helper service responded on the local port.");
    if (result.started) {
      state.helperControlAvailable = true;
      state.helperOwned = true;
    }
    state.helperTransition = null;
    refreshControls();
    return true;
  } catch (error) {
    state.helperTransition = null;
    if (error?.code === "native_host_missing") state.helperControlAvailable = false;
    markHelperOff();
    showError(error?.message || `${actionName} needs the local helper.`);
    refreshControls();
    return false;
  }
}

async function inspectHelperControl() {
  let health = null;
  try {
    health = await api.health();
  } catch {
    health = null;
  }
  if (!applyHealth(health)) markHelperOff();

  try {
    const status = await sendControlCommand(chrome, "status");
    state.helperControlAvailable = true;
    state.helperOwned = Boolean(status.owned);
    if (!state.helperOnline && status.healthy) {
      const ready = await waitForHelper(api, { attempts: 4, delayMs: 75 });
      applyHealth(ready);
    }
  } catch (error) {
    if (error?.code === "native_host_missing") {
      state.helperControlAvailable = false;
      if (!state.helperOnline) setHelperStatus("control-missing");
    }
  }
  refreshControls();
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
    if (!(await requireHelper("load"))) {
      els.channelMessage.textContent = "";
      return;
    }
    if (!state.dependencies.yt_dlp) throw new Error("yt-dlp is not installed. Run scripts/setup.ps1.");
    const result = await api.loadChannel(url);
    state.channelUrl = url;
    state.videos = result.videos;
    state.channelName = result.channel_name;
    state.selectedIds = clearSelection();
    els.channelName.textContent = result.channel_name;
    els.videoSection.classList.remove("hidden");
    els.channelMessage.textContent = `${result.videos.length} public videos loaded.`;
    renderVideos();
    await savePreferences();
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
    await savePreferences();
    if (!(await requireHelper("choose folder"))) return;
    await savePreferences();
    const result = await api.pickFolder();
    if (!result.cancelled && result.path) state.folderPath = result.path;
    await savePreferences();
    refreshControls();
  } catch (error) {
    showError(error.message);
  }
});

els.selectAll.addEventListener("click", async () => {
  state.selectedIds = selectAllVideos(state.videos);
  renderVideos();
  await savePreferences();
});

els.clearAll.addEventListener("click", async () => {
  state.selectedIds = clearSelection();
  renderVideos();
  await savePreferences();
});

for (const select of [els.mode, els.quality]) {
  select.addEventListener("change", async () => {
    refreshControls();
    await savePreferences();
  });
}

els.themeRed.addEventListener("click", async () => {
  applyTheme("red");
  await savePreferences();
});

els.themeMono.addEventListener("click", async () => {
  applyTheme("mono");
  await savePreferences();
});

els.autoStartHelper.addEventListener("change", async () => {
  state.autoStartHelper = els.autoStartHelper.checked;
  refreshControls();
  await savePreferences();
});

els.helperToggle.addEventListener("click", async () => {
  showError();
  if (state.downloading) {
    showError("Wait for the current download to finish before turning the helper off.");
    return;
  }
  if (state.helperTransition) return;

  if (state.helperOnline) {
    state.helperTransition = "stopping";
    setHelperStatus("stopping");
    refreshControls();
    try {
      requireHelperStopped(await sendControlCommand(chrome, "stop"));
      state.helperOwned = false;
      state.helperTransition = null;
      markHelperOff();
    } catch (error) {
      state.helperTransition = null;
      if (error?.code === "native_host_missing") state.helperControlAvailable = false;
      showError(error?.message || "Could not stop helper.");
    }
    refreshControls();
    return;
  }

  state.helperTransition = "starting";
  setHelperStatus("starting");
  refreshControls();
  try {
    const result = await sendControlCommand(chrome, "start");
    state.helperControlAvailable = true;
    state.helperOwned = Boolean(result.owned);
    const health = await waitForHelper(api);
    applyHealth(health);
  } catch (error) {
    if (error?.code === "native_host_missing") state.helperControlAvailable = false;
    markHelperOff();
    showError(error?.message || "Could not start helper.");
  } finally {
    state.helperTransition = null;
    refreshControls();
  }
});

els.startDownload.addEventListener("click", async () => {
  if (!state.folderPath || state.selectedIds.size === 0 || state.downloading) return;
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
    if (!(await requireHelper("download"))) return;
    if (!canStartDownload({ ...state, mode: els.mode.value })) {
      throw new Error(els.mode.value === "transcript"
        ? "yt-dlp is not installed. Run scripts/setup.ps1."
        : "FFmpeg or yt-dlp is unavailable. Run scripts/setup.ps1.");
    }
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
    if (!(await requireHelper("retry"))) return;
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
  const stored = await chrome.storage.local.get([
    "mode",
    "quality",
    "autoStartHelper",
    "theme",
    "folderPath",
    "currentJobId",
    "channelUrl",
    "channelName",
    "videos",
    "selectedIds",
  ]);
  const prefs = normalizePreferences(stored);
  const draft = normalizeChannelDraft(stored);
  els.mode.value = prefs.mode;
  els.quality.value = prefs.quality;
  state.autoStartHelper = prefs.autoStartHelper;
  els.autoStartHelper.checked = prefs.autoStartHelper;
  applyTheme(prefs.theme);
  state.folderPath = typeof stored.folderPath === "string" ? stored.folderPath : "";
  state.currentJobId = normalizeCurrentJobId(stored.currentJobId);
  state.channelUrl = draft.channelUrl;
  state.channelName = draft.channelName;
  state.videos = draft.videos;
  state.selectedIds = draft.selectedIds;
  els.channelUrl.value = draft.channelUrl;
  if (draft.videos.length) {
    els.channelName.textContent = draft.channelName || "Channel";
    els.videoSection.classList.remove("hidden");
    els.channelMessage.textContent = `${draft.videos.length} public videos loaded.`;
    renderVideos();
  }
  refreshControls();

  await inspectHelperControl();

  if (state.helperOnline) {
    try {
      const health = await api.health();
      applyHealth(health);
      if (!health.ok && health.dependencies?.messages?.length) {
        showError(health.dependencies.messages.join(" "));
      }
      const folder = await api.getFolder();
      state.folderPath = folder.path || state.folderPath;

      if (state.currentJobId) {
        const job = await getJobOrRecover(api, state.currentJobId, recoverMissingJob);
        if (job) {
          state.downloading = job.status !== "completed";
          renderJob(job);
          if (state.downloading) state.pollTimer = setTimeout(pollJob, 250);
        }
      }
    } catch (error) {
      markHelperOff();
      showError(error.message);
    }
  }

  await savePreferences();

  refreshControls();
}

window.addEventListener("unload", () => {
  if (state.pollTimer) clearTimeout(state.pollTimer);
});

initialize();
