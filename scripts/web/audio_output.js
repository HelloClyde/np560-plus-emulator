"use strict";

(function (root) {
  function decodePCM(packet) {
    if (!packet || packet.format !== "s16le" || packet.sample_rate !== 48000 ||
        packet.channels !== 2 || typeof packet.stream_id !== "string" ||
        !Number.isSafeInteger(packet.generation) || packet.generation < 0 ||
        !Number.isSafeInteger(packet.first_frame) || packet.first_frame < 0 ||
        !Number.isSafeInteger(packet.next_frame) || packet.next_frame < packet.first_frame ||
        packet.next_frame - packet.first_frame > 9600 ||
        typeof packet.pcm !== "string" || packet.pcm.length > 51200) {
      throw new Error("音频数据格式错误");
    }
    const raw = atob(packet.pcm);
    const frames = packet.next_frame - packet.first_frame;
    if (raw.length !== frames * 4) throw new Error("音频数据长度错误");
    const channels = [new Float32Array(frames), new Float32Array(frames)];
    for (let frame = 0; frame < frames; frame += 1) {
      for (let channel = 0; channel < 2; channel += 1) {
        const index = frame * 4 + channel * 2;
        const word = raw.charCodeAt(index) | (raw.charCodeAt(index + 1) << 8);
        channels[channel][frame] = (word >= 0x8000 ? word - 0x10000 : word) / 32768;
      }
    }
    return channels;
  }

  class AudioOutput {
    constructor({ fetchJSON, AudioContextClass = root.AudioContext || root.webkitAudioContext,
                  onStatus = () => {} }) {
      this.fetchJSON = fetchJSON;
      this.AudioContextClass = AudioContextClass;
      this.onStatus = onStatus;
      this.enabled = false;
      this.serial = 0;
      this.sources = new Set();
      this.stream = null;
      this.cursor = 0;
      this.droppedFrames = 0;
    }

    async start() {
      if (this.enabled) return;
      if (!this.AudioContextClass) throw new Error("当前浏览器不支持声音输出");
      const serial = ++this.serial;
      const context = new this.AudioContextClass();
      this.context = context;
      try {
        // Called only from the user's enable button, never during page load.
        await context.resume();
        if (serial !== this.serial) { await context.close(); return; }
        if (context.state !== "running") throw new Error("请点击按钮允许浏览器播放声音");
        this.gain = context.createGain();
        this.gain.gain.value = 0.25; // listening attenuation, not a guest volume write
        this.gain.connect(context.destination);
        this.enabled = true;
        this.stream = null;
        this.cursor = 0;
        this.droppedFrames = 0;
        this.endTime = context.currentTime + 0.04;
        this.onStatus("声音已启用，等待 guest 数据");
        void this.poll(serial);
      } catch (error) {
        if (serial === this.serial) this.stop();
        throw error;
      }
    }

    clearSources() {
      for (const source of this.sources) {
        source.onended = null;
        try { source.stop(); } catch (_) { /* already ended */ }
        source.disconnect();
      }
      this.sources.clear();
    }

    stop() {
      this.serial += 1;
      this.enabled = false;
      clearTimeout(this.timer);
      this.request?.abort();
      this.clearSources();
      if (this.context && this.context.state !== "closed") void this.context.close();
      this.context = null;
      this.stream = null;
      this.onStatus("声音未启用");
    }

    accept(packet) {
      const channels = decodePCM(packet);
      const stream = `${packet.stream_id}/${packet.generation}`;
      if (stream !== this.stream) {
        this.clearSources();
        this.stream = stream;
        // Start near live time rather than playing an old ring on enable/reset.
        this.cursor = Math.max(packet.first_frame, packet.next_frame - 2400);
        this.endTime = this.context.currentTime + 0.04;
      }
      if (packet.next_frame <= this.cursor) return; // repeated or older snapshot
      if (this.cursor < packet.first_frame) {
        this.droppedFrames += packet.first_frame - this.cursor;
        this.cursor = packet.first_frame;
        this.clearSources();
        this.endTime = this.context.currentTime + 0.04;
      }
      if (this.endTime > this.context.currentTime + 0.25) {
        this.clearSources();
        const live = Math.max(this.cursor, packet.next_frame - 2400);
        this.droppedFrames += live - this.cursor;
        this.cursor = live;
        this.endTime = this.context.currentTime + 0.04;
      }
      const offset = this.cursor - packet.first_frame;
      const length = packet.next_frame - this.cursor;
      const buffer = this.context.createBuffer(2, length, packet.sample_rate);
      buffer.copyToChannel(channels[0].subarray(offset), 0);
      buffer.copyToChannel(channels[1].subarray(offset), 1);
      const source = this.context.createBufferSource();
      source.buffer = buffer;
      source.connect(this.gain);
      source.onended = () => { this.sources.delete(source); source.disconnect(); };
      this.sources.add(source);
      const start = Math.max(this.endTime, this.context.currentTime + 0.015);
      source.start(start);
      this.endTime = start + length / packet.sample_rate;
      this.cursor = packet.next_frame;
      this.onStatus(this.droppedFrames
        ? `监听 guest 音频；缓冲丢失 ${Math.round(this.droppedFrames / 48)} ms`
        : "监听 guest 音频（不代替原厂解码）");
    }

    async poll(serial) {
      if (!this.enabled || serial !== this.serial) return;
      const request = new AbortController();
      this.request = request;
      const timeout = setTimeout(() => request.abort(), 2000);
      try {
        const packet = await this.fetchJSON("/api/audio", { signal: request.signal });
        if (serial === this.serial && this.enabled) this.accept(packet);
      } catch (error) {
        if (serial === this.serial && this.enabled) {
          this.onStatus(`声音暂不可用：${error.message}`);
        }
      } finally {
        clearTimeout(timeout);
        if (this.request === request) this.request = null;
        if (serial === this.serial && this.enabled) {
          this.timer = setTimeout(() => this.poll(serial), 50);
        }
      }
    }
  }

  const exported = { AudioOutput, decodePCM };
  if (typeof module !== "undefined" && module.exports) module.exports = exported;
  else root.NP560AudioOutput = exported;
})(globalThis);
