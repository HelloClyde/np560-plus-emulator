; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x305AD6
; source word byte order: little
; source file word 0 maps to 50:5AD6
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:5AD6  2E00       LINK #0x00
50:5AD8  6810 00A1  MOV REG[0x10], #0x00A1
50:5ADC  88F0 387A  MOV REG[0xF0], [0x387A]
50:5AE0  2F00       UNLINK
50:5AE2  C620       RETS
