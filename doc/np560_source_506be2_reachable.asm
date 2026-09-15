; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x306BE2
; source word byte order: little
; source file word 0 maps to 50:6BE2
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:6BE2  2E00       LINK #0x00
50:6BE4  4801       MOV R0, #0x1
50:6BE6  2F00       UNLINK
50:6BE8  C620       RETS
