; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x300000
; source word byte order: little
; source file word 0 maps to 50:0000
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:5ABA  2E00       LINK #0x00
50:5ABC  6810 00A1  MOV REG[0x10], #0x00A1
50:5AC0  99F0 3886  MOVZE REG[0xF0], [0x3886]
50:5AC4  2F00       UNLINK
50:5AC6  C620       RETS
