#!/usr/bin/env python3
"""Compile the actual device scheduler with a timer sink; no guest emulation."""
import pathlib
import re
import shutil
import subprocess
import tempfile
import unittest


class FractionalAudioClockTests(unittest.TestCase):
    def test_actual_tick_and_dac_ring_use_dispatch_time_without_lane_skew(self):
        """Late IRQ delivery must not backdate a sample or drift the next deadline."""
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            self.skipTest('C compiler required (run under WSL)')
        root = pathlib.Path(__file__).resolve().parents[2]
        source = (root / 'qemu-dmcu/hw/dmcu/np560_audio.c').read_text()
        functions = []
        for name in ('np560_audio_enabled', 'np560_audio_request_schedule',
                     'np560_audio_sync', 'np560_audio_request_tick'):
            match = re.search(r'static (?:void|bool) ' + name +
                              r'\([^\n]*\)\n\{.*?\n\}', source, re.S)
            self.assertIsNotNone(match)
            functions.append(match.group(0))
        harness = r'''
#include <stdint.h>
#include <stdbool.h>
#include <assert.h>
#include <string.h>
#include <stdio.h>
#define NP560_AUDIO_RATE 48000
#define NP560_AUDIO_FRAMES 64
#define NANOSECONDS_PER_SECOND 1000000000ULL
#define QEMU_CLOCK_VIRTUAL 0
#define MAX(a,b) ((a) > (b) ? (a) : (b))
typedef struct {
    void *request_timer, *cpu;
    int64_t request_deadline_ns, epoch_ns, current_request_ns;
    int64_t request_last_deadline_ns, request_last_lateness_ns, request_max_lateness_ns;
    uint32_t request_fraction, request_hz;
    bool request_running, request_in_progress;
    uint16_t control, sample[2];
    uint64_t next_frame, sample_writes[2], request_ticks, request_late_ticks;
    uint64_t request_writes[2], request_without_write[2], request_multiple_writes[2];
    uint8_t pcm[NP560_AUDIO_FRAMES * 4];
} NP560AudioState;
static int64_t now, armed;
static unsigned irq_count;
static uint16_t next_sample;
static int64_t qemu_clock_get_ns(int clock) { return now; }
static void timer_mod(void *timer, int64_t deadline) { armed = deadline; }
static uint64_t muldiv64(uint64_t a, uint64_t b, uint64_t c) { return a*b/c; }
static void stw_le_p(uint8_t *p, uint16_t v) { p[0]=v; p[1]=v>>8; }
static void dmcu_irq_raise(void *cpu, int irq);
'''
        harness += '\n'.join(functions)
        harness += r'''
/* Controlled DTU sink, not a test of the DTU implementation. Exercise sync
 * at both writes, as the real register-write boundary does. */
static void dmcu_irq_raise(void *cpu, int irq) {
    NP560AudioState *s = cpu;
    unsigned ch = irq == 17 ? 0 : 1;
    assert(irq == (irq_count++ % 2 ? 16 : 17));
    np560_audio_sync(s);
    s->sample[ch] = ch ? (uint16_t)~next_sample : next_sample;
    s->sample_writes[ch]++;
}
int main(void) {
    const unsigned rates[] = {22048, 44084};
    for (unsigned rate_index = 0; rate_index < 2; rate_index++) {
    NP560AudioState s = {0};
    uint8_t expected[NP560_AUDIO_FRAMES * 4] = {0};
    uint64_t frames = 0;
    uint64_t boundary_crossings = 0;
    const unsigned delays[] = {0, 41, 249, 100, 17};
    now = 0; armed = 0; irq_count = 0;
    s.cpu = &s; s.control = 1; s.request_running = true;
    s.request_hz = rates[rate_index];
    np560_audio_request_schedule(&s);
    for (uint64_t n=1; n<=100000; n++) {
        int64_t deadline = armed;
        unsigned delay = delays[n % 5];
        now = deadline + delay;
        uint64_t deadline_frame = (uint64_t)deadline * 48000 / 1000000000ULL;
        uint64_t dispatch_frame = (uint64_t)now * 48000 / 1000000000ULL;
        uint16_t previous_sample = s.sample[0];
        /* Independent presentation-boundary walk using old held values.
         * All frames ending before this actual dispatch retain those values. */
        while ((frames+1)*1000000000ULL <= (uint64_t)now*48000) {
            unsigned offset = (frames++ % NP560_AUDIO_FRAMES)*4;
            stw_le_p(expected+offset, s.sample[0]);
            stw_le_p(expected+offset+2, s.sample[1]);
        }
        next_sample = (uint16_t)(n*73);
        np560_audio_request_tick(&s);
        assert(s.next_frame == frames);
        assert(memcmp(expected, s.pcm, sizeof(expected)) == 0);
        assert(s.request_last_deadline_ns == deadline);
        assert(s.request_last_lateness_ns == delay);
        assert(s.current_request_ns == now);
        assert(armed == ((n+1)*1000000000ULL)/s.request_hz);
        assert(dispatch_frame - deadline_frame <= 1);
        if (dispatch_frame != deadline_frame) {
            unsigned offset = (deadline_frame % NP560_AUDIO_FRAMES) * 4;
            uint16_t held = s.pcm[offset] | (s.pcm[offset+1] << 8);
            /* A sub-microsecond late dispatch can cross a 48 kHz boundary.
             * It changes the duration of the old sample, not the number or
             * ordering of requests. Do not silently call this lost PCM. */
            assert(held == previous_sample);
            assert(held != next_sample);
            boundary_crossings++;
        }
        assert(s.request_writes[0] == n && s.request_writes[1] == n);
        assert(!s.request_in_progress);
    }
    assert(s.request_max_lateness_ns == 249);
    assert(s.request_late_ticks == 80000);
    s.request_running = false;
    np560_audio_request_tick(&s);
    assert(irq_count == 200000);
    assert(boundary_crossings > 0);
    printf("rate=%u requests=100000 late_boundary_holds=%llu max_delay_ns=249\n",
           s.request_hz, (unsigned long long)boundary_crossings);
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='np560-dispatch-ring-') as directory:
            src = pathlib.Path(directory) / 'clock.c'
            exe = pathlib.Path(directory) / 'clock'
            src.write_text(harness)
            subprocess.run([compiler, '-std=c99', '-O2', str(src), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=30)

    def test_actual_scheduler_retains_fraction_and_deadline(self):
        compiler = shutil.which('cc') or shutil.which('gcc')
        if not compiler:
            self.skipTest('C compiler required (run under WSL)')
        root = pathlib.Path(__file__).resolve().parents[2]
        source = (root / 'qemu-dmcu/hw/dmcu/np560_audio.c').read_text()
        match = re.search(r'static void np560_audio_request_schedule\([^\n]*\)\n\{.*?\n\}',
                          source, re.S)
        self.assertIsNotNone(match)
        harness = r'''
