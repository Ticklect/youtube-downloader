export const HELPER_HOST_NAME = "com.ycd.helper_control";
export const HELPER_SERVICE = "youtube-channel-downloader";
const ALLOWED_COMMANDS = new Set(["status", "start", "stop", "credentials"]);

export class HelperControlError extends Error {
  constructor(message, code = "helper_control_failed") {
    super(message);
    this.name = "HelperControlError";
    this.code = code;
  }
}

function classifyNativeRuntimeError(message = "") {
  const normalized = String(message).toLowerCase();
  if (
    normalized.includes("native messaging host")
    || normalized.includes("native host")
    || normalized.includes("not found")
    || normalized.includes("not registered")
  ) {
    return new HelperControlError(
      "Helper control is not installed. Run scripts/setup.ps1 once.",
      "native_host_missing",
    );
  }
  return new HelperControlError(message || "Native helper control failed.", "native_message_failed");
}

export function sendControlCommand(chromeApi, command) {
  if (!ALLOWED_COMMANDS.has(command)) {
    return Promise.reject(new HelperControlError("Unsupported helper control command.", "invalid_command"));
  }
  if (!chromeApi?.runtime?.sendNativeMessage) {
    return Promise.reject(new HelperControlError(
      "Helper control is not installed. Run scripts/setup.ps1 once.",
      "native_host_missing",
    ));
  }

  // Firefox's browser.* interface returns a Promise; Chromium's chrome.*
  // interface expects a callback and reports failures via runtime.lastError.
  if (typeof globalThis.browser !== "undefined" && chromeApi === globalThis.browser) {
    return Promise.resolve()
      .then(() => chromeApi.runtime.sendNativeMessage(HELPER_HOST_NAME, { command }))
      .then((response) => {
        if (!response || response.ok !== true) {
          const error = response?.error || {};
          throw new HelperControlError(error.message || "Native helper control failed.", error.code || "control_failed");
        }
        return response;
      }, (error) => { throw classifyNativeRuntimeError(error?.message); });
  }

  return new Promise((resolve, reject) => {
    try {
      chromeApi.runtime.sendNativeMessage(HELPER_HOST_NAME, { command }, (response) => {
        const runtimeError = chromeApi.runtime.lastError;
        if (runtimeError) {
          reject(classifyNativeRuntimeError(runtimeError.message));
          return;
        }
        if (!response || response.ok !== true) {
          const error = response?.error || {};
          reject(new HelperControlError(error.message || "Native helper control failed.", error.code || "control_failed"));
          return;
        }
        resolve(response);
      });
    } catch (error) {
      reject(classifyNativeRuntimeError(error?.message));
    }
  });
}

export function requireHelperStopped(response) {
  if (response?.healthy !== false) {
    throw new HelperControlError("Helper is still running after the stop request.", "stop_failed");
  }
  return response;
}

function isExpectedHealth(health) {
  return health?.service === HELPER_SERVICE;
}

async function tryHealth(api) {
  try {
    const health = await api.health();
    return isExpectedHealth(health) ? health : null;
  } catch {
    return null;
  }
}

export async function waitForHelper(
  api,
  { attempts = 30, delayMs = 100, sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms)) } = {},
) {
  const count = Math.max(1, Number.isFinite(attempts) ? Math.floor(attempts) : 30);
  for (let attempt = 0; attempt < count; attempt += 1) {
    const health = await tryHealth(api);
    if (health) return health;
    if (attempt + 1 < count && delayMs > 0) await sleep(delayMs);
    else if (attempt + 1 < count) await sleep(0);
  }
  throw new HelperControlError("Helper did not become ready in time.", "helper_start_timeout");
}

export async function ensureHelperReady({ api, chromeApi, autoStart, waitOptions } = {}) {
  const current = await tryHealth(api);
  if (current) return { health: current, started: false };

  if (!autoStart) {
    throw new HelperControlError("Helper is off — turn it on to continue.", "helper_off");
  }

  await sendControlCommand(chromeApi, "start");
  const health = await waitForHelper(api, waitOptions);
  return { health, started: true };
}
