# NP560+ resident SoC ROM API evidence

- Source listing: `doc/disassembly/NP560_UPD_block1_reachable.asm`
- Parsed instructions: 21,559
- Direct calls into code segment 02: 59
- Distinct resident entry points: 12
- Scope: static call-site evidence only; no original ROM bytes are present.

## Entry-point inventory

| Resident entry | Calls | Calling functions | Immediate R15 cleanup | Evidence status |
|---|---:|---:|---|---|
| `02:BAC4` | 1 | 1 | none immediately | Unclassified |
| `02:BAC8` | 3 | 2 | none immediately | Unclassified |
| `02:BB1E` | 1 | 1 | `0x4` (2 words) | Unclassified |
| `02:BBF6` | 15 | 8 | `0xE` (7 words) | NAND-related hypothesis |
| `02:BCC6` | 9 | 9 | `0xE` (7 words) | NAND-related hypothesis |
| `02:BDD6` | 13 | 8 | `0x2` (1 words) | NAND-related hypothesis |
| `02:BE5C` | 4 | 3 | `0x8` (4 words) | NAND-related hypothesis |
| `02:BF56` | 1 | 1 | `0x8` (4 words) | NAND-related hypothesis |
| `02:C04C` | 5 | 3 | none immediately | NAND-related hypothesis |
| `02:C0D2` | 1 | 1 | `0xA` (5 words) | Unclassified |
| `02:C588` | 4 | 2 | `0x2` (1 words) | Unclassified |
| `02:C5DC` | 2 | 1 | `0xC` (6 words) | Unclassified |

## Interpretation constraints

The contexts below establish the call ABI and surrounding control flow. Names such as read, write, erase, and wait remain hypotheses until a reconstructed routine produces the caller-observed results for all call sites.

## `02:BAC4`

Call sites: `52:36BA`

### `52:36BA` in `sub_52_36AA`

```text
  52:36AA  2E08       LINK #0x08
  52:36AC  58F1       MOV [--R15], R1
  52:36AE  58F2       MOV [--R15], R2
  52:36B0  58F3       MOV [--R15], R3
  52:36B2  58F4       MOV [--R15], R4
  52:36B4  58F5       MOV [--R15], R5
  52:36B6  58F6       MOV [--R15], R6
  52:36B8  58F7       MOV [--R15], R7
> 52:36BA  BD02 BAC4  SCALL 02:BAC4
  52:36BE  BD02 BAC8  SCALL 02:BAC8
  52:36C2  68F1 26CA  MOV REG[0xF1], #0x26CA
```

## `02:BAC8`

Call sites: `52:36BE`, `52:3A5C`, `52:C298`

### `52:36BE` in `sub_52_36AA`

```text
  52:36AC  58F1       MOV [--R15], R1
  52:36AE  58F2       MOV [--R15], R2
  52:36B0  58F3       MOV [--R15], R3
  52:36B2  58F4       MOV [--R15], R4
  52:36B4  58F5       MOV [--R15], R5
  52:36B6  58F6       MOV [--R15], R6
  52:36B8  58F7       MOV [--R15], R7
  52:36BA  BD02 BAC4  SCALL 02:BAC4
> 52:36BE  BD02 BAC8  SCALL 02:BAC8
  52:36C2  68F1 26CA  MOV REG[0xF1], #0x26CA
  52:36C6  68F0 0053  MOV REG[0xF0], #0x0053
```

### `52:3A5C` in `sub_52_36AA`

```text
  52:3A4A  4800       MOV R0, #0x0
  52:3A4C  58F0       MOV [--R15], R0
  52:3A4E  4810       MOV R1, #0x0
  52:3A50  4800       MOV R0, #0x0
  52:3A52  58F1       MOV [--R15], R1
  52:3A54  58F0       MOV [--R15], R0
  52:3A56  BD02 BBF6  SCALL 02:BBF6
  52:3A5A  50FE       ADD R15, #0xE
> 52:3A5C  BD02 BAC8  SCALL 02:BAC8
  52:3A60  780B FFFE  MOV R0, [R11+0xFFFE]
  52:3A64  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:C298` in `sub_52_C23C`

```text
  52:C27A  6810 00A0  MOV REG[0x10], #0x00A0
  52:C27E  88F0 07EE  MOV REG[0xF0], [0x07EE]
  52:C282  6810 00A0  MOV REG[0x10], #0x00A0
  52:C286  96F0 0836  CMP REG[0xF0], [0x0836]
  52:C28A  AC05 C298  AJMP C/UL, 52:C298
  52:C28E  BD53 293C  SCALL 53:293C
  52:C292  4800       MOV R0, #0x0
  52:C294  AC00 C4C0  AJMP ALWAYS, 52:C4C0
> 52:C298  BD02 BAC8  SCALL 02:BAC8
  52:C29C  4800       MOV R0, #0x0
  52:C29E  6A0B FFFE  MOV [R11+0xFFFE], R0
```

## `02:BB1E`

Call sites: `52:36CE`

### `52:36CE` in `sub_52_36AA`

```text
  52:36B6  58F6       MOV [--R15], R6
  52:36B8  58F7       MOV [--R15], R7
  52:36BA  BD02 BAC4  SCALL 02:BAC4
  52:36BE  BD02 BAC8  SCALL 02:BAC8
  52:36C2  68F1 26CA  MOV REG[0xF1], #0x26CA
  52:36C6  68F0 0053  MOV REG[0xF0], #0x0053
  52:36CA  58F1       MOV [--R15], R1
  52:36CC  58F0       MOV [--R15], R0
> 52:36CE  BD02 BB1E  SCALL 02:BB1E
  52:36D2  50F4       ADD R15, #0x4
  52:36D4  6A0B FFF8  MOV [R11+0xFFF8], R0
```

## `02:BBF6`

Strong NAND page/spare transfer candidate. Calls in `sub_51_0000` supply a page-like address, `50:0760` buffer, and `0x0040`, then remove seven stack words.

