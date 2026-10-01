"use strict";

// Exercise actual browser handlers, not a duplicate of their filtering logic.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { KeyboardMatrixController, normalizeKeyboardEvent } = require("../web/keyboard_input.js");
const app = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const handlers = new Map();
const documentHandlers = new Map();
const packets = [];
let now = 0, timerId = 0, emergencyReleases = 0;
const emergencyBodies = [];
const timers = new Map(), toggleHandlers = new Map();
const toggle = { checked: false,
  addEventListener: (name, handler) => toggleHandlers.set(name, handler) };
class Element {
  constructor(editable = false, control = false) {
    this.isContentEditable = editable;
    this.control = control;
  }
  closest() { return this.control ? this : null; }
}
const input = new KeyboardMatrixController({
  matrixIndexes: { A: 1, ArrowRight: 29, Enter: 53, "1": 2, ".": 54, "'": 28, Escape: 28 },
  keyBits: { ArrowRight: 3, Enter: 4 },
  sendPayload: packet => packets.push(packet),
});
const document = {
  getElementById: id => id === 'keyboard-short-tap' ? toggle : null,
  visibilityState: "visible",
  addEventListener: (name, handler) => documentHandlers.set(name, handler),
};
const sandbox = vm.createContext({
  Element, keyboardInput: input, normalizeKeyboardEvent, document,
  keyRequestQueue: Promise.resolve(), performance: { now: () => now },
  setTimeout(fn, delay) {
    assert.ok(this === undefined || this === sandbox, 'timer called with foreign receiver');
    const id = ++timerId; timers.set(id, {fn, at: now + delay}); return id;
  },
  clearTimeout(id) {
    assert.ok(this === undefined || this === sandbox, 'timer cancellation called with foreign receiver');
    timers.delete(id);
  },
  window: { addEventListener: (name, handler) => handlers.set(name, handler) },
  clearPointerReleaseTimers() {},
  keyLeaseId: 'test-keyboard-events', keyLeaseMs: 1500,
  backendReleasePending: false, Blob,
  navigator: { sendBeacon(url, body) {
    assert.equal(url, '/api/key');
    assert.ok(body instanceof Blob);
    emergencyBodies.push(body);
    emergencyReleases++;
    return true;
  } },
});
vm.runInContext(fs.readFileSync(path.join(__dirname, '../web/keyboard_input.js'), 'utf8'), sandbox);
// Use the actual release function too: a mock that only clears the matrix
// cannot detect a delayed-contact timer surviving blur or option changes.
const releaseFunction = /function releaseAllKeys\([^]*?\n\}/.exec(app)[0];
const emergencyFunction = /function sendEmergencyRelease\([^]*?\n\}/.exec(app)[0];
vm.runInContext(releaseFunction + '\n' + emergencyFunction + '\n' + app.slice(app.indexOf("function keyboardSource(event)"),
  app.indexOf("\napplySettings();")), sandbox);
function fire(type, overrides = {}) {
  const event = { code: "KeyA", key: "a", target: new Element(),
    repeat: false, ctrlKey: false, metaKey: false, altKey: false,
    isComposing: false, keyCode: 65, prevented: false,
    preventDefault() { this.prevented = true; }, ...overrides };
  handlers.get(type)(event);
  return event;
}

for (const overrides of [
  { isComposing: true }, { keyCode: 229 }, { ctrlKey: true },
  { altKey: true }, { metaKey: true },
  { target: new Element(true) }, { target: new Element(false, true) },
]) {
  const before = packets.length;
  assert.equal(fire("keydown", overrides).prevented, false);
  assert.equal(packets.length, before, "text entry/shortcut leaked into guest");
}
assert.equal(fire("keydown").prevented, true);
assert.equal(packets.at(-1).matrix_low, 2);
const count = packets.length;
fire("keydown", { repeat: true });
assert.equal(packets.length, count, "OS repeat emitted another make");
// Key-up must release an existing make even after focus/modifier/IME changes.
fire("keyup", { target: new Element(true), ctrlKey: true, isComposing: true });
assert.equal(input.hasHeldKeys(), false);
assert.equal(packets.at(-1).matrix_low, 0);

