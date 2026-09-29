# Native Helper Control Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add safe Windows Native Messaging control so the extension can manually start/stop the local helper and auto-start it when needed, with Helium integration verified end-to-end.

**Architecture:** Keep the existing Flask downloader HTTP API as the data plane and add a narrowly scoped Windows Native Messaging control plane. A packaged Python native host handles only `status`, `start`, and `stop`, persists verified process identity, and is registered per-user; the extension uses a focused `helper-control.js` module to bridge Native Messaging, health readiness, auto-start preference, and popup actions.

**Tech Stack:** Chrome/Chromium MV3 JavaScript, Python 3.11+, Flask, psutil, PyInstaller, PowerShell 5.1+, Windows Registry, Chrome Native Messaging stdio protocol.

**Spec:** `docs/superpowers/specs/2026-09-29-native-helper-control-design.md`

## Global Constraints

- Windows 10/11; normal setup must not require administrator rights.
- Helper remains bound to `127.0.0.1:17865`.
- Native host name is `com.ycd.helper_control` and accepts exactly `status`, `start`, and `stop`.
- Auto-start is enabled by default but can be disabled for manual-only behavior.
- Manual Turn On / Turn Off is always available; Turn Off must refuse while a download is active.
- No arbitrary shell commands, executable paths, arguments, or user-controlled native paths cross the extension/native-host boundary.
- Native host stdout is protocol-only; diagnostics go to stderr.
- Process stop requires verified ownership using PID plus process identity data; PID alone is never enough.
- Extension identity is pinned with a committed public manifest `key`; no private signing key is committed.
- Helium is a required browser target; final verification must exercise the real unpacked extension in Helium.
- Existing channel/video selection persistence and job recovery must remain intact.

## Review Focus

- Helper port is occupied by an unrelated service: start/status must not claim Connected unless the expected helper health marker is present. Covered in Task 2 native-host/controller tests.
- Stale PID state points to a reused unrelated process: stop must refuse and clear stale ownership without terminating it. Covered in Task 2 process-identity tests.
- Native host is unregistered/missing: popup must show `Helper control not installed` while still recognizing an already-running HTTP helper. Covered in Task 4 extension tests.
- Popup closes during startup/folder picker: auto-start preference, channel draft, selection, and current job must survive reopen. Covered in Task 4 storage/flow tests.
- User presses Turn Off during an active download: no native stop request may be sent. Covered in Task 4 UI/control tests.

---

### Task 1: Pin Extension Identity and Helper Health Marker

**Files:**
- Modify: `extension/manifest.json`
- Modify: `helper/app.py`
- Modify: `tests/js/manifest.test.mjs`
- Modify: `tests/test_app.py`
- Create: `scripts/extension-id.mjs`
- Test: `tests/js/extension-id.test.mjs`

**Interfaces:**
- Consumes: existing MV3 manifest and `/health` route.
- Produces: stable extension ID derived from committed manifest `key`; `/health` response containing `service: "youtube-channel-downloader"` plus existing dependency fields.

- [ ] **Step 1: Write failing tests for pinned identity and health marker**

