; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x222240
; source word byte order: little
; source file word 0 maps to 42:2240
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
42:2240  797B FFFB  MOVB RB7, [R11+0xFFFB]
42:2244  1937       MOVZE R3, RB7
42:2246  5631       CMP R3, #0x1
42:2248  AC0D 246C  AJMP SLE, 42:246C
42:224C  780B 0006  MOV R0, [R11+0x0006]
42:2250  781B 0008  MOV R1, [R11+0x0008]
42:2254  4971       MOVB RB7, #0x1
42:2256  3F11       IGNDS #1
42:2258  59F7       MOVB [--R15], RB7
42:225A  52F1       SUB R15, #0x1
42:225C  4C11       SL R1, #0x1
42:225E  5C01       SLOSB R0, #0x1
42:2260  4D11       SR R1, #0x1
42:2262  58F0       MOV [--R15], R0
42:2264  1F90       POP REG[0x10]
42:2266  3F01       CRIT #1
42:2268  50F1       ADD R15, #0x1
42:226A  3B1F       MOVB [R1], [R15++]
42:226C  AC00 246C  AJMP ALWAYS, 42:246C
; ---- gap: 254 word(s), data or unreachable code ----

loc_42_246C:
; xref: 42:2248, 42:226C
42:246C  4801       MOV R0, #0x1
42:246E  383F       MOV R3, [R15++]
42:2470  382F       MOV R2, [R15++]
42:2472  381F       MOV R1, [R15++]
42:2474  2F00       UNLINK
42:2476  C620       RETS
