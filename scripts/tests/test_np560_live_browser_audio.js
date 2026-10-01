#!/usr/bin/env node
"use strict";

// Opt-in browser presentation probe for an already-playing isolated device.
// It enables the Web listener, never changes guest sound settings or files.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const { chromium } = require("playwright");

if (!process.argv[2]) {
  throw new Error("pass the URL of an isolated loopback instance already playing audio");
}
const root = new URL(process.argv[2]);
if (!["127.0.0.1", "localhost"].includes(root.hostname)) {
  throw new Error("live audio probe only accepts a loopback Web instance");
}
const browserPath = process.env.NP560_BROWSER_PATH ||
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";
const durationMs = Number(process.argv[3] || 15000);
if (!Number.isInteger(durationMs) || durationMs < 1000 || durationMs > 60000) {
  throw new Error("duration must be an integer from 1000 to 60000 ms");
}
const pollMs = Number(process.argv[4] || 50);
if (!Number.isInteger(pollMs) || pollMs < 50 || pollMs > 150) {
  throw new Error("diagnostic browser poll interval must be 50..150 ms");
}
const lcdPollMs = Number(process.argv[5] || 200);
if (!Number.isInteger(lcdPollMs) || lcdPollMs < 100 || lcdPollMs > 1000) {
  throw new Error("diagnostic LCD poll interval must be 100..1000 ms");
}
const displayMode = process.argv[6] || "fast";
if (!["fast", "full", "compat"].includes(displayMode)) {
  throw new Error("display mode must be fast, full, or compat");
}
const traceGaps = process.argv.includes("--trace-gaps");

async function deviceAudio(page) {
  const response = await page.request.get(new URL("/api/audio", root).href);
  assert.equal(response.status(), 200);
  return response.json();
}

