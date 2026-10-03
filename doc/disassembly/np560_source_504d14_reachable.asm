; Reachable DMCU code from NP560.PRG
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x304D14
; source word byte order: little
; source file word 0 maps to 50:4D14
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
50:4D14  2E00       LINK #0x00
50:4D16  58F0       MOV [--R15], R0
50:4D18  780B 0006  MOV R0, [R11+0x0006]
50:4D1C  58F0       MOV [--R15], R0
50:4D1E  BD31 5014  SCALL 31:5014
50:4D22  50F2       ADD R15, #0x2
50:4D24  380F       MOV R0, [R15++]
50:4D26  2F00       UNLINK
50:4D28  C620       RETS
