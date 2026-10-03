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
  onStatus: message => { audioStatus.textContent = message; },
  onEnabledChange: enabled => {
    audioToggle.textContent = enabled ? "关闭声音" : "启用声音";
    audioToggle.setAttribute("aria-pressed", String(enabled));
  }
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
  ",": 20, ".": 54, " ": 54, "'": 28,
  // Original MP3 controls: 0E:992E dispatches E2 to the file picker,
  // E1 to the track list, and EA to settings; 0D:555A handles 8E exit.
  // The skin labels those actions F1..F4. In the normal/lowercase modes:
  // M60->E2, M52->E1, M44->EA, M4->8E. Uppercase mode instead gives
  // DD/DC/DF for F1/F2/F3; that remains guest-owned, not host-normalized.
  // These keys are NOT the 8B..8E group:
  // M26/8C is consumed by the keyboard worker as an annunciator toggle.
  F1: 60, F2: 52, F3: 44, F4: 4,
  // The NP560+ manual names the lower-right slide-out key "目录" and says it
  // returns to the root directory. All three vendor tables return 0xB0 at
  // matrix index 55. The original
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
// Raw switches expose the complete hardware matrix without inventing names
// for side keys. These are pointer controls only, not PC keyboard bindings.
for (let index = 0; index < 64; index += 1) {
  matrixIndexes[`Matrix${String(index).padStart(2, "0")}`] = index;
}
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
// Transport acknowledgements are distinct from guest scan/consumption.
const keyTransportHistory = [];
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
let filesOffline = false;
let filesBusy = false;
let filesPath = "/";
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

// The six separately driven glass electrodes are one-bit states, not two
// ranges of interchangeable marks. Their left-to-right silhouettes follow
// the supplied NP560+ photograph. The shape/position pairing is photographic
// reconstruction; the bit values remain the guest's raw LCD output.
const statusArtwork = [
  { bit: 133, x: 92, pixels: ["000010000", "000111000", "001111100", "011111110", "000111000", "000111000", "000111000", "000111000"] },
  { bit: 150, x: 110, pixels: ["000100000", "001100000", "011111110", "111111110", "011111110", "001100000", "000100000", "000000000"] },
  { bit: 163, x: 128, pixels: ["000001000", "000001100", "011111110", "011111111", "011111110", "000001100", "000001000", "000000000"] },
  { bit: 179, x: 146, pixels: ["000111000", "000111000", "000111000", "000111000", "011111110", "001111100", "000111000", "000010000"] },
  { bit: 196, x: 164, pixels: ["000000000", "000000000", "000010000", "000111000", "001111100", "011111110", "000000000", "000000000"] },
  { bit: 211, x: 182, pixels: ["000000000", "000000000", "011111110", "001111100", "000111000", "000010000", "000000000", "000000000"] },
];