Call sites: `52:3A56`, `52:44C4`, `52:45D0`, `52:7B3C`, `52:7BAE`, `52:7C30`, `52:83CA`, `52:8C30`, `52:8D8C`, `52:9C42`, `52:9CC0`, `52:A618`, `52:BA4C`, `52:BABE`, `52:BB38`

### `52:3A56` in `sub_52_36AA`

```text
  52:3A46  58F1       MOV [--R15], R1
  52:3A48  58F0       MOV [--R15], R0
  52:3A4A  4800       MOV R0, #0x0
  52:3A4C  58F0       MOV [--R15], R0
  52:3A4E  4810       MOV R1, #0x0
  52:3A50  4800       MOV R0, #0x0
  52:3A52  58F1       MOV [--R15], R1
  52:3A54  58F0       MOV [--R15], R0
> 52:3A56  BD02 BBF6  SCALL 02:BBF6
  52:3A5A  50FE       ADD R15, #0xE
  52:3A5C  BD02 BAC8  SCALL 02:BAC8
```

### `52:44C4` in `sub_52_43C0`

```text
  52:44B2  1C23       SLOSB R2, RB3
  52:44B4  781B 000A  MOV R1, [R11+0x000A]
  52:44B8  0851       MOV R5, R1
  52:44BA  4840       MOV R4, #0x0
  52:44BC  1035       ADD R3, R5
  52:44BE  1124       ADDC R2, R4
  52:44C0  58F3       MOV [--R15], R3
  52:44C2  58F2       MOV [--R15], R2
> 52:44C4  BD02 BBF6  SCALL 02:BBF6
  52:44C8  50FE       ADD R15, #0xE
  52:44CA  781B FFEA  MOV R1, [R11+0xFFEA]
```

### `52:45D0` in `sub_52_43C0`

```text
  52:45BE  1C23       SLOSB R2, RB3
  52:45C0  781B 000A  MOV R1, [R11+0x000A]
  52:45C4  0851       MOV R5, R1
  52:45C6  4840       MOV R4, #0x0
  52:45C8  1035       ADD R3, R5
  52:45CA  1124       ADDC R2, R4
  52:45CC  58F3       MOV [--R15], R3
  52:45CE  58F2       MOV [--R15], R2
> 52:45D0  BD02 BBF6  SCALL 02:BBF6
  52:45D4  50FE       ADD R15, #0xE
  52:45D6  781B FFEA  MOV R1, [R11+0xFFEA]
```

### `52:7B3C` in `sub_52_7A8C`

```text
  52:7B24  58F0       MOV [--R15], R0
  52:7B26  6810 00A0  MOV REG[0x10], #0x00A0
  52:7B2A  88F0 0830  MOV REG[0xF0], [0x0830]
  52:7B2E  58F0       MOV [--R15], R0
  52:7B30  780B FFEE  MOV R0, [R11+0xFFEE]
  52:7B34  781B FFF0  MOV R1, [R11+0xFFF0]
  52:7B38  58F1       MOV [--R15], R1
  52:7B3A  58F0       MOV [--R15], R0
> 52:7B3C  BD02 BBF6  SCALL 02:BBF6
  52:7B40  50FE       ADD R15, #0xE
  52:7B42  780B FFEC  MOV R0, [R11+0xFFEC]
```

### `52:7BAE` in `sub_52_7A8C`

```text
  52:7B98  88F0 0830  MOV REG[0xF0], [0x0830]
  52:7B9C  58F0       MOV [--R15], R0
  52:7B9E  780B FFEE  MOV R0, [R11+0xFFEE]
  52:7BA2  781B FFF0  MOV R1, [R11+0xFFF0]
  52:7BA6  5011       ADD R1, #0x1
  52:7BA8  5100       ADDC R0, #0x0
  52:7BAA  58F1       MOV [--R15], R1
  52:7BAC  58F0       MOV [--R15], R0
> 52:7BAE  BD02 BBF6  SCALL 02:BBF6
  52:7BB2  50FE       ADD R15, #0xE
  52:7BB4  780B FFEC  MOV R0, [R11+0xFFEC]
```

### `52:7C30` in `sub_52_7A8C`

```text
  52:7C18  88F0 0830  MOV REG[0xF0], [0x0830]
  52:7C1C  58F0       MOV [--R15], R0
  52:7C1E  780B FFEE  MOV R0, [R11+0xFFEE]
  52:7C22  781B FFF0  MOV R1, [R11+0xFFF0]
  52:7C26  70F1 003F  ADD REG[0xF1], #0x003F
  52:7C2A  5100       ADDC R0, #0x0
  52:7C2C  58F1       MOV [--R15], R1
  52:7C2E  58F0       MOV [--R15], R0
> 52:7C30  BD02 BBF6  SCALL 02:BBF6
  52:7C34  50FE       ADD R15, #0xE
  52:7C36  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:83CA` in `sub_52_8332`

```text
  52:83B8  58F1       MOV [--R15], R1
  52:83BA  58F0       MOV [--R15], R0
  52:83BC  4800       MOV R0, #0x0
  52:83BE  58F0       MOV [--R15], R0
  52:83C0  68F1 003F  MOV REG[0xF1], #0x003F
  52:83C4  4800       MOV R0, #0x0
  52:83C6  58F1       MOV [--R15], R1
  52:83C8  58F0       MOV [--R15], R0
> 52:83CA  BD02 BBF6  SCALL 02:BBF6
  52:83CE  50FE       ADD R15, #0xE
  52:83D0  4800       MOV R0, #0x0
```

### `52:8C30` in `sub_52_8B76`

```text
  52:8C18  58F0       MOV [--R15], R0
  52:8C1A  6810 00A0  MOV REG[0x10], #0x00A0
  52:8C1E  88F0 0830  MOV REG[0xF0], [0x0830]
  52:8C22  58F0       MOV [--R15], R0
  52:8C24  780B FFF6  MOV R0, [R11+0xFFF6]
  52:8C28  781B FFF8  MOV R1, [R11+0xFFF8]
  52:8C2C  58F1       MOV [--R15], R1
  52:8C2E  58F0       MOV [--R15], R0
> 52:8C30  BD02 BBF6  SCALL 02:BBF6
  52:8C34  50FE       ADD R15, #0xE
  52:8C36  791B 000A  MOVB RB1, [R11+0x000A]
```

