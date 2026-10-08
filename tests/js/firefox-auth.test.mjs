import test from "node:test";
import assert from "node:assert/strict";

import { getFolder, setFirefoxToken } from "../../extension/api.js";

test("Firefox token must be valid and is applied to local helper requests", async () => {
  assert.throws(() => setFirefoxToken(""), /invalid token/);
  assert.throws(() => setFirefoxToken("invalid"), /invalid token/);

  const expected = "A".repeat(43) + "=";
  const originalFetch = globalThis.fetch;
  let calls = 0;
  globalThis.fetch = async (url, options) => {
    calls++;
    assert.equal(url, "http://127.0.0.1:17865/folder");
    assert.equal(options.headers["X-YCD-Token"], expected);
    return { ok: true, json: async () => ({ path: "" }) };
  };
  try {
    setFirefoxToken(expected);
    await getFolder();
    assert.equal(calls, 1);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
