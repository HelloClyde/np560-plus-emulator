; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FEBAE
; source word byte order: little
; source file word 0 maps to 4F:EBAE
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:EBAE  2E03       LINK #0x03
4F:EBB0  58F1       MOV [--R15], R1
4F:EBB2  780B 000A  MOV R0, [R11+0x000A]
4F:EBB6  781B 000C  MOV R1, [R11+0x000C]
4F:EBBA  6A0B FFFC  MOV [R11+0xFFFC], R0
4F:EBBE  6A1B FFFE  MOV [R11+0xFFFE], R1
4F:EBC2  780B 000E  MOV R0, [R11+0x000E]
4F:EBC6  58F0       MOV [--R15], R0
4F:EBC8  780B FFFC  MOV R0, [R11+0xFFFC]
4F:EBCC  781B FFFE  MOV R1, [R11+0xFFFE]
4F:EBD0  58F1       MOV [--R15], R1
4F:EBD2  58F0       MOV [--R15], R0
4F:EBD4  780B 0006  MOV R0, [R11+0x0006]
4F:EBD8  781B 0008  MOV R1, [R11+0x0008]
4F:EBDC  58F1       MOV [--R15], R1
4F:EBDE  58F0       MOV [--R15], R0
4F:EBE0  BD33 0D7E  SCALL 33:0D7E
4F:EBE4  50FA       ADD R15, #0xA
4F:EBE6  4801       MOV R0, #0x1
4F:EBE8  381F       MOV R1, [R15++]
4F:EBEA  2F00       UNLINK
4F:EBEC  C620       RETS
