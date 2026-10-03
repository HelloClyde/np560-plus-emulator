; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FE5E4
; source word byte order: little
; source file word 0 maps to 4F:E5E4
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:E5E4  2E00       LINK #0x00
4F:E5E6  780B 0006  MOV R0, [R11+0x0006]
4F:E5EA  6B1B 0006  MOVB [R11+0x0006], RB1
4F:E5EE  791B 0006  MOVB RB1, [R11+0x0006]
4F:E5F2  1801       MOVSE R0, RB1
4F:E5F4  76F0 0061  CMP REG[0xF0], #0x0061
4F:E5F8  AC09 E604  AJMP SL, 4F:E604
4F:E5FC  76F0 007A  CMP REG[0xF0], #0x007A
4F:E600  AC0D E61A  AJMP SLE, 4F:E61A
loc_4F_E604:
; xref: 4F:E5F8
4F:E604  791B 0006  MOVB RB1, [R11+0x0006]
4F:E608  1801       MOVSE R0, RB1
4F:E60A  76F0 0041  CMP REG[0xF0], #0x0041
4F:E60E  AC09 E620  AJMP SL, 4F:E620
4F:E612  76F0 005A  CMP REG[0xF0], #0x005A
4F:E616  AC0B E620  AJMP SG, 4F:E620
loc_4F_E61A:
; xref: 4F:E600
4F:E61A  4800       MOV R0, #0x0
4F:E61C  AC00 E622  AJMP ALWAYS, 4F:E622
loc_4F_E620:
; xref: 4F:E60E, 4F:E616
4F:E620  4801       MOV R0, #0x1
loc_4F_E622:
; xref: 4F:E61C
4F:E622  2F00       UNLINK
4F:E624  C620       RETS