Add tests asserting `manifest.key` exists, `scripts/extension-id.mjs` deterministically maps it to a 32-character Chromium extension ID, and `/health` returns `service == "youtube-channel-downloader"` without changing existing `ok`/`dependencies` behavior.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `node --test tests/js/manifest.test.mjs tests/js/extension-id.test.mjs`
Expected: FAIL because the key/id helper does not exist.

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_app.py -q`
Expected: FAIL because `/health` lacks the service marker.

- [ ] **Step 3: Implement the stable manifest public key and ID helper**

Implement `deriveExtensionId(manifestKeyBase64: string) -> string` in `scripts/extension-id.mjs` using Chromium’s SHA-256/public-key ID mapping, then add the generated public key string to `manifest.json`. Do not commit private key material.

- [ ] **Step 4: Add the helper service marker**

Update `/health` to include the exact marker `service: "youtube-channel-downloader"` while preserving current dependency payloads.

- [ ] **Step 5: Run focused tests and verify GREEN**

Run both focused commands from Step 2; expected all PASS.

- [ ] **Step 6: Commit**

```powershell
git add extension/manifest.json helper/app.py scripts/extension-id.mjs tests/js/manifest.test.mjs tests/js/extension-id.test.mjs tests/test_app.py
git commit -m "feat: pin extension identity and helper marker"
```

### Task 2: Build the Safe Native Host and Process Controller

**Files:**
- Create: `native_host/protocol.py`
- Create: `native_host/controller.py`
- Create: `native_host/host.py`
- Create: `native_host/__init__.py`
- Modify: `helper/requirements.txt`
- Create: `tests/test_native_protocol.py`
- Create: `tests/test_native_controller.py`
- Create: `tests/test_native_host.py`

**Interfaces:**
- Consumes: repo-root config adjacent to packaged host, fixed helper command `<root>/.venv/Scripts/python.exe -m helper.app`, `/health` marker from Task 1.
- Produces: `read_message(stream) -> dict`, `write_message(stream, payload) -> None`, `HelperController.status() -> dict`, `HelperController.start() -> dict`, `HelperController.stop() -> dict`, and one-shot host command dispatcher accepting exactly `status|start|stop`.

- [ ] **Step 1: Write protocol RED tests**

Assert 32-bit native-endian length framing, UTF-8 JSON round-trip, EOF handling, maximum response/message sanity, and that Windows binary stdio mode setup is invoked by the host entrypoint.

- [ ] **Step 2: Run protocol tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_protocol.py -q`
Expected: FAIL because native host modules do not exist.

- [ ] **Step 3: Implement `native_host/protocol.py` minimally**

Use `struct` + JSON; stdout writes protocol bytes only. Provide a Windows helper that switches stdin/stdout to `O_BINARY` before reading/writing Native Messaging frames.

- [ ] **Step 4: Run protocol tests and verify GREEN**

Run focused protocol tests; expected PASS.

- [ ] **Step 5: Write controller RED tests**

Cover exact fixed helper command, healthy-existing-helper no-op, missing venv, startup timeout, stale state cleanup, PID reuse/create-time mismatch, executable/cmdline mismatch, verified owned stop, unrelated service on port, and duplicate-start prevention.

- [ ] **Step 6: Run controller tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_controller.py -q`
Expected: FAIL because controller is not implemented.

- [ ] **Step 7: Implement `HelperController`**

Use `psutil` for PID/create-time/exe/cmdline verification. Persist ownership metadata in a controller state JSON under the native-host install/config directory. Launch helper with hidden/no-console Windows creation flags, wait for the exact `/health` service marker with a bounded timeout, and fail safe on ownership uncertainty.

- [ ] **Step 8: Write and implement host dispatcher tests**

Tests assert accepted commands are exactly `status`, `start`, `stop`; unknown/malformed messages return a structured error and perform no controller action; host writes one response then exits for `sendNativeMessage` usage.

- [ ] **Step 9: Run all native-host tests**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_protocol.py tests/test_native_controller.py tests/test_native_host.py -q`
Expected: PASS.

- [ ] **Step 10: Commit**

```powershell
git add native_host helper/requirements.txt tests/test_native_protocol.py tests/test_native_controller.py tests/test_native_host.py
git commit -m "feat: add safe native helper controller"
```

### Task 3: Package and Register the Native Host on Windows

**Files:**
- Create: `scripts/install-native-host.ps1`
- Create: `scripts/uninstall-helper-control.ps1`
- Modify: `scripts/setup.ps1`
- Create: `tests/test_native_install.py`
- Modify: `tests/test_smoke_contract.py`

**Interfaces:**
- Consumes: stable extension ID from Task 1, `native_host/host.py` from Task 2.
- Produces: packaged `native_host/dist/ycd-helper-control.exe`, generated `native_host/install/com.ycd.helper_control.json`, generated `native_host/install/config.json`, HKCU registration under Chrome NativeMessagingHosts (the path Helium intentionally scans), and matching uninstall behavior.

- [ ] **Step 1: Write installer RED tests**

Assert deterministic host manifest fields (`name`, `description`, absolute exe path, `type: stdio`, exact single allowed origin), generated config repo root, HKCU-only registration commands/paths, idempotent setup, and uninstall scoped only to `com.ycd.helper_control`.

