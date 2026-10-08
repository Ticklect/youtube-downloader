import test from "node:test";
import assert from "node:assert/strict";

import { getJobOrRecover, recoverHelperForPolling, retryJobOrRecover } from "../../extension/job-lifecycle.js";


function missingJobError() {
  const error = new Error("Job not found");
  error.code = "job_not_found";
  return error;
}


test("getJobOrRecover clears a missing polled job through the recovery callback", async () => {
  let recoveries = 0;
  const api = {
    async getJob() {
      throw missingJobError();
    },
  };

  const result = await getJobOrRecover(api, "stale-job", async () => {
    recoveries += 1;
  });

  assert.equal(result, null);
  assert.equal(recoveries, 1);
});


test("retryJobOrRecover clears a missing retried job through the recovery callback", async () => {
  let recoveries = 0;
  const api = {
    async retryJob() {
      throw missingJobError();
    },
  };

  const result = await retryJobOrRecover(api, "stale-job", async () => {
    recoveries += 1;
  });

  assert.equal(result, null);
  assert.equal(recoveries, 1);
});


test("job lifecycle helpers rethrow non-missing helper errors", async () => {
  const transportError = new Error("connection lost");
  const api = {
    async getJob() {
      throw transportError;
    },
    async retryJob() {
      throw transportError;
    },
  };

  await assert.rejects(() => getJobOrRecover(api, "job", async () => {}), transportError);
  await assert.rejects(() => retryJobOrRecover(api, "job", async () => {}), transportError);
});

test("poll recovery auto-starts only when auto-start mode is enabled", async () => {
  let starts = 0;
  const ensureReady = async () => {
    starts += 1;
    return { health: { service: "youtube-channel-downloader", ok: true } };
  };

  assert.equal(await recoverHelperForPolling({ autoStartHelper: false, ensureReady }), null);
  assert.equal(starts, 0);

  const result = await recoverHelperForPolling({ autoStartHelper: true, ensureReady });
  assert.equal(starts, 1);
  assert.equal(result.health.ok, true);
});
