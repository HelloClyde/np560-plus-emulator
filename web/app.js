"use strict";

const canvas = document.getElementById("lcd");
const context = canvas.getContext("2d", { alpha: false });
const lcdWidth = 240;
const lcdHeight = 120;
const annunciatorHeight = 12;
const statusText = document.getElementById("status");
const statusDot = document.getElementById("status-dot");
const registerView = document.getElementById("registers");
const lcdStateView = document.getElementById("lcd-state");
const frameAddress = document.getElementById("frame-address");
const fpsView = document.getElementById("fps");
const saveNandButton = document.getElementById("save-nand");
const nandSaveState = document.getElementById("nand-save-state");
const romIdentityView = document.getElementById("rom-identity");
const keyBits = {
  ArrowUp: 0, ArrowDown: 1, ArrowLeft: 2, ArrowRight: 3, Enter: 4,
  Escape: 5, Backspace: 6, Tab: 7, F1: 8, F2: 9, F3: 10, F4: 11,
  PageUp: 12, PageDown: 13, " ": 14
};
// Exact V3.80 scanner index: column * 8 + row.  The three recovered
// 4F:29B2 key tables assign QWERTY and numeric meanings to the same physical
// top-row positions according to the active guest input mode.
const matrixIndexes = {
  E: 0, D: 1, Q: 2, W: 3, X: 6, R: 8, F: 9, A: 10, C: 14,
  T: 16, G: 17, S: 18, V: 22, Y: 24, H: 25, B: 30,
  U: 32, J: 33, Z: 34, N: 38, I: 40, K: 41, M: 46,
  O: 48, L: 49, P: 56,
  "1": 2, "2": 3, "3": 0, "4": 8, "5": 16,
  "6": 24, "7": 32, "8": 40, "9": 48, "0": 56,
  ",": 20, ".": 54, " ": 54,
  // The case has four F keys, and the only matching four-value consecutive
  // group fixed across all three vendor event tables is 8B..8E.  Correlate
  // those as F1..F4.  Their matrix wiring is non-sequential even though the
  // returned events are sequential: 23->8B, 26->8C, 15->8D, 4->8E.
  F1: 23, F2: 26, F3: 15, F4: 4,
  ArrowUp: 61, PageUp: 61,
  ArrowDown: 37, PageDown: 37, Tab: 37,
  ArrowLeft: 28, Escape: 28, Backspace: 28,
  ArrowRight: 20, Enter: 20
};
const minimumPointerHoldMs = 120;
let heldKeys = 0;
const heldMatrixKeys = new Set();
let heldMatrixLow = 0;
let heldMatrixHigh = 0;
let lastKeyCode = 0;
let keyRequestQueue = Promise.resolve();
let polling = false;
let lastFrameAt = performance.now();
let frames = 0;
let settings = { source: "lcd", base: 0xef0000, bpp: 1, stride: 30, invert: false };

function numericValue(value) {
  const parsed = Number(value.trim());
  if (!Number.isFinite(parsed)) throw new Error("数值格式不正确");
  return Math.trunc(parsed);
}

function applySettings(event) {
  if (event) event.preventDefault();
  const source = document.getElementById("source").value;
  const base = numericValue(document.getElementById("base").value);
  const bpp = Number(document.getElementById("bpp").value);
  let stride = numericValue(document.getElementById("stride").value);
  if (stride === 0) stride = Math.ceil(240 * bpp / 8);
  if (base < 0 || base > 0xffffff || stride < 1 || stride > 4096) {
    throw new Error("帧缓冲参数超出范围");
  }
  settings = { source, base, bpp, stride, invert: document.getElementById("invert").checked };
  frameAddress.textContent = source === "lcd"
    ? "CMD F00001 · DATA F00003"
    : `RAM 0x${base.toString(16).padStart(6, "0").toUpperCase()}`;
  document.querySelectorAll(".memory-setting").forEach(element => {
    element.hidden = source !== "memory";
  });
}

function colors() {
  const styles = getComputedStyle(document.documentElement);
  return [styles.getPropertyValue("--lcd-off").trim(), styles.getPropertyValue("--lcd-on").trim()];
}

