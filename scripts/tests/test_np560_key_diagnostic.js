"use strict";
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const code = app.slice(app.indexOf("async function downloadKeyDiagnostic()"),
  app.indexOf('\ndocument.getElementById("download-key-diagnostic")'));

async function check(fail = false, shortTap = false) {
  const button = { disabled: false }, message = {}, requests = [], timers = [];
  let blob, clicked = 0, removed = 0, revoked = 0;
  const context = vm.createContext({
    Date, Blob, JSON, Array,
    keyboardShortTap: { checked: shortTap }, minimumPointerHoldMs: 150,
    keyLeaseMs: 1500,
    keyTransportHistory: [{ generation: 1, outcome: "accepted", matrix_low: 16 }],
    keyboardInput: { heldCodes: () => new Set(["F4"]),
      recentTransitions: () => [{ sequence: 1, down_code: "F4", matrix_low: 16 }] },
    matrixIndexes: { F4: 4 },
    api: async (url, options) => {
      assert.equal(options, undefined, "diagnostics must not issue writes");
      requests.push(url);
      // Changing the UI during asynchronous reads must not rewrite the
      // policy snapshot captured before the first request.
      context.keyboardShortTap.checked = !shortTap;
      if (fail) throw new Error("offline");
      return url.includes("state?") ? { frame: "AA==" } : { candidates: 3 };
    },
    document: {
      getElementById: id => id === "download-key-diagnostic" ? button : message,
      createElement: () => ({ click() { clicked++; }, remove() { removed++; } }),
      body: { appendChild() {} },
    },
    URL: { createObjectURL(value) { blob = value; return "blob:test"; },
      revokeObjectURL(url) { assert.equal(url, "blob:test"); revoked++; } },
    setTimeout: fn => timers.push(fn),
  });
  vm.runInContext(code, context);
  const pending = context.downloadKeyDiagnostic();
  assert.equal(button.disabled, true);
  await context.downloadKeyDiagnostic(); // Reentry must not issue duplicate reads.
  await pending;
  assert.equal(button.disabled, false);
  if (fail) {
    assert.equal(clicked, 0);
    assert.equal(requests.length, 1);
    assert.match(message.textContent, /offline/);
  } else {
    assert.deepEqual(requests, ["/api/key-status", "/api/state?source=lcd", "/api/key-status"]);
    const report = JSON.parse(await blob.text());
    assert.equal(report.schema, "np560-key-diagnostic-v1");
    assert.equal(report.input_policy_at_start.keyboard_minimum_host_ms, shortTap ? 150 : 0);
    assert.equal(report.input_policy_at_start.pointer_minimum_host_ms, 150);
    assert.equal(report.input_policy_at_start.lease_ms, 1500);
    assert.match(report.input_policy_at_start.note, /not historical/);
    assert.match(report.input_policy_at_start.note, /do not guarantee guest/);
    assert.deepEqual(report.held_at_start, [{ code: "F4", matrix: 4 }]);
    assert.equal(report.lcd.frame, "AA==");
    assert.equal(report.key_status_after.candidates, 3);
    assert.equal(report.frontend_submissions_at_start[0].matrix_low, 16);
    assert.equal(report.transport_at_start[0].outcome, "accepted");
    assert.match(report.transport_note, /not guest consumption/);
    assert.match(report.frontend_submissions_note, /not transport ACKs/);
    assert.equal(clicked, 1);
    assert.equal(removed, 1);
    timers.forEach(fn => fn());
    assert.equal(revoked, 1);
  }
}
(async () => {
  await check(); await check(false, true); await check(true);
  console.log("Manual key diagnostic: read-only capture, reentry and failure cleanup passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
