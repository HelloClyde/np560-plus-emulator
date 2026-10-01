/* SPDX-License-Identifier: GPL-2.0-or-later */
#ifndef HW_DMCU_NP560_NPE_HLE_H
#define HW_DMCU_NP560_NPE_HLE_H

#include "cpu.h"
#include "qapi/error.h"

typedef struct NP560NPEHLE NP560NPEHLE;

NP560NPEHLE *np560_npe_hle_new(DMCUCPU *cpu, const char *codec_socket,
                                Error **errp);
void np560_npe_hle_free(NP560NPEHLE *hle);
void np560_npe_hle_reset(void *opaque);
bool np560_npe_hle_service(NP560NPEHLE *hle, CPUDMCUState *env, uint32_t pc);
char *np560_npe_hle_state(NP560NPEHLE *hle);

#endif
