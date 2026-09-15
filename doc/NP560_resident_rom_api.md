# NP560+ resident SoC ROM API evidence

- Source listing: `doc/BURN_NAND_FLASH_CODE_reachable.asm`
- Parsed instructions: 27,439
- Direct calls into code segment 02: 60
- Distinct resident entry points: 13
- Scope: static call-site evidence only; no original ROM bytes are present.

## Entry-point inventory

| Resident entry | Calls | Calling functions | Immediate R15 cleanup | Evidence status |
|---|---:|---:|---|---|
| `02:B9E2` | 1 | 1 | `0xC` (6 words) | Unclassified |
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
| `02:C588` | 4 | 2 | `0x2` (1 words) | Probable diagnostic-byte marker; normal-return ABI proven |
| `02:C5DC` | 2 | 1 | `0xC` (6 words) | Unclassified |

## Interpretation constraints

The contexts below establish the call ABI and surrounding control flow. Names such as read, write, erase, and wait remain hypotheses until a reconstructed routine produces the caller-observed results for all call sites.

## `02:B9E2`

Call sites: `51:B6D4`

### `51:B6D4` in `sub_51_B5E8`

```text
  51:B6BC  68F0 620D  MOV REG[0xF0], #0x620D
  51:B6C0  58F0       MOV [--R15], R0
  51:B6C2  68F0 620C  MOV REG[0xF0], #0x620C
  51:B6C6  58F0       MOV [--R15], R0
  51:B6C8  68F0 620B  MOV REG[0xF0], #0x620B
  51:B6CC  58F0       MOV [--R15], R0
  51:B6CE  780B FFFE  MOV R0, [R11+0xFFFE]
  51:B6D2  58F0       MOV [--R15], R0
> 51:B6D4  BD02 B9E2  SCALL 02:B9E2
  51:B6D8  50FC       ADD R15, #0xC
  51:B6DA  381F       MOV R1, [R15++]
```

## `02:BAC4`

Call sites: `50:AA2A`

### `50:AA2A` in `sub_50_AA1A`

```text
  50:AA1A  2E08       LINK #0x08
  50:AA1C  58F1       MOV [--R15], R1
  50:AA1E  58F2       MOV [--R15], R2
  50:AA20  58F3       MOV [--R15], R3
  50:AA22  58F4       MOV [--R15], R4
  50:AA24  58F5       MOV [--R15], R5
  50:AA26  58F6       MOV [--R15], R6
  50:AA28  58F7       MOV [--R15], R7
> 50:AA2A  BD02 BAC4  SCALL 02:BAC4
  50:AA2E  BD02 BAC8  SCALL 02:BAC8
  50:AA32  68F1 D05E  MOV REG[0xF1], #0xD05E
```

## `02:BAC8`

Call sites: `50:AA2E`, `50:ADCC`, `51:5BE8`

### `50:AA2E` in `sub_50_AA1A`

```text
  50:AA1C  58F1       MOV [--R15], R1
  50:AA1E  58F2       MOV [--R15], R2
  50:AA20  58F3       MOV [--R15], R3
  50:AA22  58F4       MOV [--R15], R4
  50:AA24  58F5       MOV [--R15], R5
  50:AA26  58F6       MOV [--R15], R6
  50:AA28  58F7       MOV [--R15], R7
  50:AA2A  BD02 BAC4  SCALL 02:BAC4
> 50:AA2E  BD02 BAC8  SCALL 02:BAC8
  50:AA32  68F1 D05E  MOV REG[0xF1], #0xD05E
  50:AA36  68F0 0051  MOV REG[0xF0], #0x0051
```

### `50:ADCC` in `sub_50_AA1A`

```text
  50:ADBA  4800       MOV R0, #0x0
  50:ADBC  58F0       MOV [--R15], R0
  50:ADBE  4810       MOV R1, #0x0
  50:ADC0  4800       MOV R0, #0x0
  50:ADC2  58F1       MOV [--R15], R1
  50:ADC4  58F0       MOV [--R15], R0
  50:ADC6  BD02 BBF6  SCALL 02:BBF6
  50:ADCA  50FE       ADD R15, #0xE
> 50:ADCC  BD02 BAC8  SCALL 02:BAC8
  50:ADD0  780B FFFE  MOV R0, [R11+0xFFFE]
  50:ADD4  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:5BE8` in `sub_51_5B8C`

```text
  51:5BCA  6810 00A0  MOV REG[0x10], #0x00A0
  51:5BCE  88F0 0022  MOV REG[0xF0], [0x0022]
  51:5BD2  6810 00A0  MOV REG[0x10], #0x00A0
  51:5BD6  96F0 085A  CMP REG[0xF0], [0x085A]
  51:5BDA  AC05 5BE8  AJMP C/UL, 51:5BE8
  51:5BDE  BD51 D522  SCALL 51:D522
  51:5BE2  4800       MOV R0, #0x0
  51:5BE4  AC00 5E10  AJMP ALWAYS, 51:5E10
> 51:5BE8  BD02 BAC8  SCALL 02:BAC8
  51:5BEC  4800       MOV R0, #0x0
  51:5BEE  6A0B FFFE  MOV [R11+0xFFFE], R0
```

## `02:BB1E`

Call sites: `50:AA3E`

### `50:AA3E` in `sub_50_AA1A`

```text
  50:AA26  58F6       MOV [--R15], R6
  50:AA28  58F7       MOV [--R15], R7
  50:AA2A  BD02 BAC4  SCALL 02:BAC4
  50:AA2E  BD02 BAC8  SCALL 02:BAC8
  50:AA32  68F1 D05E  MOV REG[0xF1], #0xD05E
  50:AA36  68F0 0051  MOV REG[0xF0], #0x0051
  50:AA3A  58F1       MOV [--R15], R1
  50:AA3C  58F0       MOV [--R15], R0
> 50:AA3E  BD02 BB1E  SCALL 02:BB1E
  50:AA42  50F4       ADD R15, #0x4
  50:AA44  6A0B FFF8  MOV [R11+0xFFF8], R0
```

