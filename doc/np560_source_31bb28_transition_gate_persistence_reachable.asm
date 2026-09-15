; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x11BB28
; source word byte order: little
; source file word 0 maps to 31:BB28
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
31:BB28  780B FFFC  MOV R0, [R11+0xFFFC]
31:BB2C  781B FFFE  MOV R1, [R11+0xFFFE]
31:BB30  70F1 001E  ADD REG[0xF1], #0x001E
31:BB34  5100       ADDC R0, #0x0
31:BB36  4C11       SL R1, #0x1
31:BB38  5C01       SLOSB R0, #0x1
31:BB3A  58F0       MOV [--R15], R0
31:BB3C  1F90       POP REG[0x10]
31:BB3E  4D11       SR R1, #0x1
31:BB40  2801       MOV R0, [R1]
31:BB42  6810 00A1  MOV REG[0x10], #0x00A1
31:BB46  C700       NOP
31:BB48  A8F0 387A  MOV [0x387A], REG[0xF0]
31:BB4C  6810 00A1  MOV REG[0x10], #0x00A1
31:BB50  88F0 387A  MOV REG[0xF0], [0x387A]
31:BB54  6B1B FFF8  MOVB [R11+0xFFF8], RB1
31:BB58  4801       MOV R0, #0x1
31:BB5A  58F0       MOV [--R15], R0
31:BB5C  68F0 0010  MOV REG[0xF0], #0x0010
31:BB60  68F1 D016  MOV REG[0xF1], #0xD016
31:BB64  58F1       MOV [--R15], R1
31:BB66  58F0       MOV [--R15], R0
31:BB68  081B       MOV R1, R11
31:BB6A  70F1 FFF8  ADD REG[0xF1], #0xFFF8
31:BB6E  4800       MOV R0, #0x0
31:BB70  58F1       MOV [--R15], R1
31:BB72  58F0       MOV [--R15], R0
31:BB74  BD32 EBAE  SCALL 32:EBAE
31:BB78  50FA       ADD R15, #0xA
31:BB7A  AC00 BE64  AJMP ALWAYS, 31:BE64