- [ ] **Step 2: Run installer tests and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_native_install.py tests/test_smoke_contract.py -q`
Expected: FAIL because installer scripts are absent.

- [ ] **Step 3: Implement `scripts/install-native-host.ps1`**

Use the project venv to install/build PyInstaller output for `native_host/host.py`; write config/manifest; derive/verify the extension ID from committed manifest key; register `HKCU\Software\Google\Chrome\NativeMessagingHosts\com.ycd.helper_control`. Keep the script repeatable and non-admin.

- [ ] **Step 4: Extend `scripts/setup.ps1`**

After existing Python/dependency setup, invoke the native-host installer and print concise success guidance. Preserve existing FFmpeg validation behavior.

- [ ] **Step 5: Implement uninstall script**

Remove only the owned registry key and generated native-host install/build artifacts after verifying they resolve under this repo’s `native_host` directory. Leave downloader data, `.venv`, and unrelated registry entries untouched.

- [ ] **Step 6: Run installer tests and verify GREEN**

Run focused installer/smoke tests; expected PASS.

- [ ] **Step 7: Commit**

```powershell
git add scripts/setup.ps1 scripts/install-native-host.ps1 scripts/uninstall-helper-control.ps1 tests/test_native_install.py tests/test_smoke_contract.py
git commit -m "feat: install native helper control host"
```

### Task 4: Add Extension Helper-Control Module and Readiness Gate

**Files:**
- Create: `extension/helper-control.js`
- Modify: `extension/manifest.json`
- Modify: `extension/state.js`
- Create: `tests/js/helper-control.test.mjs`
- Modify: `tests/js/manifest.test.mjs`
- Modify: `tests/js/ui.test.mjs`

**Interfaces:**
- Consumes: Chrome `runtime.sendNativeMessage`, `api.health()`, host name `com.ycd.helper_control`.
- Produces: `sendControlCommand(chromeApi, command) -> Promise<object>`, `waitForHelper(api, options) -> Promise<object>`, `ensureHelperReady({ api, chromeApi, autoStart }) -> Promise<object>`, and normalized helper UI state/preference helpers.

- [ ] **Step 1: Write helper-control RED tests**

Cover native success/error mapping, host-missing classification, health-already-online fast path, auto-start enabled start→health→continue, manual mode refusal without native start, startup timeout, and `autoStartHelper` defaulting to true while preserving explicit false.

- [ ] **Step 2: Run tests and verify RED**

Run: `node --test tests/js/helper-control.test.mjs tests/js/manifest.test.mjs tests/js/ui.test.mjs`
Expected: FAIL because helper-control module/permission/preference do not exist.

- [ ] **Step 3: Implement `extension/helper-control.js`**

Use one-shot `chrome.runtime.sendNativeMessage("com.ycd.helper_control", {command})`. Treat HTTP `/health` with the service marker as authoritative; classify missing native host separately from helper offline; implement bounded readiness polling.

- [ ] **Step 4: Add manifest permission and preference normalization**

Add only `nativeMessaging` alongside existing `storage`; preserve no `tabs` permission. Extend state normalization with `autoStartHelper` default true and explicit false preservation.

- [ ] **Step 5: Run focused JS tests and verify GREEN**

Run command from Step 2; expected PASS.

- [ ] **Step 6: Commit**

```powershell
git add extension/helper-control.js extension/manifest.json extension/state.js tests/js/helper-control.test.mjs tests/js/manifest.test.mjs tests/js/ui.test.mjs
git commit -m "feat: add extension helper control bridge"
```

### Task 5: Wire Popup Controls and Auto-Start Into Every Helper-Required Action

**Files:**
- Modify: `extension/popup.html`
- Modify: `extension/popup.css`
- Modify: `extension/popup.js`
- Modify: `tests/js/popup-structure.test.mjs`
- Create: `tests/js/popup-helper-flow.test.mjs`

**Interfaces:**
- Consumes: `ensureHelperReady`, `sendControlCommand`, and auto-start preference from Task 4.
- Produces: popup manual Turn On/Turn Off, persisted Auto-start checkbox, transitional/helper-control states, and shared helper readiness gating for Load, Choose Folder, Download, and Retry Failed.

- [ ] **Step 1: Write popup structure/flow RED tests**

Assert helper control row IDs/copy exist, Auto-start checkbox is persisted, Turn Off is disabled/refused during active download, and all four helper-required actions call one shared readiness gate before their existing API operation.

- [ ] **Step 2: Run popup tests and verify RED**

Run: `node --test tests/js/popup-structure.test.mjs tests/js/popup-helper-flow.test.mjs`
Expected: FAIL because controls/gating are absent.

- [ ] **Step 3: Add helper-control UI**

Add a compact panel near the header with status, one Turn On/Turn Off button, Auto-start checkbox, and concise control-not-installed/start/stop messages. Keep the existing 540px × 580px popup and sticky download action reachable.

- [ ] **Step 4: Refactor popup readiness flow**

Create one popup-level `requireHelper(actionName)` wrapper around Task 4’s readiness gate. Use it before Load, Choose Folder, Download Selected, and Retry Failed. On successful auto-start, continue the original action without requiring a second click.

- [ ] **Step 5: Implement manual controls**

Turn On sends fixed `start`, waits for HTTP readiness, then renders Connected. Turn Off refuses while `state.downloading` is true; otherwise sends fixed `stop` and renders Helper Off. Manual stop does not change the user’s Auto-start preference.

- [ ] **Step 6: Preserve popup state across native transitions**

Ensure every new preference/control transition continues using existing storage draft fields and never clears `channelUrl`, `channelName`, `videos`, `selectedIds`, `folderPath`, or `currentJobId` on start failure or popup reopen.

- [ ] **Step 7: Run popup tests and full JS suite**

Run: `npm test`
Expected: all JS tests PASS.

- [ ] **Step 8: Commit**

```powershell
git add extension/popup.html extension/popup.css extension/popup.js tests/js/popup-structure.test.mjs tests/js/popup-helper-flow.test.mjs
git commit -m "feat: control helper from extension popup"
```

### Task 6: Documentation, Installation, and Real Helium Verification

**Files:**
- Modify: `README.md`
- Modify: `tests/test_smoke_contract.py`
- Generated during setup: `native_host/install/config.json`
- Generated during setup: `native_host/install/com.ycd.helper_control.json`
- Generated during setup: `native_host/dist/ycd-helper-control.exe`

**Interfaces:**
- Consumes: all prior tasks.
- Produces: documented one-time setup/uninstall flow and verified Helium Native Messaging integration.

- [ ] **Step 1: Write/update smoke-doc RED assertions**

Require README to document `Turn On`, `Turn Off`, `Auto-start when needed`, one-time `scripts/setup.ps1`, and `scripts/uninstall-helper-control.ps1`; remove normal-use instructions that require manually running `start-helper.ps1` first.

- [ ] **Step 2: Run smoke test and verify RED**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_smoke_contract.py -q`
Expected: FAIL until docs are updated.

