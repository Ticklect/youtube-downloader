# Native Helper Control Design

## Goal

Make the Windows local helper feel like part of the browser extension instead of a separate PowerShell process the user must manage manually.

The extension must support both of these modes:

- **Auto-start enabled (default):** if an action such as Load, Choose Folder, or Download needs the helper and it is off, the extension starts it automatically and then continues the requested action.
- **Manual mode:** the user can disable auto-start. In that mode the helper remains off until the user explicitly presses **Turn On**.

The popup must always expose manual **Turn On / Turn Off** control regardless of the auto-start preference.

## Current Constraints

The existing downloader helper is a local Flask app launched with:

`<repo>/.venv/Scripts/python.exe -m helper.app`

It listens only on `127.0.0.1:17865`. The extension currently talks to it over HTTP and has no ability to launch local Windows processes.

Browser extensions cannot directly execute PowerShell or Python. A Windows-side bridge is therefore required.

The primary browser in the user's environment is Helium, a Chromium-based browser. The implementation must also remain compatible with ordinary Chromium/Chrome-style extension loading where practical.

## Architecture

### 1. Browser extension

The extension remains the user-facing UI. It gains:

- `nativeMessaging` permission.
- A compact **Local Helper** control row in the existing popup.
- Manual **Turn On** and **Turn Off** buttons.
- An **Auto-start when needed** checkbox, enabled by default.
- A helper state machine with the visible states:
  - `Off`
  - `Starting…`
  - `Connected`
  - `Stopping…`
  - `Control not installed`
  - `Error`

The popup will use the existing HTTP `/health` endpoint as the authoritative signal that the downloader helper is actually usable. Native Messaging reports process-control results, but the extension does not call the helper "Connected" until `/health` responds.

### 2. Native Messaging host

Add a small Windows Native Messaging host under a dedicated project folder, for example `native_host/`.

It exposes only three commands:

- `status`
- `start`
- `stop`

No command supplied by the extension may contain an executable path, shell command, arbitrary arguments, or arbitrary file path. The host derives the repository root from its own installed configuration and always launches the project's fixed helper command.

The host speaks standard Native Messaging JSON messages over stdin/stdout. It must not write diagnostics to stdout because stdout is reserved for the protocol. Diagnostics go to stderr or a log file if logging is required.

### 3. Helper process controller

The native host owns helper process lifecycle.

`start` behavior:

1. Check whether the helper is already healthy on `127.0.0.1:17865`.
2. If healthy, return success without spawning another helper.
3. If not healthy, validate that `.venv/Scripts/python.exe` exists.
4. Launch `python.exe -m helper.app` with the repository root as the working directory.
5. Launch hidden/detached enough that no PowerShell or console window flashes in normal use.
6. Persist process identity information for later verification and stop control.
7. Wait for helper readiness with a bounded timeout.
8. Return success only after readiness is confirmed.

`stop` behavior:

1. Check the persisted process identity.
2. Verify the process still matches the helper process that this controller owns.
3. Stop only that verified process.
4. Never terminate an unrelated process merely because Windows reused a PID.
5. Clear stale controller state when the owned process is gone.

`status` behavior:

- Report whether the helper is healthy.
- Report whether the controller believes it owns the current helper process.
- Clean stale PID/process metadata when it no longer matches a live owned helper.

## Process Identity Safety

PID alone is insufficient because Windows can reuse process IDs.

The controller must persist and later verify additional identity data. The exact implementation may use a combination such as:

- PID
- process creation timestamp
- executable path
- command line or another stable process attribute available from Windows

The implementation must prove ownership before stopping a process. If ownership cannot be established, `stop` fails safely instead of killing the process.

## Stable Extension Identity

Native Messaging manifests allow only specific extension origins, so the unpacked extension needs a stable extension ID.

The implementation will pin the extension identity using a committed manifest `key` containing the extension public key material (never a private signing key). That gives the unpacked extension a reproducible ID across reloads on Chromium-compatible browsers that honor the standard manifest key. The installer then uses that exact origin in the native host manifest:

`chrome-extension://<stable-extension-id>/`

The installer/integration check must verify the resulting ID used by the installed/unpacked extension matches the host manifest. If Helium does not honor the standard Chromium manifest `key` behavior, implementation must stop and adapt the identity mechanism rather than registering a mismatched origin.

## Windows Installation

`scripts/setup.ps1` remains the main one-time setup entry point. It will be extended to:

1. Create/install the existing Python virtual environment and downloader dependencies as it does today.
2. Install or prepare the Native Messaging host launcher.
3. Write the Native Messaging host manifest with the fixed allowed extension origin.
4. Register the host for the supported browser registry location(s) under the current user where possible.
5. Avoid requiring administrator rights for the normal supported path.
6. Print a concise success/failure summary.

Add a matching uninstall script, such as `scripts/uninstall-helper-control.ps1`, which removes only registrations/files created by this helper-control feature.

### Helium support

Helium is a required target for this implementation.

Before finalizing registration, implementation must inspect the actual installed Helium environment and determine which Native Messaging host registry location it uses. The installer should register for Helium explicitly if its lookup path differs from Chrome/Chromium.

The feature is not considered complete until Native Messaging is exercised from the real Helium extension instance, not only from unit tests.

## Popup UX

Add a compact helper-control panel near the popup header.

### Connected

- Green status indicator.
- Label: `Connected`.
- Button: `Turn Off`.
- Checkbox: `Auto-start when needed`.

### Off

- Neutral/off status indicator.
- Label: `Helper Off`.
- Button: `Turn On`.
- Checkbox: `Auto-start when needed`.

