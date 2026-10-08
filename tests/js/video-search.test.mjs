import test from "node:test";
import assert from "node:assert/strict";
import { matchingVideoIds } from "../../extension/state.js";

test("video search matches case-insensitive titles and IDs without changing source order", () => {
  const videos = [
    { video_id: "ABC123", title: "Rocket League Highlights" },
    { video_id: "xyz789", title: "Minecraft Clips" },
    { video_id: "six000", title: "ROCKET montage" },
  ];
  assert.deepEqual(matchingVideoIds(videos, " rocket "), ["ABC123", "six000"]);
  assert.deepEqual(matchingVideoIds(videos, "XYZ"), ["xyz789"]);
  assert.deepEqual(matchingVideoIds(videos, ""), ["ABC123", "xyz789", "six000"]);
  assert.deepEqual(matchingVideoIds(videos, "nothing"), []);
});