### `52:8D8C` in `sub_52_8B76`

```text
  52:8D74  58F0       MOV [--R15], R0
  52:8D76  6810 00A0  MOV REG[0x10], #0x00A0
  52:8D7A  88F0 0830  MOV REG[0xF0], [0x0830]
  52:8D7E  58F0       MOV [--R15], R0
  52:8D80  780B FFF6  MOV R0, [R11+0xFFF6]
  52:8D84  781B FFF8  MOV R1, [R11+0xFFF8]
  52:8D88  58F1       MOV [--R15], R1
  52:8D8A  58F0       MOV [--R15], R0
> 52:8D8C  BD02 BBF6  SCALL 02:BBF6
  52:8D90  50FE       ADD R15, #0xE
  52:8D92  4801       MOV R0, #0x1
```

### `52:9C42` in `sub_52_99DE`

```text
  52:9C2E  58F1       MOV [--R15], R1
  52:9C30  58F0       MOV [--R15], R0
  52:9C32  4800       MOV R0, #0x0
  52:9C34  58F0       MOV [--R15], R0
  52:9C36  780B FFF8  MOV R0, [R11+0xFFF8]
  52:9C3A  781B FFFA  MOV R1, [R11+0xFFFA]
  52:9C3E  58F1       MOV [--R15], R1
  52:9C40  58F0       MOV [--R15], R0
> 52:9C42  BD02 BBF6  SCALL 02:BBF6
  52:9C46  50FE       ADD R15, #0xE
  52:9C48  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:9CC0` in `sub_52_99DE`

```text
  52:9CAC  58F1       MOV [--R15], R1
  52:9CAE  58F0       MOV [--R15], R0
  52:9CB0  4800       MOV R0, #0x0
  52:9CB2  58F0       MOV [--R15], R0
  52:9CB4  780B FFF4  MOV R0, [R11+0xFFF4]
  52:9CB8  781B FFF6  MOV R1, [R11+0xFFF6]
  52:9CBC  58F1       MOV [--R15], R1
  52:9CBE  58F0       MOV [--R15], R0
> 52:9CC0  BD02 BBF6  SCALL 02:BBF6
  52:9CC4  50FE       ADD R15, #0xE
  52:9CC6  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:A618` in `sub_52_A3FA`

```text
  52:A606  1C07       SLOSB R0, RB7
  52:A608  783B 0006  MOV R3, [R11+0x0006]
  52:A60C  4D38       SR R3, #0x8
  52:A60E  4820       MOV R2, #0x0
  52:A610  1013       ADD R1, R3
  52:A612  1102       ADDC R0, R2
  52:A614  58F1       MOV [--R15], R1
  52:A616  58F0       MOV [--R15], R0
> 52:A618  BD02 BBF6  SCALL 02:BBF6
  52:A61C  50FE       ADD R15, #0xE
  52:A61E  68F1 023C  MOV REG[0xF1], #0x023C
```

### `52:BA4C` in `sub_52_B9A2`

```text
  52:BA34  58F0       MOV [--R15], R0
  52:BA36  6810 00A0  MOV REG[0x10], #0x00A0
  52:BA3A  88F0 0830  MOV REG[0xF0], [0x0830]
  52:BA3E  58F0       MOV [--R15], R0
  52:BA40  780B FFF6  MOV R0, [R11+0xFFF6]
  52:BA44  781B FFF8  MOV R1, [R11+0xFFF8]
  52:BA48  58F1       MOV [--R15], R1
  52:BA4A  58F0       MOV [--R15], R0
> 52:BA4C  BD02 BBF6  SCALL 02:BBF6
  52:BA50  50FE       ADD R15, #0xE
  52:BA52  780B FFF2  MOV R0, [R11+0xFFF2]
```

### `52:BABE` in `sub_52_B9A2`

```text
  52:BAA8  88F0 0830  MOV REG[0xF0], [0x0830]
  52:BAAC  58F0       MOV [--R15], R0
  52:BAAE  780B FFF6  MOV R0, [R11+0xFFF6]
  52:BAB2  781B FFF8  MOV R1, [R11+0xFFF8]
  52:BAB6  5011       ADD R1, #0x1
  52:BAB8  5100       ADDC R0, #0x0
  52:BABA  58F1       MOV [--R15], R1
  52:BABC  58F0       MOV [--R15], R0
> 52:BABE  BD02 BBF6  SCALL 02:BBF6
  52:BAC2  50FE       ADD R15, #0xE
  52:BAC4  780B FFF2  MOV R0, [R11+0xFFF2]
```

### `52:BB38` in `sub_52_B9A2`

```text
  52:BB20  88F0 0830  MOV REG[0xF0], [0x0830]
  52:BB24  58F0       MOV [--R15], R0
  52:BB26  780B FFF6  MOV R0, [R11+0xFFF6]
  52:BB2A  781B FFF8  MOV R1, [R11+0xFFF8]
  52:BB2E  70F1 003F  ADD REG[0xF1], #0x003F
  52:BB32  5100       ADDC R0, #0x0
  52:BB34  58F1       MOV [--R15], R1
  52:BB36  58F0       MOV [--R15], R0
> 52:BB38  BD02 BBF6  SCALL 02:BBF6
  52:BB3C  50FE       ADD R15, #0xE
  52:BB3E  6810 00A0  MOV REG[0x10], #0x00A0
```

## `02:BCC6`

NAND transfer variant candidate. Its exact direction and spare-area contract remain unproven.

Call sites: `52:18D0`, `52:486E`, `52:873A`, `52:8D18`, `52:9AC4`, `52:A536`, `52:B3A4`, `52:C3FA`, `52:FCBA`

### `52:18D0` in `sub_52_1232`

