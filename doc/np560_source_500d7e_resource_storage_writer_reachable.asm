; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x300D7E
; source word byte order: little
; source file word 0 maps to 50:0D7E
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:0D7E  2E00       LINK #0x00
50:0D80  58F0       MOV [--R15], R0
50:0D82  58F1       MOV [--R15], R1
50:0D84  780B 000E  MOV R0, [R11+0x000E]
50:0D88  58F0       MOV [--R15], R0
50:0D8A  780B 000A  MOV R0, [R11+0x000A]
50:0D8E  781B 000C  MOV R1, [R11+0x000C]
50:0D92  58F1       MOV [--R15], R1
50:0D94  58F0       MOV [--R15], R0
50:0D96  780B 0006  MOV R0, [R11+0x0006]
50:0D9A  781B 0008  MOV R1, [R11+0x0008]
50:0D9E  58F1       MOV [--R15], R1
50:0DA0  58F0       MOV [--R15], R0
50:0DA2  BD28 0F92  SCALL 28:0F92
50:0DA6  50FA       ADD R15, #0xA
50:0DA8  381F       MOV R1, [R15++]
50:0DAA  380F       MOV R0, [R15++]
50:0DAC  2F00       UNLINK
50:0DAE  C620       RETS
