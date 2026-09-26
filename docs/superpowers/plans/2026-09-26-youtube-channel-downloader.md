# YouTube Channel Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a private Windows Chrome extension plus localhost Python helper that loads a public YouTube channel, lets the user choose individual/all videos, choose a download folder, and download permitted video, MP3 audio, captions/transcripts, or everything with progress and duplicate protection.

**Architecture:** A Manifest V3 extension provides the UI and stores lightweight preferences in `chrome.storage.local`. A Flask helper bound to `127.0.0.1` owns channel discovery, the native folder picker, yt-dlp/FFmpeg execution, output-path safety, transcript conversion, job state, and duplicate archives; the extension communicates with it over a narrow localhost JSON API.

**Tech Stack:** Chrome Manifest V3, vanilla HTML/CSS/JavaScript, Python 3.11+, Flask, pytest, yt-dlp, FFmpeg, Windows PowerShell, tkinter folder picker.

**Spec:** `docs/superpowers/specs/2026-09-26-youtube-channel-downloader-design.md`

## Global Constraints

- Private/local single-user tool only; no cloud service, accounts, sync, or remote backend.
- Helper must bind only to `127.0.0.1` on a fixed local port.
- Accept public YouTube channel/video content only; no account login, member-only/private access, or DRM circumvention.
- Download modes: `video`, `audio`, `transcript`, `everything`.
- Video quality choices: `360`, `720`, `1080`, `best`.
- User chooses the download root through the native Windows folder picker; requests cannot inject arbitrary per-file paths.
- Store independent duplicate archives for video, audio, and transcript artifacts beneath the chosen root.
- Transcript retrieval prefers creator captions, then automatic captions; save `.vtt` plus cleaned `.txt`; unavailable captions are a non-fatal per-item state.
- One failed item must not cancel the rest of the queue.
- Browser requests must have a `chrome-extension://` origin and a custom state-changing request header; CORS preflight must allow only the local API's required methods/headers.
- Process arguments must be passed without shell string concatenation.
- Tests must mock yt-dlp/FFmpeg and must not bulk-download real media.

## Review Focus

- Malformed/non-YouTube URLs: reject with a clear 400 response and never spawn yt-dlp. Covered in Task 2 API and channel tests.
- Folder becomes deleted or unwritable after selection: reject job start without touching files outside the chosen root. Covered in Task 3 settings/path tests and Task 6 API tests.
- A video title contains Windows-reserved characters/names: sanitize deterministically while keeping the video ID suffix. Covered in Task 4 downloader tests.
- Helper restarts while the extension still has stale state: health check must recover gracefully and persisted folder/options must reload independently of in-memory jobs. Covered in Tasks 3, 6, and 7.
- Mixed queue where one item is private/deleted or FFmpeg fails: only that artifact/item fails; later items continue. Covered in Task 5 job tests.

---

### Task 1: Project Scaffolding and Dependency Checks

**Files:**
- Create: `helper/__init__.py`
- Create: `helper/dependencies.py`
- Create: `helper/requirements.txt`
- Create: `tests/test_dependencies.py`
- Create: `scripts/setup.ps1`
- Create: `scripts/start-helper.ps1`
- Create: `pytest.ini`
- Create: `README.md`

**Interfaces:**
- Produces: `DependencyStatus` dataclass and `check_dependencies() -> DependencyStatus` for later health/API use.
- Produces: repeatable PowerShell setup/start commands documented in README.

- [ ] **Step 1: Write failing dependency tests**

Create tests asserting `check_dependencies()` reports Python yt-dlp availability separately from FFmpeg and returns human-readable missing-dependency messages without raising.

- [ ] **Step 2: Run the dependency tests and verify failure**

Run: `python -m pytest tests/test_dependencies.py -v`

Expected: FAIL because `helper.dependencies` does not exist.

- [ ] **Step 3: Implement dependency checks and requirements**

Implement `DependencyStatus(yt_dlp: bool, ffmpeg: bool, messages: list[str])` and `check_dependencies() -> DependencyStatus`. Detect yt-dlp with `importlib.util.find_spec("yt_dlp")`; detect FFmpeg with `shutil.which("ffmpeg")`.

- [ ] **Step 4: Add Windows setup/start scripts and README bootstrap instructions**