## `02:BBF6`

Strong NAND page/spare transfer candidate. Calls in `sub_51_0000` supply a page-like address, `50:0760` buffer, and `0x0040`, then remove seven stack words.

Call sites: `50:ADC6`, `50:B834`, `50:B940`, `51:00B0`, `51:0122`, `51:01A4`, `51:093E`, `51:19AA`, `51:1B06`, `51:29BC`, `51:2A3A`, `51:303A`, `51:4DEE`, `51:4E60`, `51:4EDA`

### `50:ADC6` in `sub_50_AA1A`

```text
  50:ADB6  58F1       MOV [--R15], R1
  50:ADB8  58F0       MOV [--R15], R0
  50:ADBA  4800       MOV R0, #0x0
  50:ADBC  58F0       MOV [--R15], R0
  50:ADBE  4810       MOV R1, #0x0
  50:ADC0  4800       MOV R0, #0x0
  50:ADC2  58F1       MOV [--R15], R1
  50:ADC4  58F0       MOV [--R15], R0
> 50:ADC6  BD02 BBF6  SCALL 02:BBF6
  50:ADCA  50FE       ADD R15, #0xE
  50:ADCC  BD02 BAC8  SCALL 02:BAC8
```

### `50:B834` in `sub_50_B730`

```text
  50:B822  1C23       SLOSB R2, RB3
  50:B824  781B 000A  MOV R1, [R11+0x000A]
  50:B828  0851       MOV R5, R1
  50:B82A  4840       MOV R4, #0x0
  50:B82C  1035       ADD R3, R5
  50:B82E  1124       ADDC R2, R4
  50:B830  58F3       MOV [--R15], R3
  50:B832  58F2       MOV [--R15], R2
> 50:B834  BD02 BBF6  SCALL 02:BBF6
  50:B838  50FE       ADD R15, #0xE
  50:B83A  781B FFEA  MOV R1, [R11+0xFFEA]
```

### `50:B940` in `sub_50_B730`

```text
  50:B92E  1C23       SLOSB R2, RB3
  50:B930  781B 000A  MOV R1, [R11+0x000A]
  50:B934  0851       MOV R5, R1
  50:B936  4840       MOV R4, #0x0
  50:B938  1035       ADD R3, R5
  50:B93A  1124       ADDC R2, R4
  50:B93C  58F3       MOV [--R15], R3
  50:B93E  58F2       MOV [--R15], R2
> 50:B940  BD02 BBF6  SCALL 02:BBF6
  50:B944  50FE       ADD R15, #0xE
  50:B946  781B FFEA  MOV R1, [R11+0xFFEA]
```

### `51:00B0` in `sub_51_0000`

```text
  51:0098  58F0       MOV [--R15], R0
  51:009A  6810 00A0  MOV REG[0x10], #0x00A0
  51:009E  88F0 002E  MOV REG[0xF0], [0x002E]
  51:00A2  58F0       MOV [--R15], R0
  51:00A4  780B FFEE  MOV R0, [R11+0xFFEE]
  51:00A8  781B FFF0  MOV R1, [R11+0xFFF0]
  51:00AC  58F1       MOV [--R15], R1
  51:00AE  58F0       MOV [--R15], R0
> 51:00B0  BD02 BBF6  SCALL 02:BBF6
  51:00B4  50FE       ADD R15, #0xE
  51:00B6  780B FFEC  MOV R0, [R11+0xFFEC]
```

### `51:0122` in `sub_51_0000`

```text
  51:010C  88F0 002E  MOV REG[0xF0], [0x002E]
  51:0110  58F0       MOV [--R15], R0
  51:0112  780B FFEE  MOV R0, [R11+0xFFEE]
  51:0116  781B FFF0  MOV R1, [R11+0xFFF0]
  51:011A  5011       ADD R1, #0x1
  51:011C  5100       ADDC R0, #0x0
  51:011E  58F1       MOV [--R15], R1
  51:0120  58F0       MOV [--R15], R0
> 51:0122  BD02 BBF6  SCALL 02:BBF6
  51:0126  50FE       ADD R15, #0xE
  51:0128  780B FFEC  MOV R0, [R11+0xFFEC]
```

### `51:01A4` in `sub_51_0000`

```text
  51:018C  88F0 002E  MOV REG[0xF0], [0x002E]
  51:0190  58F0       MOV [--R15], R0
  51:0192  780B FFEE  MOV R0, [R11+0xFFEE]
  51:0196  781B FFF0  MOV R1, [R11+0xFFF0]
  51:019A  70F1 003F  ADD REG[0xF1], #0x003F
  51:019E  5100       ADDC R0, #0x0
  51:01A0  58F1       MOV [--R15], R1
  51:01A2  58F0       MOV [--R15], R0
> 51:01A4  BD02 BBF6  SCALL 02:BBF6
  51:01A8  50FE       ADD R15, #0xE
  51:01AA  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:093E` in `sub_51_08A6`

```text
  51:092C  58F1       MOV [--R15], R1
  51:092E  58F0       MOV [--R15], R0
  51:0930  4800       MOV R0, #0x0
  51:0932  58F0       MOV [--R15], R0
  51:0934  68F1 003F  MOV REG[0xF1], #0x003F
  51:0938  4800       MOV R0, #0x0
  51:093A  58F1       MOV [--R15], R1
  51:093C  58F0       MOV [--R15], R0
> 51:093E  BD02 BBF6  SCALL 02:BBF6
  51:0942  50FE       ADD R15, #0xE
  51:0944  4800       MOV R0, #0x0
```

### `51:19AA` in `sub_51_18F0`

```text
  51:1992  58F0       MOV [--R15], R0
  51:1994  6810 00A0  MOV REG[0x10], #0x00A0
  51:1998  88F0 002E  MOV REG[0xF0], [0x002E]
  51:199C  58F0       MOV [--R15], R0
  51:199E  780B FFF6  MOV R0, [R11+0xFFF6]
  51:19A2  781B FFF8  MOV R1, [R11+0xFFF8]
  51:19A6  58F1       MOV [--R15], R1
  51:19A8  58F0       MOV [--R15], R0
> 51:19AA  BD02 BBF6  SCALL 02:BBF6
  51:19AE  50FE       ADD R15, #0xE
  51:19B0  791B 000A  MOVB RB1, [R11+0x000A]
```