```text
  52:18BE  DE03       RJMP SGE, 52:18C6 ; rel +3
  52:18C0  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  52:18C4  D001       RJMP ALWAYS, 52:18C8 ; rel +1
  52:18C6  4800       MOV R0, #0x0
  52:18C8  1031       ADD R3, R1
  52:18CA  1120       ADDC R2, R0
  52:18CC  58F3       MOV [--R15], R3
  52:18CE  58F2       MOV [--R15], R2
> 52:18D0  BD02 BCC6  SCALL 02:BCC6
  52:18D4  50FE       ADD R15, #0xE
  52:18D6  781B FFF8  MOV R1, [R11+0xFFF8]
```

### `52:486E` in `sub_52_43C0`

```text
  52:485C  0C17       SL R1, RB7
  52:485E  1C07       SLOSB R0, RB7
  52:4860  783B 000A  MOV R3, [R11+0x000A]
  52:4864  4820       MOV R2, #0x0
  52:4866  1013       ADD R1, R3
  52:4868  1102       ADDC R0, R2
  52:486A  58F1       MOV [--R15], R1
  52:486C  58F0       MOV [--R15], R0
> 52:486E  BD02 BCC6  SCALL 02:BCC6
  52:4872  50FE       ADD R15, #0xE
  52:4874  6A0B FFF8  MOV [R11+0xFFF8], R0
```

### `52:873A` in `sub_52_8332`

```text
  52:8728  58F1       MOV [--R15], R1
  52:872A  58F0       MOV [--R15], R0
  52:872C  4800       MOV R0, #0x0
  52:872E  58F0       MOV [--R15], R0
  52:8730  68F1 003F  MOV REG[0xF1], #0x003F
  52:8734  4800       MOV R0, #0x0
  52:8736  58F1       MOV [--R15], R1
  52:8738  58F0       MOV [--R15], R0
> 52:873A  BD02 BCC6  SCALL 02:BCC6
  52:873E  50FE       ADD R15, #0xE
  52:8740  5600       CMP R0, #0x0
```

### `52:8D18` in `sub_52_8B76`

```text
  52:8D04  58F1       MOV [--R15], R1
  52:8D06  58F0       MOV [--R15], R0
  52:8D08  4800       MOV R0, #0x0
  52:8D0A  58F0       MOV [--R15], R0
  52:8D0C  780B FFF6  MOV R0, [R11+0xFFF6]
  52:8D10  781B FFF8  MOV R1, [R11+0xFFF8]
  52:8D14  58F1       MOV [--R15], R1
  52:8D16  58F0       MOV [--R15], R0
> 52:8D18  BD02 BCC6  SCALL 02:BCC6
  52:8D1C  50FE       ADD R15, #0xE
  52:8D1E  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:9AC4` in `sub_52_99DE`

```text
  52:9AB0  58F1       MOV [--R15], R1
  52:9AB2  58F0       MOV [--R15], R0
  52:9AB4  4800       MOV R0, #0x0
  52:9AB6  58F0       MOV [--R15], R0
  52:9AB8  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9ABC  781B FFFE  MOV R1, [R11+0xFFFE]
  52:9AC0  58F1       MOV [--R15], R1
  52:9AC2  58F0       MOV [--R15], R0
> 52:9AC4  BD02 BCC6  SCALL 02:BCC6
  52:9AC8  50FE       ADD R15, #0xE
  52:9ACA  5600       CMP R0, #0x0
```

### `52:A536` in `sub_52_A3FA`

```text
  52:A524  0C17       SL R1, RB7
  52:A526  1C07       SLOSB R0, RB7
  52:A528  783B FFFA  MOV R3, [R11+0xFFFA]
  52:A52C  4820       MOV R2, #0x0
  52:A52E  1013       ADD R1, R3
  52:A530  1102       ADDC R0, R2
  52:A532  58F1       MOV [--R15], R1
  52:A534  58F0       MOV [--R15], R0
> 52:A536  BD02 BCC6  SCALL 02:BCC6
  52:A53A  50FE       ADD R15, #0xE
  52:A53C  6A0B FFFE  MOV [R11+0xFFFE], R0
```

### `52:B3A4` in `sub_52_B0B0`

```text
  52:B392  58F1       MOV [--R15], R1
  52:B394  58F0       MOV [--R15], R0
  52:B396  4800       MOV R0, #0x0
  52:B398  58F0       MOV [--R15], R0
  52:B39A  68F1 003F  MOV REG[0xF1], #0x003F
  52:B39E  4800       MOV R0, #0x0
  52:B3A0  58F1       MOV [--R15], R1
  52:B3A2  58F0       MOV [--R15], R0
> 52:B3A4  BD02 BCC6  SCALL 02:BCC6
  52:B3A8  50FE       ADD R15, #0xE
  52:B3AA  4800       MOV R0, #0x0
```

### `52:C3FA` in `sub_52_C23C`

```text
  52:C3E6  1C07       SLOSB R0, RB7
  52:C3E8  6810 00A0  MOV REG[0x10], #0x00A0
  52:C3EC  88F3 07F0  MOV REG[0xF3], [0x07F0]
  52:C3F0  4820       MOV R2, #0x0
  52:C3F2  1013       ADD R1, R3
  52:C3F4  1102       ADDC R0, R2
  52:C3F6  58F1       MOV [--R15], R1
  52:C3F8  58F0       MOV [--R15], R0
> 52:C3FA  BD02 BCC6  SCALL 02:BCC6
  52:C3FE  50FE       ADD R15, #0xE
  52:C400  6A0B FFFE  MOV [R11+0xFFFE], R0
```

### `52:FCBA` in `sub_52_FBFA`

```text
  52:FCA6  1C07       SLOSB R0, RB7
  52:FCA8  6810 00A0  MOV REG[0x10], #0x00A0
  52:FCAC  88F3 07F0  MOV REG[0xF3], [0x07F0]
  52:FCB0  4820       MOV R2, #0x0
  52:FCB2  1013       ADD R1, R3
  52:FCB4  1102       ADDC R0, R2
  52:FCB6  58F1       MOV [--R15], R1
  52:FCB8  58F0       MOV [--R15], R0
> 52:FCBA  BD02 BCC6  SCALL 02:BCC6
  52:FCBE  50FE       ADD R15, #0xE
  52:FCC0  6A0B FFFA  MOV [R11+0xFFFA], R0
```

