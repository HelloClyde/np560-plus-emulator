#ifndef DMCU_CPU_PARAM_H
#define DMCU_CPU_PARAM_H

#define TARGET_LONG_BITS 32
/*
 * This is QEMU's translation/memory-dispatch granularity, not a hardware MMU
 * page size (the DMCU has no paged MMU).  A 2-KiB target page preserves the
 * independently dispatched unbanked low and SFR windows.  Writable program
 * overlays are consolidated at exact contiguous source/destination
 * boundaries so their physical-section indices remain within this geometry.
 */
#define TARGET_PAGE_BITS 11
#define TARGET_PHYS_ADDR_SPACE_BITS 25
#define TARGET_VIRT_ADDR_SPACE_BITS 24

#endif