### `51:1B06` in `sub_51_18F0`

```text
  51:1AEE  58F0       MOV [--R15], R0
  51:1AF0  6810 00A0  MOV REG[0x10], #0x00A0
  51:1AF4  88F0 002E  MOV REG[0xF0], [0x002E]
  51:1AF8  58F0       MOV [--R15], R0
  51:1AFA  780B FFF6  MOV R0, [R11+0xFFF6]
  51:1AFE  781B FFF8  MOV R1, [R11+0xFFF8]
  51:1B02  58F1       MOV [--R15], R1
  51:1B04  58F0       MOV [--R15], R0
> 51:1B06  BD02 BBF6  SCALL 02:BBF6
  51:1B0A  50FE       ADD R15, #0xE
  51:1B0C  4801       MOV R0, #0x1
```

### `51:29BC` in `sub_51_2758`

```text
  51:29A8  58F1       MOV [--R15], R1
  51:29AA  58F0       MOV [--R15], R0
  51:29AC  4800       MOV R0, #0x0
  51:29AE  58F0       MOV [--R15], R0
  51:29B0  780B FFF8  MOV R0, [R11+0xFFF8]
  51:29B4  781B FFFA  MOV R1, [R11+0xFFFA]
  51:29B8  58F1       MOV [--R15], R1
  51:29BA  58F0       MOV [--R15], R0
> 51:29BC  BD02 BBF6  SCALL 02:BBF6
  51:29C0  50FE       ADD R15, #0xE
  51:29C2  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:2A3A` in `sub_51_2758`

```text
  51:2A26  58F1       MOV [--R15], R1
  51:2A28  58F0       MOV [--R15], R0
  51:2A2A  4800       MOV R0, #0x0
  51:2A2C  58F0       MOV [--R15], R0
  51:2A2E  780B FFF4  MOV R0, [R11+0xFFF4]
  51:2A32  781B FFF6  MOV R1, [R11+0xFFF6]
  51:2A36  58F1       MOV [--R15], R1
  51:2A38  58F0       MOV [--R15], R0
> 51:2A3A  BD02 BBF6  SCALL 02:BBF6
  51:2A3E  50FE       ADD R15, #0xE
  51:2A40  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:303A` in `sub_51_2E1C`

```text
  51:3028  1C07       SLOSB R0, RB7
  51:302A  783B 0006  MOV R3, [R11+0x0006]
  51:302E  4D38       SR R3, #0x8
  51:3030  4820       MOV R2, #0x0
  51:3032  1013       ADD R1, R3
  51:3034  1102       ADDC R0, R2
  51:3036  58F1       MOV [--R15], R1
  51:3038  58F0       MOV [--R15], R0
> 51:303A  BD02 BBF6  SCALL 02:BBF6
  51:303E  50FE       ADD R15, #0xE
  51:3040  68F1 029E  MOV REG[0xF1], #0x029E
```

### `51:4DEE` in `sub_51_4D44`

```text
  51:4DD6  58F0       MOV [--R15], R0
  51:4DD8  6810 00A0  MOV REG[0x10], #0x00A0
  51:4DDC  88F0 002E  MOV REG[0xF0], [0x002E]
  51:4DE0  58F0       MOV [--R15], R0
  51:4DE2  780B FFF6  MOV R0, [R11+0xFFF6]
  51:4DE6  781B FFF8  MOV R1, [R11+0xFFF8]
  51:4DEA  58F1       MOV [--R15], R1
  51:4DEC  58F0       MOV [--R15], R0
> 51:4DEE  BD02 BBF6  SCALL 02:BBF6
  51:4DF2  50FE       ADD R15, #0xE
  51:4DF4  780B FFF2  MOV R0, [R11+0xFFF2]
```

### `51:4E60` in `sub_51_4D44`

```text
  51:4E4A  88F0 002E  MOV REG[0xF0], [0x002E]
  51:4E4E  58F0       MOV [--R15], R0
  51:4E50  780B FFF6  MOV R0, [R11+0xFFF6]
  51:4E54  781B FFF8  MOV R1, [R11+0xFFF8]
  51:4E58  5011       ADD R1, #0x1
  51:4E5A  5100       ADDC R0, #0x0
  51:4E5C  58F1       MOV [--R15], R1
  51:4E5E  58F0       MOV [--R15], R0
> 51:4E60  BD02 BBF6  SCALL 02:BBF6
  51:4E64  50FE       ADD R15, #0xE
  51:4E66  780B FFF2  MOV R0, [R11+0xFFF2]
```

### `51:4EDA` in `sub_51_4D44`

```text
  51:4EC2  88F0 002E  MOV REG[0xF0], [0x002E]
  51:4EC6  58F0       MOV [--R15], R0
  51:4EC8  780B FFF6  MOV R0, [R11+0xFFF6]
  51:4ECC  781B FFF8  MOV R1, [R11+0xFFF8]
  51:4ED0  70F1 003F  ADD REG[0xF1], #0x003F
  51:4ED4  5100       ADDC R0, #0x0
  51:4ED6  58F1       MOV [--R15], R1
  51:4ED8  58F0       MOV [--R15], R0
> 51:4EDA  BD02 BBF6  SCALL 02:BBF6
  51:4EDE  50FE       ADD R15, #0xE
  51:4EE0  6810 00A0  MOV REG[0x10], #0x00A0
```

## `02:BCC6`

NAND transfer variant candidate. Its exact direction and spare-area contract remain unproven.

Call sites: `50:8476`, `50:BBDE`, `51:0CAE`, `51:1A92`, `51:283E`, `51:2F58`, `51:4746`, `51:5D4A`, `51:9E44`

### `50:8476` in `sub_50_7DD8`

