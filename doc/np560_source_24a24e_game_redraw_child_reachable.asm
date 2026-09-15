; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x4A24E
; source word byte order: little
; source file word 0 maps to 24:A24E
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
24:A24E  2E02       LINK #0x02
24:A250  58F1       MOV [--R15], R1
24:A252  58F2       MOV [--R15], R2
24:A254  58F3       MOV [--R15], R3
24:A256  780B 0006  MOV R0, [R11+0x0006]
24:A25A  781B 0008  MOV R1, [R11+0x0008]
24:A25E  6A0B FFFC  MOV [R11+0xFFFC], R0
24:A262  6A1B FFFE  MOV [R11+0xFFFE], R1
24:A266  4C11       SL R1, #0x1
24:A268  5C01       SLOSB R0, #0x1
24:A26A  58F0       MOV [--R15], R0
24:A26C  1F90       POP REG[0x10]
24:A26E  4D11       SR R1, #0x1
24:A270  2971       MOVB RB7, [R1]
24:A272  1807       MOVSE R0, RB7
24:A274  782B FFFC  MOV R2, [R11+0xFFFC]
24:A278  783B FFFE  MOV R3, [R11+0xFFFE]
24:A27C  5031       ADD R3, #0x1
24:A27E  5120       ADDC R2, #0x0
24:A280  4C31       SL R3, #0x1
24:A282  5C21       SLOSB R2, #0x1
24:A284  58F2       MOV [--R15], R2
24:A286  1F90       POP REG[0x10]
24:A288  4D31       SR R3, #0x1
24:A28A  2953       MOVB RB5, [R3]
24:A28C  1825       MOVSE R2, RB5
24:A28E  4C24       SL R2, #0x4
24:A290  4C24       SL R2, #0x4
24:A292  1002       ADD R0, R2
24:A294  383F       MOV R3, [R15++]
24:A296  382F       MOV R2, [R15++]
24:A298  381F       MOV R1, [R15++]
24:A29A  2F00       UNLINK
24:A29C  C620       RETS
