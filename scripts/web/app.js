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
const deviceIdentityView = document.getElementById("device-identity");
const audioToggle = document.getElementById("audio-toggle");
const audioStatus = document.getElementById("audio-status");
const audioOutput = new NP560AudioOutput.AudioOutput({
  fetchJSON: (url, options) => api(url, options),
  onStatus: message => { audioStatus.textContent = message; }
});
audioToggle.addEventListener("click", async () => {
  audioToggle.disabled = true;
  try {
    if (audioOutput.enabled) audioOutput.stop();
    else await audioOutput.start();
  } catch (error) {
    audioStatus.textContent = `声音不可用：${error.message}`;
  } finally {
    audioToggle.disabled = false;
    audioToggle.textContent = audioOutput.enabled ? "关闭声音" : "启用声音";
    audioToggle.setAttribute("aria-pressed", String(audioOutput.enabled));
  }
});
window.addEventListener("pagehide", () => audioOutput.stop());
const { KeyboardMatrixController, normalizeKeyboardEvent } = NP560KeyboardInput;
const keyBits = {
  ArrowUp: 0, ArrowDown: 1, ArrowLeft: 2, ArrowRight: 3, Enter: 4,
  Escape: 5, Backspace: 6, Tab: 7, F1: 8, F2: 9, F3: 10, F4: 11,
  PageUp: 12, PageDown: 13, " ": 14, StartMenu: 15
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
  // Original MP3 controls: 0E:992E dispatches E2 to the file picker,
  // E1 to the track list, and EA to settings; 0D:555A handles 8E exit.
  // The skin labels those actions F1..F4. In the normal/lowercase modes:
  // M60->E2, M52->E1, M44->EA, M4->8E. Uppercase mode instead gives
  // DD/DC/DF for F1/F2/F3; that remains guest-owned, not host-normalized.
  // These keys are NOT the 8B..8E group:
  // M26/8C is consumed by the keyboard worker as an annunciator toggle.
  F1: 60, F2: 52, F3: 44, F4: 4,
  // All three vendor tables return 0xB0 at matrix index 55. The original
  // 20:3102 dispatcher requests application FF; 22:52DC then switches menu
  // category 1 to 0, or any other category to 1. This is not a host command
  // to open Start unconditionally. Keep one physical key per user action.
  StartMenu: 55,
  ArrowUp: 61, PageUp: 61,
  ArrowDown: 37, PageDown: 37, Tab: 37,
  // Live NPE-game execution proves the four-way pad uses the dedicated
  // 0x80..0x83 event group.  Escape/Backspace remain the separate 0x84 key.
  ArrowLeft: 45, Escape: 28, Backspace: 28,
  ArrowRight: 29, Enter: 53
};
// Original TBC=8009 runs at 64 Hz. 08:40D0 makes the keyboard worker eligible
// after four ticks, and 31:BE70 requires two scans for a new physical key:
// nominally up to 125 ms depending on phase (busy guest code can delay it).
// A mouse tap becomes a 150 ms minimum
// contact, including a small transport margin; this is not a factory timing
// constant. PC key-up and held-key repetition remain unmodified.
const minimumPointerHoldMs = 150;
const keyLeaseMs = 1500;
const keyHeartbeatMs = 500;
const keyLeaseId = typeof globalThis.crypto?.randomUUID === "function"
  ? globalThis.crypto.randomUUID()
  : `web-${Date.now()}-${Math.random().toString(16).slice(2)}`;
let keyRequestQueue = Promise.resolve();
let keyPayloadGeneration = 0;
let backendReleasePending = false;
let releaseRequestsInFlight = 0;
let keyHeartbeatInFlight = false;
let keyLeaseAccepted = false;
const pointerPressedAt = new Map();
const pointerReleaseTimers = new Map();
const pointerPressReady = new Map();
const pointerReleasePending = new Set();
let pointerButtonSequence = 0;
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

function payloadIsReleased(payload) {
  return payload.state === 0 && payload.code === 0 &&
    payload.matrix_low === 0 && payload.matrix_high === 0;
}

function updatePressedButtons(heldCodes) {
  document.querySelectorAll("[data-key]").forEach(button => {
    button.classList.toggle("is-pressed", heldCodes.has(button.dataset.key));
    button.setAttribute("aria-pressed", heldCodes.has(button.dataset.key) ? "true" : "false");
  });
}