## `02:BDD6`

NAND follow-up/status candidate. It repeatedly follows transfer paths and its return value is checked by the caller.

Call sites: `52:14AE`, `52:1586`, `52:176A`, `52:85E4`, `52:8614`, `52:8C50`, `52:952E`, `52:9890`, `52:9A84`, `52:9B38`, `52:9B8C`, `52:B0CC`, `52:E3B6`

### `52:14AE` in `sub_52_1232`

```text
  52:1490  6810 00A0  MOV REG[0x10], #0x00A0
  52:1494  B0F1 07C0  ADD [0x07C0], REG[0xF1]
  52:1498  781B FFF0  MOV R1, [R11+0xFFF0]
  52:149C  6810 00A0  MOV REG[0x10], #0x00A0
  52:14A0  96F1 0836  CMP REG[0xF1], [0x0836]
  52:14A4  AC0C 14D4  AJMP ULE, 52:14D4
  52:14A8  781B FFF6  MOV R1, [R11+0xFFF6]
  52:14AC  58F1       MOV [--R15], R1
> 52:14AE  BD02 BDD6  SCALL 02:BDD6
  52:14B2  50F2       ADD R15, #0x2
  52:14B4  5600       CMP R0, #0x0
```

### `52:1586` in `sub_52_1232`

```text
  52:156E  4D11       SR R1, #0x1
  52:1570  0A12       MOV [R1], R2
  52:1572  AC00 169E  AJMP ALWAYS, 52:169E
  52:1576  782B FFFA  MOV R2, [R11+0xFFFA]
  52:157A  5620       CMP R2, #0x0
  52:157C  AC02 15AC  AJMP NZ/NE, 52:15AC
  52:1580  782B FFF6  MOV R2, [R11+0xFFF6]
  52:1584  58F2       MOV [--R15], R2
> 52:1586  BD02 BDD6  SCALL 02:BDD6
  52:158A  50F2       ADD R15, #0x2
  52:158C  5600       CMP R0, #0x0
```

### `52:176A` in `sub_52_1232`

```text
  52:1758  4C11       SL R1, #0x1
  52:175A  5C01       SLOSB R0, #0x1
  52:175C  58F0       MOV [--R15], R0
  52:175E  1F90       POP REG[0x10]
  52:1760  4D11       SR R1, #0x1
  52:1762  0A12       MOV [R1], R2
  52:1764  782B FFF6  MOV R2, [R11+0xFFF6]
  52:1768  58F2       MOV [--R15], R2
> 52:176A  BD02 BDD6  SCALL 02:BDD6
  52:176E  50F2       ADD R15, #0x2
  52:1770  5600       CMP R0, #0x0
```

### `52:85E4` in `sub_52_8332`

```text
  52:85D0  58F0       MOV [--R15], R0
  52:85D2  781B FFEC  MOV R1, [R11+0xFFEC]
  52:85D6  58F1       MOV [--R15], R1
  52:85D8  58F0       MOV [--R15], R0
  52:85DA  BD52 E12A  SCALL 52:E12A
  52:85DE  50F8       ADD R15, #0x8
  52:85E0  4800       MOV R0, #0x0
  52:85E2  58F0       MOV [--R15], R0
> 52:85E4  BD02 BDD6  SCALL 02:BDD6
  52:85E8  50F2       ADD R15, #0x2
  52:85EA  5600       CMP R0, #0x0
```

### `52:8614` in `sub_52_8332`

```text
  52:85FE  58F0       MOV [--R15], R0
  52:8600  58F0       MOV [--R15], R0
  52:8602  780B FFEC  MOV R0, [R11+0xFFEC]
  52:8606  58F0       MOV [--R15], R0
  52:8608  BD52 E12A  SCALL 52:E12A
  52:860C  50F8       ADD R15, #0x8
  52:860E  780B FFEC  MOV R0, [R11+0xFFEC]
  52:8612  58F0       MOV [--R15], R0
> 52:8614  BD02 BDD6  SCALL 02:BDD6
  52:8618  50F2       ADD R15, #0x2
  52:861A  5600       CMP R0, #0x0
```

### `52:8C50` in `sub_52_8B76`

```text
  52:8C36  791B 000A  MOVB RB1, [R11+0x000A]
  52:8C3A  1901       MOVZE R0, RB1
  52:8C3C  5600       CMP R0, #0x0
  52:8C3E  AC01 8C4A  AJMP Z/EQ, 52:8C4A
  52:8C42  76F0 0011  CMP REG[0xF0], #0x0011
  52:8C46  AC02 8E08  AJMP NZ/NE, 52:8E08
  52:8C4A  780B 0006  MOV R0, [R11+0x0006]
  52:8C4E  58F0       MOV [--R15], R0
> 52:8C50  BD02 BDD6  SCALL 02:BDD6
  52:8C54  50F2       ADD R15, #0x2
  52:8C56  5600       CMP R0, #0x0
```

### `52:952E` in `sub_52_9318`

```text
  52:9514  50F2       ADD R15, #0x2
  52:9516  1901       MOVZE R0, RB1
  52:9518  6A0B FFFC  MOV [R11+0xFFFC], R0
  52:951C  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9520  76F0 0011  CMP REG[0xF0], #0x0011
  52:9524  AC02 9552  AJMP NZ/NE, 52:9552
  52:9528  780B FFFE  MOV R0, [R11+0xFFFE]
  52:952C  58F0       MOV [--R15], R0
> 52:952E  BD02 BDD6  SCALL 02:BDD6
  52:9532  50F2       ADD R15, #0x2
  52:9534  5600       CMP R0, #0x0
```

### `52:9890` in `sub_52_967C`