`setup.ps1` creates `.venv`, installs `helper/requirements.txt`, verifies FFmpeg, and prints exact next steps. `start-helper.ps1` activates `.venv` and starts `python -m helper.app`.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_dependencies.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add helper tests scripts pytest.ini README.md
git commit -m "chore: scaffold local downloader helper"
```

### Task 2: Channel URL Validation and Discovery

**Files:**
- Create: `helper/channel.py`
- Create: `tests/test_channel.py`

**Interfaces:**
- Consumes: Python yt-dlp package from Task 1.
- Produces: `normalize_channel_url(url: str) -> str`.
- Produces: `load_channel(url: str) -> ChannelResult` where `ChannelResult` contains `channel_name: str` and `videos: list[VideoInfo]`.
- Produces: `VideoInfo(video_id: str, title: str, url: str, thumbnail: str | None, duration: int | None)`.

- [ ] **Step 1: Write failing URL tests**

Cover accepted `youtube.com/@handle`, `/channel/...`, `/c/...`, `/user/...`, and channel `/videos` URLs; reject blank input, non-HTTP(S), non-YouTube hosts, single watch URLs, and malformed URLs.

- [ ] **Step 2: Write failing discovery normalization tests**

Mock yt-dlp metadata and assert channel name plus stable `VideoInfo` objects are returned; skip malformed playlist entries instead of crashing the entire load.

- [ ] **Step 3: Run tests and verify failure**

Run: `python -m pytest tests/test_channel.py -v`

Expected: FAIL because channel functions are missing.

- [ ] **Step 4: Implement channel validation and discovery**

Use yt-dlp's Python API in flat-playlist/extract-flat mode with no download. Normalize to the channel videos page when appropriate and never invoke a shell.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_channel.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add helper/channel.py tests/test_channel.py
git commit -m "feat: load public youtube channel metadata"
```

### Task 3: Folder Picker, Persistence, and Root Safety

**Files:**
- Create: `helper/settings.py`
- Create: `tests/test_settings.py`

**Interfaces:**
- Produces: `pick_download_root() -> Path | None` using `tkinter.filedialog.askdirectory`.
- Produces: `validate_download_root(path: Path) -> Path` that resolves, verifies directory existence, and verifies writability.
- Produces: `SettingsStore(path: Path)` with `load() -> dict`, `save_download_root(path: Path) -> None`, and `get_download_root() -> Path | None`.
- Produces: `safe_child(root: Path, *parts: str) -> Path` that guarantees the resolved result remains under `root`.

- [ ] **Step 1: Write failing persistence and root-safety tests**

Assert a selected root survives a new `SettingsStore` instance, missing/corrupt JSON falls back safely, unwritable/nonexistent paths are rejected, and traversal such as `..` cannot escape the chosen root.

- [ ] **Step 2: Write failing stale-folder test**

Persist a valid folder, delete it, then assert `get_download_root()` returns no usable root until the user chooses again.

- [ ] **Step 3: Run tests and verify failure**

Run: `python -m pytest tests/test_settings.py -v`

Expected: FAIL because settings module is missing.

- [ ] **Step 4: Implement folder picking, persistence, and safe path joining**

Store helper settings in `%LOCALAPPDATA%/YouTubeChannelDownloader/settings.json` by default; permit a test-injected path. Use a small write/delete probe to verify folder writability.

- [ ] **Step 5: Run tests**

Run: `python -m pytest tests/test_settings.py -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add helper/settings.py tests/test_settings.py
git commit -m "feat: add download folder selection and persistence"
```

### Task 4: Download Planning, Paths, Archives, and Transcript Conversion

**Files:**
- Create: `helper/downloader.py`
- Create: `helper/transcripts.py`
- Create: `tests/test_downloader.py`
- Create: `tests/test_transcripts.py`

**Interfaces:**
- Consumes: `safe_child()` and validated root from Task 3.
- Produces: `sanitize_component(value: str) -> str` for Windows-safe channel/video folder names.
- Produces: `build_video_dir(root: Path, channel: str, title: str, video_id: str) -> Path`.
- Produces: `build_ydl_options(mode: str, quality: str, output_dir: Path) -> dict`.
- Produces: `ArtifactArchives(root: Path)` with `contains(kind: str, video_id: str) -> bool` and `mark_complete(kind: str, video_id: str) -> None` for `video|audio|transcript`.
- Produces: `vtt_to_text(vtt: str) -> str`.

- [ ] **Step 1: Write failing path sanitization tests**

Cover `<>:"/\\|?*`, trailing dots/spaces, Windows device names such as `CON`, duplicate titles, very long titles, and verify `[video_id]` remains in the folder name.

- [ ] **Step 2: Write failing quality/output option tests**

For each quality (`360`, `720`, `1080`, `best`) assert generated yt-dlp options cap height correctly for video, use MP3 post-processing for audio, request preferred/manual then automatic subtitles for transcripts, and combine all required outputs for `everything`.