async function main() {
  let browser;
  try {
    browser = await chromium.launch({ executablePath: browserPath, headless: true });
    const page = await browser.newPage({ viewport: { width: 390, height: 844 } });
    const pageErrors = [];
    let audioRequests = 0;
    let displayRequests = 0;
    let stateRequests = 0;
    page.on("pageerror", error => pageErrors.push(error.message));
    page.on("request", request => {
      const pathname = new URL(request.url()).pathname;
      if (pathname === "/api/audio") audioRequests += 1;
      if (pathname === "/api/display") displayRequests += 1;
      if (pathname === "/api/state") stateRequests += 1;
    });
    if (pollMs !== 50) {
      const asset = fs.readFileSync(path.join(__dirname, "../web/audio_output.js"), "utf8");
      const original = "this.timer = setTimeout(() => this.poll(serial), 50);";
      assert.equal(asset.split(original).length, 2, "expected one audio poll timer");
      await page.route("**/audio_output.js", route => route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: asset.replace(original,
          `this.timer = setTimeout(() => this.poll(serial), ${pollMs});`),
      }));
    }
    if (lcdPollMs !== 200 || displayMode === "full") {
      let asset = fs.readFileSync(path.join(__dirname, "../web/app.js"), "utf8");
      if (lcdPollMs !== 200) {
        const original = "setInterval(poll, 200);";
        assert.equal(asset.split(original).length, 2, "expected one LCD poll timer");
        asset = asset.replace(original, `setInterval(poll, ${lcdPollMs});`);
      }
      if (displayMode === "full") {
        const original = 'const displayOnly = settings.source === "lcd" && !diagnosticsDue && fastDisplayAvailable;';
        assert.equal(asset.split(original).length, 2, "expected one display mode switch");
        asset = asset.replace(original, "const displayOnly = false;");
      }
      await page.route("**/app.js", route => route.fulfill({
        status: 200,
        contentType: "application/javascript",
        body: asset,
      }));
    }
    if (displayMode === "compat") {
      await page.route("**/api/display", route => route.fulfill({
        status: 404, contentType: "text/html", body: "old bridge: no display API",
      }));
    }
    await page.goto(root.href, { waitUntil: "domcontentloaded" });
    if (traceGaps) {
      // Diagnostic-only wrapper. Preserve the production accept() behavior,
      // but retain enough device/control and browser-clock context to tell a
      // slow guest window from a stopped DAC or an HTTP scheduling delay.
      await page.evaluate(() => {
        const original = audioOutput.accept;
        const trace = [];
        let previousAt = null;
        let previousFrame = null;
        let nextControl = 0;
        let lastDacState = null;
        let lastPll = null;
        window.__np560AudioTrace = trace;
        audioOutput.accept = function (packet) {
          const at = performance.now();
          const beforeGap = this.presentationGapSeconds;
          const leadMs = (this.endTime - this.context.currentTime) * 1000;
          const cursorBefore = this.cursor;
          const streamBefore = this.stream;
          const controls = [];
          for (const event of packet.control_events || []) {
            if (event.sequence < nextControl) continue;
            if (event.reg === 114) {
              const state = `${event.enabled}/${event.running}/${event.value}`;
              if (state === lastDacState) continue;
              lastDacState = state;
            } else if (event.reg === 234) {
              if (event.value === lastPll) continue;
              lastPll = event.value;
            } else {
              continue;
            }
            controls.push({ sequence: event.sequence, frame: event.frame,
              enabled: event.enabled, running: event.running,
              pc: event.pc, reg: event.reg, value: event.value });
          }
          nextControl = packet.control_event_next ?? nextControl;
          try {
            return original.call(this, packet);
          } finally {
            trace.push({
              at_ms: Math.round(at),
              accept_ms: Number((performance.now() - at).toFixed(3)),
              interval_ms: previousAt === null ? null : Math.round(at - previousAt),
              device_ms: previousFrame === null ? null :
                Math.round((packet.next_frame - previousFrame) / 48),
              packet_ms: Math.round((packet.next_frame - packet.first_frame) / 48),
              new_ms: Math.round((packet.next_frame - cursorBefore) / 48),
              lead_before_ms: Math.round(leadMs),
              lead_after_ms: Math.round((this.endTime - this.context.currentTime) * 1000),
              gap_ms: Math.round((this.presentationGapSeconds - beforeGap) * 1000),
              stream_changed: streamBefore !== this.stream,
              audio_enabled: packet.enabled,
              request_running: packet.request_clock?.running,
              next_frame: packet.next_frame,
              controls,
            });
            previousAt = at;
            previousFrame = packet.next_frame;
          }
        };
      });
    }
    await page.locator("#audio-toggle").click();
    await page.waitForFunction(() => audioOutput.enabled, null, { timeout: 5000 });

    const samples = [];
    const deviceFirst = await deviceAudio(page);
    const started = Date.now();
    while (Date.now() - started < durationMs) {
      const sample = await page.evaluate(() => ({
        enabled: audioOutput.enabled,
        context_state: audioOutput.context?.state,
        context_time: audioOutput.context?.currentTime,
        stream: audioOutput.stream,
        cursor: audioOutput.cursor,
        queued_sources: audioOutput.sources.size,
        dropped_frames: audioOutput.droppedFrames,
        presentation_gap_ms: Math.round(audioOutput.presentationGapSeconds * 1000),
        status: document.getElementById("audio-status")?.textContent,
      }));
      samples.push({ at_ms: Date.now() - started, ...sample });
      await page.waitForTimeout(500);
    }
    const deviceLast = await deviceAudio(page);
    const first = samples[0];
    const last = samples.at(-1);
    assert.equal(pageErrors.length, 0, "uncaught browser JavaScript errors");
    assert.ok(samples.every(sample => sample.enabled && sample.context_state === "running"),
      "browser audio listener stopped during the observation");
    const slowWindows = [];
    for (let i = 1; i < samples.length; i += 1) {
      const previous = samples[i - 1];
      const current = samples[i];
      if (!previous.stream || previous.stream !== current.stream) continue;
      const elapsedMs = current.at_ms - previous.at_ms;
      const guestMs = (current.cursor - previous.cursor) / 48;
      const gapMs = current.presentation_gap_ms - previous.presentation_gap_ms;
      if (guestMs < elapsedMs * 0.85 || gapMs >= 50) {
        slowWindows.push({
          from_ms: previous.at_ms,
          to_ms: current.at_ms,
          guest_audio_ms: Math.round(guestMs),
          speed_ratio: Number((guestMs / elapsedMs).toFixed(3)),
          new_presentation_gap_ms: gapMs,
        });
      }
    }
    const trace = traceGaps ? await page.evaluate(() => window.__np560AudioTrace) : [];
    const gapEvents = trace.filter(entry => entry.gap_ms >= 1);
    const largestGaps = [...gapEvents].sort((a, b) => b.gap_ms - a.gap_ms).slice(0, 12);
    const controlTransitions = trace.flatMap(entry => entry.controls.map(
      event => ({ at_ms: entry.at_ms, ...event })));
    const acceptCosts = trace.map(entry => entry.accept_ms).sort((a, b) => a - b);
    const report = {
      schema: "np560-live-browser-audio-v1",
      root: root.href,
      poll_ms: pollMs,
      lcd_poll_ms: lcdPollMs,
      display_mode: displayMode,
      observed_ms: Date.now() - started,
      audio_requests: audioRequests,
      display_requests: displayRequests,
      state_requests: stateRequests,
      samples: samples.length,
      device_frames_delta: deviceLast.next_frame - deviceFirst.next_frame,
      device_speed_ratio: (deviceLast.next_frame - deviceFirst.next_frame) /
        48 / (Date.now() - started),
      stream_first: first.stream,
      stream_last: last.stream,
      cursor_first: first.cursor,
      cursor_last: last.cursor,
      dropped_frames_delta: last.dropped_frames - first.dropped_frames,
      presentation_gap_ms_delta: last.presentation_gap_ms - first.presentation_gap_ms,
      slow_windows: slowWindows,
      ...(traceGaps ? {
        gap_event_count: gapEvents.length,
        largest_gap_events: largestGaps,
        control_transition_count: controlTransitions.length,
        control_transitions: controlTransitions.slice(0, 40),
        max_packet_interval_ms: Math.max(0, ...trace.map(entry => entry.interval_ms || 0)),
        accept_cost_ms: {
          median: acceptCosts[Math.floor(acceptCosts.length / 2)] || 0,
          p95: acceptCosts[Math.floor(acceptCosts.length * 0.95)] || 0,
          max: acceptCosts.at(-1) || 0,
        },
      } : {}),
      max_queued_sources: Math.max(...samples.map(sample => sample.queued_sources)),
      first_status: first.status,
      last_status: last.status,
      page_errors: pageErrors,
    };
    if (process.env.NP560_AUDIO_REPORT) {
      // Keep the compact per-packet trace only in the explicitly requested
      // diagnostic artifact; avoid dumping it into routine terminal output.
      fs.writeFileSync(path.resolve(process.env.NP560_AUDIO_REPORT),
        JSON.stringify({ ...report, packet_trace: trace }, null, 2) + "\n");
    }
    console.log(JSON.stringify(report, null, 2));
  } finally {
    if (browser) await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
