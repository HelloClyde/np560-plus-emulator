"use strict";
const assert = require("node:assert/strict");
const { AudioOutput, decodePCM } = require("./web/audio_output.js");

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
