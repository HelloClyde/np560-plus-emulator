"use strict";
// Run the actual queue function; do not replace its serialisation with a mock.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const code = app.slice(app.indexOf("function queueKeyPayload("),
  app.indexOf("\nconst keyboardInput ="));
const history = [], requests = [];
const sandbox = vm.createContext({
  Date, JSON, keyTransportHistory: history,
  keyPayloadGeneration: 0, keyRequestQueue: Promise.resolve(),
  releaseRequestsInFlight: 0, backendReleasePending: false,
  keyLeaseAccepted: false, keyLeaseId: "test", keyLeaseMs: 1500,
  statusText: {}, payloadIsReleased: p => !p.matrix_low && !p.matrix_high,
  api: (url, options) => new Promise((resolve, reject) => {
    requests.push({ url, payload: JSON.parse(options.body), resolve, reject });
  }),
});
vm.runInContext(code, sandbox);
let resends = 0;
sandbox.keyboardInput = { hasHeldKeys: () => false, resendHeld: () => resends++ };
sandbox.keyHeartbeatInFlight = false;
vm.runInContext(app.slice(app.indexOf('function synchronizeReleasedBackend()'),
  app.indexOf('\nlet lastDiagnosticsPoll')), sandbox);
const press = { state: 0, code: 65, matrix_low: 2, matrix_high: 0 };
const release = { state: 0, code: 0, matrix_low: 0, matrix_high: 0 };
const flush = async () => { for (let i = 0; i < 8; i++) await Promise.resolve(); };
(async () => {
  const first = sandbox.queueKeyPayload(press);
  const second = sandbox.queueKeyPayload(release);
  assert.deepEqual(history.map(x => x.outcome), ["queued", "queued"]);
  await flush();
  assert.equal(requests.length, 1);
  assert.deepEqual(history.map(x => x.outcome), ["pending", "queued"]);
  requests[0].resolve({ applied: false }); await first; await flush();
  assert.deepEqual(history.map(x => x.outcome), ["rejected", "pending"]);
  requests[1].resolve({ applied: true }); await second; await flush();
  assert.equal(history[1].outcome, "accepted");
  assert.equal(sandbox.releaseRequestsInFlight, 0);
  const failed = sandbox.queueKeyPayload(press);
  const recovered = sandbox.queueKeyPayload(release);
  await flush(); requests[2].reject(new Error("offline"));
  await assert.rejects(failed, /offline/); await flush();
  assert.equal(history[2].outcome, "error");
  requests[3].resolve({}); await recovered; await flush();
  assert.equal(history[3].outcome, "unconfirmed");
  // An incomplete response is not proof of ownership. In particular an
  // unconfirmed release must remain pending so polling can retry the break.
  assert.equal(sandbox.backendReleasePending, true);
  sandbox.synchronizeReleasedBackend();
  await flush();
  assert.equal(requests.at(-1).payload.matrix_low, 0);
  requests.at(-1).resolve({applied: true});
  await sandbox.keyRequestQueue; await flush();
  assert.equal(sandbox.backendReleasePending, false);
  const uncertainMake = sandbox.queueKeyPayload(press);
  await flush(); requests.at(-1).resolve({}); await uncertainMake; await flush();
  assert.equal(sandbox.keyLeaseAccepted, false);
  assert.equal(sandbox.backendReleasePending, true);
  sandbox.keyboardInput.hasHeldKeys = () => true;
  const beforeRetry = requests.length;
  await sandbox.maintainKeyLease();
  assert.equal(resends, 1);
  assert.equal(requests.length, beforeRetry, 'unconfirmed make must retry, not heartbeat');
  for (let i = 0; i < 130; i++) {
    const pending = sandbox.queueKeyPayload(press);
    await flush(); requests.at(-1).resolve({ applied: true }); await pending;
  }
  assert.equal(history.length, 128);
  assert.equal(history[0].generation, 9);
  assert.equal(history.at(-1).generation, 136);
  assert.ok(history.every(x => x.queued_at_ms <= x.sent_at_ms &&
    x.sent_at_ms <= x.completed_at_ms && x.outcome === "accepted"));
  assert.equal(requests[0].payload.matrix_low, 2);
  // JSON null is a syntactically valid but invalid ACK. It must not throw
  // inside the detached completion handler and strand the release counter.
  sandbox.keyboardInput.hasHeldKeys = () => false;
  for (const reply of [null, false, 0, "ok", [], {applied: "true"}]) {
    const pending = sandbox.queueKeyPayload(release);
    await flush(); requests.at(-1).resolve(reply); await pending; await flush();
    assert.equal(history.at(-1).outcome, "unconfirmed");
    assert.equal(sandbox.releaseRequestsInFlight, 0);
    assert.equal(sandbox.backendReleasePending, true);
    assert.equal(sandbox.keyLeaseAccepted, false);
    const previousCount = requests.length;
    sandbox.synchronizeReleasedBackend(); await flush();
    assert.equal(requests.length, previousCount + 1);
    requests.at(-1).resolve({applied: true});
    await sandbox.keyRequestQueue; await flush();
    assert.equal(sandbox.backendReleasePending, false);
    assert.equal(sandbox.releaseRequestsInFlight, 0);
  }
  console.log("Key transport: serial queue, rejection, error recovery and bounded ACK history passed");
})().catch(error => { console.error(error); process.exitCode = 1; });