```text
  52:9876  50F2       ADD R15, #0x2
  52:9878  1901       MOVZE R0, RB1
  52:987A  6A0B FFFC  MOV [R11+0xFFFC], R0
  52:987E  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9882  76F0 0011  CMP REG[0xF0], #0x0011
  52:9886  AC02 98B4  AJMP NZ/NE, 52:98B4
  52:988A  780B FFFE  MOV R0, [R11+0xFFFE]
  52:988E  58F0       MOV [--R15], R0
> 52:9890  BD02 BDD6  SCALL 02:BDD6
  52:9894  50F2       ADD R15, #0x2
  52:9896  5600       CMP R0, #0x0
```

### `52:9A84` in `sub_52_99DE`

```text
  52:9A72  58F3       MOV [--R15], R3
  52:9A74  58F2       MOV [--R15], R2
  52:9A76  58F1       MOV [--R15], R1
  52:9A78  58F0       MOV [--R15], R0
  52:9A7A  BD53 2D20  SCALL 53:2D20
  52:9A7E  50F8       ADD R15, #0x8
  52:9A80  0801       MOV R0, R1
  52:9A82  58F0       MOV [--R15], R0
> 52:9A84  BD02 BDD6  SCALL 02:BDD6
  52:9A88  50F2       ADD R15, #0x2
  52:9A8A  5600       CMP R0, #0x0
```

### `52:9B38` in `sub_52_99DE`

```text
  52:9B26  58F3       MOV [--R15], R3
  52:9B28  58F2       MOV [--R15], R2
  52:9B2A  58F1       MOV [--R15], R1
  52:9B2C  58F0       MOV [--R15], R0
  52:9B2E  BD53 2D20  SCALL 53:2D20
  52:9B32  50F8       ADD R15, #0x8
  52:9B34  0801       MOV R0, R1
  52:9B36  58F0       MOV [--R15], R0
> 52:9B38  BD02 BDD6  SCALL 02:BDD6
  52:9B3C  50F2       ADD R15, #0x2
  52:9B3E  5600       CMP R0, #0x0
```

### `52:9B8C` in `sub_52_99DE`

```text
  52:9B7A  58F3       MOV [--R15], R3
  52:9B7C  58F2       MOV [--R15], R2
  52:9B7E  58F1       MOV [--R15], R1
  52:9B80  58F0       MOV [--R15], R0
  52:9B82  BD53 2D20  SCALL 53:2D20
  52:9B86  50F8       ADD R15, #0x8
  52:9B88  0801       MOV R0, R1
  52:9B8A  58F0       MOV [--R15], R0
> 52:9B8C  BD02 BDD6  SCALL 02:BDD6
  52:9B90  50F2       ADD R15, #0x2
  52:9B92  5600       CMP R0, #0x0
```

### `52:B0CC` in `sub_52_B0B0`

```text
  52:B0B4  58F2       MOV [--R15], R2
  52:B0B6  58F3       MOV [--R15], R3
  52:B0B8  68F1 003C  MOV REG[0xF1], #0x003C
  52:B0BC  68F0 0050  MOV REG[0xF0], #0x0050
  52:B0C0  6A0B FFFC  MOV [R11+0xFFFC], R0
  52:B0C4  6A1B FFFE  MOV [R11+0xFFFE], R1
  52:B0C8  4800       MOV R0, #0x0
  52:B0CA  58F0       MOV [--R15], R0
> 52:B0CC  BD02 BDD6  SCALL 02:BDD6
  52:B0D0  50F2       ADD R15, #0x2
  52:B0D2  6810 00A0  MOV REG[0x10], #0x00A0
```

### `52:E3B6` in `sub_52_E2FE`

```text
  52:E39A  AC01 E3A2  AJMP Z/EQ, 52:E3A2
  52:E39E  AC00 E3B0  AJMP ALWAYS, 52:E3B0
  52:E3A2  4801       MOV R0, #0x1
  52:E3A4  6810 00A0  MOV REG[0x10], #0x00A0
  52:E3A8  B0F0 07CC  ADD [0x07CC], REG[0xF0]
  52:E3AC  AC00 E42C  AJMP ALWAYS, 52:E42C
  52:E3B0  780B FFFE  MOV R0, [R11+0xFFFE]
  52:E3B4  58F0       MOV [--R15], R0
> 52:E3B6  BD02 BDD6  SCALL 02:BDD6
  52:E3BA  50F2       ADD R15, #0x2
  52:E3BC  5600       CMP R0, #0x0
```

## `02:BE5C`

Asynchronous NAND operation variant. Callers pair it immediately with `02:C04C`.

Call sites: `52:9BDE`, `52:9C00`, `52:E2AE`, `53:1770`

### `52:9BDE` in `sub_52_99DE`

```text
  52:9BC6  780B FFF8  MOV R0, [R11+0xFFF8]
  52:9BCA  781B FFFA  MOV R1, [R11+0xFFFA]
  52:9BCE  58F1       MOV [--R15], R1
  52:9BD0  58F0       MOV [--R15], R0
  52:9BD2  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9BD6  781B FFFE  MOV R1, [R11+0xFFFE]
  52:9BDA  58F1       MOV [--R15], R1
  52:9BDC  58F0       MOV [--R15], R0
> 52:9BDE  BD02 BE5C  SCALL 02:BE5C
  52:9BE2  50F8       ADD R15, #0x8
  52:9BE4  BD02 C04C  SCALL 02:C04C
```

### `52:9C00` in `sub_52_99DE`

```text
  52:9BE8  780B FFF4  MOV R0, [R11+0xFFF4]
  52:9BEC  781B FFF6  MOV R1, [R11+0xFFF6]
  52:9BF0  58F1       MOV [--R15], R1
  52:9BF2  58F0       MOV [--R15], R0
  52:9BF4  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9BF8  781B FFFE  MOV R1, [R11+0xFFFE]
  52:9BFC  58F1       MOV [--R15], R1
  52:9BFE  58F0       MOV [--R15], R0
> 52:9C00  BD02 BE5C  SCALL 02:BE5C
  52:9C04  50F8       ADD R15, #0x8
  52:9C06  BD02 C04C  SCALL 02:C04C
```

