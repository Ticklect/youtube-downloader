# Extension Full-Page Downloader Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Convert the current all-in-popup Chrome extension into a compact launcher popup plus a full-page downloader while preserving the existing paste-link → load videos → select videos → download workflow.

**Architecture:** Keep the helper API and shared state logic unchanged. Move the complete downloader UI/behavior into a new `downloader.html` / `downloader.js` / `downloader.css` surface, reduce the existing popup to helper status plus an **Open Downloader** launcher, and add a small shared tab-opening utility for deterministic reuse/focus behavior.

**Tech Stack:** Chrome Manifest V3, vanilla HTML/CSS/ES modules, `chrome.tabs`, `chrome.runtime`, `chrome.storage.local`, Node built-in test runner, Python helper test suite.

**Spec:** `docs/superpowers/specs/2026-09-29-extension-full-page-design.md`

## Global Constraints

- Preserve the manual pasted-URL workflow; do not add current-tab detection or YouTube content scripts.
- Keep the existing helper API and `127.0.0.1:17865` protocol unchanged.
- Preserve output modes: Video, Audio (MP3), Transcript, Everything.
- Preserve video qualities: 360p, 720p, 1080p, Best available.
- Keep `chrome.storage.local` persistence for mode, quality, folder path, and current job ID.
- Keep the existing dark/charcoal/indigo visual language.
- Do not make a standalone desktop app mandatory.

## Review Focus

- Clicking **Open Downloader** repeatedly should focus/reuse the existing downloader tab rather than creating unbounded duplicates.
- If `chrome.tabs.query` fails or returns an unusable tab, the launcher should still create a working downloader tab.
- The full page must remain understandable while the helper is offline, with disabled helper-dependent controls and a clear message.
- A stale persisted job ID after helper restart must still be cleared on `job_not_found` without breaking initialization.
- Narrow browser windows must collapse the two-column layout without hiding core controls or making the video list unusable.

---

### Task 1: Add deterministic downloader-page launcher behavior

**Files:**
- Create: `extension/navigation.js`
- Create: `tests/js/navigation.test.mjs`

**Interfaces:**
- Consumes: Chrome-like object exposing `runtime.getURL`, `tabs.query`, `tabs.update`, and `tabs.create`.
- Produces: `openOrFocusDownloader(chromeApi) -> Promise<{ action: "focused" | "created", tabId?: number }>`.

- [ ] **Step 1: Write failing tests for reuse, fallback create, and duplicate prevention**

Add tests named:

- `openOrFocusDownloader focuses an existing downloader tab`
- `openOrFocusDownloader creates a downloader tab when none exists`
- `openOrFocusDownloader creates a downloader tab if query fails`

Assert the target URL is exactly `chrome.runtime.getURL("downloader.html")`, existing tabs are updated with `{ active: true }`, and a new tab is created with `{ url: targetUrl }` only when needed.

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `node --test tests/js/navigation.test.mjs`

Expected: FAIL because `extension/navigation.js` does not exist.

- [ ] **Step 3: Implement `openOrFocusDownloader(chromeApi)`**

Use exact URL matching against queried extension tabs. Prefer focusing the first matching tab with a numeric `id`; otherwise create a new tab. Treat query failure as a create fallback rather than surfacing a dead launcher.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run: `node --test tests/js/navigation.test.mjs`

Expected: all launcher navigation tests PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/navigation.js tests/js/navigation.test.mjs
git commit -m "feat: add downloader page launcher navigation"
```

---

### Task 2: Convert the toolbar popup into a compact launcher

**Files:**
- Modify: `extension/popup.html`
- Modify: `extension/popup.css`
- Replace behavior in: `extension/popup.js`
- Test: `tests/js/popup-structure.test.mjs`

**Interfaces:**
- Consumes: `api.health()` and `openOrFocusDownloader(chrome)` from Task 1.
- Produces: popup controls `#helperStatus`, `#helperMessage`, and `#openDownloader`.

- [ ] **Step 1: Write failing structural tests for the compact popup**

Assert `popup.html`:

- contains `id="openDownloader"`, `id="helperStatus"`, and `id="helperMessage"`;
- does not contain the old channel/video/download control IDs such as `channelUrl`, `videoList`, or `startDownload`;
- imports `popup.js` as a module.

Also assert `popup.js` imports `openOrFocusDownloader` and invokes it from the launcher click path.

Add an initialization-focused assertion that an offline helper state leaves **Open Downloader** enabled and renders `Offline` plus the helper-start guidance instead of disabling the launcher.

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `node --test tests/js/popup-structure.test.mjs`

Expected: FAIL because the popup still contains the full downloader UI.

- [ ] **Step 3: Implement the compact launcher popup**

Keep helper states exactly `Connected`, `Limited`, and `Offline`. Show dependency messages when health is limited. The **Open Downloader** button should remain usable even while the helper is offline so the full page can explain the state.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run: `node --test tests/js/popup-structure.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/popup.html extension/popup.css extension/popup.js tests/js/popup-structure.test.mjs
git commit -m "feat: turn extension popup into downloader launcher"
```

