#ifndef DMCU_CPU_PARAM_H
#define DMCU_CPU_PARAM_H

#define TARGET_LONG_BITS 32
/*
 * This is QEMU's translation/memory-dispatch granularity, not a hardware MMU
 * page size (the DMCU has no paged MMU).  A 2-KiB target page leaves ample
 * section-index space for the sparse writable code overlays recovered from
 * NP560.PRG; subpage dispatch still preserves the small SFR windows.  Eleven
 * bits also satisfies QEMU's 25-bit physical-address TB page-table geometry.
 */
#define TARGET_PAGE_BITS 11
#define TARGET_PHYS_ADDR_SPACE_BITS 25
#define TARGET_VIRT_ADDR_SPACE_BITS 24

#endif
