; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FF6D2
; source word byte order: little
; source file word 0 maps to 4F:F6D2
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:F6D2  2E00       LINK #0x00
4F:F6D4  58F1       MOV [--R15], R1
4F:F6D6  6810 00A1  MOV REG[0x10], #0x00A1
4F:F6DA  88F0 387A  MOV REG[0xF0], [0x387A]
4F:F6DE  5600       CMP R0, #0x0
4F:F6E0  AC01 F6EA  AJMP Z/EQ, 4F:F6EA
4F:F6E4  4800       MOV R0, #0x0
4F:F6E6  AC00 F708  AJMP ALWAYS, 4F:F708
loc_4F_F6EA:
; xref: 4F:F6E0
4F:F6EA  780B 000A  MOV R0, [R11+0x000A]
4F:F6EE  781B 000C  MOV R1, [R11+0x000C]
4F:F6F2  58F1       MOV [--R15], R1
4F:F6F4  58F0       MOV [--R15], R0
4F:F6F6  780B 0006  MOV R0, [R11+0x0006]
4F:F6FA  781B 0008  MOV R1, [R11+0x0008]
4F:F6FE  58F1       MOV [--R15], R1
4F:F700  58F0       MOV [--R15], R0
4F:F702  BD33 6BD2  SCALL 33:6BD2
4F:F706  50F8       ADD R15, #0x8
loc_4F_F708:
; xref: 4F:F6E6
4F:F708  381F       MOV R1, [R15++]
4F:F70A  2F00       UNLINK
4F:F70C  C620       RETS