// Distinct PC sources can hold the same switch without premature release.
for (const key of ["'", '"']) {
  const before = packets.length;
  fire("keydown", { code: "Quote", key });
  assert.equal(packets.at(-1).matrix_low, 1 << 28);
  fire("keydown", { code: "Escape", key: "Escape" });
  fire("keyup", { code: "Quote", key });
  assert.equal(packets.length, before + 1, "alias must preserve held M28");
  fire("keyup", { code: "Escape", key: "Escape" });
  assert.equal(packets.at(-1).matrix_low, 0);
}
fire("keydown", { code: "Enter", key: "Enter" });
fire("keydown", { code: "NumpadEnter", key: "Enter" });
fire("keyup", { code: "Enter", key: "Enter" });
assert.equal(input.hasHeldKeys(), true);
assert.equal(packets.at(-1).matrix_high, 1 << 21);
fire("keyup", { code: "NumpadEnter", key: "Enter" });
assert.equal(input.hasHeldKeys(), false);
fire("keydown");
handlers.get("blur")();
assert.equal(input.hasHeldKeys(), false);
fire("keydown");
document.visibilityState = "hidden";
documentHandlers.get("visibilitychange")();
assert.equal(input.hasHeldKeys(), false);
// A page may enter the back/forward cache without a prior blur/hidden event.
// Restoring it must not let the heartbeat resend a pre-navigation contact.
fire("keydown");
const emergenciesBeforeHide = emergencyReleases;
handlers.get("pagehide")({ persisted: true });
assert.equal(input.hasHeldKeys(), false, "pagehide retained a key for BFCache restore");
assert.equal(emergencyReleases, emergenciesBeforeHide + 1);
assert.equal(sandbox.backendReleasePending, true);
// NumLock digits must use the same physical switches as the number row.
for (let digit = 0; digit < 10; digit++) {
  assert.equal(normalizeKeyboardEvent({ code: `Numpad${digit}`, key: String(digit) }),
    String(digit));
}
assert.equal(normalizeKeyboardEvent({ code: "Numpad6", key: "ArrowRight" }), "ArrowRight");
assert.equal(normalizeKeyboardEvent({ code: "Numpad5", key: "Clear" }), null);
assert.equal(normalizeKeyboardEvent({ code: "NumpadAdd", key: "+" }), null);
assert.equal(normalizeKeyboardEvent({ code: "NumpadDecimal", key: "." }), ".");
assert.equal(normalizeKeyboardEvent({ code: "NumpadDecimal", key: "Delete" }), null);
// Decimal is an alias of the existing dot switch, not a new guest key.
fire("keydown", { code: "Period", key: "." });
const decimalPackets = packets.length;
fire("keydown", { code: "NumpadDecimal", key: "." });
assert.equal(packets.length, decimalPackets);
fire("keyup", { code: "Period", key: "." });
assert.equal(packets.at(-1).matrix_high, 1 << 22);
fire("keyup", { code: "NumpadDecimal", key: "Delete" });
assert.equal(input.hasHeldKeys(), false);
assert.equal(packets.at(-1).matrix_high, 0);
fire("keydown", { code: "Digit1", key: "1" });
fire("keydown", { code: "Numpad1", key: "1" });
fire("keyup", { code: "Digit1", key: "1" });
assert.equal(packets.at(-1).matrix_low, 4);
// Changing NumLock while held must still release the original physical source.
fire("keyup", { code: "Numpad1", key: "End" });
assert.equal(input.hasHeldKeys(), false);
assert.equal(packets.at(-1).matrix_low, 0);
console.log("Keyboard IME, focus, aliases, repeat and release: passed");

// The history is bounded submission intent, not a duplicate make for aliases.
const historyInput = new KeyboardMatrixController({
  matrixIndexes: { A: 1, AliasA: 1 }, keyBits: {}, sendPayload() {},
});
historyInput.press('a', 'A');
historyInput.press('alias', 'AliasA');
historyInput.release('a');
assert.equal(historyInput.recentTransitions().length, 1);
historyInput.release('alias');
assert.equal(historyInput.recentTransitions()[1].matrix_low, 0);
historyInput.recentTransitions()[0].matrix_low = 999;
assert.equal(historyInput.recentTransitions()[0].matrix_low, 2);
for (let i = 0; i < 100; i++) {
  historyInput.press('a', 'A'); historyInput.release('a');
}
const history = historyInput.recentTransitions();
assert.equal(history.length, 128);
assert.equal(history[0].sequence, 75);
assert.equal(history.at(-1).sequence, 202);
assert.equal(history.at(-1).down_code, null);
assert.equal(history.at(-1).matrix_low, 0);
assert.ok(history.every(entry => Number.isFinite(entry.at_ms)));

(async () => {
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); await Promise.resolve(); };
  const advance = async ms => {
    now += ms; await flush();
    for (const [id, timer] of [...timers]) if (timer.at <= now) {
      timers.delete(id); timer.fn();
    }
  };
  document.visibilityState = 'visible';
  toggle.checked = true; toggleHandlers.get('change')();
  let acknowledge;
  sandbox.keyRequestQueue = new Promise(resolve => { acknowledge = resolve; });
  fire('keydown'); fire('keyup');
  await advance(1000); assert.equal(input.hasHeldKeys(), true);
  acknowledge({applied: true}); await flush();
  await advance(149); assert.equal(input.hasHeldKeys(), true);
  await advance(1); assert.equal(input.hasHeldKeys(), false);
  sandbox.keyRequestQueue = Promise.resolve();
  for (const release of [() => handlers.get('blur')(),
    () => handlers.get('pagehide')({ persisted: true }),
    () => handlers.get('beforeunload')(),
    () => { document.visibilityState = 'hidden'; documentHandlers.get('visibilitychange')(); },
    () => { toggle.checked = false; toggleHandlers.get('change')(); }]) {
    toggle.checked = true; document.visibilityState = 'visible';
    fire('keydown'); await flush(); fire('keyup'); await flush();
    assert.equal(timers.size, 1);
    release(); assert.equal(input.hasHeldKeys(), false); assert.equal(timers.size, 0);
    const count = packets.length;
    await advance(1000); assert.equal(packets.length, count);
  }
  toggle.checked = false;
  fire('keydown'); fire('keyup'); assert.equal(input.hasHeldKeys(), false);
  for (const body of emergencyBodies) {
    assert.deepEqual(JSON.parse(await body.text()), {
      state: 0, code: 0, matrix_low: 0, matrix_high: 0,
      lease_id: 'test-keyboard-events', lease_ms: 1500,
    });
  }
  console.log('Actual optional-contact handlers: timing, toggle, blur and hidden release passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
