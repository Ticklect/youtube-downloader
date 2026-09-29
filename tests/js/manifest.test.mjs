import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


const manifestUrl = new URL("../../extension/manifest.json", import.meta.url);


test("manifest exposes only the popup downloader and no tab-navigation permission", async () => {
  const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));

  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.action?.default_popup, "popup.html");
  assert.ok(manifest.permissions?.includes("storage"));
  assert.equal(manifest.permissions?.includes("tabs"), false);
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:17865/*"]);
  assert.equal(manifest.content_scripts, undefined);
});