- [ ] **Step 3: Write failing archive separation tests**

Mark `video` complete for one ID and assert `audio` and `transcript` remain incomplete. Assert unavailable transcripts are not marked complete.

- [ ] **Step 4: Write failing VTT conversion tests**

Assert WEBVTT headers, timestamps, cue indices, HTML-like tags, and duplicate adjacent caption lines are removed while readable text order remains.

- [ ] **Step 5: Run tests and verify failure**

Run: `python -m pytest tests/test_downloader.py tests/test_transcripts.py -v`

Expected: FAIL because implementation is missing.

- [ ] **Step 6: Implement path, options, archives, and transcript conversion**

Use yt-dlp option dictionaries rather than shell command strings. Keep archive files at `<root>/.youtube-channel-downloader/archive-{kind}.txt`.

- [ ] **Step 7: Run tests**

Run: `python -m pytest tests/test_downloader.py tests/test_transcripts.py -v`

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add helper/downloader.py helper/transcripts.py tests/test_downloader.py tests/test_transcripts.py
git commit -m "feat: plan safe media and transcript outputs"
```

### Task 5: Download Execution and Job State

**Files:**
- Create: `helper/jobs.py`
- Modify: `helper/downloader.py`
- Create: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `VideoInfo`, validated root, yt-dlp options, artifact archives, and transcript conversion.
- Produces: `DownloadRequest(video_id: str, url: str, title: str, channel_name: str, mode: str, quality: str)`.
- Produces: `JobManager(max_workers: int = 2)` with `create_job(items: list[DownloadRequest], root: Path) -> str`, `get_job(job_id: str) -> dict`, and `retry_failed(job_id: str) -> str`.
- Produces: item states `queued|active|completed|skipped|unavailable|failed` and aggregate counts.
- Produces: `download_item(request: DownloadRequest, root: Path, progress_cb: Callable[[dict], None]) -> ItemResult`.

- [ ] **Step 1: Write failing state-transition tests**

Assert jobs begin queued, transition active, then completed/skipped/unavailable/failed, expose aggregate counts, and reject unknown job IDs cleanly.

- [ ] **Step 2: Write failing failure-isolation test**

Mock three items where the middle yt-dlp/FFmpeg operation raises; assert first and third complete and only the middle item fails.

- [ ] **Step 3: Write failing duplicate and retry tests**

Assert requested artifact kinds already in their archive are skipped, failed artifacts are not archived, and `retry_failed()` creates a new job containing only retryable failed items.

- [ ] **Step 4: Run tests and verify failure**

Run: `python -m pytest tests/test_jobs.py -v`

Expected: FAIL because jobs are missing.

- [ ] **Step 5: Implement bounded-concurrency job manager and item executor**

Use `ThreadPoolExecutor(max_workers=2)`; guard shared state with a lock. Catch exceptions per item. Use yt-dlp progress hooks to update percentage/status but keep tests independent of live downloads.

- [ ] **Step 6: Run tests**

Run: `python -m pytest tests/test_jobs.py tests/test_downloader.py -v`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add helper/jobs.py helper/downloader.py tests/test_jobs.py
git commit -m "feat: add resilient download job queue"
```

### Task 6: Localhost HTTP API and Security Boundary

**Files:**
- Create: `helper/app.py`
- Create: `tests/test_api.py`

**Interfaces:**
- Consumes: Tasks 1-5 services.
- Produces Flask routes: `GET /health`, `POST /channel`, `POST /folder/pick`, `GET /folder`, `POST /jobs`, `GET /jobs/<job_id>`, `POST /jobs/<job_id>/retry`.
- Produces JSON error shape: `{ "error": { "code": str, "message": str } }`.

- [ ] **Step 1: Write failing health, origin/header, and preflight tests**

Assert `/health` reports dependency status. Reject normal web origins, missing/invalid `Origin`, and state-changing requests without `X-YCD-Client: 1`; allow `chrome-extension://<id>` origins. Assert `OPTIONS` preflight allows only the required localhost methods and `Content-Type, X-YCD-Client` headers for accepted extension origins.

- [ ] **Step 2: Write failing channel/folder/job API tests**

Mock services and assert invalid channel URLs produce 400, no-videos produces a clear response, cancelled folder picker leaves existing settings untouched, stale/unwritable roots reject job creation, and valid job requests return a job ID.

- [ ] **Step 3: Run tests and verify failure**

Run: `python -m pytest tests/test_api.py -v`

Expected: FAIL because the Flask app is missing.

- [ ] **Step 4: Implement Flask app and request validation**