- [ ] **Step 3: Update README**

Document that setup installs/registers helper control, auto-start is default, manual mode is available, manual `start-helper.ps1` remains troubleshooting/fallback only, and uninstall removes helper-control registration.

- [ ] **Step 4: Run the one-time setup on this machine**

Run: `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1`
Expected: venv/dependencies valid, native host packaged, exact stable extension origin written, HKCU Chrome NativeMessagingHosts registration present.

- [ ] **Step 5: Verify generated registration artifacts**

Check registry default value, native manifest path/exe existence, `allowed_origins`, and generated repo-root config. Confirm no HKLM/admin registration was used.

- [ ] **Step 6: Reload the unpacked extension in the existing Helium instance**

Use the existing browser/extension environment; verify the extension ID matches the stable allowed origin. Do not create a second browser profile or debug-port instance.

- [ ] **Step 7: Execute real Helium control scenarios**

Verify: helper off → Turn On → Connected; Connected → Turn Off → Off; auto-start ON + helper off + Load → helper starts and action continues; auto-start OFF + helper off + Load → no process starts and UI instructs Turn On; active download state prevents Turn Off.

- [ ] **Step 8: Run final automated verification**

Run: `npm test`
Expected: all JS tests PASS.

Run: `.\.venv\Scripts\python.exe -m pytest -q`
Expected: all Python tests PASS.

Run: `git diff --check`
Expected: no output.

- [ ] **Step 9: Request fresh whole-branch review and fix any Critical/Important/Medium findings**

Review against the approved spec with focus on process ownership, native-host attack surface, setup/uninstall safety, auto-start action continuation, popup state persistence, and Helium integration.

- [ ] **Step 10: Commit documentation/integration adjustments**

```powershell
git add README.md tests/test_smoke_contract.py
git commit -m "docs: document extension helper control"
```
