"use strict";

(function exposeKeyboardInput(root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) module.exports = api;
  root.NP560KeyboardInput = api;
}(typeof globalThis === "undefined" ? this : globalThis, () => {
  function owns(object, name) {
    return Object.prototype.hasOwnProperty.call(object, name);
  }

  function normalizeKeyboardEvent(event) {
    const code = String(event.code || "");
    const key = String(event.key || "");
    let match = /^Key([A-Z])$/.exec(code);
    if (match) return match[1];
    match = /^Digit([0-9])$/.exec(code);
    if (match) return match[1];
    // Respect NumLock: navigation events from these switches must continue
    // through the named-key mapping below, not become numeric key presses.
    match = /^Numpad([0-9])$/.exec(code);
    if (match && key === match[1]) return match[1];
    // NumLock-off Decimal reports Delete; do not turn navigation/editing
    // into a guest dot contact. Other locale separators need their own mapping.
    if (code === "NumpadDecimal" && key === ".") return ".";
    if (code === "Space") return " ";
    if (code === "Comma") return ",";
    if (code === "Period") return ".";
    // Physical quote switch, not host-composed text: the guest input mode
    // decides between apostrophe and the normal-mode 0x84 event.
    if (code === "Quote") return "'";
    if (key === "Home") return "StartMenu";
    if ([
      "ArrowUp", "ArrowDown", "ArrowLeft", "ArrowRight", "Enter",
      "Escape", "Backspace", "Tab", "PageUp", "PageDown",
      "F1", "F2", "F3", "F4",
    ].includes(key)) return key;
    return null;
  }

  class KeyboardMatrixController {
    constructor({ matrixIndexes, keyBits, sendPayload, onHeldChange }) {
      this.matrixIndexes = matrixIndexes;
      this.keyBits = keyBits;
      this.sendPayload = sendPayload;
      this.onHeldChange = onHeldChange || (() => {});
      this.sources = new Map();
      this.lastSignature = "0:0:0";
      this.transitionHistory = [];
      this.transitionSequence = 0;
    }

    isMapped(code) {
      return typeof code === "string" && owns(this.matrixIndexes, code);
    }

    hasSource(source) {
      return this.sources.has(source);
    }

    hasHeldKeys() {
      return this.sources.size !== 0;
    }

    heldCodes() {
      return new Set(this.sources.values());
    }

    recentTransitions() {
      return this.transitionHistory.map(entry => ({ ...entry,
        held_sources: entry.held_sources.map(source => ({ ...source })),
      }));
    }

    press(source, code) {
      if (!this.isMapped(code) || this.sources.get(source) === code) {
        return false;
      }
      this.sources.set(source, code);
      return this._commit(code, false, source);
    }

    release(source) {
      if (!this.sources.delete(source)) return false;
      return this._commit(null, false, source);
    }

    releaseAll(force = false) {
      const changed = this.sources.size !== 0;
      this.sources.clear();
      if (!changed && !force) return false;
      return this._commit(null, force);
    }

    resendHeld() {
      if (!this.sources.size) return false;
      const codes = Array.from(this.sources.values());
      return this._commit(codes[codes.length - 1], true);
    }

    _snapshot(downCode) {
      let state = 0;
      let matrixLow = 0;
      let matrixHigh = 0;
      for (const code of new Set(this.sources.values())) {
        const bit = this.keyBits[code];
        if (bit !== undefined) state = (state | (1 << bit)) >>> 0;
        const index = this.matrixIndexes[code];
        if (index < 32) matrixLow = (matrixLow | (1 << index)) >>> 0;
        else matrixHigh = (matrixHigh | (1 << (index - 32))) >>> 0;
      }
      let legacyCode = 0;
      if (downCode !== null) {
        const bit = this.keyBits[downCode];
        legacyCode = downCode.length === 1
          ? downCode.charCodeAt(0)
          : 0x100 + (bit === undefined ? 0x7f : bit);
      }
      return {
        state: state >>> 0,
        code: legacyCode >>> 0,
        matrix_low: matrixLow >>> 0,
        matrix_high: matrixHigh >>> 0,
      };
    }

    _commit(downCode, force = false, source = null) {
      const payload = this._snapshot(downCode);
      // Strict QEMU input is the recovered 64-bit matrix.  Several Web/PC
      // labels intentionally alias one physical matrix switch, so compare
      // physical levels and do not emit a second make/break for an alias.
      const signature = `${payload.matrix_low}:${payload.matrix_high}:` +
        `${payload.matrix_low || payload.matrix_high ? 0 : payload.state}`;
      const physicalChanged = signature !== this.lastSignature;
      this.lastSignature = signature;
      this.onHeldChange(this.heldCodes());
      if (!physicalChanged && !force) return false;
      // Local submission intent only: this is not a server ACK or proof the
      // guest consumed a key. Bound memory; never record unrelated host typing.
      this.transitionHistory.push({
        sequence: ++this.transitionSequence, at_ms: Date.now(),
        source,
        held_sources: Array.from(this.sources, ([source, code]) => ({
          source, code, matrix: this.matrixIndexes[code],
        })),
        down_code: downCode, forced: force, ...payload,
      });
      if (this.transitionHistory.length > 128) this.transitionHistory.shift();
      this.sendPayload(payload);
      return true;
    }
  }

  class MinimumKeyboardContact {
    constructor(controller, ready, now = () => performance.now(),
                schedule = (fn, delay) => setTimeout(fn, delay),
                cancel = id => clearTimeout(id)) {
      Object.assign(this, { controller, ready, now, schedule, cancel });
      this.contacts = new Map();
    }
    press(source, code, minimumMs = 0) {
      const previous = this.contacts.get(source);
      if (previous?.timer !== undefined) this.cancel(previous.timer);
      this.controller.press(source, code);
      const contact = { minimumMs, at: this.now(), released: false };
      this.contacts.set(source, contact);
      contact.ready = Promise.resolve(this.ready()).then(result => {
        if (this.contacts.get(source) === contact && result?.applied !== false) {
          contact.at = this.now();
        }
      }, () => {});
    }
    release(source) {
      const contact = this.contacts.get(source);
      if (!contact) return this.controller.release(source);
      if (contact.released) return;
      contact.released = true;
      const finish = () => {
        if (this.contacts.get(source) !== contact) return;
        this.contacts.delete(source);
        this.controller.release(source);
      };
      if (!contact.minimumMs) return finish();
      contact.ready.then(() => {
        if (this.contacts.get(source) !== contact) return;
        const remaining = contact.minimumMs - (this.now() - contact.at);
        if (remaining > 0) contact.timer = this.schedule(finish, remaining);
        else finish();
      });
    }
    cancelAll() {
      for (const contact of this.contacts.values()) {
        if (contact.timer !== undefined) this.cancel(contact.timer);
      }
      this.contacts.clear();
    }
  }

  return { KeyboardMatrixController, MinimumKeyboardContact, normalizeKeyboardEvent };
}));