Bind with `app.run(host="127.0.0.1", port=17865, threaded=True)`. Add narrow CORS response headers only for accepted Chrome-extension origins. Validate JSON schemas manually with small explicit validators; do not expose a generic command/run endpoint.

- [ ] **Step 5: Run API tests and full helper suite**

Run: `python -m pytest -v`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add helper/app.py tests/test_api.py
git commit -m "feat: expose secure localhost downloader api"
```

### Task 7: Chrome Extension UI, Preferences, and Progress

**Files:**
- Create: `extension/manifest.json`
- Create: `extension/popup.html`
- Create: `extension/popup.css`
- Create: `extension/api.js`
- Create: `extension/state.js`
- Create: `extension/popup.js`
- Create: `tests/js/ui.test.mjs`
- Create: `package.json`

**Interfaces:**
- Consumes: Task 6 API at `http://127.0.0.1:17865`.
- Produces: `api.js` functions `health()`, `loadChannel(url)`, `pickFolder()`, `getFolder()`, `createJob(payload)`, `getJob(id)`, `retryJob(id)`.
- Produces: pure `state.js` functions for selection, enable/disable rules, progress summaries, and preference normalization.
- Produces: popup state for selected video IDs, output mode, quality, folder path, current job, and polling lifecycle.

- [ ] **Step 1: Write failing JavaScript state/render tests**

Using Node's built-in test runner against pure `state.js` functions, assert Select All/Clear All behavior, start button disable rules (no folder/no selection/helper offline), normalized remembered `mode` and `quality`, and progress summaries for queued/active/completed/skipped/unavailable/failed.

- [ ] **Step 2: Run JS tests and verify failure**

Run: `npm test`

Expected: FAIL because extension modules do not exist.

- [ ] **Step 3: Implement Manifest V3 and localhost API client**

Declare only required permissions: `storage` and host permission for `http://127.0.0.1:17865/*`. Every state-changing request includes `X-YCD-Client: 1`.

- [ ] **Step 4: Implement popup UI and preference restoration**

Render channel URL input, folder chooser/current path, selectable video cards, select/clear controls, output and quality selectors, Download, Retry Failed, helper-status/errors, and progress panel. Store output mode, quality, and the last folder path as cached UI preferences in `chrome.storage.local`; helper remains authoritative for folder validity and jobs.

- [ ] **Step 5: Implement polling lifecycle**

Poll active jobs roughly once per second, stop polling after terminal state or popup teardown, and handle helper restarts by showing a clear disconnected state rather than throwing uncaught errors.

- [ ] **Step 6: Run JS tests**

Run: `npm test`

Expected: PASS.

- [ ] **Step 7: Commit**

```bash
git add extension tests/js package.json
git commit -m "feat: add chrome downloader interface"
```

### Task 8: End-to-End Verification and User Setup Polish

**Files:**
- Modify: `README.md`
- Modify: `scripts/setup.ps1`
- Create: `tests/test_smoke_contract.py`

**Interfaces:**
- Consumes: complete helper and extension.
- Produces: one documented setup path from fresh clone to running helper + loaded unpacked extension.

- [ ] **Step 1: Add a smoke-contract test**

Assert extension API route names match Flask routes, fixed port `17865` matches manifest/API code, required output modes and quality values match across UI and helper, and project files referenced by README exist.

- [ ] **Step 2: Run all automated tests**

Run: `python -m pytest -v`

Expected: PASS.

Run: `npm test`

Expected: PASS.

- [ ] **Step 3: Run static/syntax checks**

Run: `python -m compileall helper tests`

Expected: no syntax errors.

- [ ] **Step 4: Perform dependency/setup verification on Windows**

Run: `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1`

Expected: venv/dependencies configured successfully or a precise FFmpeg installation warning with no destructive changes.

- [ ] **Step 5: Perform manual permitted-content smoke test**

Start helper, load unpacked extension, load one public channel, choose a custom folder, download one short permitted video at 360p, then its audio and transcript if available, verify output layout and duplicate skipping, and restart helper/extension to verify folder/options persistence.

- [ ] **Step 6: Update README with exact install/use/troubleshooting steps**

Document Chrome `Load unpacked`, helper start, FFmpeg prerequisite, folder selection, supported output modes, permission/legal-use note, and common error messages.

- [ ] **Step 7: Re-run automated tests after documentation/setup changes**

Run: `python -m pytest -v`

Run: `npm test`

Expected: all PASS.

- [ ] **Step 8: Commit**

```bash
git add README.md scripts/setup.ps1 tests/test_smoke_contract.py
git commit -m "docs: finish setup and end to end verification"
```
