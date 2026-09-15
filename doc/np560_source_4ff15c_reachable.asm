; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FF15C
; source word byte order: little
; source file word 0 maps to 4F:F15C
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:F15C  2E02       LINK #0x02
4F:F15E  58F0       MOV [--R15], R0
4F:F160  58F1       MOV [--R15], R1
4F:F162  780B 0006  MOV R0, [R11+0x0006]
4F:F166  781B 0008  MOV R1, [R11+0x0008]
4F:F16A  6A0B FFFC  MOV [R11+0xFFFC], R0
4F:F16E  6A1B FFFE  MOV [R11+0xFFFE], R1
4F:F172  780B FFFC  MOV R0, [R11+0xFFFC]
4F:F176  781B FFFE  MOV R1, [R11+0xFFFE]
4F:F17A  4C11       SL R1, #0x1
4F:F17C  5C01       SLOSB R0, #0x1
4F:F17E  58F0       MOV [--R15], R0
4F:F180  1F90       POP REG[0x10]
4F:F182  4D11       SR R1, #0x1
4F:F184  3801       MOV R0, [R1++]
4F:F186  2811       MOV R1, [R1]
4F:F188  58F1       MOV [--R15], R1
4F:F18A  58F0       MOV [--R15], R0
4F:F18C  BD2B 593E  SCALL 2B:593E
4F:F190  50F4       ADD R15, #0x4
4F:F192  381F       MOV R1, [R15++]
4F:F194  380F       MOV R0, [R15++]
4F:F196  2F00       UNLINK
4F:F198  C620       RETS
