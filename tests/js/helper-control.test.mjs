import test from "node:test";
import assert from "node:assert/strict";

import {
  HELPER_HOST_NAME,
  HelperControlError,
  ensureHelperReady,
  requireHelperStopped,
  sendControlCommand,
  waitForHelper,
} from "../../extension/helper-control.js";


function chromeWithNative(handler) {
  const runtime = {
    lastError: null,
    sendNativeMessage(host, message, callback) {
      handler({ host, message, callback, runtime });
    },
  };
  return { runtime };
}


test("sendControlCommand sends only fixed commands to the expected native host", async () => {
  const calls = [];
  const chromeApi = chromeWithNative(({ host, message, callback }) => {
    calls.push({ host, message });
    callback({ ok: true, healthy: true, owned: true });
  });

  const result = await sendControlCommand(chromeApi, "start");
  assert.equal(result.healthy, true);
  assert.deepEqual(calls, [{ host: HELPER_HOST_NAME, message: { command: "start" } }]);
  await assert.rejects(() => sendControlCommand(chromeApi, "launch arbitrary.exe"), /Unsupported helper control command/);
});


test("sendControlCommand classifies a missing native host", async () => {
  const chromeApi = chromeWithNative(({ callback, runtime }) => {
    runtime.lastError = { message: "Specified native messaging host not found." };
    callback(undefined);
    runtime.lastError = null;
  });

  await assert.rejects(
    () => sendControlCommand(chromeApi, "status"),
    (error) => error instanceof HelperControlError
      && error.code === "native_host_missing"
      && /setup\.ps1/.test(error.message),
  );
});


test("sendControlCommand maps structured native errors", async () => {
  const chromeApi = chromeWithNative(({ callback }) => callback({
    ok: false,
    error: { code: "ownership_unverified", message: "nothing was stopped" },
  }));
  await assert.rejects(
    () => sendControlCommand(chromeApi, "stop"),
    (error) => error.code === "ownership_unverified" && /nothing was stopped/.test(error.message),
  );
});


test("requireHelperStopped rejects any successful stop response that is still healthy", () => {
  assert.deepEqual(
    requireHelperStopped({ ok: true, healthy: false, owned: false }),
    { ok: true, healthy: false, owned: false },
  );
  assert.throws(
    () => requireHelperStopped({ ok: true, healthy: true, owned: false }),
    (error) => error instanceof HelperControlError
      && error.code === "stop_failed"
      && /still running/i.test(error.message),
  );
});


test("ensureHelperReady fast-paths when the expected helper is already healthy", async () => {
  const api = { health: async () => ({ service: "youtube-channel-downloader", ok: true }) };
  let nativeCalls = 0;
  const chromeApi = chromeWithNative(() => { nativeCalls += 1; });

  const result = await ensureHelperReady({ api, chromeApi, autoStart: true });
  assert.equal(result.started, false);
  assert.equal(result.health.service, "youtube-channel-downloader");
  assert.equal(nativeCalls, 0);
});


test("ensureHelperReady auto-starts and resumes after helper becomes healthy", async () => {
  const healthResults = [new Error("offline"), new Error("still starting"), { service: "youtube-channel-downloader", ok: true }];
  const api = {
    async health() {
      const next = healthResults.shift();
      if (next instanceof Error) throw next;
      return next;
    },
  };
  const nativeCommands = [];
  const chromeApi = chromeWithNative(({ message, callback }) => {
    nativeCommands.push(message.command);
    callback({ ok: true, healthy: true, owned: true });
  });

  const result = await ensureHelperReady({
    api,
    chromeApi,
    autoStart: true,
    waitOptions: { attempts: 3, delayMs: 0, sleep: async () => {} },
  });

  assert.equal(result.started, true);
  assert.deepEqual(nativeCommands, ["start"]);
  assert.equal(result.health.service, "youtube-channel-downloader");
});


test("ensureHelperReady manual mode refuses without starting the native host", async () => {
  const api = { health: async () => { throw new Error("offline"); } };
  let nativeCalls = 0;
  const chromeApi = chromeWithNative(() => { nativeCalls += 1; });

  await assert.rejects(
    () => ensureHelperReady({ api, chromeApi, autoStart: false }),
    (error) => error.code === "helper_off" && /turn it on/i.test(error.message),
  );
  assert.equal(nativeCalls, 0);
});


test("waitForHelper rejects wrong service markers and times out deterministically", async () => {
  const api = { health: async () => ({ service: "not-our-helper", ok: true }) };
  await assert.rejects(
    () => waitForHelper(api, { attempts: 2, delayMs: 0, sleep: async () => {} }),
    (error) => error.code === "helper_start_timeout",
  );
});