```text
  50:8464  DE03       RJMP SGE, 50:846C ; rel +3
  50:8466  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  50:846A  D001       RJMP ALWAYS, 50:846E ; rel +1
  50:846C  4800       MOV R0, #0x0
  50:846E  1031       ADD R3, R1
  50:8470  1120       ADDC R2, R0
  50:8472  58F3       MOV [--R15], R3
  50:8474  58F2       MOV [--R15], R2
> 50:8476  BD02 BCC6  SCALL 02:BCC6
  50:847A  50FE       ADD R15, #0xE
  50:847C  781B FFF8  MOV R1, [R11+0xFFF8]
```

### `50:BBDE` in `sub_50_B730`

```text
  50:BBCC  0C17       SL R1, RB7
  50:BBCE  1C07       SLOSB R0, RB7
  50:BBD0  783B 000A  MOV R3, [R11+0x000A]
  50:BBD4  4820       MOV R2, #0x0
  50:BBD6  1013       ADD R1, R3
  50:BBD8  1102       ADDC R0, R2
  50:BBDA  58F1       MOV [--R15], R1
  50:BBDC  58F0       MOV [--R15], R0
> 50:BBDE  BD02 BCC6  SCALL 02:BCC6
  50:BBE2  50FE       ADD R15, #0xE
  50:BBE4  6A0B FFF8  MOV [R11+0xFFF8], R0
```

### `51:0CAE` in `sub_51_08A6`

```text
  51:0C9C  58F1       MOV [--R15], R1
  51:0C9E  58F0       MOV [--R15], R0
  51:0CA0  4800       MOV R0, #0x0
  51:0CA2  58F0       MOV [--R15], R0
  51:0CA4  68F1 003F  MOV REG[0xF1], #0x003F
  51:0CA8  4800       MOV R0, #0x0
  51:0CAA  58F1       MOV [--R15], R1
  51:0CAC  58F0       MOV [--R15], R0
> 51:0CAE  BD02 BCC6  SCALL 02:BCC6
  51:0CB2  50FE       ADD R15, #0xE
  51:0CB4  5600       CMP R0, #0x0
```

### `51:1A92` in `sub_51_18F0`

```text
  51:1A7E  58F1       MOV [--R15], R1
  51:1A80  58F0       MOV [--R15], R0
  51:1A82  4800       MOV R0, #0x0
  51:1A84  58F0       MOV [--R15], R0
  51:1A86  780B FFF6  MOV R0, [R11+0xFFF6]
  51:1A8A  781B FFF8  MOV R1, [R11+0xFFF8]
  51:1A8E  58F1       MOV [--R15], R1
  51:1A90  58F0       MOV [--R15], R0
> 51:1A92  BD02 BCC6  SCALL 02:BCC6
  51:1A96  50FE       ADD R15, #0xE
  51:1A98  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:283E` in `sub_51_2758`

```text
  51:282A  58F1       MOV [--R15], R1
  51:282C  58F0       MOV [--R15], R0
  51:282E  4800       MOV R0, #0x0
  51:2830  58F0       MOV [--R15], R0
  51:2832  780B FFFC  MOV R0, [R11+0xFFFC]
  51:2836  781B FFFE  MOV R1, [R11+0xFFFE]
  51:283A  58F1       MOV [--R15], R1
  51:283C  58F0       MOV [--R15], R0
> 51:283E  BD02 BCC6  SCALL 02:BCC6
  51:2842  50FE       ADD R15, #0xE
  51:2844  5600       CMP R0, #0x0
```

### `51:2F58` in `sub_51_2E1C`

```text
  51:2F46  0C17       SL R1, RB7
  51:2F48  1C07       SLOSB R0, RB7
  51:2F4A  783B FFFA  MOV R3, [R11+0xFFFA]
  51:2F4E  4820       MOV R2, #0x0
  51:2F50  1013       ADD R1, R3
  51:2F52  1102       ADDC R0, R2
  51:2F54  58F1       MOV [--R15], R1
  51:2F56  58F0       MOV [--R15], R0
> 51:2F58  BD02 BCC6  SCALL 02:BCC6
  51:2F5C  50FE       ADD R15, #0xE
  51:2F5E  6A0B FFFE  MOV [R11+0xFFFE], R0
```

### `51:4746` in `sub_51_4452`

```text
  51:4734  58F1       MOV [--R15], R1
  51:4736  58F0       MOV [--R15], R0
  51:4738  4800       MOV R0, #0x0
  51:473A  58F0       MOV [--R15], R0
  51:473C  68F1 003F  MOV REG[0xF1], #0x003F
  51:4740  4800       MOV R0, #0x0
  51:4742  58F1       MOV [--R15], R1
  51:4744  58F0       MOV [--R15], R0
> 51:4746  BD02 BCC6  SCALL 02:BCC6
  51:474A  50FE       ADD R15, #0xE
  51:474C  4800       MOV R0, #0x0
```

### `51:5D4A` in `sub_51_5B8C`

```text
  51:5D36  1C07       SLOSB R0, RB7
  51:5D38  6810 00A0  MOV REG[0x10], #0x00A0
  51:5D3C  88F3 0024  MOV REG[0xF3], [0x0024]
  51:5D40  4820       MOV R2, #0x0
  51:5D42  1013       ADD R1, R3
  51:5D44  1102       ADDC R0, R2
  51:5D46  58F1       MOV [--R15], R1
  51:5D48  58F0       MOV [--R15], R0
> 51:5D4A  BD02 BCC6  SCALL 02:BCC6
  51:5D4E  50FE       ADD R15, #0xE
  51:5D50  6A0B FFFE  MOV [R11+0xFFFE], R0
```

### `51:9E44` in `sub_51_9D84`

```text
  51:9E30  1C07       SLOSB R0, RB7
  51:9E32  6810 00A0  MOV REG[0x10], #0x00A0
  51:9E36  88F3 0024  MOV REG[0xF3], [0x0024]
  51:9E3A  4820       MOV R2, #0x0
  51:9E3C  1013       ADD R1, R3
  51:9E3E  1102       ADDC R0, R2
  51:9E40  58F1       MOV [--R15], R1
  51:9E42  58F0       MOV [--R15], R0
> 51:9E44  BD02 BCC6  SCALL 02:BCC6
  51:9E48  50FE       ADD R15, #0xE
  51:9E4A  6A0B FFFA  MOV [R11+0xFFFA], R0
```

