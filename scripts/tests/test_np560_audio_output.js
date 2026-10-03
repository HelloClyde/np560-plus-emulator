"use strict";
const assert = require("node:assert/strict");
const { AudioOutput, decodePCM } = require("../web/audio_output.js");

function packet(first, pairs, generation = 1, stream_id = "test") {
  const data = Buffer.alloc(pairs.length * 4);
  pairs.forEach((pair, i) => pair.forEach((value, c) => data.writeInt16LE(value, i * 4 + c * 2)));
  return { format: "s16le", sample_rate: 48000, channels: 2, generation,
           stream_id, first_frame: first, next_frame: first + pairs.length,
           pcm: data.toString("base64") };
}

const samples = packet(0, [[0, 0], [32767, -32768], [-1, 1]]);
assert.deepEqual(Array.from(decodePCM(samples)[0]), [0, 32767 / 32768, -1 / 32768]);
assert.deepEqual(Array.from(decodePCM(samples)[1]), [0, -1, 1 / 32768]);
for (const invalid of [{ ...samples, channels: 1 }, { ...samples, pcm: "AA==" },
  { ...samples, first_frame: -1 }, { ...samples, next_frame: 9601 },
  { ...samples, generation: NaN }, { ...samples, sample_rate: 8000 }]) {
  assert.throws(() => decodePCM(invalid));
}

const scheduled = [];
const context = {
  state: "running",
  currentTime: 1,
  createBuffer(channels, length, rate) {
    return { channels, length, rate, data: [], copyToChannel(data, channel) {
      this.data[channel] = Array.from(data);
    } };
  },
  createBufferSource() {
    return { connect() {}, disconnect() {}, stop() { this.stopped = true; },
      start(at) { this.at = at; scheduled.push(this); } };
  }
};
const output = new AudioOutput({ fetchJSON: () => assert.fail("not polling") });
output.context = context;
output.gain = {};
output.accept(samples);
assert.equal(scheduled.length, 1);
assert.equal(scheduled[0].buffer.length, 3);
output.accept(samples);
assert.equal(scheduled.length, 1, "duplicate snapshots must not replay");
output.accept(packet(1, [[32767, -32768], [-1, 1], [10, -20]]));
assert.equal(scheduled.length, 2);
assert.deepEqual(scheduled[1].buffer.data, [[10 / 32768], [-20 / 32768]]);
assert.ok(scheduled[1].at >= scheduled[0].at + 3 / 48000);
output.accept(packet(20, [[30, -40]]));
assert.equal(output.droppedFrames, 16);
assert.ok(scheduled[0].stopped && scheduled[1].stopped);
output.accept(packet(0, [[50, -60]], 2));
assert.equal(output.cursor, 1);
assert.ok(scheduled[2].stopped, "reset discards queued previous-generation sound");
output.accept(packet(0, [[70, -80]], 2, "replacement-process"));
assert.equal(scheduled.length, 5, "new process identity replaces old stream");
output.clearSources();
assert.equal(output.sources.size, 0);
assert.ok(scheduled[4].stopped);
console.log("Web PCM: signed lanes, validation, deduplication, gaps, reset and process replacement passed");

// The ring may deliver every frame while the guest produces them too slowly
// for the browser's real-time clock. This is an audible scheduling underrun,
// not a device-ring overrun, and the status must distinguish the two.
const presentationStatuses = [];
const presentationClock = { ...context, currentTime: 1 };
const presentation = new AudioOutput({ fetchJSON: () => assert.fail("not polling"),
  onStatus: value => presentationStatuses.push(value) });
presentation.context = presentationClock;
presentation.gain = {};
const continuousPCM = Array.from({ length: 1000 }, () => [100, -100]);
presentation.accept(packet(0, continuousPCM));
presentationClock.currentTime = 1.10;
presentation.accept(packet(1000, continuousPCM));
assert.equal(presentation.droppedFrames, 0, "continuous guest frames were marked lost");
assert.ok(presentation.presentationGapSeconds > 0.05);
assert.match(presentationStatuses.at(-1), /播放空档 \d+ ms/);
assert.doesNotMatch(presentationStatuses.at(-1), /缓冲丢失/);
presentation.clearSources();
console.log("Web PCM: presentation underrun is reported separately from ring loss");

