; Reachable DMCU code from v814-live-code-001002.bin
; ISA: King Billion 16-bit DMCU (CN1916884A instruction appendix)
; source file offset: 0x0
; source word byte order: little
; source file word 0 maps to 00:1002
; addresses are byte-addressed CS:PC; words are in CPU numeric order

entry:
00:1002  6810 00A4  MOV REG[0x10], #0x00A4
00:1006  99F0 7A3E  MOVZE REG[0xF0], [0x7A3E]
00:100A  5601       CMP R0, #0x1
00:100C  AC02 56FA  AJMP NZ/NE, 00:56FA
00:1010  68F0 0037  MOV REG[0xF0], #0x0037
00:1014  6A0B FFFC  MOV [R11+0xFFFC], R0
00:1018  480B       MOV R0, #0xB
00:101A  6A0B FFFE  MOV [R11+0xFFFE], R0
00:101E  4805       MOV R0, #0x5
00:1020  58F0       MOV [--R15], R0
00:1022  68F1 5932  MOV REG[0xF1], #0x5932
00:1026  68F0 0030  MOV REG[0xF0], #0x0030
00:102A  58F1       MOV [--R15], R1
00:102C  58F0       MOV [--R15], R0