function rgb(color) {
  const probe = document.createElement("span");
  probe.style.color = color;
  document.body.appendChild(probe);
  const match = getComputedStyle(probe).color.match(/\d+/g).map(Number);
  probe.remove();
  return match.slice(0, 3);
}

function updateRomIdentity(state) {
  const configured = String(state.soc_rom_configured || "");
  if (!configured) {
    romIdentityView.textContent = "SoC ROM：未配置";
    romIdentityView.title = "";
    return;
  }
  const name = configured.replaceAll("\\", "/").split("/").pop();
  const size = Number(state.soc_rom_size);
  const digest = String(state.soc_rom_sha256 || "").toLowerCase();
  const sizeText = Number.isFinite(size) && size >= 0
    ? `${size.toLocaleString("zh-CN")} B`
    : "大小未知";
  const digestText = /^[0-9a-f]{64}$/.test(digest)
    ? digest.slice(0, 12)
    : "SHA 未知";
  romIdentityView.textContent = `SoC ROM：${name} · ${sizeText} · SHA-256 ${digestText}`;
  romIdentityView.title = /^[0-9a-f]{64}$/.test(digest)
    ? `SHA-256 ${digest}`
    : configured;
}

function annunciatorActive(bytes, plane, bit) {
  const byte = bytes[plane * 30 + (bit >> 3)] || 0;
  return (byte & (1 << (bit & 7))) !== 0;
}

function annunciatorGroupActive(bytes, first, last) {
  for (let bit = first; bit <= last; bit += 1) {
    if (annunciatorActive(bytes, 1, bit)) return true;
  }
  return false;
}

function drawPhotographicStatusMark(x, active, color) {
  if (!active) return;
  // The two centre electrodes are visible in the supplied real-device photo,
  // but their user-facing names are not documented.  Preserve that neutral
  // status-mark silhouette instead of assigning invented firmware semantics.
  context.fillStyle = color;
  context.fillRect(x, 3, 2, 6);
  context.fillRect(x + 2, 4, 2, 4);
  context.fillRect(x + 4, 5, 2, 2);
}

function drawBatteryAnnunciator(bytes, color) {
  // ADC experiments recover two always-on outline electrodes followed by
  // four independently added level groups.  Draw only from those guest LCD
  // segment bits; no browser-side battery value is consulted.
  const outline = annunciatorActive(bytes, 1, 228) ||
    annunciatorActive(bytes, 1, 235);
  if (!outline) return;
  context.fillStyle = color;
  context.fillRect(207, 2, 18, 1);
  context.fillRect(207, 9, 18, 1);
  context.fillRect(206, 3, 1, 6);
  context.fillRect(225, 3, 1, 6);
  context.fillRect(226, 5, 2, 3);
  const levels = [
    [224, 230],
    [234],
    [232, 236],
    [225, 238],
  ];
  levels.forEach((segments, level) => {
    if (segments.some(bit => annunciatorActive(bytes, 1, bit))) {
      context.fillRect(208 + level * 4, 4, 3, 4);
    }
  });
}

function drawAnnunciators(encoded, on) {
  if (!encoded) return;
  const raw = atob(encoded);
  const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
  if (bytes.length !== 60) return;
  const color = `rgb(${on[0]}, ${on[1]}, ${on[2]})`;
  drawPhotographicStatusMark(
    130, annunciatorGroupActive(bytes, 129, 161), color
  );
  drawPhotographicStatusMark(
    170, annunciatorGroupActive(bytes, 166, 188), color
  );
  drawBatteryAnnunciator(bytes, color);
}

