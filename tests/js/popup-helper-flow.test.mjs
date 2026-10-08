import test from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";

const popupJs = new URL("../../extension/popup.js", import.meta.url);

function indexOrFail(source, pattern, message) {
  const match = source.match(pattern);
  assert.ok(match, message);
  return match.index;
}

test("popup funnels every helper-required action through one readiness gate", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /import\s*\{[^}]*ensureHelperReady[^}]*sendControlCommand[^}]*waitForHelper[^}]*\}\s*from\s*["']\.\/helper-control\.js["']/s);
  assert.match(source, /async function requireHelper\(actionName\)/);
  assert.match(source, /ensureHelperReady\(\{[^}]*autoStart:\s*state\.autoStartHelper/s);

  const cases = [
    ["load", /await requireHelper\(["']load["']\)/, /await api\.loadChannel\(/],
    ["choose folder", /await requireHelper\(["']choose folder["']\)/, /await api\.pickFolder\(/],
    ["download", /await requireHelper\(["']download["']\)/, /await api\.createJob\(/],
    ["retry", /await requireHelper\(["']retry["']\)/, /retryJobOrRecover\(/],
  ];
  for (const [name, gatePattern, operationPattern] of cases) {
    const gate = indexOrFail(source, gatePattern, `missing ${name} readiness gate`);
    const operation = indexOrFail(source.slice(gate), operationPattern, `missing ${name} operation after gate`);
    assert.ok(operation > 0, `${name} operation must follow readiness gate`);
  }
});

test("manual turn off refuses while a download is active before native stop", async () => {
  const source = await readFile(popupJs, "utf8");
  const handler = indexOrFail(source, /helperToggle\.addEventListener\(["']click["'],\s*async\s*\(\)\s*=>\s*\{/, "missing helper toggle handler");
  const body = source.slice(handler);
  const guard = indexOrFail(body, /if\s*\(state\.downloading\s*&&\s*state\.helperOnline\)/, "missing active-download stop guard");
  const stop = indexOrFail(body, /sendControlCommand\(chrome,\s*["']stop["']\)/, "missing native stop command");
  assert.ok(guard < stop);
  assert.match(body.slice(guard, stop), /finish|download/i);
});

test("manual turn off validates the native stop result before rendering helper off", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /requireHelperStopped\(await sendControlCommand\(chrome,\s*["']stop["']\)\)/);
  const validation = indexOrFail(source, /requireHelperStopped\(await sendControlCommand\(chrome,\s*["']stop["']\)\)/, "missing stop validation");
  const markOff = indexOrFail(source.slice(validation), /markHelperOff\(\)/, "missing off-state rendering after validation");
  assert.ok(markOff > 0);
});

test("offline auto-start mode leaves helper actions reachable", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /state\.autoStartHelper/);
  assert.match(source, /helperCanStart|canAutoStart|autoStartAvailable/);
  assert.doesNotMatch(source, /els\.loadChannel\.disabled\s*=\s*!state\.helperOnline\s*\|\|/);
  assert.doesNotMatch(source, /els\.chooseFolder\.disabled\s*=\s*!state\.helperOnline\s*;/);
});

test("auto-start checkbox changes persist without clearing downloader draft", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /autoStartHelper\.addEventListener\(["']change["']/);
  assert.match(source, /state\.autoStartHelper\s*=\s*els\.autoStartHelper\.checked/);
  assert.match(source, /await savePreferences\(\)/);
  for (const field of ["channelUrl", "channelName", "videos", "selectedIds", "folderPath", "currentJobId", "autoStartHelper"]) {
    assert.match(source, new RegExp(`${field}:`), `savePreferences must keep ${field}`);
  }
});

test("loading a replacement channel clears stale videos before requesting the new channel", async () => {
  const source = await readFile(popupJs, "utf8");
  const handler = indexOrFail(
    source,
    /loadChannel\.addEventListener\(["']click["'],\s*async\s*\(\)\s*=>\s*\{/,
    "missing load-channel handler",
  );
  const body = source.slice(handler);
  const clearVideos = indexOrFail(body, /state\.videos\s*=\s*\[\]/, "replacement load must clear stale videos");
  const clearSelection = indexOrFail(body, /state\.selectedIds\s*=\s*clearSelection\(\)/, "replacement load must clear stale selection");
  const hideOldResults = indexOrFail(body, /videoSection\.classList\.add\(["']hidden["']\)/, "replacement load must hide old results");
  const persistClearedDraft = indexOrFail(body, /await\s+savePreferences\(\)/, "replacement load must persist the cleared draft");
  const loadRequest = indexOrFail(body, /await\s+api\.loadChannel\(url\)/, "missing channel request");

  assert.ok(clearVideos < loadRequest);
  assert.ok(clearSelection < loadRequest);
  assert.ok(hideOldResults < loadRequest);
  assert.ok(persistClearedDraft < loadRequest);
});

test("transient polling errors keep an unresolved job protected and schedule another poll", async () => {
  const source = await readFile(popupJs, "utf8");
  const pollStart = indexOrFail(source, /async function pollJob\(\)/, "missing pollJob");
  const loadOffset = indexOrFail(source.slice(pollStart), /els\.loadChannel\.addEventListener/, "missing load handler after pollJob");
  const pollBody = source.slice(pollStart, pollStart + loadOffset);
  const catchStart = indexOrFail(pollBody, /catch\s*\(error\)\s*\{/, "missing poll error handler");
  const catchBody = pollBody.slice(catchStart);

  assert.doesNotMatch(catchBody, /state\.downloading\s*=\s*false/, "transport failure must not mark an unresolved job finished");
  assert.match(catchBody, /state\.downloading\s*=\s*true/, "transport failure must keep active-job controls protected");
  assert.match(catchBody, /state\.pollTimer\s*=\s*setTimeout\(pollJob,\s*1000\)/, "transport failure must retry polling");
});

test("loading a replacement channel clears stale completed-job state and UI before the request", async () => {
  const source = await readFile(popupJs, "utf8");
  const handler = indexOrFail(
    source,
    /loadChannel\.addEventListener\(["']click["'],\s*async\s*\(\)\s*=>\s*\{/,
    "missing load-channel handler",
  );
  const body = source.slice(handler);
  const reset = indexOrFail(body, /clearStaleCompletedJob\(\)/, "replacement load must clear stale completed-job state");
  const loadRequest = indexOrFail(body, /await\s+api\.loadChannel\(url\)/, "missing channel request");
  assert.ok(reset < loadRequest, "stale job reset must happen before loading the replacement channel");

  const resetFn = indexOrFail(source, /function clearStaleCompletedJob\(\)/, "missing stale completed-job reset helper");
  const resetBody = source.slice(resetFn, handler);
  assert.match(resetBody, /if\s*\(state\.downloading\)\s*return/, "active jobs must remain attached while switching channels");
  assert.match(resetBody, /state\.currentJobId\s*=\s*null/);
  assert.match(resetBody, /progressPanel\.classList\.add\(["']hidden["']\)/);
  assert.match(resetBody, /retryFailed\.classList\.add\(["']hidden["']\)/);
  assert.match(resetBody, /jobItems\.textContent\s*=\s*["']["']/);
});

test("channel loading stays disabled while a job is unresolved", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /els\.loadChannel\.disabled\s*=\s*!canLoadChannel\(\{\s*\.\.\.state,\s*helperCanStart\s*\}\)/);
});

test("a successful poll revalidates helper health after a transient offline state", async () => {
  const source = await readFile(popupJs, "utf8");
  const pollStart = indexOrFail(source, /async function pollJob\(\)/, "missing pollJob");
  const loadOffset = indexOrFail(source.slice(pollStart), /els\.loadChannel\.addEventListener/, "missing load handler after pollJob");
  const pollBody = source.slice(pollStart, pollStart + loadOffset);
  const getJob = indexOrFail(pollBody, /getJobOrRecover\(/, "missing job polling request");
  const restore = indexOrFail(pollBody.slice(getJob), /restoreHelperAfterSuccessfulPoll\(\)/, "successful polling must restore helper health state safely");
  assert.ok(restore > 0);

  const restoreFn = indexOrFail(source, /async function restoreHelperAfterSuccessfulPoll\(\)/, "missing helper recovery function");
  const restoreBody = source.slice(restoreFn, pollStart);
  assert.match(restoreBody, /await api\.health\(\)/);
  assert.match(restoreBody, /applyHealth\(health\)/);
});

test("poll transport failure attempts auto-start recovery before polling again", async () => {
  const source = await readFile(popupJs, "utf8");
  const pollStart = indexOrFail(source, /async function pollJob\(\)/, "missing pollJob");
  const loadOffset = indexOrFail(source.slice(pollStart), /els\.loadChannel\.addEventListener/, "missing load handler after pollJob");
  const pollBody = source.slice(pollStart, pollStart + loadOffset);
  const catchStart = indexOrFail(pollBody, /catch\s*\(error\)\s*\{/, "missing poll error handler");
  const catchBody = pollBody.slice(catchStart);
  const recover = indexOrFail(catchBody, /await recoverHelperAfterPollFailure\(\)/, "poll failure must attempt helper recovery");
  const retry = indexOrFail(catchBody, /setTimeout\(pollJob,\s*1000\)/, "poll failure must continue polling");
  assert.ok(recover < retry);
});

test("helper toggle blocks stop for unresolved jobs but permits offline restart", async () => {
  const source = await readFile(popupJs, "utf8");
  assert.match(source, /els\.helperToggle\.disabled\s*=\s*!canToggleHelper\(state\)/);
  const handler = indexOrFail(source, /helperToggle\.addEventListener\(["']click["'],\s*async\s*\(\)\s*=>\s*\{/, "missing helper toggle handler");
  const body = source.slice(handler);
  assert.match(body, /if\s*\(state\.downloading\s*&&\s*state\.helperOnline\)/);
});