#include <stdint.h>
#include <assert.h>
typedef struct {
    void *request_timer;
    int64_t request_deadline_ns;
    uint32_t request_fraction, request_hz;
} NP560AudioState;
static int64_t armed;
static void timer_mod(void *timer, int64_t deadline) { armed = deadline; }
'''
        harness += match.group(0)
        harness += r'''
int main(void) {
    const unsigned rates[] = {8000, 22048, 22050, 32000, 44084, 48000, 1, 99999};
    for (unsigned r = 0; r < sizeof(rates)/sizeof(rates[0]); r++) {
        const int64_t epoch = 1234567890123LL;
        NP560AudioState s = {0};
        s.request_hz = rates[r];
        s.request_deadline_ns = epoch;
        for (uint64_t n = 1; n <= 1000000; n++) {
            int64_t previous = s.request_deadline_ns;
            np560_audio_request_schedule(&s);
            assert(armed == epoch + (n * 1000000000ULL) / rates[r]);
            assert(s.request_fraction == (n * 1000000000ULL) % rates[r]);
            assert(armed > previous);
        }
    }
    return 0;
}
'''
        with tempfile.TemporaryDirectory(prefix='np560-fractional-clock-') as directory:
            src = pathlib.Path(directory) / 'clock.c'
            exe = pathlib.Path(directory) / 'clock'
            src.write_text(harness)
            subprocess.run([compiler, '-std=c99', '-O2', str(src), '-o', str(exe)], check=True)
            subprocess.run([str(exe)], check=True, timeout=30)


if __name__ == '__main__':
    unittest.main()
