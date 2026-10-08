import test from "node:test";
import assert from "node:assert/strict";
import { createStorageQueue } from "../../extension/storage-queue.js";

test("storage writes are serialized and keep snapshots from their invocation", async () => {
  const writes = [];
  let finishFirst;
  const enqueue = createStorageQueue((snapshot) => {
    writes.push(snapshot);
    if (writes.length === 1) return new Promise((resolve) => { finishFirst = resolve; });
    return Promise.resolve();
  });

  const selection = ["a"];
  const first = enqueue({ selectedIds: [...selection] });
  selection.push("b");
  const second = enqueue({ selectedIds: [...selection] });
  await Promise.resolve();
  assert.deepEqual(writes, [{ selectedIds: ["a"] }], "second write must await first");
  finishFirst();
  await Promise.all([first, second]);
  assert.deepEqual(writes, [{ selectedIds: ["a"] }, { selectedIds: ["a", "b"] }]);
});

test("a rejected write does not prevent subsequent saves", async () => {
  const writes = [];
  const enqueue = createStorageQueue((snapshot) => {
    writes.push(snapshot);
    return writes.length === 1 ? Promise.reject(new Error("quota")) : Promise.resolve();
  });
  const failed = enqueue({ theme: "red" });
  const saved = enqueue({ theme: "mono" });
  await assert.rejects(failed, /quota/);
  await saved;
  assert.deepEqual(writes, [{ theme: "red" }, { theme: "mono" }]);
});
