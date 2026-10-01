/* Translation-time metadata. No guest state or dynamic addresses cached. */
#ifndef DMCU_DECODE_H
#define DMCU_DECODE_H

#define DMCU_META_SIZE_SHIFT 16
#define DMCU_META_REPEAT (1u << 19)
#define DMCU_META_FORBIDDEN_REP (1u << 20)
#define DMCU_META_CYCLES_SHIFT 21
#define DMCU_META_SPARSE_PRELUDE (1u << 24)
#define DMCU_META_Y_ACCESS (1u << 25)

uint32_t dmcu_exec_metadata(uint16_t word, uint32_t pc);
unsigned dmcu_decode_cycles(uint16_t word, uint32_t pc);
#endif