### `52:E2AE` in `sub_52_E12A`

```text
  52:E29A  58F3       MOV [--R15], R3
  52:E29C  58F2       MOV [--R15], R2
  52:E29E  782B FFF4  MOV R2, [R11+0xFFF4]
  52:E2A2  783B FFF6  MOV R3, [R11+0xFFF6]
  52:E2A6  1031       ADD R3, R1
  52:E2A8  1120       ADDC R2, R0
  52:E2AA  58F3       MOV [--R15], R3
  52:E2AC  58F2       MOV [--R15], R2
> 52:E2AE  BD02 BE5C  SCALL 02:BE5C
  52:E2B2  50F8       ADD R15, #0x8
  52:E2B4  BD02 C04C  SCALL 02:C04C
```

### `53:1770` in `sub_53_16F4`

```text
  53:175C  6810 00A0  MOV REG[0x10], #0x00A0
  53:1760  88F3 07B0  MOV REG[0xF3], [0x07B0]
  53:1764  0C27       SL R2, RB7
  53:1766  1020       ADD R2, R0
  53:1768  0812       MOV R1, R2
  53:176A  4800       MOV R0, #0x0
  53:176C  58F1       MOV [--R15], R1
  53:176E  58F0       MOV [--R15], R0
> 53:1770  BD02 BE5C  SCALL 02:BE5C
  53:1774  50F8       ADD R15, #0x8
  53:1776  4801       MOV R0, #0x1
```

## `02:BF56`

Second asynchronous NAND operation variant, selected for device ID `0x76` and paired immediately with `02:C04C`.

Call sites: `52:E24A`

### `52:E24A` in `sub_52_E12A`

```text
  52:E236  58F3       MOV [--R15], R3
  52:E238  58F2       MOV [--R15], R2
  52:E23A  782B FFF4  MOV R2, [R11+0xFFF4]
  52:E23E  783B FFF6  MOV R3, [R11+0xFFF6]
  52:E242  1031       ADD R3, R1
  52:E244  1120       ADDC R2, R0
  52:E246  58F3       MOV [--R15], R3
  52:E248  58F2       MOV [--R15], R2
> 52:E24A  BD02 BF56  SCALL 02:BF56
  52:E24E  50F8       ADD R15, #0x8
  52:E250  BD02 C04C  SCALL 02:C04C
```

## `02:C04C`

Completion/status routine candidate. It follows `02:BE5C` or `02:BF56`, and callers branch on R0.

Call sites: `52:9BE4`, `52:9C06`, `52:E250`, `52:E2B4`, `53:179C`

### `52:9BE4` in `sub_52_99DE`

```text
  52:9BCE  58F1       MOV [--R15], R1
  52:9BD0  58F0       MOV [--R15], R0
  52:9BD2  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9BD6  781B FFFE  MOV R1, [R11+0xFFFE]
  52:9BDA  58F1       MOV [--R15], R1
  52:9BDC  58F0       MOV [--R15], R0
  52:9BDE  BD02 BE5C  SCALL 02:BE5C
  52:9BE2  50F8       ADD R15, #0x8
> 52:9BE4  BD02 C04C  SCALL 02:C04C
  52:9BE8  780B FFF4  MOV R0, [R11+0xFFF4]
  52:9BEC  781B FFF6  MOV R1, [R11+0xFFF6]
```

### `52:9C06` in `sub_52_99DE`

```text
  52:9BF0  58F1       MOV [--R15], R1
  52:9BF2  58F0       MOV [--R15], R0
  52:9BF4  780B FFFC  MOV R0, [R11+0xFFFC]
  52:9BF8  781B FFFE  MOV R1, [R11+0xFFFE]
  52:9BFC  58F1       MOV [--R15], R1
  52:9BFE  58F0       MOV [--R15], R0
  52:9C00  BD02 BE5C  SCALL 02:BE5C
  52:9C04  50F8       ADD R15, #0x8
> 52:9C06  BD02 C04C  SCALL 02:C04C
  52:9C0A  4800       MOV R0, #0x0
  52:9C0C  58F0       MOV [--R15], R0
```

### `52:E250` in `sub_52_E12A`

```text
  52:E23A  782B FFF4  MOV R2, [R11+0xFFF4]
  52:E23E  783B FFF6  MOV R3, [R11+0xFFF6]
  52:E242  1031       ADD R3, R1
  52:E244  1120       ADDC R2, R0
  52:E246  58F3       MOV [--R15], R3
  52:E248  58F2       MOV [--R15], R2
  52:E24A  BD02 BF56  SCALL 02:BF56
  52:E24E  50F8       ADD R15, #0x8
> 52:E250  BD02 C04C  SCALL 02:C04C
  52:E254  6A0B FFFC  MOV [R11+0xFFFC], R0
  52:E258  5600       CMP R0, #0x0
```

### `52:E2B4` in `sub_52_E12A`

```text
  52:E29E  782B FFF4  MOV R2, [R11+0xFFF4]
  52:E2A2  783B FFF6  MOV R3, [R11+0xFFF6]
  52:E2A6  1031       ADD R3, R1
  52:E2A8  1120       ADDC R2, R0
  52:E2AA  58F3       MOV [--R15], R3
  52:E2AC  58F2       MOV [--R15], R2
  52:E2AE  BD02 BE5C  SCALL 02:BE5C
  52:E2B2  50F8       ADD R15, #0x8
> 52:E2B4  BD02 C04C  SCALL 02:C04C
  52:E2B8  6A0B FFFC  MOV [R11+0xFFFC], R0
  52:E2BC  5600       CMP R0, #0x0
```

### `53:179C` in `sub_53_16F4`

