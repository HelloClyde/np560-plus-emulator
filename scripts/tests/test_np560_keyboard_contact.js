"use strict";
const assert = require('node:assert/strict');
const { KeyboardMatrixController, MinimumKeyboardContact } = require('../web/keyboard_input.js');

(async () => {
  let now = 0, serial = 0, resolve;
  const timers = new Map(), sent = [];
  let ack = Promise.resolve();
  const matrix = new KeyboardMatrixController({
    matrixIndexes: { A: 1, B: 2, AliasA: 1 }, keyBits: {},
    sendPayload: payload => sent.push(payload),
  });
  const contact = new MinimumKeyboardContact(matrix, () => ack, () => now,
    (fn, delay) => { const id = ++serial; timers.set(id, { fn, at: now + delay }); return id; },
    id => timers.delete(id));
  const flush = async () => { await Promise.resolve(); await Promise.resolve(); };
  const advance = async ms => {
    now += ms; await flush();
    for (const [id, timer] of [...timers]) if (timer.at <= now) {
      timers.delete(id); timer.fn();
    }
  };
  // Default remains raw, synchronous release.
  contact.press('raw', 'A'); contact.release('raw');
  assert.equal(matrix.hasHeldKeys(), false);
  const history = matrix.recentTransitions();
  assert.equal(history[0].source, 'raw');
  assert.deepEqual(history[0].held_sources, [{ source: 'raw', code: 'A', matrix: 1 }]);
  assert.equal(history[1].source, 'raw');
  assert.deepEqual(history[1].held_sources, []);
  history[0].held_sources[0].matrix = 63;
  assert.equal(matrix.recentTransitions()[0].held_sources[0].matrix, 1,
    'downloaded history must not mutate retained source snapshots');
  // Minimum interval begins after transport acknowledgement, not keydown.
  ack = new Promise(r => { resolve = r; });
  contact.press('a', 'A', 150); contact.release('a');
  await advance(1000); assert.equal(matrix.hasHeldKeys(), true);
  resolve({ applied: true }); await flush();
  await advance(149); assert.equal(matrix.hasHeldKeys(), true);
  await advance(1); assert.equal(matrix.hasHeldKeys(), false);
  ack = Promise.resolve();
  // Independent overlapping directions and aliases preserve physical holds.
  contact.press('a', 'A', 150); await flush(); contact.release('a');
  contact.press('b', 'B', 150); await flush();
  assert.equal(sent.at(-1).matrix_low, 6);
  await advance(150); assert.equal(sent.at(-1).matrix_low, 4);
  contact.release('b'); await flush(); assert.equal(matrix.hasHeldKeys(), false);
  contact.press('a', 'A', 150); await flush(); contact.release('a');
  contact.press('alias', 'AliasA', 150); await flush();
  await advance(150); assert.equal(sent.at(-1).matrix_low, 2);
  contact.release('alias'); await flush(); assert.equal(matrix.hasHeldKeys(), false);
  // Repress invalidates old release; blur/cancel defeats pending ACK/timers.
  contact.press('a', 'A', 150); await flush(); contact.release('a');
  await advance(100); contact.press('a', 'A', 150); await flush();
  await advance(100); assert.equal(matrix.hasHeldKeys(), true);
  contact.release('a'); contact.cancelAll(); matrix.releaseAll();
  await advance(1000); assert.equal(matrix.hasHeldKeys(), false);
  ack = new Promise(r => { resolve = r; });
  contact.press('a', 'A', 150); contact.release('a');
  contact.cancelAll(); matrix.releaseAll(); resolve(); await advance(1000);
  assert.equal(matrix.hasHeldKeys(), false); assert.equal(timers.size, 0);
  console.log('Optional keyboard minimum contact: passed');
})().catch(error => { console.error(error); process.exitCode = 1; });