---

### Task 3: Move the complete downloader workflow to a full extension page

**Files:**
- Create: `extension/downloader.html`
- Create: `extension/downloader.css`
- Create: `extension/downloader.js`
- Test: `tests/js/downloader-structure.test.mjs`

**Interfaces:**
- Consumes: all existing exports from `extension/api.js` and `extension/state.js`.
- Produces: full-page controls retaining the existing IDs used by the downloader behavior, including `channelUrl`, `loadChannel`, `channelMessage`, `folderPath`, `chooseFolder`, `videoSection`, `channelName`, `selectionCount`, `videoList`, `selectAll`, `clearAll`, `mode`, `quality`, `startDownload`, `retryFailed`, `progressPanel`, `progressSummary`, `jobItems`, and `errorMessage`.

- [ ] **Step 1: Write failing structural tests for the full page**

Assert `downloader.html` contains every required control ID above and imports `downloader.js` as a module. Assert it labels the URL field for a YouTube channel, provides all four output modes, and provides the four existing quality values.

Also assert `downloader.css` contains a narrow-width media query that collapses the desktop grid to one column and that the video list is not constrained by the old `max-height: 260px` rule.

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `node --test tests/js/downloader-structure.test.mjs`

Expected: FAIL because `downloader.html` does not exist.

- [ ] **Step 3: Create `downloader.html` and migrate behavior from the old popup**

Move the existing downloader behavior from the old `popup.js` into `downloader.js` with functional parity: helper health, folder fetch/pick, channel load, select/clear, mode/quality persistence, job creation, job polling, stale-job recovery, progress rendering, and retry.

Add a focused testable helper around stale-job recovery if needed so `job_not_found` clears the persisted/current job ID while other polling errors still surface normally.

- [ ] **Step 4: Implement the responsive full-page visual layout**

Use a centered page shell, wide source panel, responsive two-column content layout, larger thumbnails, page-level scrolling, and a stacked single-column layout at narrow widths. Do not reintroduce the old `max-height: 260px` trapped video-list experience.

- [ ] **Step 5: Run focused JS tests and confirm GREEN**

Run: `node --test tests/js/downloader-structure.test.mjs tests/js/ui.test.mjs`

Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add extension/downloader.html extension/downloader.css extension/downloader.js tests/js/downloader-structure.test.mjs
git commit -m "feat: add full-page channel downloader"
```

---

### Task 4: Pin manifest integration and extension-page routing

**Files:**
- Modify: `extension/manifest.json`
- Create: `tests/js/manifest.test.mjs`

**Interfaces:**
- Consumes: `popup.html` launcher and `downloader.html` full page.
- Produces: Manifest V3 package retaining `popup.html` as the toolbar action popup and required permissions for the launcher.

- [ ] **Step 1: Write failing manifest integration tests**

Assert:

- `manifest_version === 3`;
- `action.default_popup === "popup.html"`;
- permissions include `storage` and `tabs`;
- host permission remains `http://127.0.0.1:17865/*`.

- [ ] **Step 2: Run the focused test and confirm RED**

Run: `node --test tests/js/manifest.test.mjs`

Expected: FAIL because `tabs` permission is not present.

- [ ] **Step 3: Add the minimum manifest permission required by launcher tab reuse**

Add only the permission needed for the chosen tab-query implementation; do not add YouTube host access or content scripts.

- [ ] **Step 4: Run the focused test and confirm GREEN**

Run: `node --test tests/js/manifest.test.mjs`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add extension/manifest.json tests/js/manifest.test.mjs
git commit -m "feat: wire full-page downloader into extension manifest"
```

---

### Task 5: Update documentation and run full regression verification

**Files:**
- Modify: `README.md`
- Test: existing JS and Python suites

**Interfaces:**
- Consumes: completed extension behavior from Tasks 1-4.
- Produces: accurate install/use documentation for the launcher + full-page workflow.

- [ ] **Step 1: Update usage documentation**

Document that clicking the toolbar extension opens a compact launcher, **Open Downloader** opens/focuses the full extension page, and the user then follows the unchanged paste URL → Load → select videos → choose folder/output/quality → download workflow.

- [ ] **Step 2: Run the complete JS test suite**

Run: `npm test`

Expected: all Node tests PASS.

- [ ] **Step 3: Run the complete Python helper test suite**

Run: `.venv\Scripts\python.exe -m pytest -q`

Expected: all Python tests PASS.

- [ ] **Step 4: Run repository diff checks**

Run: `git diff --check`

Expected: no whitespace errors.

- [ ] **Step 5: Manually inspect the extension package structure**

Verify the manifest references the compact popup, both HTML entry points exist, no content scripts/YouTube host permissions were introduced, and the downloader page references only local extension assets/modules.

- [ ] **Step 6: Commit**

```bash
git add README.md
git commit -m "docs: explain full-page extension downloader"
```