```text
  53:1784  68F0 0040  MOV REG[0xF0], #0x0040
  53:1788  58F0       MOV [--R15], R0
  53:178A  68F1 0746  MOV REG[0xF1], #0x0746
  53:178E  68F0 0050  MOV REG[0xF0], #0x0050
  53:1792  58F1       MOV [--R15], R1
  53:1794  58F0       MOV [--R15], R0
  53:1796  BD02 C0D2  SCALL 02:C0D2
  53:179A  50FA       ADD R15, #0xA
> 53:179C  BD02 C04C  SCALL 02:C04C
  53:17A0  6A0B FFFC  MOV [R11+0xFFFC], R0
  53:17A4  780B 000A  MOV R0, [R11+0x000A]
```

## `02:C0D2`

Call sites: `53:1796`

### `53:1796` in `sub_53_16F4`

```text
  53:177E  88F0 0830  MOV REG[0xF0], [0x0830]
  53:1782  58F0       MOV [--R15], R0
  53:1784  68F0 0040  MOV REG[0xF0], #0x0040
  53:1788  58F0       MOV [--R15], R0
  53:178A  68F1 0746  MOV REG[0xF1], #0x0746
  53:178E  68F0 0050  MOV REG[0xF0], #0x0050
  53:1792  58F1       MOV [--R15], R1
  53:1794  58F0       MOV [--R15], R0
> 53:1796  BD02 C0D2  SCALL 02:C0D2
  53:179A  50FA       ADD R15, #0xA
  53:179C  BD02 C04C  SCALL 02:C04C
```

## `02:C588`

Call sites: `52:3A12`, `52:3A1E`, `52:FF40`, `52:FF96`

### `52:3A12` in `sub_52_36AA`

```text
  52:39F4  68F0 FFFE  MOV REG[0xF0], #0xFFFE
  52:39F8  AC00 3D30  AJMP ALWAYS, 52:3D30
  52:39FC  6810 00A0  MOV REG[0x10], #0x00A0
  52:3A00  88F0 0006  MOV REG[0xF0], [0x0006]
  52:3A04  76F0 00EC  CMP REG[0xF0], #0x00EC
  52:3A08  AC02 3C6A  AJMP NZ/NE, 52:3C6A
  52:3A0C  68F0 0030  MOV REG[0xF0], #0x0030
  52:3A10  58F0       MOV [--R15], R0
> 52:3A12  BD02 C588  SCALL 02:C588
  52:3A16  50F2       ADD R15, #0x2
  52:3A18  68F0 0065  MOV REG[0xF0], #0x0065
```

### `52:3A1E` in `sub_52_36AA`

```text
  52:3A04  76F0 00EC  CMP REG[0xF0], #0x00EC
  52:3A08  AC02 3C6A  AJMP NZ/NE, 52:3C6A
  52:3A0C  68F0 0030  MOV REG[0xF0], #0x0030
  52:3A10  58F0       MOV [--R15], R0
  52:3A12  BD02 C588  SCALL 02:C588
  52:3A16  50F2       ADD R15, #0x2
  52:3A18  68F0 0065  MOV REG[0xF0], #0x0065
  52:3A1C  58F0       MOV [--R15], R0
> 52:3A1E  BD02 C588  SCALL 02:C588
  52:3A22  50F2       ADD R15, #0x2
  52:3A24  4800       MOV R0, #0x0
```

### `52:FF40` in `sub_52_FEDC`

```text
  52:FF28  58F1       MOV [--R15], R1
  52:FF2A  58F0       MOV [--R15], R0
  52:FF2C  BD53 2B78  SCALL 53:2B78
  52:FF30  50F8       ADD R15, #0x8
  52:FF32  6A0B 000A  MOV [R11+0x000A], R0
  52:FF36  6A1B 000C  MOV [R11+0x000C], R1
  52:FF3A  68F0 0023  MOV REG[0xF0], #0x0023
  52:FF3E  58F0       MOV [--R15], R0
> 52:FF40  BD02 C588  SCALL 02:C588
  52:FF44  50F2       ADD R15, #0x2
  52:FF46  4800       MOV R0, #0x0
```

### `52:FF96` in `sub_52_FEDC`

```text
  52:FF82  1901       MOVZE R0, RB1
  52:FF84  58F0       MOV [--R15], R0
  52:FF86  4803       MOV R0, #0x3
  52:FF88  58F0       MOV [--R15], R0
  52:FF8A  BD02 C5DC  SCALL 02:C5DC
  52:FF8E  50FC       ADD R15, #0xC
  52:FF90  68F0 0024  MOV REG[0xF0], #0x0024
  52:FF94  58F0       MOV [--R15], R0
> 52:FF96  BD02 C588  SCALL 02:C588
  52:FF9A  50F2       ADD R15, #0x2
  52:FF9C  4800       MOV R0, #0x0
```

## `02:C5DC`

Call sites: `52:FF8A`, `52:FFE0`

### `52:FF8A` in `sub_52_FEDC`

```text
  52:FF7A  58F4       MOV [--R15], R4
  52:FF7C  1413       AND R1, R3
  52:FF7E  1402       AND R0, R2
  52:FF80  0913       MOVB RB1, RB3
  52:FF82  1901       MOVZE R0, RB1
  52:FF84  58F0       MOV [--R15], R0
  52:FF86  4803       MOV R0, #0x3
  52:FF88  58F0       MOV [--R15], R0
> 52:FF8A  BD02 C5DC  SCALL 02:C5DC
  52:FF8E  50FC       ADD R15, #0xC
  52:FF90  68F0 0024  MOV REG[0xF0], #0x0024
```

### `52:FFE0` in `sub_52_FEDC`

```text
  52:FFD0  58F4       MOV [--R15], R4
  52:FFD2  1413       AND R1, R3
  52:FFD4  1402       AND R0, R2
  52:FFD6  0913       MOVB RB1, RB3
  52:FFD8  1901       MOVZE R0, RB1
  52:FFDA  58F0       MOV [--R15], R0
  52:FFDC  4803       MOV R0, #0x3
  52:FFDE  58F0       MOV [--R15], R0
> 52:FFE0  BD02 C5DC  SCALL 02:C5DC
  52:FFE4  50FC       ADD R15, #0xC
  52:FFE6  385F       MOV R5, [R15++]
```
