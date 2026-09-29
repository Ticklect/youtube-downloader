import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";


const manifestUrl = new URL("../../extension/manifest.json", import.meta.url);


test("manifest keeps the compact popup and grants only required extension permissions", async () => {
  const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));

  assert.equal(manifest.manifest_version, 3);
  assert.equal(manifest.action?.default_popup, "popup.html");
  assert.ok(manifest.permissions?.includes("storage"));
  assert.ok(manifest.permissions?.includes("tabs"));
  assert.deepEqual(manifest.host_permissions, ["http://127.0.0.1:17865/*"]);
  assert.equal(manifest.content_scripts, undefined);
});
