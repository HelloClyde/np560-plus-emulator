#!/usr/bin/env node
"use strict";

// An opt-in live bridge check. It opens a fresh headless browser against an
// isolated NP560 Web instance; it does not start, reset, or modify that device.
const assert = require("node:assert/strict");
const { chromium } = require("playwright");

if (!process.argv[2]) {
  throw new Error("pass the URL of an isolated, freshly started loopback Web instance");
}
const root = new URL(process.argv[2]);
if (!["127.0.0.1", "localhost"].includes(root.hostname)) {
  throw new Error("live pointer probe only accepts a loopback Web instance");
}
const browserPath = process.env.NP560_BROWSER_PATH ||
  "C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe";

async function keyStatus(page) {
  const response = await page.request.get(new URL("/api/key-status", root).href);
  assert.equal(response.status(), 200);
  return response.json();
}

async function waitForNonblankFrame(page) {
  const deadline = Date.now() + 10000;
  while (Date.now() < deadline) {
    const response = await page.request.get(new URL("/api/frame", root).href);
    assert.equal(response.status(), 200);
    const frame = await response.json();
    if (Buffer.from(frame.frame, "base64").some(value => value !== 0)) {
      return frame.sequence;
    }
    await new Promise(resolve => setTimeout(resolve, 100));
  }
  throw new Error("LCD stayed blank before the first pointer action; cold-boot input precondition not met");
}

async function waitForDelivery(page, before, event, label) {
  const deadline = Date.now() + 6000;
  let state;
  while (Date.now() < deadline) {
    state = await keyStatus(page);
    if (state.faulted) throw new Error(`${label}: guest faulted`);
    const consumed =
      (state.acknowledgements > before.acknowledgements &&
       state.acknowledgement === event) ||
      (state.modal_acknowledgements > before.modal_acknowledgements &&
       state.modal_acknowledgement === event);
    if (state.maps > before.maps && state.event === event && consumed &&
        state.matrix_rearmed) {
      break;
    }
    await new Promise(resolve => setTimeout(resolve, 50));
  }
  if (!state || state.maps !== before.maps + 1 || state.event !== event ||
      !state.matrix_rearmed) {
    throw new Error(`${label}: no single rearmed delivery: ${JSON.stringify(state)}`);
  }
  await new Promise(resolve => setTimeout(resolve, 350));
  const settled = await keyStatus(page);
  assert.equal(settled.maps, before.maps + 1, `${label}: duplicate mapping`);
  assert.equal(settled.matrix_rearmed, true, `${label}: switch not released`);
  return {
    label,
    event,
    maps: `${before.maps}->${settled.maps}`,
    modal_ack_delta: settled.modal_acknowledgements - before.modal_acknowledgements,
    foreground_ack_delta: settled.acknowledgements - before.acknowledgements,
    matrix_reads_delta: settled.matrix_reads - before.matrix_reads,
  };
}

async function inspectFrontend(page) {
  return page.evaluate(() => ({
    frontend_submissions: keyboardInput.recentTransitions(),
    transport: keyTransportHistory.map(entry => ({ ...entry })),
    held: Array.from(keyboardInput.heldCodes()),
    status_text: document.getElementById("status-text")?.textContent,
  }));
}

async function main() {
  let browser;
  try {
    browser = await chromium.launch({
      executablePath: browserPath,
      headless: true,
    });
    const context = await browser.newContext({
      viewport: { width: 390, height: 844 },
      deviceScaleFactor: 1,
      hasTouch: true,
      isMobile: true,
    });
    const page = await context.newPage();
    const errors = [];
    const keyRequests = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("request", request => {
      if (new URL(request.url()).pathname !== "/api/key") return;
      keyRequests.push({ at_ms: Date.now(), payload: request.postDataJSON() });
    });
    await page.goto(root.href, { waitUntil: "domcontentloaded" });
    await page.locator('#lcd').waitFor();
    const canvas = await page.locator('#lcd').evaluate(element => ({
      width: element.width,
      height: element.height,
    }));
    assert.deepEqual(canvas, { width: 240, height: 132 });
    const layout = await page.evaluate(() => ({
      viewport_width: document.documentElement.clientWidth,
      content_width: document.documentElement.scrollWidth,
    }));
    assert.ok(layout.content_width <= layout.viewport_width + 1,
      "mobile page requires horizontal scrolling");
    const firstVisibleFrame = await waitForNonblankFrame(page);

    const results = [];
    try {
      let before = await keyStatus(page);
      if (before.application_state !== 253) {
        throw new Error(`expected boot prompt application state 253, got ${before.application_state}`);
      }
      await page.locator('[data-key="F4"]').tap();
      results.push(await waitForDelivery(page, before, 0x8e, "touch-F4"));

      before = await keyStatus(page);
      await page.locator('[data-key="StartMenu"]').click();
      results.push(await waitForDelivery(page, before, 0xb0, "mouse-Start"));

      before = await keyStatus(page);
      await page.locator('[data-key="ArrowRight"]').tap();
      results.push(await waitForDelivery(page, before, 0x81, "touch-Right"));
    } catch (error) {
      console.error(JSON.stringify({
        error: error.message,
        key_requests: keyRequests,
        diagnostic: await inspectFrontend(page),
        page_errors: errors,
      }, null, 2));
      throw error;
    }

    assert.deepEqual(errors, [], "uncaught browser JavaScript errors");
    console.log(JSON.stringify({
      schema: "np560-live-browser-pointer-v1",
      root: root.href,
      viewport: "390x844 mobile touch",
      canvas,
      layout,
      first_visible_frame: firstVisibleFrame,
      results,
      page_errors: errors,
    }, null, 2));
    await context.close();
  } finally {
    if (browser) await browser.close();
  }
}

main().catch(error => {
  console.error(error);
  process.exitCode = 1;
});
