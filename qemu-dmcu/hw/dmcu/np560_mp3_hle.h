/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DMCU_NP560_MP3_HLE_H
#define HW_DMCU_NP560_MP3_HLE_H

typedef struct NP560MP3HLE NP560MP3HLE;
NP560MP3HLE *np560_mp3_hle_new(DMCUCPU *cpu, uint32_t base, Error **errp);
void np560_mp3_hle_free(NP560MP3HLE *state);
void np560_mp3_hle_reset(void *opaque);
bool np560_mp3_hle_service(void *opaque, CPUDMCUState *env, uint32_t pc);
char *np560_mp3_hle_state(NP560MP3HLE *state);
#endif
