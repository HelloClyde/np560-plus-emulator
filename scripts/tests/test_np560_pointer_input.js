"use strict";

// Exercise the real app handlers with deterministic transport and time.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const { KeyboardMatrixController } = require("../web/keyboard_input.js");
const source = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
const minimum = Number(/const minimumPointerHoldMs = (\d+);/.exec(source)[1]);
assert.equal(minimum, 150);

function fixture() {
  let now = 0;
  let nextTimer = 0;
  const timers = new Map();
  const sent = [];
  const pending = [];
  const sandbox = {
    performance: { now: () => now },
    minimumPointerHoldMs: minimum,
    pointerButtonSequence: 0,
    pointerPressedAt: new Map(),
    pointerReleaseTimers: new Map(),
    pointerPressReady: new Map(),
    pointerReleasePending: new Set(),
    matrixIndexes: { ArrowRight: 29 },
    keyRequestQueue: Promise.resolve({ applied: true }),
    setTimeout(fn, delay) {
      const id = ++nextTimer;
      timers.set(id, { at: now + delay, fn });
      return id;
    },
    clearTimeout(id) { timers.delete(id); },
  };
  sandbox.keyboardInput = new KeyboardMatrixController({
    matrixIndexes: sandbox.matrixIndexes, keyBits: { ArrowRight: 3 },
    sendPayload(payload) {
      sent.push({ at: now, payload });
      sandbox.keyRequestQueue = new Promise((resolve, reject) => {
        pending.push({ resolve, reject });
      });
    },
  });
  const handlers = new Map();
  const captures = [];
  const button = {
    dataset: { key: "ArrowRight" }, textContent: "Right",
    setAttribute() {},
    setPointerCapture(id) { captures.push(id); },
    addEventListener(name, handler) { handlers.set(name, handler); },
  };
  const functions = ["clearPointerReleaseTimers", "releaseAllKeys", "bindKeyButton"]
    .map(name => {
      const match = new RegExp(`function ${name}\\([^]*?\\n\\}`).exec(source);
      assert.ok(match, name);
      return match[0];
    }).join("\n");
  vm.createContext(sandbox);
  vm.runInContext(functions, sandbox);
  sandbox.bindKeyButton(button);
  return {
    sent, timers, captures, sandbox,
    press(overrides = {}) { return handlers.get("pointerdown")({ pointerId: 1, button: 0, pointerType: "mouse", preventDefault() {}, ...overrides }); },
    release(overrides = {}) { return handlers.get("pointerup")({ pointerId: 1, button: 0, pointerType: "mouse", preventDefault() {}, ...overrides }); },
    ack(value = { applied: true }) { pending.shift().resolve(value); },
    fail() { pending.shift().reject(new Error("transport lost")); },
    blur() { sandbox.releaseAllKeys(false); },
    advance(ms) {
      now += ms;
      for (const [id, timer] of Array.from(timers)) {
        if (timer.at <= now) { timers.delete(id); timer.fn(); }
      }
    },
  };
}

const flush = async () => { for (let i = 0; i < 6; ++i) await Promise.resolve(); };
const released = f => f.sent.at(-1).payload.matrix_low === 0;

async function main() {
  {
    const f = fixture();
    for (const button of [1, 2, 3, 4]) f.press({ button });
    f.press({ pointerType: "pen", button: 2 });
    assert.equal(f.sent.length, 0, "context/auxiliary clicks must not press a guest key");
    assert.equal(f.captures.length, 0);
  }
  {
    const f = fixture();
    f.press({ pointerType: "touch", isPrimary: true });
    f.ack(); await flush();
    f.press({ pointerType: "touch", isPrimary: false, pointerId: 2 });
    await flush();
    f.advance(200);
    await f.release({ pointerType: "touch" });
    assert.equal(released(f), false, "second finger must retain the shared physical key");
    await f.release({ pointerType: "touch", pointerId: 2 });
    assert.equal(released(f), true);
  }
  {
    const f = fixture();
    f.press(); f.advance(5); const release = f.release();
    f.advance(200);
    assert.equal(f.sent.length, 1, "make not acknowledged; tap must not be shortened");
    f.ack(); await release;
    f.advance(149); assert.equal(released(f), false);
    f.advance(1); assert.equal(released(f), true);
    assert.equal(f.sent[1].at, 355, "contact duration starts at make acknowledgement");
  }
  {
    const f = fixture();
    f.press(); f.ack(); await flush(); f.advance(500);
    await f.release();
    assert.equal(f.sent.length, 2);
    assert.equal(released(f), true, "long hold releases without an extra minimum interval");
  }
  {
    const f = fixture();
    f.press(); const release = f.release(); f.blur();
    assert.equal(released(f), true, "blur immediately releases, even before make acknowledgement");
    f.ack(); await release; f.advance(1000);
    assert.equal(f.sent.length, 2, "late acknowledgement cannot resurrect a cleared pointer");
    assert.equal(f.timers.size, 0);
  }
  {
    const f = fixture();
    f.press(); f.ack(); await flush(); f.advance(5); await f.release();
    f.advance(45); f.press(); await flush();
    assert.equal(f.sent.length, 1, "rapid re-press must not issue another physical make");
    f.advance(100); assert.equal(released(f), false, "old timer must be cancelled");
    await f.release(); f.advance(50);
    assert.equal(released(f), true);
    assert.equal(f.captures.length, 2);
  }
  {
    const f = fixture();
    f.press(); const oldRelease = f.release();
    f.press(); f.ack(); await oldRelease; await flush();
    f.advance(200);
    assert.equal(released(f), false, "old pending release must not release a new press");
    await f.release(); assert.equal(released(f), true);
  }
  {
    const f = fixture();
    f.press(); const release = f.release(); f.advance(200); f.fail();
    await release;
    assert.equal(released(f), true, "failed make still permits release cleanup");
  }
  console.log("Pointer timing, transport delay, rapid re-press, blur and failure: passed");
}
main().catch(error => { console.error(error); process.exitCode = 1; });