## `02:BDD6`

NAND follow-up/status candidate. It repeatedly follows transfer paths and its return value is checked by the caller.

Call sites: `50:8054`, `50:812C`, `50:8310`, `51:0B58`, `51:0B88`, `51:19CA`, `51:22A8`, `51:260A`, `51:27FE`, `51:28B2`, `51:2906`, `51:446E`, `51:856A`

### `50:8054` in `sub_50_7DD8`

```text
  50:8036  6810 00A0  MOV REG[0x10], #0x00A0
  50:803A  B0F1 07DA  ADD [0x07DA], REG[0xF1]
  50:803E  781B FFF0  MOV R1, [R11+0xFFF0]
  50:8042  6810 00A0  MOV REG[0x10], #0x00A0
  50:8046  96F1 085A  CMP REG[0xF1], [0x085A]
  50:804A  AC0C 807A  AJMP ULE, 50:807A
  50:804E  781B FFF6  MOV R1, [R11+0xFFF6]
  50:8052  58F1       MOV [--R15], R1
> 50:8054  BD02 BDD6  SCALL 02:BDD6
  50:8058  50F2       ADD R15, #0x2
  50:805A  5600       CMP R0, #0x0
```

### `50:812C` in `sub_50_7DD8`

```text
  50:8114  4D11       SR R1, #0x1
  50:8116  0A12       MOV [R1], R2
  50:8118  AC00 8244  AJMP ALWAYS, 50:8244
  50:811C  782B FFFA  MOV R2, [R11+0xFFFA]
  50:8120  5620       CMP R2, #0x0
  50:8122  AC02 8152  AJMP NZ/NE, 50:8152
  50:8126  782B FFF6  MOV R2, [R11+0xFFF6]
  50:812A  58F2       MOV [--R15], R2
> 50:812C  BD02 BDD6  SCALL 02:BDD6
  50:8130  50F2       ADD R15, #0x2
  50:8132  5600       CMP R0, #0x0
```

### `50:8310` in `sub_50_7DD8`

```text
  50:82FE  4C11       SL R1, #0x1
  50:8300  5C01       SLOSB R0, #0x1
  50:8302  58F0       MOV [--R15], R0
  50:8304  1F90       POP REG[0x10]
  50:8306  4D11       SR R1, #0x1
  50:8308  0A12       MOV [R1], R2
  50:830A  782B FFF6  MOV R2, [R11+0xFFF6]
  50:830E  58F2       MOV [--R15], R2
> 50:8310  BD02 BDD6  SCALL 02:BDD6
  50:8314  50F2       ADD R15, #0x2
  50:8316  5600       CMP R0, #0x0
```

### `51:0B58` in `sub_51_08A6`

```text
  51:0B44  58F0       MOV [--R15], R0
  51:0B46  781B FFEC  MOV R1, [R11+0xFFEC]
  51:0B4A  58F1       MOV [--R15], R1
  51:0B4C  58F0       MOV [--R15], R0
  51:0B4E  BD51 8114  SCALL 51:8114
  51:0B52  50F8       ADD R15, #0x8
  51:0B54  4800       MOV R0, #0x0
  51:0B56  58F0       MOV [--R15], R0
> 51:0B58  BD02 BDD6  SCALL 02:BDD6
  51:0B5C  50F2       ADD R15, #0x2
  51:0B5E  5600       CMP R0, #0x0
```

### `51:0B88` in `sub_51_08A6`

```text
  51:0B72  58F0       MOV [--R15], R0
  51:0B74  58F0       MOV [--R15], R0
  51:0B76  780B FFEC  MOV R0, [R11+0xFFEC]
  51:0B7A  58F0       MOV [--R15], R0
  51:0B7C  BD51 8114  SCALL 51:8114
  51:0B80  50F8       ADD R15, #0x8
  51:0B82  780B FFEC  MOV R0, [R11+0xFFEC]
  51:0B86  58F0       MOV [--R15], R0
> 51:0B88  BD02 BDD6  SCALL 02:BDD6
  51:0B8C  50F2       ADD R15, #0x2
  51:0B8E  5600       CMP R0, #0x0
```

### `51:19CA` in `sub_51_18F0`

```text
  51:19B0  791B 000A  MOVB RB1, [R11+0x000A]
  51:19B4  1901       MOVZE R0, RB1
  51:19B6  5600       CMP R0, #0x0
  51:19B8  AC01 19C4  AJMP Z/EQ, 51:19C4
  51:19BC  76F0 0011  CMP REG[0xF0], #0x0011
  51:19C0  AC02 1B82  AJMP NZ/NE, 51:1B82
  51:19C4  780B 0006  MOV R0, [R11+0x0006]
  51:19C8  58F0       MOV [--R15], R0
> 51:19CA  BD02 BDD6  SCALL 02:BDD6
  51:19CE  50F2       ADD R15, #0x2
  51:19D0  5600       CMP R0, #0x0
```

### `51:22A8` in `sub_51_2092`

```text
  51:228E  50F2       ADD R15, #0x2
  51:2290  1901       MOVZE R0, RB1
  51:2292  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:2296  780B FFFC  MOV R0, [R11+0xFFFC]
  51:229A  76F0 0011  CMP REG[0xF0], #0x0011
  51:229E  AC02 22CC  AJMP NZ/NE, 51:22CC
  51:22A2  780B FFFE  MOV R0, [R11+0xFFFE]
  51:22A6  58F0       MOV [--R15], R0
> 51:22A8  BD02 BDD6  SCALL 02:BDD6
  51:22AC  50F2       ADD R15, #0x2
  51:22AE  5600       CMP R0, #0x0
```

### `51:260A` in `sub_51_23F6`

