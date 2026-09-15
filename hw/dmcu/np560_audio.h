#ifndef HW_DMCU_NP560_AUDIO_H
#define HW_DMCU_NP560_AUDIO_H

#include "qemu/timer.h"
#include "hw/ptimer.h"
#include "cpu.h"

/* Host presentation rate, not the guest DAC clock. Register transitions are
 * timestamped in virtual time and held between writes. */
#define NP560_AUDIO_RATE 48000
#define NP560_AUDIO_FRAMES 9600
#define NP560_AUDIO_CONTROL_EVENTS 64

/* Bounded, read-only write evidence. Counters distinguish DAC-off time from
 * enabled requests without DTU data; this never records every PCM sample. */
typedef struct NP560AudioControlEvent {
    int64_t virtual_ns;
    uint64_t frame, ticks, writes[2], empty[2], outside[2];
    uint32_t pc;
    uint16_t reg, old_value, value;
    bool enabled, running;
} NP560AudioControlEvent;

typedef struct NP560AudioState {
    DMCUCPU *cpu;
    QEMUTimer *timer;
    ptimer_state *request_timer;
    uint32_t request_hz;
    uint64_t request_ticks;
    uint64_t request_writes[2];
    uint64_t request_without_write[2];
    uint64_t request_multiple_writes[2];
    uint64_t writes_outside_request[2];
    uint16_t pll;
    bool request_running;
    bool request_in_progress;
    int64_t epoch_ns;
    uint64_t generation;
    uint64_t next_frame;
    uint64_t sample_writes[2];
    uint64_t control_writes;
    uint16_t sample[2];
    uint16_t control;
    uint64_t control_event_next;
    NP560AudioControlEvent control_events[NP560_AUDIO_CONTROL_EVENTS];
    uint8_t pcm[NP560_AUDIO_FRAMES * 4];
} NP560AudioState;

void np560_audio_init(NP560AudioState *s, DMCUCPU *cpu);
void np560_audio_reset(void *opaque);
void np560_audio_destroy(NP560AudioState *s);
void np560_audio_write(NP560AudioState *s, unsigned reg, uint16_t value);
char *np560_audio_snapshot(NP560AudioState *s);

#endif
