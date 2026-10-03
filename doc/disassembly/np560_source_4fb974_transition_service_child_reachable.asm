; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FB974
; source word byte order: little
; source file word 0 maps to 4F:B974
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:B974  2E00       LINK #0x00
4F:B976  58F1       MOV [--R15], R1
4F:B978  4800       MOV R0, #0x0
4F:B97A  58F0       MOV [--R15], R0
4F:B97C  780B 001A  MOV R0, [R11+0x001A]
4F:B980  781B 001C  MOV R1, [R11+0x001C]
4F:B984  58F1       MOV [--R15], R1
4F:B986  58F0       MOV [--R15], R0
4F:B988  780B 0016  MOV R0, [R11+0x0016]
4F:B98C  781B 0018  MOV R1, [R11+0x0018]
4F:B990  58F1       MOV [--R15], R1
4F:B992  58F0       MOV [--R15], R0
4F:B994  780B 0012  MOV R0, [R11+0x0012]
4F:B998  781B 0014  MOV R1, [R11+0x0014]
4F:B99C  58F1       MOV [--R15], R1
4F:B99E  58F0       MOV [--R15], R0
4F:B9A0  780B 000A  MOV R0, [R11+0x000A]
4F:B9A4  781B 000C  MOV R1, [R11+0x000C]
4F:B9A8  58F1       MOV [--R15], R1
4F:B9AA  58F0       MOV [--R15], R0
4F:B9AC  780B 0006  MOV R0, [R11+0x0006]
4F:B9B0  781B 0008  MOV R1, [R11+0x0008]
4F:B9B4  58F1       MOV [--R15], R1
4F:B9B6  58F0       MOV [--R15], R0
4F:B9B8  BD25 0000  SCALL 25:0000
4F:B9BC  70FF 0016  ADD REG[0xFF], #0x0016
4F:B9C0  381F       MOV R1, [R15++]
4F:B9C2  2F00       UNLINK
4F:B9C4  C620       RETS