```text
  51:25F0  50F2       ADD R15, #0x2
  51:25F2  1901       MOVZE R0, RB1
  51:25F4  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:25F8  780B FFFC  MOV R0, [R11+0xFFFC]
  51:25FC  76F0 0011  CMP REG[0xF0], #0x0011
  51:2600  AC02 262E  AJMP NZ/NE, 51:262E
  51:2604  780B FFFE  MOV R0, [R11+0xFFFE]
  51:2608  58F0       MOV [--R15], R0
> 51:260A  BD02 BDD6  SCALL 02:BDD6
  51:260E  50F2       ADD R15, #0x2
  51:2610  5600       CMP R0, #0x0
```

### `51:27FE` in `sub_51_2758`

```text
  51:27EC  58F3       MOV [--R15], R3
  51:27EE  58F2       MOV [--R15], R2
  51:27F0  58F1       MOV [--R15], R1
  51:27F2  58F0       MOV [--R15], R0
  51:27F4  BD51 DA40  SCALL 51:DA40
  51:27F8  50F8       ADD R15, #0x8
  51:27FA  0801       MOV R0, R1
  51:27FC  58F0       MOV [--R15], R0
> 51:27FE  BD02 BDD6  SCALL 02:BDD6
  51:2802  50F2       ADD R15, #0x2
  51:2804  5600       CMP R0, #0x0
```

### `51:28B2` in `sub_51_2758`

```text
  51:28A0  58F3       MOV [--R15], R3
  51:28A2  58F2       MOV [--R15], R2
  51:28A4  58F1       MOV [--R15], R1
  51:28A6  58F0       MOV [--R15], R0
  51:28A8  BD51 DA40  SCALL 51:DA40
  51:28AC  50F8       ADD R15, #0x8
  51:28AE  0801       MOV R0, R1
  51:28B0  58F0       MOV [--R15], R0
> 51:28B2  BD02 BDD6  SCALL 02:BDD6
  51:28B6  50F2       ADD R15, #0x2
  51:28B8  5600       CMP R0, #0x0
```

### `51:2906` in `sub_51_2758`

```text
  51:28F4  58F3       MOV [--R15], R3
  51:28F6  58F2       MOV [--R15], R2
  51:28F8  58F1       MOV [--R15], R1
  51:28FA  58F0       MOV [--R15], R0
  51:28FC  BD51 DA40  SCALL 51:DA40
  51:2900  50F8       ADD R15, #0x8
  51:2902  0801       MOV R0, R1
  51:2904  58F0       MOV [--R15], R0
> 51:2906  BD02 BDD6  SCALL 02:BDD6
  51:290A  50F2       ADD R15, #0x2
  51:290C  5600       CMP R0, #0x0
```

### `51:446E` in `sub_51_4452`

```text
  51:4456  58F2       MOV [--R15], R2
  51:4458  58F3       MOV [--R15], R3
  51:445A  68F1 009E  MOV REG[0xF1], #0x009E
  51:445E  68F0 0050  MOV REG[0xF0], #0x0050
  51:4462  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:4466  6A1B FFFE  MOV [R11+0xFFFE], R1
  51:446A  4800       MOV R0, #0x0
  51:446C  58F0       MOV [--R15], R0
> 51:446E  BD02 BDD6  SCALL 02:BDD6
  51:4472  50F2       ADD R15, #0x2
  51:4474  6810 00A0  MOV REG[0x10], #0x00A0
```

### `51:856A` in `sub_51_84B2`

```text
  51:854E  AC01 8556  AJMP Z/EQ, 51:8556
  51:8552  AC00 8564  AJMP ALWAYS, 51:8564
  51:8556  4801       MOV R0, #0x1
  51:8558  6810 00A0  MOV REG[0x10], #0x00A0
  51:855C  B0F0 07E6  ADD [0x07E6], REG[0xF0]
  51:8560  AC00 85E0  AJMP ALWAYS, 51:85E0
  51:8564  780B FFFE  MOV R0, [R11+0xFFFE]
  51:8568  58F0       MOV [--R15], R0
> 51:856A  BD02 BDD6  SCALL 02:BDD6
  51:856E  50F2       ADD R15, #0x2
  51:8570  5600       CMP R0, #0x0
```

## `02:BE5C`

Asynchronous NAND operation variant. Callers pair it immediately with `02:C04C`.

Call sites: `51:2958`, `51:297A`, `51:8298`, `51:BBF0`

### `51:2958` in `sub_51_2758`

```text
  51:2940  780B FFF8  MOV R0, [R11+0xFFF8]
  51:2944  781B FFFA  MOV R1, [R11+0xFFFA]
  51:2948  58F1       MOV [--R15], R1
  51:294A  58F0       MOV [--R15], R0
  51:294C  780B FFFC  MOV R0, [R11+0xFFFC]
  51:2950  781B FFFE  MOV R1, [R11+0xFFFE]
  51:2954  58F1       MOV [--R15], R1
  51:2956  58F0       MOV [--R15], R0
> 51:2958  BD02 BE5C  SCALL 02:BE5C
  51:295C  50F8       ADD R15, #0x8
  51:295E  BD02 C04C  SCALL 02:C04C
```

### `51:297A` in `sub_51_2758`

```text
  51:2962  780B FFF4  MOV R0, [R11+0xFFF4]
  51:2966  781B FFF6  MOV R1, [R11+0xFFF6]
  51:296A  58F1       MOV [--R15], R1
  51:296C  58F0       MOV [--R15], R0
  51:296E  780B FFFC  MOV R0, [R11+0xFFFC]
  51:2972  781B FFFE  MOV R1, [R11+0xFFFE]
  51:2976  58F1       MOV [--R15], R1
  51:2978  58F0       MOV [--R15], R0
> 51:297A  BD02 BE5C  SCALL 02:BE5C
  51:297E  50F8       ADD R15, #0x8
  51:2980  BD02 C04C  SCALL 02:C04C
```

### `51:8298` in `sub_51_8114`

