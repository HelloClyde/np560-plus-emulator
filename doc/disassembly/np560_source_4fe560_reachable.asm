; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x2FE560
; source word byte order: little
; source file word 0 maps to 4F:E560
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
4F:E560  2E00       LINK #0x00
4F:E562  58F1       MOV [--R15], R1
4F:E564  780B 0006  MOV R0, [R11+0x0006]
4F:E568  781B 0008  MOV R1, [R11+0x0008]
4F:E56C  58F1       MOV [--R15], R1
4F:E56E  58F0       MOV [--R15], R0
4F:E570  BD32 FA06  SCALL 32:FA06
4F:E574  50F4       ADD R15, #0x4
4F:E576  5600       CMP R0, #0x0
4F:E578  AC02 E59A  AJMP NZ/NE, 4F:E59A
4F:E57C  780B 0006  MOV R0, [R11+0x0006]
4F:E580  781B 0008  MOV R1, [R11+0x0008]
4F:E584  58F1       MOV [--R15], R1
4F:E586  58F0       MOV [--R15], R0
4F:E588  BD32 C1A6  SCALL 32:C1A6
4F:E58C  50F4       ADD R15, #0x4
4F:E58E  5600       CMP R0, #0x0
4F:E590  AC02 E59A  AJMP NZ/NE, 4F:E59A
4F:E594  4800       MOV R0, #0x0
4F:E596  AC00 E59C  AJMP ALWAYS, 4F:E59C
loc_4F_E59A:
; xref: 4F:E578, 4F:E590
4F:E59A  4801       MOV R0, #0x1
loc_4F_E59C:
; xref: 4F:E596
4F:E59C  381F       MOV R1, [R15++]
4F:E59E  2F00       UNLINK
4F:E5A0  C620       RETS