function queueKeyPayload(payload, keepalive = false) {
  const generation = ++keyPayloadGeneration;
  const released = payloadIsReleased(payload);
  if (released) releaseRequestsInFlight += 1;
  backendReleasePending = true;
  const request = keyRequestQueue.catch(() => {}).then(() => api("/api/key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload, lease_id: keyLeaseId, lease_ms: keyLeaseMs,
    }),
    keepalive,
  }));
  keyRequestQueue = request;
  void request.then(result => {
    if (generation === keyPayloadGeneration) {
      // A different live page may still own the server-side lease.  Keep a
      // rejected make locally held so maintainKeyLease() can retry it after
      // that lease expires; a rejected break belongs to this stale page and
      // needs no further synchronization.
      keyLeaseAccepted = !released && result.applied !== false;
      backendReleasePending = !released;
    }
    if (released) releaseRequestsInFlight -= 1;
  }, error => {
    if (generation === keyPayloadGeneration) keyLeaseAccepted = false;
    if (released) releaseRequestsInFlight -= 1;
    statusText.textContent = error.message;
  });
  return request;
}

const keyboardInput = new KeyboardMatrixController({
  matrixIndexes,
  keyBits,
  sendPayload: payload => { void queueKeyPayload(payload); },
  onHeldChange: updatePressedButtons,
});

function clearPointerReleaseTimers() {
  for (const timer of pointerReleaseTimers.values()) clearTimeout(timer);
  pointerReleaseTimers.clear();
  pointerPressedAt.clear();
  pointerPressReady.clear();
  pointerReleasePending.clear();
}

function releaseAllKeys(force = false) {
  clearPointerReleaseTimers();
  return keyboardInput.releaseAll(force);
}

function sendEmergencyRelease() {
  releaseAllKeys(false);
  const payload = {
    state: 0, code: 0, matrix_low: 0, matrix_high: 0,
  };
  const body = JSON.stringify({
    ...payload, lease_id: keyLeaseId, lease_ms: keyLeaseMs,
  });
  backendReleasePending = true;
  if (typeof navigator.sendBeacon === "function") {
    navigator.sendBeacon(
      "/api/key", new Blob([body], { type: "application/json" })
    );
  } else {
    void fetch("/api/key", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body,
      keepalive: true,
    });
  }
}

function synchronizeReleasedBackend() {
  if (!backendReleasePending || keyboardInput.hasHeldKeys() || releaseRequestsInFlight) return;
  void queueKeyPayload({
    state: 0, code: 0, matrix_low: 0, matrix_high: 0,
  }, true);
}

async function maintainKeyLease() {
  if (!keyboardInput.hasHeldKeys() || keyHeartbeatInFlight) return;
  keyHeartbeatInFlight = true;
  try {
    await keyRequestQueue.catch(() => {});
    if (!keyboardInput.hasHeldKeys()) return;
    if (!keyLeaseAccepted) {
      keyboardInput.resendHeld();
      return;
    }
    const result = await api("/api/key-heartbeat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lease_id: keyLeaseId }),
    });
    if (!result.active && keyboardInput.hasHeldKeys()) {
      keyLeaseAccepted = false;
      keyboardInput.resendHeld();
    }
  } catch (error) {
    releaseAllKeys(true);
    statusText.textContent = error.message;
  } finally {
    keyHeartbeatInFlight = false;
  }
}

let lastDiagnosticsPoll = -Infinity;
let latestRegisters = "";
async function poll() {
  if (polling) return;
  polling = true;
  try {
    const size = settings.stride * 120;
    let query = settings.source === "lcd" ? "" :
      `?source=memory&base=${settings.base}&size=${size}`;
    const diagnosticsDue = performance.now() - lastDiagnosticsPoll >= 2000;
    if (!diagnosticsDue) query += `${query ? "&" : "?"}diagnostics=0`;
    const state = await api(`/api/state${query}`);
    if (diagnosticsDue) lastDiagnosticsPoll = performance.now();
    synchronizeReleasedBackend();
    const raw = atob(state.frame);
    const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
    drawFrame(bytes, state);
    if (state.registers !== null && state.registers !== undefined) {
      latestRegisters = state.registers;
      registerView.textContent = latestRegisters || "没有寄存器数据";
    }
    lcdStateView.textContent = state.lcd_state || "没有 LCD 状态";
    updateRomIdentity(state);
    if (deviceIdentityView) {
      deviceIdentityView.textContent = state.device ?
        `设备：${state.device.name} · ${state.device.id}` : "设备：未绑定配置（使用本次启动参数）";
    }
    saveNandButton.disabled = !state.nand_save_enabled;
    const durableNand = state.nand_journal_state || "disabled";
    if (durableNand.startsWith("failed")) {
      nandSaveState.textContent = "NAND 实时保存失败，请检查磁盘";
    } else if (durableNand.startsWith("durable")) {
      nandSaveState.textContent = "NAND 擦写实时保存（增量日志）";
    } else if (!state.nand_save_enabled) {
      nandSaveState.textContent = "NAND 保存未启用";
    }
    const hle = /HLE_UI=active/.test(latestRegisters);
    statusText.textContent = state.running ? (hle ? "运行中 · ROM 兼容界面" : "运行中") : state.status;
    statusDot.classList.add("online");
  } catch (error) {
    if (keyboardInput.hasHeldKeys()) releaseAllKeys(true);
    statusText.textContent = error.message;
    statusDot.classList.remove("online");
  } finally {
    polling = false;
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
    button.dataset.matrixIndex = String(matrixIndexes[key]).padStart(2, "0");
    button.textContent = labels[key] || key;
    button.title = `${button.textContent} · 实体矩阵 M${button.dataset.matrixIndex}`;
    button.setAttribute("aria-pressed", "false");
    if (["Backspace", "Escape", "Tab", "PageUp", "PageDown", " ", "Enter"].includes(key)) button.classList.add("wide");
    keyboard.appendChild(button);
  }
}