```text
  51:8284  58F3       MOV [--R15], R3
  51:8286  58F2       MOV [--R15], R2
  51:8288  782B FFF4  MOV R2, [R11+0xFFF4]
  51:828C  783B FFF6  MOV R3, [R11+0xFFF6]
  51:8290  1031       ADD R3, R1
  51:8292  1120       ADDC R2, R0
  51:8294  58F3       MOV [--R15], R3
  51:8296  58F2       MOV [--R15], R2
> 51:8298  BD02 BE5C  SCALL 02:BE5C
  51:829C  50F8       ADD R15, #0x8
  51:829E  BD02 C04C  SCALL 02:C04C
```

### `51:BBF0` in `sub_51_BB74`

```text
  51:BBDC  6810 00A0  MOV REG[0x10], #0x00A0
  51:BBE0  88F3 07CA  MOV REG[0xF3], [0x07CA]
  51:BBE4  0C27       SL R2, RB7
  51:BBE6  1020       ADD R2, R0
  51:BBE8  0812       MOV R1, R2
  51:BBEA  4800       MOV R0, #0x0
  51:BBEC  58F1       MOV [--R15], R1
  51:BBEE  58F0       MOV [--R15], R0
> 51:BBF0  BD02 BE5C  SCALL 02:BE5C
  51:BBF4  50F8       ADD R15, #0x8
  51:BBF6  4801       MOV R0, #0x1
```

## `02:BF56`

Second asynchronous NAND operation variant, selected for device ID `0x76` and paired immediately with `02:C04C`.

Call sites: `51:8234`

### `51:8234` in `sub_51_8114`

```text
  51:8220  58F3       MOV [--R15], R3
  51:8222  58F2       MOV [--R15], R2
  51:8224  782B FFF4  MOV R2, [R11+0xFFF4]
  51:8228  783B FFF6  MOV R3, [R11+0xFFF6]
  51:822C  1031       ADD R3, R1
  51:822E  1120       ADDC R2, R0
  51:8230  58F3       MOV [--R15], R3
  51:8232  58F2       MOV [--R15], R2
> 51:8234  BD02 BF56  SCALL 02:BF56
  51:8238  50F8       ADD R15, #0x8
  51:823A  BD02 C04C  SCALL 02:C04C
```

## `02:C04C`

Completion/status routine candidate. It follows `02:BE5C` or `02:BF56`, and callers branch on R0.

Call sites: `51:295E`, `51:2980`, `51:823A`, `51:829E`, `51:BC1C`

### `51:295E` in `sub_51_2758`

```text
  51:2948  58F1       MOV [--R15], R1
  51:294A  58F0       MOV [--R15], R0
  51:294C  780B FFFC  MOV R0, [R11+0xFFFC]
  51:2950  781B FFFE  MOV R1, [R11+0xFFFE]
  51:2954  58F1       MOV [--R15], R1
  51:2956  58F0       MOV [--R15], R0
  51:2958  BD02 BE5C  SCALL 02:BE5C
  51:295C  50F8       ADD R15, #0x8
> 51:295E  BD02 C04C  SCALL 02:C04C
  51:2962  780B FFF4  MOV R0, [R11+0xFFF4]
  51:2966  781B FFF6  MOV R1, [R11+0xFFF6]
```

### `51:2980` in `sub_51_2758`

```text
  51:296A  58F1       MOV [--R15], R1
  51:296C  58F0       MOV [--R15], R0
  51:296E  780B FFFC  MOV R0, [R11+0xFFFC]
  51:2972  781B FFFE  MOV R1, [R11+0xFFFE]
  51:2976  58F1       MOV [--R15], R1
  51:2978  58F0       MOV [--R15], R0
  51:297A  BD02 BE5C  SCALL 02:BE5C
  51:297E  50F8       ADD R15, #0x8
> 51:2980  BD02 C04C  SCALL 02:C04C
  51:2984  4800       MOV R0, #0x0
  51:2986  58F0       MOV [--R15], R0
```

### `51:823A` in `sub_51_8114`

```text
  51:8224  782B FFF4  MOV R2, [R11+0xFFF4]
  51:8228  783B FFF6  MOV R3, [R11+0xFFF6]
  51:822C  1031       ADD R3, R1
  51:822E  1120       ADDC R2, R0
  51:8230  58F3       MOV [--R15], R3
  51:8232  58F2       MOV [--R15], R2
  51:8234  BD02 BF56  SCALL 02:BF56
  51:8238  50F8       ADD R15, #0x8
> 51:823A  BD02 C04C  SCALL 02:C04C
  51:823E  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:8242  5600       CMP R0, #0x0
```

### `51:829E` in `sub_51_8114`

```text
  51:8288  782B FFF4  MOV R2, [R11+0xFFF4]
  51:828C  783B FFF6  MOV R3, [R11+0xFFF6]
  51:8290  1031       ADD R3, R1
  51:8292  1120       ADDC R2, R0
  51:8294  58F3       MOV [--R15], R3
  51:8296  58F2       MOV [--R15], R2
  51:8298  BD02 BE5C  SCALL 02:BE5C
  51:829C  50F8       ADD R15, #0x8
> 51:829E  BD02 C04C  SCALL 02:C04C
  51:82A2  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:82A6  5600       CMP R0, #0x0
```

### `51:BC1C` in `sub_51_BB74`

```text
  51:BC04  68F0 0040  MOV REG[0xF0], #0x0040
  51:BC08  58F0       MOV [--R15], R0
  51:BC0A  68F1 0760  MOV REG[0xF1], #0x0760
  51:BC0E  68F0 0050  MOV REG[0xF0], #0x0050
  51:BC12  58F1       MOV [--R15], R1
  51:BC14  58F0       MOV [--R15], R0
  51:BC16  BD02 C0D2  SCALL 02:C0D2
  51:BC1A  50FA       ADD R15, #0xA
> 51:BC1C  BD02 C04C  SCALL 02:C04C
  51:BC20  6A0B FFFC  MOV [R11+0xFFFC], R0
  51:BC24  780B 000A  MOV R0, [R11+0x000A]
```

## `02:C0D2`

Call sites: `51:BC16`

