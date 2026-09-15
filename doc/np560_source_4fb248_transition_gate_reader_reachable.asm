; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FB248
; source word byte order: little
; source file word 0 maps to 4F:B248
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:B248  2E00       LINK #0x00
4F:B24A  58F1       MOV [--R15], R1
4F:B24C  6810 00A1  MOV REG[0x10], #0x00A1
4F:B250  88F0 387A  MOV REG[0xF0], [0x387A]
4F:B254  5600       CMP R0, #0x0
4F:B256  AC01 B260  AJMP Z/EQ, 4F:B260
4F:B25A  4800       MOV R0, #0x0
4F:B25C  AC00 B298  AJMP ALWAYS, 4F:B298
loc_4F_B260:
; xref: 4F:B256
4F:B260  780B 0012  MOV R0, [R11+0x0012]
4F:B264  781B 0014  MOV R1, [R11+0x0014]
4F:B268  58F1       MOV [--R15], R1
4F:B26A  58F0       MOV [--R15], R0
4F:B26C  780B 000E  MOV R0, [R11+0x000E]
4F:B270  781B 0010  MOV R1, [R11+0x0010]
4F:B274  58F1       MOV [--R15], R1
4F:B276  58F0       MOV [--R15], R0
4F:B278  780B 000A  MOV R0, [R11+0x000A]
4F:B27C  781B 000C  MOV R1, [R11+0x000C]
4F:B280  58F1       MOV [--R15], R1
4F:B282  58F0       MOV [--R15], R0
4F:B284  780B 0006  MOV R0, [R11+0x0006]
4F:B288  781B 0008  MOV R1, [R11+0x0008]
4F:B28C  58F1       MOV [--R15], R1
4F:B28E  58F0       MOV [--R15], R0
4F:B290  BD32 E4DC  SCALL 32:E4DC
4F:B294  70FF 0010  ADD REG[0xFF], #0x0010
loc_4F_B298:
; xref: 4F:B25C
4F:B298  381F       MOV R1, [R15++]
4F:B29A  2F00       UNLINK
4F:B29C  C620       RETS
