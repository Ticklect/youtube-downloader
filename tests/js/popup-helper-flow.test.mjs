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
  const guard = indexOrFail(body, /if\s*\(state\.downloading\)/, "missing active-download stop guard");
  const stop = indexOrFail(body, /sendControlCommand\(chrome,\s*["']stop["']\)/, "missing native stop command");
  assert.ok(guard < stop);
  assert.match(body.slice(guard, stop), /finish|download/i);
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