// Audio scheduling can fail when the browser loses its output device. A
// retry must not retain a connected, never-started node or advance the cursor.
for (const failAt of ['connect', 'start']) {
  const nodes = [];
  let fail = true;
  const failedOutput = new AudioOutput({ fetchJSON: () => assert.fail('not polling') });
  failedOutput.context = { ...context, createBufferSource() {
    const node = {
      connect() { if (fail && failAt === 'connect') throw new Error('device unavailable'); },
      disconnect() { this.disconnected = true; },
      stop() { this.stopped = true; },
      start() { if (fail && failAt === 'start') throw new Error('device unavailable'); },
    };
    nodes.push(node);
    return node;
  } };
  failedOutput.gain = {};
  assert.throws(() => failedOutput.accept(samples), /device unavailable/);
  assert.equal(failedOutput.sources.size, 0, 'failed scheduling retained a node');
  assert.equal(nodes[0].disconnected, true, 'failed scheduling kept an audio connection');
  assert.equal(nodes[0].onended, null);
  assert.equal(failedOutput.cursor, 0, 'failed scheduling consumed unplayed samples');
  fail = false;
  failedOutput.accept(samples);
  assert.equal(failedOutput.cursor, 3);
  assert.equal(failedOutput.sources.size, 1);
  failedOutput.clearSources();
}
console.log('Web PCM: failed node connection/scheduling is cleaned up and remains retryable');

// Measured QMP + Web polling intervals are often 125-150 ms. Scheduling
// only 50 ms of the first ring drains before the second complete packet.
scheduled.length = 0;
const jitterOutput = new AudioOutput({ fetchJSON: () => assert.fail("not polling") });
jitterOutput.context = context;
jitterOutput.gain = {};
for (const elapsed of [0, .13, .26, .41, .54]) {
  context.currentTime = 10 + elapsed;
  const next = 9600 + Math.round(elapsed * 48000);
  const first = next - 9600;
  const pairs = Array.from({ length: 9600 }, (_, i) => [(first + i) % 2000, -((first + i) % 2000)]);
  jitterOutput.accept(packet(first, pairs));
}
for (let i = 1; i < scheduled.length; i++) {
  const previousEnd = scheduled[i - 1].at + scheduled[i - 1].buffer.length / 48000;
  assert.ok(Math.abs(scheduled[i].at - previousEnd) < 1e-9,
            "125-150 ms packet cadence must not insert presentation gaps");
}
assert.equal(jitterOutput.droppedFrames, 0);
const retained = scheduled.flatMap(source => source.buffer.data[0]);
const firstRetained = jitterOutput.cursor - retained.length;
retained.forEach((value, i) => assert.equal(value, ((firstRetained + i) % 2000) / 32768));
assert.ok(scheduled[0].buffer.length / 48000 <= .2, "startup latency stays within the existing ring");
console.log("Web PCM: measured packet cadence schedules continuous, unmodified samples");

// A mobile browser may suspend its audio clock while HTTP polling continues.
// Do not queue sound into that frozen timeline or replay pre-interruption audio.
scheduled.length = 0;
const interruptedOutput = new AudioOutput({ fetchJSON: () => assert.fail("not polling") });
interruptedOutput.context = context;
interruptedOutput.gain = {};
context.currentTime = 20;
interruptedOutput.accept(samples);
const oldSource = scheduled[0];
context.state = "suspended";
interruptedOutput.accept(packet(3, [[100, -100]]));
assert.equal(scheduled.length, 1, "suspended context must not schedule new audio");
assert.ok(oldSource.stopped, "suspension must discard the old presentation queue");
context.state = "running";
interruptedOutput.accept(packet(10000, [[200, -200]]));
assert.equal(scheduled.length, 2);
assert.deepEqual(scheduled[1].buffer.data, [[200 / 32768], [-200 / 32768]]);
assert.equal(interruptedOutput.droppedFrames, 0, "resumption starts a live window, not a false ring overrun");
interruptedOutput.clearSources();
console.log("Web PCM: suspended clock discards queued sound and resumes from live PCM");

