import test from "node:test";
import assert from "node:assert/strict";

import { openOrFocusDownloader } from "../../extension/navigation.js";


function makeChrome({ tabs = [], queryError = null } = {}) {
  const calls = { query: [], update: [], create: [] };
  const targetUrl = "chrome-extension://test/downloader.html";
  const chromeApi = {
    runtime: {
      getURL(path) {
        assert.equal(path, "downloader.html");
        return targetUrl;
      },
    },
    tabs: {
      async query(queryInfo) {
        calls.query.push(queryInfo);
        if (queryError) throw queryError;
        return tabs;
      },
      async update(tabId, updateProperties) {
        calls.update.push([tabId, updateProperties]);
        return { id: tabId };
      },
      async create(createProperties) {
        calls.create.push(createProperties);
        return { id: 42, url: createProperties.url };
      },
    },
  };
  return { chromeApi, calls, targetUrl };
}


test("openOrFocusDownloader focuses an existing downloader tab", async () => {
  const targetUrl = "chrome-extension://test/downloader.html";
  const { chromeApi, calls } = makeChrome({
    tabs: [
      { id: 8, url: targetUrl },
      { id: 9, url: targetUrl },
    ],
  });

  const result = await openOrFocusDownloader(chromeApi);

  assert.deepEqual(calls.query, [{ url: targetUrl }]);
  assert.deepEqual(calls.update, [[8, { active: true }]]);
  assert.deepEqual(calls.create, []);
  assert.deepEqual(result, { action: "focused", tabId: 8 });
});


test("openOrFocusDownloader creates a downloader tab when none exists", async () => {
  const { chromeApi, calls, targetUrl } = makeChrome({ tabs: [] });

  const result = await openOrFocusDownloader(chromeApi);

  assert.deepEqual(calls.query, [{ url: targetUrl }]);
  assert.deepEqual(calls.update, []);
  assert.deepEqual(calls.create, [{ url: targetUrl }]);
  assert.deepEqual(result, { action: "created", tabId: 42 });
});


test("openOrFocusDownloader creates a downloader tab if query fails", async () => {
  const { chromeApi, calls, targetUrl } = makeChrome({
    queryError: new Error("tabs query unavailable"),
  });

  const result = await openOrFocusDownloader(chromeApi);

  assert.deepEqual(calls.query, [{ url: targetUrl }]);
  assert.deepEqual(calls.update, []);
  assert.deepEqual(calls.create, [{ url: targetUrl }]);
  assert.deepEqual(result, { action: "created", tabId: 42 });
});


test("openOrFocusDownloader ignores unusable matching tabs", async () => {
  const targetUrl = "chrome-extension://test/downloader.html";
  const { chromeApi, calls } = makeChrome({
    tabs: [{ id: undefined, url: targetUrl }],
  });

  const result = await openOrFocusDownloader(chromeApi);

  assert.deepEqual(calls.update, []);
  assert.deepEqual(calls.create, [{ url: targetUrl }]);
  assert.deepEqual(result, { action: "created", tabId: 42 });
});
