import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

import { deriveExtensionId } from "../../scripts/extension-id.mjs";

const manifestUrl = new URL("../../extension/manifest.json", import.meta.url);

test("deriveExtensionId maps public-key bytes to Chromium's 32-character id", () => {
  assert.equal(deriveExtensionId("AQIDBA=="), "jpgekhehobljhpbdbpkllgleehcjgmjl");
});

test("committed manifest key produces a deterministic extension id", async () => {
  const manifest = JSON.parse(await readFile(manifestUrl, "utf8"));
  const first = deriveExtensionId(manifest.key);
  const second = deriveExtensionId(manifest.key);

  assert.equal(first, second);
  assert.match(first, /^[a-p]{32}$/);
});