### Starting / stopping

- Disable the helper control button while a transition is active.
- Show `Starting…` or `Stopping…`.
- Prevent duplicate start/stop requests.

### Native host unavailable

If `chrome.runtime.connectNative` / `sendNativeMessage` reports that the host is missing or inaccessible:

- Show `Helper control not installed`.
- Explain that the one-time setup script must be run.
- Do not pretend the helper itself is necessarily unavailable; if `/health` already works, downloads may still continue.

## Auto-start Flow

Auto-start is enabled by default and persisted in `chrome.storage.local`.

For any action requiring the helper:

1. Check `/health`.
2. If healthy, continue immediately.
3. If unhealthy and auto-start is disabled, stop the action and show `Helper is off — turn it on to continue.`
4. If unhealthy and auto-start is enabled, call the native host `start` command.
5. Wait for `/health` with a bounded retry loop.
6. Continue the original action automatically after health succeeds.
7. If startup fails or times out, keep the original action cancelled and display the real startup error.

The shared helper-readiness function must be used by at least:

- Load channel
- Choose Folder
- Start Download

Retrying failed jobs should also require helper readiness.

## Manual Turn Off Semantics

Pressing **Turn Off** requests a clean stop through the native host.

If a download job is currently active, the extension must not silently terminate the helper and orphan the active job. The initial implementation should disable or refuse **Turn Off** while a job is running and explain that the current download must finish first.

After a successful stop:

- popup state becomes `Helper Off`;
- downloader actions are disabled in manual mode;
- in auto-start mode, a later helper-dependent action may start it again.

## Security Boundaries

The Native Messaging host is intentionally narrow:

- only the configured extension origin may connect;
- only `status`, `start`, and `stop` commands are accepted;
- no arbitrary shell execution;
- no arbitrary path execution;
- no user-controlled command line;
- helper binds only to loopback as it does today;
- existing HTTP origin/header checks remain in place;
- stopping a process requires verified controller ownership.

Unknown commands return an error and perform no action.

## Error Handling

Errors must be actionable and must preserve the user's downloader state.

Examples:

- Missing native host: `Helper control is not installed. Run scripts/setup.ps1 once.`
- Missing venv: `Helper environment is missing. Run scripts/setup.ps1.`
- Start timeout: `Helper did not become ready in time.`
- Port already occupied by a non-helper process: refuse to claim success unless `/health` confirms the expected helper API.
- Stop ownership mismatch: `Helper process ownership could not be verified; nothing was stopped.`

Auto-start failures must not clear the loaded channel, selected videos, folder, or current job state.

## Testing Strategy

Implementation follows TDD.

### Extension unit/contract tests

Cover:

- auto-start preference defaults to enabled and persists;
- manual mode does not auto-start;
- helper-required actions call the shared readiness gate;
- successful auto-start resumes the original action;
- failed auto-start surfaces an error and does not execute the original action;
- Turn Off is unavailable during an active download;
- popup renders Off / Starting / Connected / control-not-installed states correctly;
- manifest includes only the permissions required by the new design.

### Native host tests

Cover:

- Native Messaging length-prefixed JSON protocol encode/decode;
- accepted commands are exactly status/start/stop;
- unknown commands are rejected;
- duplicate start does not spawn duplicate helpers;
- stale PID state is cleaned;
- PID reuse / identity mismatch cannot kill an unrelated process;
- stop terminates only an owned helper;
- startup timeout and missing-venv errors are deterministic;
- protocol stdout remains free of logging noise.

### Installer tests

Cover as practical:

- deterministic manifest generation;
- exact allowed extension origin;
- current-user registry registration;
- uninstall removes only owned registration;
- repeated setup is idempotent.

### Integration verification

Before completion:

1. Run the full existing JS and Python suites.
2. Run new native-host tests.
3. Run `git diff --check`.
4. Reload the unpacked extension in Helium.
5. With the helper initially off, click **Turn On** and verify it becomes Connected.
6. Click **Turn Off** and verify the helper stops.
7. Enable auto-start, leave helper off, press **Load**, and verify the helper starts and the channel action continues without another click.
8. Disable auto-start, leave helper off, press **Load**, and verify no process starts and the UI asks the user to turn it on.

## Files / Components Expected to Change

Likely runtime changes:

- `extension/manifest.json`
- `extension/popup.html`
- `extension/popup.css`
- `extension/popup.js`
- new extension helper-control module(s)
- new `native_host/` controller/protocol files
- `scripts/setup.ps1`
- new uninstall helper-control script
- README/setup documentation
- JS/Python/native-host tests

The existing downloader HTTP API and job/download internals should remain unchanged except where a small testability or lifecycle hook is strictly necessary.

## Non-Goals

This feature does not add:

- a Windows service;
- a system tray application;
- helper auto-start at Windows login;
- arbitrary native process execution;
- remote/network control;
- a second full-page downloader UI.

## Acceptance Criteria

The feature is complete when all of the following are true:

1. The extension popup exposes working Turn On / Turn Off helper controls.
2. Auto-start when needed is enabled by default and can be disabled for manual-only behavior.
3. Load, Choose Folder, Download, and retry flows reliably gate on helper readiness.
4. No visible PowerShell console is required during normal start/stop use.
5. The extension cannot ask the native host to execute arbitrary commands or paths.
6. Stop cannot kill an unverified unrelated process.
7. The one-time setup and uninstall flows are documented and repeatable.
8. The real Helium browser can communicate with the native host and control the helper.
9. Existing downloader selection/job persistence behavior remains intact.
10. Full automated test suites and manual Helium integration checks pass.