function bindKeyButton(button) {
  const code = button.dataset.key;
  const pointerButtonId = ++pointerButtonSequence;
  button.dataset.matrixIndex = String(matrixIndexes[code]).padStart(2, "0");
  button.title = `${button.textContent.trim()} · 实体矩阵 M${button.dataset.matrixIndex}`;
  button.setAttribute("aria-pressed", "false");
  const source = event =>
    `pointer:${pointerButtonId}:${code}:${event.pointerId}`;
  const finishRelease = sourceName => {
    pointerReleaseTimers.delete(sourceName);
    pointerPressedAt.delete(sourceName);
    pointerPressReady.delete(sourceName);
    pointerReleasePending.delete(sourceName);
    keyboardInput.release(sourceName);
  };
  const press = event => {
    event.preventDefault();
    const sourceName = source(event);
    if (pointerReleaseTimers.has(sourceName)) {
      clearTimeout(pointerReleaseTimers.get(sourceName));
      pointerReleaseTimers.delete(sourceName);
    }
    if (typeof button.setPointerCapture === "function") {
      button.setPointerCapture(event.pointerId);
    }
    pointerPressedAt.set(sourceName, performance.now());
    pointerReleasePending.delete(sourceName);
    // A rapid second press can arrive before the first press's minimum-hold
    // release timer fires.  It still needs fresh pointer capture and timing,
    // but the physical switch must not receive a duplicate make.
    if (!keyboardInput.hasSource(sourceName)) keyboardInput.press(sourceName, code);
    // Start the minimum contact interval after the make has reached QEMU,
    // not before it waits in the HTTP/QMP queue. Use a fresh promise even for
    // a rapid re-press, so an older pending release cannot release this press.
    const ready = keyRequestQueue.then(result => {
      if (pointerPressReady.get(sourceName) !== ready) return;
      if (result?.applied !== false) {
        pointerPressedAt.set(sourceName, performance.now());
      }
    }, () => {});
    pointerPressReady.set(sourceName, ready);
  };
  const release = async event => {
    event.preventDefault();
    const sourceName = source(event);
    if (!keyboardInput.hasSource(sourceName) || pointerReleaseTimers.has(sourceName) ||
        pointerReleasePending.has(sourceName)) return;
    const ready = pointerPressReady.get(sourceName);
    pointerReleasePending.add(sourceName);
    await ready;
    if (pointerPressReady.get(sourceName) !== ready ||
        !keyboardInput.hasSource(sourceName)) return;
    pointerReleasePending.delete(sourceName);
    const pressedAt = pointerPressedAt.get(sourceName) || 0;
    const remaining = minimumPointerHoldMs - (performance.now() - pressedAt);
    if (remaining > 0) {
      pointerReleaseTimers.set(
        sourceName, setTimeout(() => finishRelease(sourceName), remaining)
      );
    } else finishRelease(sourceName);
  };
  button.addEventListener("pointerdown", press);
  button.addEventListener("pointerup", release);
  button.addEventListener("pointercancel", release);
  button.addEventListener("lostpointercapture", release);
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
function keyboardSource(event) {
  return `keyboard:${event.code || event.key}`;
}

function editableTarget(target) {
  return target instanceof Element && Boolean(target.closest(
    "input, select, textarea, [contenteditable='true']"
  ));
}

window.addEventListener("keydown", event => {
  if (editableTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
  const code = normalizeKeyboardEvent(event);
  if (!keyboardInput.isMapped(code)) return;
  event.preventDefault();
  if (event.repeat) return;
  keyboardInput.press(keyboardSource(event), code);
});
window.addEventListener("keyup", event => {
  const sourceName = keyboardSource(event);
  if (!keyboardInput.hasSource(sourceName)) return;
  event.preventDefault();
  keyboardInput.release(sourceName);
});
window.addEventListener("blur", () => { releaseAllKeys(false); });
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "hidden") releaseAllKeys(false);
});
window.addEventListener("pagehide", sendEmergencyRelease);
window.addEventListener("beforeunload", sendEmergencyRelease);

applySettings();
poll();
setInterval(poll, 200);
setInterval(() => { void maintainKeyLease(); }, keyHeartbeatMs);
