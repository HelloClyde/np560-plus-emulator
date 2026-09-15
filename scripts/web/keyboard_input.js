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
    if (code === "Space") return " ";
    if (code === "Comma") return ",";
    if (code === "Period") return ".";
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

    press(source, code) {
      if (!this.isMapped(code) || this.sources.get(source) === code) {
        return false;
      }
      this.sources.set(source, code);
      return this._commit(code);
    }

    release(source) {
      if (!this.sources.delete(source)) return false;
      return this._commit(null);
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

    _commit(downCode, force = false) {
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
      this.sendPayload(payload);
      return true;
    }
  }

  return { KeyboardMatrixController, normalizeKeyboardEvent };
}));