function drawStatusArtwork(pixels, x, color) {
  context.fillStyle = color;
  pixels.forEach((row, y) => {
    for (let column = 0; column < row.length; column += 1) {
      if (row[column] === "1") context.fillRect(x + column, y + 2, 1, 1);
    }
  });
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

function drawAnnunciators(encoded, on, off) {
  if (!encoded) return;
  const raw = atob(encoded);
  const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
  if (bytes.length !== 60) return;
  const color = `rgb(${on[0]}, ${on[1]}, ${on[2]})`;
  // Unselected glass silhouettes remain faintly visible in the real-device
  // photograph. They are artwork only, never synthesized active status bits.
  const ghost = `rgb(${off.map((value, index) => Math.round(value * 0.86 + on[index] * 0.14)).join(",")})`;
  for (const artwork of statusArtwork) {
    drawStatusArtwork(artwork.pixels, artwork.x,
      annunciatorActive(bytes, 1, artwork.bit) ? color : ghost);
  }
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
  drawAnnunciators(state.lcd_annunciators, on, off);
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

async function downloadKeyDiagnostic() {
  const button = document.getElementById("download-key-diagnostic");
  const message = document.getElementById("key-diagnostic-status");
  if (button.disabled) return;
  button.disabled = true;
  message.textContent = "正在读取…";
  let url;
  let link;
  try {
    const startedAt = new Date().toISOString();
    const inputPolicy = {
      keyboard_minimum_host_ms: keyboardShortTap?.checked ? 150 : 0,
      pointer_minimum_host_ms: minimumPointerHoldMs,
      lease_ms: keyLeaseMs,
      note: "Policy at capture start, not historical per-contact settings. Minimum intervals use host time after request completion; they do not guarantee guest scan/debounce acceptance.",
    };
    const held = Array.from(keyboardInput.heldCodes(), code => ({
      code, matrix: matrixIndexes[code],
    }));
    const transitions = keyboardInput.recentTransitions();
    const transport = keyTransportHistory.map(entry => ({ ...entry }));
    const before = await api("/api/key-status");
    const lcd = await api("/api/state?source=lcd");
    const after = await api("/api/key-status");
    const report = {
      schema: "np560-key-diagnostic-v1", started_at: startedAt,
      finished_at: new Date().toISOString(),
      note: "Sequential read-only snapshots, not atomic. Counters are cumulative; no per-key attribution.",
      held_at_start: held, matrix_mapping: matrixIndexes,
      input_policy_at_start: inputPolicy,
      frontend_submissions_at_start: transitions,
      transport_at_start: transport,
      transport_note: "Last 128 queued key requests: server acceptance is not guest consumption. Emergency beacons and heartbeat requests are not included. Reload clears history.",
      frontend_submissions_note: "Last 128 local matrix submission intents, not transport ACKs or guest events. source identifies the triggering control; held_sources lists active controls. Alias changes without a matrix change are not submissions. May start mid-contact; reload clears history.",
      key_status_before: before, lcd, key_status_after: after,
    };
    url = URL.createObjectURL(new Blob([JSON.stringify(report, null, 2)],
      { type: "application/json" }));
    link = document.createElement("a");
    link.href = url;
    link.download = `np560-keys-${startedAt.replace(/[:.]/g, "-")}.json`;
    document.body.appendChild(link);
    link.click();
    message.textContent = "已请求下载；请附上页面、按键顺序及预期结果。";
  } catch (error) {
    message.textContent = `诊断读取失败：${error.message}`;
  } finally {
    if (link) link.remove();
    if (url) setTimeout(() => URL.revokeObjectURL(url), 1000);
    button.disabled = false;
  }
}

document.getElementById("download-key-diagnostic")?.addEventListener("click", downloadKeyDiagnostic);

function updatePressedButtons(heldCodes) {
  const heldIndexes = new Set(Array.from(heldCodes, code => matrixIndexes[code]));
  document.querySelectorAll("[data-key]").forEach(button => {
    const pressed = heldIndexes.has(matrixIndexes[button.dataset.key]);
    button.classList.toggle("is-pressed", pressed);
    button.setAttribute("aria-pressed", pressed ? "true" : "false");
  });
}

function queueKeyPayload(payload, keepalive = false) {
  if (filesOffline) return Promise.resolve({ ok: false, applied: false });
  const generation = ++keyPayloadGeneration;
  const trace = {
    generation, queued_at_ms: Date.now(), sent_at_ms: null,
    completed_at_ms: null, outcome: "queued", ...payload,
  };
  keyTransportHistory.push(trace);
  if (keyTransportHistory.length > 128) keyTransportHistory.shift();
  const released = payloadIsReleased(payload);
  if (released) releaseRequestsInFlight += 1;
  backendReleasePending = true;
  const request = keyRequestQueue.catch(() => {}).then(() => {
    trace.sent_at_ms = Date.now();
    trace.outcome = "pending";
    return api("/api/key", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      ...payload, lease_id: keyLeaseId, lease_ms: keyLeaseMs,
    }),
    keepalive,
    });
  });
  keyRequestQueue = request;
  void request.then(result => {
    // A valid JSON response is not necessarily an ACK object (e.g. null).
    // Keep malformed replies unconfirmed without stranding the release
    // counter inside this detached completion handler.
    const applied = result && typeof result === "object" && !Array.isArray(result)
      ? result.applied : undefined;
    trace.completed_at_ms = Date.now();
    trace.outcome = applied === true ? "accepted"
      : applied === false ? "rejected" : "unconfirmed";
    if (generation === keyPayloadGeneration) {
      // A different live page may still own the server-side lease.  Keep a
      // rejected make locally held so maintainKeyLease() can retry it after
      // that lease expires; a rejected break belongs to this stale page and
      // needs no further synchronization.
      // Only an explicit ACK proves ownership. An incomplete reply to a
      // break cannot prove release either; keep it eligible for retry.
      keyLeaseAccepted = !released && applied === true;
      backendReleasePending = !released ||
        (applied !== true && applied !== false);
    }
    if (released) releaseRequestsInFlight -= 1;
  }, error => {
    trace.completed_at_ms = Date.now();
    trace.outcome = "error";
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
  if (typeof keyboardContact !== "undefined") keyboardContact.cancelAll();
  return keyboardInput.releaseAll(force);
}

function sendEmergencyRelease() {
  if (typeof filesOffline !== "undefined" && filesOffline) return;
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
  if (filesOffline) return;
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
let fastDisplayAvailable = true;
async function poll() {
  if (polling || filesOffline) return;
  polling = true;
  try {
    const size = settings.stride * 120;
    let query = settings.source === "lcd" ? "" :
      `?source=memory&base=${settings.base}&size=${size}`;
    const diagnosticsDue = performance.now() - lastDiagnosticsPoll >= 2000;
    const displayOnly = settings.source === "lcd" && !diagnosticsDue && fastDisplayAvailable;
    if (!diagnosticsDue) query += `${query ? "&" : "?"}diagnostics=0`;
    let state;
    let usedDisplayOnly = displayOnly;
    if (displayOnly) {
      try {
        state = await api("/api/display");
      } catch (_) {
        // Pages served by an already-running older bridge still need to work
        // after app.js is updated on disk. Fall back once to its full API.
        fastDisplayAvailable = false;
        usedDisplayOnly = false;
        state = await api(`/api/state${query}`);
      }
    } else {
      state = await api(`/api/state${query}`);
    }
    if (diagnosticsDue) lastDiagnosticsPoll = performance.now();
    synchronizeReleasedBackend();
    const raw = atob(state.frame);
    const bytes = Uint8Array.from(raw, character => character.charCodeAt(0));
    drawFrame(bytes, state);
    if (usedDisplayOnly) return;
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
    if (filesOffline) return;
    if (keyboardInput.hasHeldKeys()) releaseAllKeys(true);
    statusText.textContent = error.message;
    statusDot.classList.remove("online");
  } finally {
    polling = false;
  }
}

function buildRawMatrixKeyboard() {
  const keyboard = document.getElementById("matrix-keyboard");
  for (let index = 0; index < 64; index += 1) {
    const number = String(index).padStart(2, "0");
    const button = document.createElement("button");
    button.type = "button";
    button.dataset.key = `Matrix${number}`;
    button.textContent = `M${number}`;
    keyboard.appendChild(button);
  }
}

function buildSkinKeyboard() {
  const skin = document.getElementById("skin-keys");
  const size = 1254; // Generated cutout's square coordinate system.
  const add = (code, label, x, y, width, height) => {
    const button = document.createElement("button");
    button.type = "button";
    button.className = "skin-key";
    button.dataset.key = code;
    button.textContent = label;
    button.setAttribute("aria-label", label);
    Object.assign(button.style, {
      left: `${100 * x / size}%`, top: `${100 * y / size}%`,
      width: `${100 * width / size}%`, height: `${100 * height / size}%`,
    });
    skin.appendChild(button);
    return button;
  };
  // Match the attached NP560+ upper-shell photograph and the opened-keyboard
  // NP560T reference. Only switches with an existing, evidenced matrix mapping
  // receive hotspots. The two models share this visible key arrangement; their
  // unverified side-switch electrical identities are not assumed identical.
  ["F1", "F2", "F3", "F4"].forEach((key, index) =>
    add(key, `左侧 ${key}/${"ABCD"[index]}`, 87, 198 + index * 60, 125, 37));
  // The separate left paging disc is not the right-hand cursor pad.
  // On the vendor desktop M11/94 moves up, M19/92 confirms, and M27/95
  // moves down; do not alias them to the right-pad contacts.
  add("Matrix11", "左侧翻页盘上", 117, 465, 64, 40);
  add("Matrix19", "左侧翻页盘中／确认", 117, 505, 64, 50);
  add("Matrix27", "左侧翻页盘下", 117, 555, 64, 40);
  add("Matrix12", "设置", 88, 634, 126, 38);
  // Right-hand shortcut column, verified on the original guest desktop:
  // M59/B4 -> 同步学习, M51/B7 -> 多科助考, M43/BF -> 我的硬盘,
  // M35/97 -> MP3. These are physical contacts, not host-side navigation.
  add("Matrix59", "同步学习", 1038, 198, 129, 37);
  add("Matrix51", "多科助考", 1038, 258, 129, 37);
  add("Matrix43", "我的硬盘", 1038, 318, 129, 37);
  add("Matrix35", "MP3", 1038, 377, 129, 37);
  // The user identified the side-mounted power switch as M63.  Its guest
  // event 0x8F is known to enter the original screen-off path; keep this a
  // physical matrix contact, not a host shutdown/reset command.  The switch
  // itself is hidden in the front-facing reference. Place the visible access
  // button below the pull-out keyboard's right edge, with an air gap.
  const power = add("Matrix63", "电源／休眠", 1019, 1195, 56, 56);
  power.classList.add("skin-side-power");
  power.innerHTML = '<svg class="skin-power-icon" viewBox="0 0 24 24" aria-hidden="true" focusable="false"><path d="M12 2v10M18.36 6.64a9 9 0 1 1-12.73 0"/></svg><span class="visually-hidden">电源／休眠</span>';
  power.setAttribute("aria-label", "侧边电源／休眠键，矩阵 M63");
  add("ArrowUp", "上", 1080, 461, 58, 49);
  add("ArrowLeft", "左", 1039, 501, 50, 60);
  add("Enter", "确认", 1080, 501, 61, 60);
  add("ArrowRight", "右", 1132, 501, 43, 60);
  add("ArrowDown", "下", 1080, 555, 58, 42);
  add("Escape", "返回", 88, 696, 126, 38);
  add(" ", "发音／空格", 1039, 634, 129, 37);
  add("Matrix26", "SHIFT／符号模式（候选映射）", 154, 1003, 94, 65);
  const qwerty = ["Q", "W", "E", "R", "T", "Y", "U", "I", "O", "P"];
  const home = ["A", "S", "D", "F", "G", "H", "J", "K", "L"];
  const lower = ["Z", "X", "C", "V", "B", "N", "M"];
  qwerty.forEach((key, index) => add(key, `${key}／${(index + 1) % 10}`, 154 + index * 94, 863, 94, 62));
  home.forEach((key, index) => add(key, key, 154 + index * 94, 927, 94, 65));
  // In the alphabet table these contacts emit the secondary glyphs printed
  // on the keycaps: M57='@', M62='?', M39='*'.
  add("Matrix57", "生词／@", 1000, 927, 94, 65);
  lower.forEach((key, index) => add(key, key, 248 + index * 94, 1003, 94, 65));
  add(" ", "空格／发音", 906, 1003, 94, 65);
  add("Matrix62", "音标／?", 1000, 1003, 94, 65);
  add("Matrix42", "英汉词典／朗文双解", 154, 1069, 94, 65);
  add("Matrix50", "简明汉英／现代汉语", 248, 1069, 94, 65);
  // User-confirmed in the running emulator: M07 invokes 屏幕取词.
  add("Matrix07", "屏幕取词", 342, 1069, 94, 65);
  add("Matrix15", "帮助", 436, 1069, 94, 65);
  // User-confirmed in the running emulator: M58 invokes 输入法. Preserve the
  // guest matrix path; this is not a host-side input-method implementation.
  add("Matrix58", "输入法", 530, 1069, 94, 65);
  add("Matrix47", "删除", 624, 1069, 94, 65);
  // User-confirmed in the running emulator: M23 invokes 查找.
  add("Matrix23", "查找", 718, 1069, 94, 65);
  // User-confirmed in the running emulator: M31 invokes 添加.
  add("Matrix31", "添加", 812, 1069, 94, 65);
  add("Matrix39", "修改／*", 906, 1069, 94, 65);
  add("StartMenu", "目录（返回总目录）", 1000, 1069, 94, 65);
  const backlight = document.createElement("button");
  backlight.type = "button";
  backlight.className = "skin-key";
  backlight.textContent = "背光";
  backlight.setAttribute("aria-label", "背光亮度");
  Object.assign(backlight.style, {
    left: `${100 * 1039 / size}%`, top: `${100 * 696 / size}%`,
    width: `${100 * 129 / size}%`, height: `${100 * 38 / size}%`,
  });
  backlight.addEventListener("click", () => {
    const slider = document.getElementById("backlight");
    slider.value = String((Number(slider.value) + 1) % 3);
    slider.dispatchEvent(new Event("input", { bubbles: true }));
  });
  skin.appendChild(backlight);
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
    // Only the normal contact activates a key, not mouse context/auxiliary
    // buttons or a pen barrel button. Do not filter isPrimary: a second
    // touch must remain available for multi-finger game controls.
    if (event.button !== 0) return;
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

const homeTabs = [...document.querySelectorAll('.home-tabs [role="tab"]')];
const filesConfirmDialog = document.getElementById("files-confirm-dialog");
const filesConfirmCancel = document.getElementById("files-confirm-cancel");
const filesStatus = document.getElementById("files-status");
const filesList = document.getElementById("files-list");
const filesPathLabel = document.getElementById("files-path");
function setFileMessage(message) { filesStatus.textContent = message; }
function setFilesOffline(offline) {
  filesOffline = offline;
  statusText.textContent = offline ? "已关机 · NAND 文件管理" : "连接中";
  statusDot.classList.toggle("online", !offline);
  document.querySelectorAll(".run-controls button").forEach(button => { button.disabled = offline; });
  audioToggle.disabled = offline;
}
async function listNandFiles(path = filesPath) {
  const result = await api(`/api/files/list?path=${encodeURIComponent(path)}`);
  filesPath = result.path;
  filesPathLabel.textContent = filesPath;
  filesList.replaceChildren();
  for (const entry of result.entries) {
    const item = document.createElement("li");
    const label = document.createElement("button");
    label.type = "button";
    label.textContent = `${entry.directory ? "📁" : "📄"} ${entry.name}`;
    const target = `${filesPath === "/" ? "" : filesPath}/${entry.name}`;
    if (entry.directory) {
      label.addEventListener("click", () => {
        void listNandFiles(target).catch(error => setFileMessage(error.message));
      });
    } else {
      label.disabled = true;
      const size = document.createElement("span");
      size.className = "file-size";
      size.textContent = `${entry.size.toLocaleString()} B`;
      item.appendChild(size);
      const link = document.createElement("a");
      link.href = `/api/files/download?path=${encodeURIComponent(target)}`;
      link.textContent = "下载";
      link.setAttribute("download", entry.name);
      item.appendChild(link);
    }
    item.prepend(label);
    filesList.appendChild(item);
  }
  setFileMessage(`已关机 · ${result.entries.length} 项；导入会保存到新的检查点。`);
}
function confirmFilesShutdown() {
  return new Promise(resolve => {
    filesConfirmDialog.returnValue = "cancel";
    filesConfirmDialog.addEventListener("close", () => {
      resolve(filesConfirmDialog.returnValue === "continue");
    }, { once: true });
    if (keyboardInput.hasHeldKeys()) releaseAllKeys(false);
    filesConfirmDialog.showModal();
    filesConfirmCancel.focus();
  });
}
async function openFilesTab() {
  if (filesOffline) { await listNandFiles(); return true; }
  filesBusy = true;
  try {
    if (!await confirmFilesShutdown()) return false;
    setFileMessage("正在暂停模拟器并导出完整 NAND，请勿关闭页面…");
    releaseAllKeys(false);
    await keyRequestQueue.catch(() => {});
    audioOutput.stop();
    setFilesOffline(true);
    await api("/api/files/open", { method: "POST", body: "" });
    await listNandFiles("/");
    return true;
  } catch (error) {
    setFilesOffline(false);
    setFileMessage(`进入失败：${error.message}`);
    return false;
  } finally { filesBusy = false; }
}
async function resumeFromFiles() {
  if (!filesOffline) return true;
  filesBusy = true;
  setFileMessage("正在保存设备配置并重新开机…");
  try {
    await api("/api/files/resume", { method: "POST", body: "" });
    setFilesOffline(false);
    setFileMessage("模拟器已重新开机。");
    void poll();
    return true;
  } catch (error) {
    setFileMessage(`开机失败：${error.message}。文件检查点仍保留，可重试。`);
    return false;
  } finally { filesBusy = false; }
}
function selectHomeTab(selectedTab) {
  for (const tab of homeTabs) {
    const selected = tab === selectedTab;
    tab.setAttribute("aria-selected", String(selected));
    tab.tabIndex = selected ? 0 : -1;
    document.getElementById(tab.getAttribute("aria-controls")).hidden = !selected;
  }
}
async function changeHomeTab(tab) {
  if (filesBusy) return;
  if (tab.id === "tab-files") {
    if (!await openFilesTab()) return;
  } else if (filesOffline && !await resumeFromFiles()) return;
  selectHomeTab(tab);
  tab.focus();
}
homeTabs.forEach((tab, index) => {
  tab.addEventListener("click", () => { void changeHomeTab(tab); });
  tab.addEventListener("keydown", event => {
    let next = index;
    if (event.key === "ArrowRight") next = (index + 1) % homeTabs.length;
    else if (event.key === "ArrowLeft") next = (index - 1 + homeTabs.length) % homeTabs.length;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = homeTabs.length - 1;
    else return;
    event.preventDefault();
    event.stopPropagation();
    void changeHomeTab(homeTabs[next]);
  });
});
document.getElementById("files-up").addEventListener("click", () => {
  const parts = filesPath.split("/").filter(Boolean);
  parts.pop();
  void listNandFiles("/" + parts.join("/")).catch(error => setFileMessage(error.message));
});
document.getElementById("files-resume").addEventListener("click", async () => {
  if (await resumeFromFiles()) selectHomeTab(document.getElementById("tab-device"));
});
document.getElementById("files-import").addEventListener("click", async () => {
  if (filesBusy || !filesOffline) return;
  const input = document.getElementById("files-upload");
  const file = input.files?.[0];
  if (!file) { setFileMessage("请先选择本机文件。"); return; }
  if (file.size > 64 * 1024 * 1024) { setFileMessage("文件超过 64 MiB 上限。"); return; }
  filesBusy = true;
  setFileMessage(`正在导入 ${file.name}；复制与校验完整 NAND 可能需要一些时间…`);
  try {
    await api(`/api/files/import?path=${encodeURIComponent(filesPath)}&name=${encodeURIComponent(file.name)}`,
      { method: "POST", body: file });
    input.value = "";
    await listNandFiles();
    setFileMessage(`${file.name} 已导入并校验；点击“完成并开机”使设备使用新检查点。`);
  } catch (error) { setFileMessage(`导入失败：${error.message}`); }
  finally { filesBusy = false; }
});
void api("/api/files/status").then(state => {
  if (state.mode === "offline") {
    setFilesOffline(true);
    selectHomeTab(document.getElementById("tab-files"));
    void listNandFiles("/").catch(error => setFileMessage(error.message));
  }
}).catch(() => {
  const tab = document.getElementById("tab-files");
  tab.disabled = true;
  tab.title = "当前网页服务仍是旧版本；保存游戏后重启服务即可启用 NAND 文件管理";
});

buildRawMatrixKeyboard();
buildSkinKeyboard();
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

const keyboardContact = new NP560KeyboardInput.MinimumKeyboardContact(
  keyboardInput, () => keyRequestQueue);
const keyboardShortTap = document.getElementById("keyboard-short-tap");
keyboardShortTap?.addEventListener("change", () => releaseAllKeys(false));

function editableTarget(target) {
  return target instanceof Element && (target.isContentEditable || Boolean(
    target.closest("input, select, textarea")
  ));
}

window.addEventListener("keydown", event => {
  if (filesConfirmDialog.open) return;
  if (typeof filesOffline !== "undefined" && filesOffline) return;
  // IME composition is text input, not a physical guest key. Some browsers
  // report the composition boundary with keyCode 229 before isComposing.
  if (event.isComposing || event.keyCode === 229) return;
  if (editableTarget(event.target) || event.ctrlKey || event.metaKey || event.altKey) return;
  const code = normalizeKeyboardEvent(event);
  if (!keyboardInput.isMapped(code)) return;
  event.preventDefault();
  if (event.repeat) return;
  keyboardContact.press(keyboardSource(event), code, keyboardShortTap?.checked ? 150 : 0);
});
window.addEventListener("keyup", event => {
  const sourceName = keyboardSource(event);
  if (!keyboardInput.hasSource(sourceName)) return;
  event.preventDefault();
  keyboardContact.release(sourceName);
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
