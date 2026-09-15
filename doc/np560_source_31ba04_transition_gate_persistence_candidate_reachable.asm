; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x11BA04
; source word byte order: little
; source file word 0 maps to 31:BA04
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
31:BA04  BE64 780B  MAC cfg=0x64, operands=0x780B
31:BA08  FFFC       BCLR BIT[0xFC].15
31:BA0A  781B FFFE  MOV R1, [R11+0xFFFE]
31:BA0E  70F1 001E  ADD REG[0xF1], #0x001E
31:BA12  5100       ADDC R0, #0x0
31:BA14  4C11       SL R1, #0x1
31:BA16  5C01       SLOSB R0, #0x1
31:BA18  58F0       MOV [--R15], R0
31:BA1A  1F90       POP REG[0x10]
31:BA1C  4D11       SR R1, #0x1
31:BA1E  2801       MOV R0, [R1]
31:BA20  6810 00A1  MOV REG[0x10], #0x00A1
31:BA24  C700       NOP
31:BA26  A9F1 387D  MOVB [0x387D], REG[0xF1]
31:BA2A  6810 00A1  MOV REG[0x10], #0x00A1
31:BA2E  89F1 387D  MOVB REG[0xF1], [0x387D]
31:BA32  6B1B FFF8  MOVB [R11+0xFFF8], RB1
31:BA36  4801       MOV R0, #0x1
31:BA38  58F0       MOV [--R15], R0
31:BA3A  68F0 0010  MOV REG[0xF0], #0x0010
31:BA3E  68F1 D018  MOV REG[0xF1], #0xD018
31:BA42  58F1       MOV [--R15], R1
31:BA44  58F0       MOV [--R15], R0
31:BA46  081B       MOV R1, R11
31:BA48  70F1 FFF8  ADD REG[0xF1], #0xFFF8
31:BA4C  4800       MOV R0, #0x0
31:BA4E  58F1       MOV [--R15], R1
31:BA50  58F0       MOV [--R15], R0
31:BA52  BD32 EBAE  SCALL 32:EBAE
31:BA56  50FA       ADD R15, #0xA
31:BA58  AC00 BE64  AJMP ALWAYS, 31:BE64
