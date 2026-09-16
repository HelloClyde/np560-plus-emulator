#ifndef HW_DMCU_NP560_TIMER_H
#define HW_DMCU_NP560_TIMER_H

#include "hw/ptimer.h"
#include "cpu.h"

#define NP560_PERIODIC_TIMERS 3

typedef struct NP560PeriodicTimerState {
    DMCUCPU *cpu;
    ptimer_state *timer;
    unsigned index;
    uint32_t frequency;
    bool running;
    uint64_t expirations;
    uint64_t unsupported_configs;
} NP560PeriodicTimerState;

typedef struct NP560TimersState {
    DMCUCPU *cpu;
    NP560PeriodicTimerState channel[NP560_PERIODIC_TIMERS];
    NP560PeriodicTimerState timebase;
} NP560TimersState;

void np560_timers_init(NP560TimersState *s, DMCUCPU *cpu);
uint16_t np560_timers_read(void *opaque, unsigned reg, uint16_t value);
void np560_timers_write(void *opaque, unsigned reg,
                       uint16_t old_value, uint16_t value);
void np560_timers_reset(void *opaque);
void np560_timers_destroy(NP560TimersState *s);
char *np560_periodic_timer_state(NP560TimersState *s, unsigned index);
char *np560_timebase_state(NP560TimersState *s);

#endif
