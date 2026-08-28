#ifndef TARGET_DMCU_CPU_QOM_H
#define TARGET_DMCU_CPU_QOM_H

#include "hw/core/cpu.h"

#define TYPE_DMCU_CPU "dmcu-cpu"
OBJECT_DECLARE_CPU_TYPE(DMCUCPU, DMCUCPUClass, DMCU_CPU)

#define DMCU_CPU_TYPE_NAME(name) (name "-" TYPE_DMCU_CPU)
#define TYPE_DMCU_V1_CPU DMCU_CPU_TYPE_NAME("v1")

#endif