function drawFrame(bytes, state) {
  const image = context.createImageData(lcdWidth, lcdHeight + annunciatorHeight);
  const [off, on] = colors().map(rgb);
  const levels = state.format === "gray5" ? 31 : (1 << settings.bpp) - 1;
  for (let y = 0; y < lcdHeight + annunciatorHeight; y += 1) {
    for (let x = 0; x < lcdWidth; x += 1) {
      const target = (y * lcdWidth + x) * 4;
      image.data[target] = off[0];
      image.data[target + 1] = off[1];
      image.data[target + 2] = off[2];
      image.data[target + 3] = 255;
    }
  }
  for (let y = 0; y < lcdHeight; y += 1) {
    for (let x = 0; x < lcdWidth; x += 1) {
      let value;
      if (state.format === "gray5") {
        value = bytes[y * lcdWidth + x] & 31;
      } else {
        const bit = x * settings.bpp;
        const source = bytes[y * settings.stride + (bit >> 3)] || 0;
        const shift = 8 - settings.bpp - (bit & 7);
        value = (source >> shift) & levels;
      }
      if (settings.invert) value = levels - value;
      const mix = value / levels;
      const target = ((y + annunciatorHeight) * lcdWidth + x) * 4;
      image.data[target] = Math.round(off[0] + (on[0] - off[0]) * mix);
      image.data[target + 1] = Math.round(off[1] + (on[1] - off[1]) * mix);
      image.data[target + 2] = Math.round(off[2] + (on[2] - off[2]) * mix);
      image.data[target + 3] = 255;
    }
  }
  context.putImageData(image, 0, 0);
  drawAnnunciators(state.lcd_annunciators, on);
  frames += 1;
  const now = performance.now();
  if (now - lastFrameAt >= 1000) {
    fpsView.textContent = `${Math.round(frames * 1000 / (now - lastFrameAt))} fps`;
    frames = 0;
    lastFrameAt = now;
  }
}

async function api(path, options) {
  const response = await fetch(path, options);
  const payload = await response.json();
  if (!response.ok || payload.error) throw new Error(payload.error || response.statusText);
  return payload;
}

async function poll() {
  if (polling) return;
  polling = true;
  try {
    const size = settings.stride * 120;
    const query = settings.source === "lcd" ? "" :
      `?source=memory&base=${settings.base}&size=${size}`;
    const state = await api(`/api/state${query}`);
    const raw = atob(state.frame);
    const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
    drawFrame(bytes, state);
    registerView.textContent = state.registers || "没有寄存器数据";
    lcdStateView.textContent = state.lcd_state || "没有 LCD 状态";
    updateRomIdentity(state);
    saveNandButton.disabled = !state.nand_save_enabled;
    if (!state.nand_save_enabled) nandSaveState.textContent = "NAND 保存未启用";
    const hle = /HLE_UI=active/.test(state.registers || "");
    statusText.textContent = state.running ? (hle ? "运行中 · ROM 兼容界面" : "运行中") : state.status;
    statusDot.classList.add("online");
  } catch (error) {
    statusText.textContent = error.message;
    statusDot.classList.remove("online");
  } finally {
    polling = false;
  }
}

async function sendKey(code, down) {
  const bit = keyBits[code];
  if (bit !== undefined) {
    heldKeys = down ? heldKeys | (1 << bit) : heldKeys & ~(1 << bit);
  }
  if (matrixIndexes[code] !== undefined) {
    if (down) heldMatrixKeys.add(code);
    else heldMatrixKeys.delete(code);
    heldMatrixLow = 0;
    heldMatrixHigh = 0;
    for (const held of heldMatrixKeys) {
      const index = matrixIndexes[held];
      if (index < 32) heldMatrixLow = (heldMatrixLow | (1 << index)) >>> 0;
      else heldMatrixHigh = (heldMatrixHigh | (1 << (index - 32))) >>> 0;
    }
  }
  if (down) {
    if (code.length === 1) lastKeyCode = code.charCodeAt(0);
    else lastKeyCode = 0x100 + (bit === undefined ? 0x7f : bit);
  }
  const payload = {
    state: heldKeys >>> 0,
    code: down ? lastKeyCode : 0,
    matrix_low: heldMatrixLow,
    matrix_high: heldMatrixHigh
  };
  // Pointer-up can follow pointer-down within the same browser frame.  Keep
  // QMP writes ordered so a fast click can never overtake its make event.
  keyRequestQueue = keyRequestQueue.catch(() => {}).then(() => api("/api/key", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload)
    }));
  try {
    await keyRequestQueue;
  } catch (error) {
    statusText.textContent = error.message;
  }
}

