"use strict";

(function (root) {
  // A complete QMP/HTTP poll commonly arrives every 125-150 ms. Retain
  // 150 ms of actual ring audio plus the 40 ms scheduling lead; 50 ms
  // drained before the next packet. No generated silence or resampling.
  const startupFrames = 7200;
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
                  onStatus = () => {}, onEnabledChange = () => {} }) {
      this.fetchJSON = fetchJSON;
      this.AudioContextClass = AudioContextClass;
      this.onStatus = onStatus;
      this.onEnabledChange = onEnabledChange;
      this.enabled = false;
      this.serial = 0;
      this.presentationEpoch = 0;
      this.sources = new Set();
      this.stream = null;
      this.cursor = 0;
      this.droppedFrames = 0;
      this.presentationGapSeconds = 0;
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
        if (serial !== this.serial) {
          if (context.state !== "closed") await context.close();
          return;
        }
        if (context.state !== "running") throw new Error("请点击按钮允许浏览器播放声音");
        this.gain = context.createGain();
        this.gain.gain.value = 0.25; // listening attenuation, not a guest volume write
        this.gain.connect(context.destination);
        this.enabled = true;
        this.onEnabledChange(true);
        this.contextStateChanged = () => {
          if (this.context !== context || !this.enabled) return;
          if (context.state === "closed") { this.stop(); return; }
          if (context.state !== "running") this.discardInterruptedAudio();
        };
        context.addEventListener("statechange", this.contextStateChanged);
        this.stream = null;
        this.cursor = 0;
        this.droppedFrames = 0;
        this.presentationGapSeconds = 0;
        this.endTime = context.currentTime + 0.04;
        this.onStatus("声音已启用，等待 guest 数据");
        void this.poll(serial);
      } catch (error) {
        if (serial === this.serial) this.stop();
        else if (context.state !== "closed") {
          // A superseded start still owns its old context. Do not stop the
          // current session, and do not replace the original resume error.
          try { await context.close(); } catch (_) { /* cleanup only */ }
        }
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
      this.onEnabledChange(false);
      clearTimeout(this.timer);
      this.request?.abort();
      if (this.context && this.contextStateChanged) {
        this.context.removeEventListener("statechange", this.contextStateChanged);
      }
      this.contextStateChanged = null;
      this.clearSources();
      const closingContext = this.context;
      this.context = null;
      this.stream = null;
      this.onStatus("声音未启用");
      if (closingContext && closingContext.state !== "closed") {
        const serial = this.serial;
        const failed = () => {
          // A late cleanup failure belongs to the stopped session, never a
          // replacement. Listening is off even if browser release failed.
          if (serial === this.serial && !this.enabled) {
            this.onStatus("声音监听已停止；浏览器音频设备释放失败");
          }
        };
        try { Promise.resolve(closingContext.close()).catch(failed); }
        catch (_) { failed(); }
      }
    }

    discardInterruptedAudio() {
      // Abort is best effort: a completed fetch/JSON promise may still resolve.
      // Invalidate its presentation epoch as well, without resetting the guest.
      this.presentationEpoch += 1;
      this.request?.abort();
      this.clearSources();
      this.stream = null;
      this.onStatus("浏览器已暂停声音；恢复后从实时音频继续，必要时关闭再启用声音");
    }

    accept(packet) {
      const channels = decodePCM(packet);
      // HTTP can keep delivering while a mobile AudioContext is suspended or
      // interrupted. Its currentTime is then frozen. Drop presentation state,
      // not guest state; the next running packet establishes a fresh live window.
      if (this.context.state !== "running") {
        this.discardInterruptedAudio();
        return;
      }
      const stream = `${packet.stream_id}/${packet.generation}`;
      if (stream !== this.stream) {
        this.clearSources();
        this.stream = stream;
        // Bounded prebuffer remains inside the existing 200 ms device ring.
        this.cursor = Math.max(packet.first_frame, packet.next_frame - startupFrames);
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
        const live = Math.max(this.cursor, packet.next_frame - startupFrames);
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
      const start = Math.max(this.endTime, this.context.currentTime + 0.015);
      try {
        source.connect(this.gain);
        source.onended = () => { this.sources.delete(source); source.disconnect(); };
        this.sources.add(source);
        source.start(start);
      } catch (error) {
        // Keep the packet retryable if the output device/context fails.
        // A node that never starts will not deliver onended for cleanup.
        this.sources.delete(source);
        source.onended = null;
        try { source.stop(); } catch (_) { /* may not have started */ }
        try { source.disconnect(); } catch (_) { /* preserve scheduling error */ }
        throw error;
      }
      // The device ring can be intact while the guest produces PCM slower
      // than the browser consumes it. Count that presentation gap separately
      // from droppedFrames; this changes diagnostics, not playback timing.
      this.presentationGapSeconds += Math.max(0, start - this.endTime);
      this.endTime = start + length / packet.sample_rate;
      this.cursor = packet.next_frame;
      const issues = [];
      if (this.droppedFrames) issues.push(`缓冲丢失 ${Math.round(this.droppedFrames / 48)} ms`);
      if (this.presentationGapSeconds >= 0.001) {
        issues.push(`播放空档 ${Math.round(this.presentationGapSeconds * 1000)} ms`);
      }
      this.onStatus(issues.length
        ? `监听 guest 音频；${issues.join("；")}`
        : "监听 guest 音频（不代替原厂解码）");
    }

    async poll(serial) {
      if (!this.enabled || serial !== this.serial) return;
      const epoch = this.presentationEpoch;
      const request = new AbortController();
      this.request = request;
      const timeout = setTimeout(() => request.abort(), 2000);
      try {
        const packet = await this.fetchJSON("/api/audio", { signal: request.signal });
        if (serial === this.serial && epoch === this.presentationEpoch && this.enabled) this.accept(packet);
      } catch (error) {
        if (serial === this.serial && epoch === this.presentationEpoch && this.enabled) {
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