(async () => {
  class LifecycleContext {
    constructor() {
      this.state = "suspended";
      this.currentTime = 30;
      this.listeners = new Set();
      this.createBuffer = context.createBuffer;
      this.createBufferSource = context.createBufferSource;
    }
    async resume() { this.state = "running"; }
    async close() { this.changeState("closed"); }
    createGain() { return { gain: {}, connect() {} }; }
    addEventListener(name, listener) {
      assert.equal(name, "statechange"); this.listeners.add(listener);
    }
    removeEventListener(name, listener) {
      assert.equal(name, "statechange"); this.listeners.delete(listener);
    }
    changeState(state) {
      this.state = state;
      for (const listener of [...this.listeners]) listener();
    }
  }
  const live = new AudioOutput({ fetchJSON: () => assert.fail("unexpected poll"),
                                 AudioContextClass: LifecycleContext });
  live.poll = () => {}; // This test drives delivery; no real timers or HTTP.
  await live.start();
  const firstContext = live.context;
  const staleListener = [...firstContext.listeners][0];
  live.accept(samples);
  const queued = [...live.sources][0];
  // No HTTP response is needed to flush audio on an interruption.
  firstContext.changeState("interrupted");
  assert.equal(live.sources.size, 0);
  assert.ok(queued.stopped);
  assert.equal(live.stream, null);
  live.accept(samples);
  assert.equal(live.sources.size, 0);
  firstContext.changeState("running");
  live.accept(packet(10000, [[30, -30]]));
  assert.equal(live.sources.size, 1);
  live.stop();
  assert.equal(firstContext.listeners.size, 0);
  assert.equal(firstContext.state, "closed");
  assert.equal(live.sources.size, 0);
  await live.start();
  staleListener();
  assert.equal(live.enabled, true, "old context event must not stop a replacement");
  live.context.changeState("closed");
  assert.equal(live.enabled, false);
  assert.equal(live.context, null);
  console.log("Web PCM: interruption events, restart and listener cleanup passed");

  // An HTTP request begun BEFORE mobile audio interruption may complete after
  // the clock resumes, even if abort is requested. Never play that stale PCM.
  let resolvePacket;
  const race = new AudioOutput({
    fetchJSON: () => new Promise(resolve => { resolvePacket = resolve; }),
    AudioContextClass: LifecycleContext,
  });
  race.poll = () => {}; // Drive exactly one in-flight poll below.
  await race.start();
  const pending = AudioOutput.prototype.poll.call(race, race.serial);
  race.context.changeState("interrupted");
  race.context.changeState("running");
  resolvePacket(samples);
  await pending;
  assert.equal(race.sources.size, 0, "pre-interruption response replayed stale PCM");
  assert.equal(race.stream, null);
  race.accept(packet(10000, [[300, -300]]));
  assert.equal(race.sources.size, 1, "fresh live PCM must still play");
  race.stop();
  console.log("Web PCM: in-flight response cannot cross an interruption boundary");

  // Leaving the page while the user-gesture resume is pending closes the
  // context. A late resume must not close the same context twice or surface
  // an error from the cancelled start operation.
  const pendingContexts = [];
  class PendingContext extends LifecycleContext {
    constructor() { super(); pendingContexts.push(this); this.closes = 0; }
    resume() { return new Promise((resolve, reject) => {
      this.resolveResume = resolve; this.rejectResume = reject;
    }); }
    async close() {
      if (this.state === 'closed') throw new Error('context already closed');
      this.closes++;
      await super.close();
    }
  }
  const canceled = new AudioOutput({ fetchJSON: () => assert.fail('unexpected poll'),
    AudioContextClass: PendingContext });
  canceled.poll = () => {};
  const canceledStart = canceled.start();
  const canceledContext = pendingContexts.at(-1);
  canceled.stop();
  canceledContext.resolveResume();
  await canceledStart;
  assert.equal(canceledContext.closes, 1);
  assert.equal(canceled.enabled, false);
  assert.equal(canceled.context, null);

  // A failed superseded resume must release its own context, not stop or
  // close the replacement that is already running.
  const obsoleteStart = canceled.start();
  const obsoleteContext = pendingContexts.at(-1);
  const replacementStart = canceled.start();
  const replacementContext = pendingContexts.at(-1);
  replacementContext.state = 'running'; replacementContext.resolveResume();
  await replacementStart;
  obsoleteContext.rejectResume(new Error('old resume rejected'));
  await assert.rejects(obsoleteStart, /old resume rejected/);
  assert.equal(obsoleteContext.closes, 1);
  assert.equal(canceled.context, replacementContext);
  assert.equal(canceled.enabled, true);
  canceled.stop();
  assert.equal(replacementContext.closes, 1);
  console.log('Web PCM: cancelled/superseded resume closes only its owned context');

  // A failed asynchronous close must not escape pagehide/stop as an unhandled
  // rejection. Its delayed result must not overwrite a replacement's status.
  const closeFailures = [], releaseStatuses = [];
  const unhandledClose = error => closeFailures.push(error);
  process.on('unhandledRejection', unhandledClose);
  try {
    class FailedCloseContext extends LifecycleContext {
      close() { return new Promise((resolve, reject) => { this.rejectClose = reject; }); }
    }
    const releasing = new AudioOutput({ fetchJSON: () => assert.fail('unexpected poll'),
      AudioContextClass: FailedCloseContext,
      onStatus: message => releaseStatuses.push(message) });
    releasing.poll = () => {};
    await releasing.start();
    const first = releasing.context;
    releasing.stop();
    first.rejectClose(new Error('output device release failed'));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(closeFailures, [], 'stop leaked a close rejection');
    assert.equal(releasing.enabled, false);
    assert.equal(releasing.context, null);
    assert.match(releaseStatuses.at(-1), /释放失败/);
    await releasing.start();
    const second = releasing.context;
    releasing.stop();
    await releasing.start();
    const runningStatus = releaseStatuses.at(-1);
    second.rejectClose(new Error('obsolete release failed'));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(closeFailures, []);
    assert.equal(releaseStatuses.at(-1), runningStatus);
    assert.equal(releasing.enabled, true);
    const third = releasing.context;
    releasing.stop();
    third.rejectClose(new Error('final release failed'));
    await new Promise(resolve => setImmediate(resolve));
    assert.deepEqual(closeFailures, []);
    await releasing.start();
    releasing.context.close = () => { throw new Error('synchronous release failure'); };
    assert.doesNotThrow(() => releasing.stop());
    assert.equal(releasing.context, null);
    assert.equal(releasing.enabled, false);
    assert.match(releaseStatuses.at(-1), /释放失败/);
  } finally {
    process.removeListener('unhandledRejection', unhandledClose);
  }
  console.log('Web PCM: failed close is handled without corrupting a replacement session');

  // Exercise the actual app wiring as well as the audio controller: an
  // externally closed context must not leave the button saying "关闭声音".
  const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm');
  const app = fs.readFileSync(path.join(__dirname, '../web/app.js'), 'utf8');
  const handlers = {}, attributes = {}, status = {};
  const button = { textContent: '启用声音', disabled: false,
    addEventListener: (name, fn) => { handlers[name] = fn; },
    setAttribute: (name, value) => { attributes[name] = value; } };
  let wired;
  class WiredOutput extends AudioOutput {
    constructor(options) {
      super({ ...options, AudioContextClass: LifecycleContext });
      wired = this; this.poll = () => {};
    }
  }
  vm.runInNewContext(app.slice(app.indexOf('const audioToggle ='),
    app.indexOf('const { KeyboardMatrixController')),
    { NP560AudioOutput: { AudioOutput: WiredOutput },
      document: { getElementById: id => id === 'audio-toggle' ? button : status },
      window: { addEventListener() {} } });
  await handlers.click();
  assert.equal(button.textContent, '关闭声音');
  assert.equal(attributes['aria-pressed'], 'true');
  wired.context.changeState('closed');
  assert.equal(wired.enabled, false);
  assert.equal(button.textContent, '启用声音', 'closed context left a stale audio button');
  assert.equal(attributes['aria-pressed'], 'false');
  await handlers.click();
  assert.equal(wired.enabled, true);
  assert.equal(button.textContent, '关闭声音');
  await handlers.click();
  assert.equal(wired.enabled, false);
  assert.equal(button.textContent, '启用声音');
  console.log('Web PCM: actual UI follows external closure and supports re-enable');

  const autoCalls = [];
  const autoHandlers = {};
  const autoButton = {disabled: false, textContent: '启用声音',
    addEventListener: (name, fn) => {autoHandlers[name] = fn;},
    setAttribute() {}};
  class AutoOutput {
    constructor(options) {this.options = options; this.enabled = false;}
    start() {
      autoCalls.push('start');
      this.enabled = true;
      this.options.onEnabledChange(true);
      return Promise.resolve();
    }
    stop() {
      autoCalls.push('stop');
      this.enabled = false;
      this.options.onEnabledChange(false);
    }
  }
  const autoContext = {NP560AudioOutput: {AudioOutput: AutoOutput},
    document: {getElementById: id => id === 'audio-toggle' ? autoButton : status},
    window: {addEventListener() {}}};
  vm.runInNewContext(app.slice(app.indexOf('const audioToggle ='),
    app.indexOf('const { KeyboardMatrixController')), autoContext);
  autoContext.enableAudioOnFirstGesture();
  assert.deepEqual(autoCalls, ['start']);
  await Promise.resolve();
  await autoHandlers.click();
  assert.deepEqual(autoCalls, ['start', 'stop']);
  autoContext.enableAudioOnFirstGesture();
  assert.deepEqual(autoCalls, ['start', 'stop'], 'manual mute must prevent re-enabling');
  console.log('Web PCM: first user gesture enables once; manual mute stays off');
})().catch(error => { console.error(error); process.exitCode = 1; });