function buildKeyboard() {
  const rows = [
    ["1", "2", "3", "4", "5", "6", "7", "8", "9", "0"],
    ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"],
    ["A", "S", "D", "F", "G", "H", "J", "K", "L", "Backspace"],
    ["Z", "X", "C", "V", "B", "N", "M", ",", ".", "Escape"],
    ["Tab", "PageUp", " ", "PageDown", "Enter"]
  ];
  const labels = { Backspace: "退格", Escape: "返回", Tab: "切换", PageUp: "上页", PageDown: "下页", " ": "空格", Enter: "确认" };
  const keyboard = document.getElementById("keyboard");
  for (const key of rows.flat()) {
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.key = key;
    button.textContent = labels[key] || key;
    if (["Backspace", "Escape", "Tab", "PageUp", "PageDown", " ", "Enter"].includes(key)) button.classList.add("wide");
    keyboard.appendChild(button);
  }
}

function bindKeyButton(button) {
  const code = button.dataset.key;
  let pressedAt = 0;
  let releaseTimer = 0;
  const finishRelease = () => {
    releaseTimer = 0;
    button.classList.remove("is-pressed");
    void sendKey(code, false);
  };
  const press = event => {
    event.preventDefault();
    if (releaseTimer) {
      clearTimeout(releaseTimer);
      releaseTimer = 0;
    }
    pressedAt = performance.now();
    button.classList.add("is-pressed");
    void sendKey(code, true);
  };
  const release = event => {
    event.preventDefault();
    if (!button.classList.contains("is-pressed") || releaseTimer) return;
    const remaining = minimumPointerHoldMs - (performance.now() - pressedAt);
    if (remaining > 0) releaseTimer = setTimeout(finishRelease, remaining);
    else finishRelease();
  };
  button.addEventListener("pointerdown", press);
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("pointerleave", event => { if (button.classList.contains("is-pressed")) release(event); });
}

buildKeyboard();
document.querySelectorAll("[data-key]").forEach(bindKeyButton);
document.getElementById("frame-settings").addEventListener("submit", event => {
  try { applySettings(event); } catch (error) { statusText.textContent = error.message; }
});
document.getElementById("source").addEventListener("change", () => {
  try { applySettings(); } catch (error) { statusText.textContent = error.message; }
});
document.getElementById("page-back").addEventListener("click", () => {
  document.getElementById("base").value = `0x${Math.max(0, settings.base - 0x1000).toString(16)}`; applySettings();
});
document.getElementById("page-next").addEventListener("click", () => {
  document.getElementById("base").value = `0x${Math.min(0xffffff, settings.base + 0x1000).toString(16)}`; applySettings();
});
document.querySelectorAll("[data-action]").forEach(button => button.addEventListener("click", async () => {
  try { await api("/api/control", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ action: button.dataset.action }) }); }
  catch (error) { statusText.textContent = error.message; }
}));
document.getElementById("backlight").addEventListener("input", event => {
  const level = Number(event.target.value);
  canvas.style.filter = `brightness(${0.55 + level * 0.28})`;
});
saveNandButton.addEventListener("click", async () => {
  saveNandButton.disabled = true;
  nandSaveState.textContent = "正在保存完整 NAND…";
  try {
    await api("/api/nand/save", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: "{}"
    });
    nandSaveState.textContent = "NAND 已保存";
  } catch (error) {
    nandSaveState.textContent = error.message;
  } finally {
    saveNandButton.disabled = false;
  }
});
window.addEventListener("keydown", event => {
  if (event.repeat || event.target.matches("input, select")) return;
  const code = event.key.length === 1 ? event.key.toUpperCase() : event.key;
  if (keyBits[code] !== undefined || code.length === 1) { event.preventDefault(); sendKey(code, true); }
});
window.addEventListener("keyup", event => {
  if (event.target.matches("input, select")) return;
  const code = event.key.length === 1 ? event.key.toUpperCase() : event.key;
  if (keyBits[code] !== undefined || code.length === 1) { event.preventDefault(); sendKey(code, false); }
});

applySettings();
poll();
setInterval(poll, 200);