### `51:BC16` in `sub_51_BB74`

```text
  51:BBFE  88F0 002E  MOV REG[0xF0], [0x002E]
  51:BC02  58F0       MOV [--R15], R0
  51:BC04  68F0 0040  MOV REG[0xF0], #0x0040
  51:BC08  58F0       MOV [--R15], R0
  51:BC0A  68F1 0760  MOV REG[0xF1], #0x0760
  51:BC0E  68F0 0050  MOV REG[0xF0], #0x0050
  51:BC12  58F1       MOV [--R15], R1
  51:BC14  58F0       MOV [--R15], R0
> 51:BC16  BD02 C0D2  SCALL 02:C0D2
  51:BC1A  50FA       ADD R15, #0xA
  51:BC1C  BD02 C04C  SCALL 02:C04C
```

## `02:C588`

Call sites: `50:AD82`, `50:AD8E`, `51:B01E`, `51:B074`

All callers pass one immediate byte (`0x23`, `0x24`, `0x30`, or `0x65`),
reclaim the one-word argument themselves, and do not consume a return value.
The `0x23`/`0x24` calls bracket two three-byte emissions through nearby entry
`02:C5DC`; `0x30`/`0x65` occurs only after the chip-ID value `0xEC` is observed
and immediately before a NAND self-test. This is strong evidence for a
diagnostic/marker output. The reconstructed ROM can therefore provide the
CPU-visible normal return, while any external byte-output side effect remains
unmodeled until its SFR or physical pin is identified.

### `50:AD82` in `sub_50_AA1A`

```text
  50:AD64  68F0 FFFE  MOV REG[0xF0], #0xFFFE
  50:AD68  AC00 B0A0  AJMP ALWAYS, 50:B0A0
  50:AD6C  6810 00A0  MOV REG[0x10], #0x00A0
  50:AD70  88F0 0000  MOV REG[0xF0], [0x0000]
  50:AD74  76F0 00EC  CMP REG[0xF0], #0x00EC
  50:AD78  AC02 AFDA  AJMP NZ/NE, 50:AFDA
  50:AD7C  68F0 0030  MOV REG[0xF0], #0x0030
  50:AD80  58F0       MOV [--R15], R0
> 50:AD82  BD02 C588  SCALL 02:C588
  50:AD86  50F2       ADD R15, #0x2
  50:AD88  68F0 0065  MOV REG[0xF0], #0x0065
```

### `50:AD8E` in `sub_50_AA1A`

```text
  50:AD74  76F0 00EC  CMP REG[0xF0], #0x00EC
  50:AD78  AC02 AFDA  AJMP NZ/NE, 50:AFDA
  50:AD7C  68F0 0030  MOV REG[0xF0], #0x0030
  50:AD80  58F0       MOV [--R15], R0
  50:AD82  BD02 C588  SCALL 02:C588
  50:AD86  50F2       ADD R15, #0x2
  50:AD88  68F0 0065  MOV REG[0xF0], #0x0065
  50:AD8C  58F0       MOV [--R15], R0
> 50:AD8E  BD02 C588  SCALL 02:C588
  50:AD92  50F2       ADD R15, #0x2
  50:AD94  4800       MOV R0, #0x0
```

### `51:B01E` in `sub_51_AFBA`

```text
  51:B006  58F1       MOV [--R15], R1
  51:B008  58F0       MOV [--R15], R0
  51:B00A  BD51 D864  SCALL 51:D864
  51:B00E  50F8       ADD R15, #0x8
  51:B010  6A0B 000A  MOV [R11+0x000A], R0
  51:B014  6A1B 000C  MOV [R11+0x000C], R1
  51:B018  68F0 0023  MOV REG[0xF0], #0x0023
  51:B01C  58F0       MOV [--R15], R0
> 51:B01E  BD02 C588  SCALL 02:C588
  51:B022  50F2       ADD R15, #0x2
  51:B024  4800       MOV R0, #0x0
```

### `51:B074` in `sub_51_AFBA`

```text
  51:B060  1901       MOVZE R0, RB1
  51:B062  58F0       MOV [--R15], R0
  51:B064  4803       MOV R0, #0x3
  51:B066  58F0       MOV [--R15], R0
  51:B068  BD02 C5DC  SCALL 02:C5DC
  51:B06C  50FC       ADD R15, #0xC
  51:B06E  68F0 0024  MOV REG[0xF0], #0x0024
  51:B072  58F0       MOV [--R15], R0
> 51:B074  BD02 C588  SCALL 02:C588
  51:B078  50F2       ADD R15, #0x2
  51:B07A  4800       MOV R0, #0x0
```

## `02:C5DC`

Call sites: `51:B068`, `51:B0BE`

### `51:B068` in `sub_51_AFBA`

```text
  51:B058  58F4       MOV [--R15], R4
  51:B05A  1413       AND R1, R3
  51:B05C  1402       AND R0, R2
  51:B05E  0913       MOVB RB1, RB3
  51:B060  1901       MOVZE R0, RB1
  51:B062  58F0       MOV [--R15], R0
  51:B064  4803       MOV R0, #0x3
  51:B066  58F0       MOV [--R15], R0
> 51:B068  BD02 C5DC  SCALL 02:C5DC
  51:B06C  50FC       ADD R15, #0xC
  51:B06E  68F0 0024  MOV REG[0xF0], #0x0024
```

### `51:B0BE` in `sub_51_AFBA`

```text
  51:B0AE  58F4       MOV [--R15], R4
  51:B0B0  1413       AND R1, R3
  51:B0B2  1402       AND R0, R2
  51:B0B4  0913       MOVB RB1, RB3
  51:B0B6  1901       MOVZE R0, RB1
  51:B0B8  58F0       MOV [--R15], R0
  51:B0BA  4803       MOV R0, #0x3
  51:B0BC  58F0       MOV [--R15], R0
> 51:B0BE  BD02 C5DC  SCALL 02:C5DC
  51:B0C2  50FC       ADD R15, #0xC
  51:B0C4  385F       MOV R5, [R15++]
```
