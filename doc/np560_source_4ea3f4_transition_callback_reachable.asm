; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2EA3F4
; source word byte order: little
; source file word 0 maps to 4E:A3F4
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4E:A3F4  2E00       LINK #0x00
4E:A3F6  58F0       MOV [--R15], R0
4E:A3F8  58F1       MOV [--R15], R1
4E:A3FA  58F2       MOV [--R15], R2
4E:A3FC  58F3       MOV [--R15], R3
4E:A3FE  58F4       MOV [--R15], R4
4E:A400  58F5       MOV [--R15], R5
4E:A402  68F1 A3F4  MOV REG[0xF1], #0xA3F4
4E:A406  68F0 0031  MOV REG[0xF0], #0x0031
4E:A40A  58F1       MOV [--R15], R1
4E:A40C  58F0       MOV [--R15], R0
4E:A40E  4810       MOV R1, #0x0
4E:A410  4800       MOV R0, #0x0
4E:A412  58F1       MOV [--R15], R1
4E:A414  58F0       MOV [--R15], R0
4E:A416  58F1       MOV [--R15], R1
4E:A418  58F0       MOV [--R15], R0
4E:A41A  6810 00A4  MOV REG[0x10], #0x00A4
4E:A41E  99F0 7A04  MOVZE REG[0xF0], [0x7A04]
4E:A422  0810       MOV R1, R0
4E:A424  5610       CMP R1, #0x0
4E:A426  DE03       RJMP SGE, 4E:A42E ; rel +3
4E:A428  68F0 FFFF  MOV REG[0xF0], #0xFFFF
4E:A42C  D001       RJMP ALWAYS, 4E:A430 ; rel +1
loc_4E_A42E:
; xref: 4E:A426
4E:A42E  4800       MOV R0, #0x0
loc_4E_A430:
; xref: 4E:A42C
4E:A430  4C12       SL R1, #0x2
4E:A432  5C02       SLOSB R0, #0x2
4E:A434  68F3 78F2  MOV REG[0xF3], #0x78F2
4E:A438  68F2 0052  MOV REG[0xF2], #0x0052
4E:A43C  0840       MOV R4, R0
4E:A43E  0851       MOV R5, R1
4E:A440  1053       ADD R5, R3
4E:A442  1142       ADDC R4, R2
4E:A444  4C51       SL R5, #0x1
4E:A446  5C41       SLOSB R4, #0x1
4E:A448  58F4       MOV [--R15], R4
4E:A44A  1F90       POP REG[0x10]
4E:A44C  4D51       SR R5, #0x1
4E:A44E  3845       MOV R4, [R5++]
4E:A450  2855       MOV R5, [R5]
4E:A452  58F5       MOV [--R15], R5
4E:A454  58F4       MOV [--R15], R4
4E:A456  68F5 78FE  MOV REG[0xF5], #0x78FE
4E:A45A  68F4 0052  MOV REG[0xF4], #0x0052
4E:A45E  1015       ADD R1, R5
4E:A460  1104       ADDC R0, R4
4E:A462  4C11       SL R1, #0x1
4E:A464  5C01       SLOSB R0, #0x1
4E:A466  58F0       MOV [--R15], R0
4E:A468  1F90       POP REG[0x10]
4E:A46A  4D11       SR R1, #0x1
4E:A46C  3801       MOV R0, [R1++]
4E:A46E  2811       MOV R1, [R1]
4E:A470  58F1       MOV [--R15], R1
4E:A472  58F0       MOV [--R15], R0
4E:A474  68F1 6EBA  MOV REG[0xF1], #0x6EBA
4E:A478  68F0 0052  MOV REG[0xF0], #0x0052
4E:A47C  58F1       MOV [--R15], R1
4E:A47E  58F0       MOV [--R15], R0
4E:A480  BD03 438C  SCALL 03:438C
4E:A484  70FF 0018  ADD REG[0xFF], #0x0018
4E:A488  385F       MOV R5, [R15++]
4E:A48A  384F       MOV R4, [R15++]
4E:A48C  383F       MOV R3, [R15++]
4E:A48E  382F       MOV R2, [R15++]
4E:A490  381F       MOV R1, [R15++]
4E:A492  380F       MOV R0, [R15++]
4E:A494  2F00       UNLINK
4E:A496  C620       RETS
