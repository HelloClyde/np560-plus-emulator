# NP560+ resident SoC ROM API evidence

- Source listing: `doc/NP560_reachable_code.asm`
- Parsed instructions: 159,362
- Direct calls into code segment 02: 452
- Distinct resident entry points: 27
- Scope: static call-site evidence only; no original ROM bytes are present.

## Entry-point inventory

| Resident entry | Calls | Calling functions | Immediate R15 cleanup | Evidence status |
|---|---:|---:|---|---|
| `03:0030` | 1 | 1 | none immediately | Unclassified |
| `03:4010` | 275 | 16 | `0xA` (5 words) | Unclassified |
| `03:401C` | 6 | 3 | `0xA` (5 words) | Unclassified |
| `03:4068` | 1 | 1 | `0xA` (5 words) | Unclassified |
| `03:407C` | 33 | 4 | `0x8` (4 words) | Unclassified |
| `03:4080` | 15 | 3 | `0x8` (4 words) | Unclassified |
| `03:40B4` | 27 | 4 | `0xA` (5 words) | Unclassified |
| `03:4120` | 6 | 5 | `0x2` (1 words) | Unclassified |
| `03:4124` | 6 | 5 | none immediately | Unclassified |
| `03:4154` | 1 | 1 | `0x2` (1 words) | Unclassified |
| `03:4184` | 1 | 1 | `0x2` (1 words) | Unclassified |
| `03:41A8` | 14 | 5 | `0x8` (4 words) | Unclassified |
| `03:41AC` | 4 | 1 | `0xA` (5 words) | Unclassified |
| `03:41C8` | 10 | 8 | `0x4` (2 words) | Unclassified |
| `03:41F8` | 1 | 1 | none immediately | Unclassified |
| `03:420C` | 1 | 1 | `0x8` (4 words) | Unclassified |
| `03:4214` | 11 | 8 | `0x8` (4 words) | Unclassified |
| `03:4218` | 1 | 1 | `0x8` (4 words) | Unclassified |
| `03:4224` | 8 | 5 | `0x2` (1 words) | Unclassified |
| `03:422C` | 2 | 2 | none immediately | Unclassified |
| `03:431C` | 4 | 1 | `0x2` (1 words) | Unclassified |
| `03:4320` | 4 | 1 | `0x2` (1 words) | Unclassified |
| `03:4324` | 6 | 2 | `0x2` (1 words) | Unclassified |
| `03:4328` | 6 | 2 | `0x2` (1 words) | Unclassified |
| `03:4398` | 1 | 1 | none immediately | Unclassified |
| `03:B548` | 2 | 2 | `0xC` (6 words) | Unclassified |
| `03:E126` | 5 | 2 | none immediately | Unclassified |

## Interpretation constraints

The contexts below establish the call ABI and surrounding control flow. Names such as read, write, erase, and wait remain hypotheses until a reconstructed routine produces the caller-observed results for all call sites.

## `03:0030`

Call sites: `20:0000`

### `20:0000` in `(unlabelled)`

```text
> 20:0000  BD03 0030  SCALL 03:0030
  20:0004  AD33 4F50  SJMP 33:4F50
```

## `03:4010`

Call sites: `29:DB1A`, `29:DB40`, `29:DB80`, `29:DBC0`, `29:DC00`, `29:DC50`, `29:DC9C`, `29:DCE8`, `29:DD34`, `29:DD80`, `29:DDD0`, `29:DE1C`, `29:DE68`, `29:DEB4`, `29:DF00`, `29:DF4C`, `29:DF98`, `29:DFE8`, `29:E034`, `29:E080`, `29:E0CC`, `29:E118`, `29:E168`, `29:E1B4`, `29:E200`, `29:E24C`, `29:E298`, `29:E2E4`, `29:E330`, `29:E37C`, `29:E40C`, `29:E432`, `29:E472`, `29:E4B2`, `29:E4F2`, `29:E532`, `29:E572`, `29:E600`, `29:E64C`, `29:E672`, `29:E698`, `29:E6FE`, `29:E78C`, `29:E7D8`, `29:E84E`, `29:E89A`, `29:E8E6`, `29:E932`, `29:E958`, `29:E9BE`, `29:EAD8`, `29:EB24`, `29:EB70`, `29:EBBC`, `29:EC0C`, `29:EC4C`, `29:EC8C`, `29:ECCC`, `29:ED0C`, `29:ED74`, `29:EDB4`, `29:EDF4`, `29:EE34`, `29:EE74`, `29:EEC4`, `29:EF10`, `29:EF5C`, `29:EFA8`, `29:EFF4`, `29:F040`, `29:F0D0`, `29:F11C`, `29:F168`, `29:F1B4`, `29:F200`, `2C:C066`, `2C:C188`, `2C:C208`, `2C:C2AC`, `2C:C32C`, `2C:C3D0`, `2C:C450`, `2C:C4F4`, `2C:C574`, `2C:C5F4`, `2C:C61A`, `2C:C640`, `2C:C666`, `2C:C68C`, `2C:C6B2`, `2E:733C`, `2E:73C2`, `2E:7468`, `2E:74B8`, `2E:7508`, `2E:7558`, `2E:75A8`, `2E:75F8`, `2E:7648`, `2E:7698`, `2E:76E8`, `2E:7738`, `2E:7788`, `2E:77D8`, `2E:7828`, `2E:7878`, `2E:78C8`, `2E:7918`, `2E:7968`, `2E:79B8`, `2E:7A08`, `2E:7A58`, `2E:7AA8`, `2E:7AF8`, `2E:7B48`, `2E:7B98`, `2E:7BE8`, `2E:7C38`, `2E:7C88`, `2E:7CD8`, `2E:7D28`, `2E:7D78`, `2E:7DC8`, `2E:7E18`, `2E:7E68`, `2E:7EB8`, `2E:7F08`, `2E:7F58`, `2E:7FA8`, `2E:7FF8`, `2E:8048`, `2E:8098`, `2E:80E8`, `2E:8138`, `2E:8188`, `2E:81D8`, `2E:8228`, `2E:8278`, `2E:82C8`, `2E:8318`, `2E:8368`, `2E:83B8`, `2E:8408`, `2E:8458`, `2E:84A8`, `2E:84F8`, `2E:8548`, `2E:8598`, `2E:85E8`, `2E:8638`, `2E:8688`, `2E:86D8`, `2E:8728`, `31:C9AC`, `31:CA2C`, `31:CA7A`, `31:CAA0`, `31:CB3A`, `31:CBE0`, `31:CC86`, `31:CD2C`, `31:CDD2`, `31:CE20`, `31:CE6E`, `31:CE9A`, `31:CF6C`, `31:CFBA`, `31:D008`, `31:D056`, `31:D0A4`, `31:EA0E`, `31:EA34`, `31:EA5A`, `31:EA80`, `31:EAA6`, `31:EACC`, `31:EAF2`, `31:EB18`, `31:EB3E`, `31:EB64`, `31:EB8A`, `31:EBB0`, `31:EBD6`, `31:EBFC`, `31:EC22`, `31:EC48`, `31:EC6E`, `31:EC94`, `31:ECBA`, `31:ECE0`, `31:ED06`, `31:ED2C`, `31:ED52`, `31:ED78`, `31:ED9E`, `31:EDC4`, `31:EDEA`, `31:EE10`, `31:EE36`, `31:EE5C`, `31:EE82`, `31:EEA8`, `31:EECE`, `31:EEF4`, `31:EF1A`, `31:EF40`, `31:EF66`, `31:EF8C`, `31:EFB2`, `31:EFD8`, `31:EFFE`, `31:F024`, `31:F04A`, `31:F070`, `31:F096`, `31:F0BC`, `31:F0E2`, `31:F108`, `31:F12E`, `31:F154`, `31:F17A`, `31:F1A0`, `31:F1C6`, `31:F1EC`, `31:F212`, `31:F238`, `31:F25E`, `31:F284`, `31:F2AA`, `31:F2D0`, `31:F2F6`, `31:F31C`, `31:F342`, `31:F368`, `31:F38E`, `31:F3B4`, `31:F3DA`, `31:F400`, `31:F426`, `31:F44C`, `31:F472`, `31:F498`, `31:F4BE`, `31:F4E4`, `31:F50A`, `31:F530`, `31:F556`, `31:F57C`, `31:F5A2`, `31:F5C8`, `31:F5EE`, `31:F614`, `31:F63A`, `31:F660`, `31:F686`, `31:F6AC`, `31:F6D2`, `31:F6F8`, `32:8B9C`, `32:8C1C`, `32:8C6A`, `32:8C90`, `32:8D2A`, `32:8DD0`, `32:8E76`, `32:8F1C`, `32:8FC2`, `32:9010`, `32:905E`, `32:908A`, `32:915C`, `32:91AA`, `32:91F8`, `32:9246`, `32:9294`

### `29:DB1A` in `sub_29_DB0A`

```text
  29:DB0A  6810 00A4  MOV REG[0x10], #0x00A4
  29:DB0E  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DB12  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DB16  58F1       MOV [--R15], R1
  29:DB18  58F0       MOV [--R15], R0
> 29:DB1A  BD03 4010  SCALL 03:4010
  29:DB1E  50FA       ADD R15, #0xA
  29:DB20  4801       MOV R0, #0x1
  29:DB22  58F0       MOV [--R15], R0
  29:DB24  081B       MOV R1, R11
  29:DB26  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:DB2A  4800       MOV R0, #0x0
  29:DB2C  58F1       MOV [--R15], R1
  29:DB2E  58F0       MOV [--R15], R0
  29:DB30  6810 00A4  MOV REG[0x10], #0x00A4
  29:DB34  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DB38  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DB3C  58F1       MOV [--R15], R1
```

### `29:DB40` in `sub_29_DB0A`

```text
  29:DB24  081B       MOV R1, R11
  29:DB26  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:DB2A  4800       MOV R0, #0x0
  29:DB2C  58F1       MOV [--R15], R1
  29:DB2E  58F0       MOV [--R15], R0
  29:DB30  6810 00A4  MOV REG[0x10], #0x00A4
  29:DB34  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DB38  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DB3C  58F1       MOV [--R15], R1
  29:DB3E  58F0       MOV [--R15], R0
> 29:DB40  BD03 4010  SCALL 03:4010
  29:DB44  50FA       ADD R15, #0xA
  29:DB46  4801       MOV R0, #0x1
  29:DB48  58F0       MOV [--R15], R0
  29:DB4A  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DB4E  0810       MOV R1, R0
  29:DB50  5610       CMP R1, #0x0
  29:DB52  DE03       RJMP SGE, 29:DB5A ; rel +3
  29:DB54  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:DB58  D001       RJMP ALWAYS, 29:DB5C ; rel +1
  29:DB5A  4800       MOV R0, #0x0
  29:DB5C  4C12       SL R1, #0x2
  29:DB5E  5C02       SLOSB R0, #0x2
```

### `29:DB80` in `sub_29_DB0A`

```text
  29:DB64  68F2 0052  MOV REG[0xF2], #0x0052
  29:DB68  1013       ADD R1, R3
  29:DB6A  1102       ADDC R0, R2
  29:DB6C  58F1       MOV [--R15], R1
  29:DB6E  58F0       MOV [--R15], R0
  29:DB70  6810 00A4  MOV REG[0x10], #0x00A4
  29:DB74  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DB78  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DB7C  58F1       MOV [--R15], R1
  29:DB7E  58F0       MOV [--R15], R0
> 29:DB80  BD03 4010  SCALL 03:4010
  29:DB84  50FA       ADD R15, #0xA
  29:DB86  4801       MOV R0, #0x1
  29:DB88  58F0       MOV [--R15], R0
  29:DB8A  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DB8E  0810       MOV R1, R0
  29:DB90  5610       CMP R1, #0x0
  29:DB92  DE03       RJMP SGE, 29:DB9A ; rel +3
  29:DB94  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:DB98  D001       RJMP ALWAYS, 29:DB9C ; rel +1
  29:DB9A  4800       MOV R0, #0x0
  29:DB9C  4C12       SL R1, #0x2
  29:DB9E  5C02       SLOSB R0, #0x2
```

### `29:DBC0` in `sub_29_DB0A`

```text
  29:DBA4  68F2 0052  MOV REG[0xF2], #0x0052
  29:DBA8  1013       ADD R1, R3
  29:DBAA  1102       ADDC R0, R2
  29:DBAC  58F1       MOV [--R15], R1
  29:DBAE  58F0       MOV [--R15], R0
  29:DBB0  6810 00A4  MOV REG[0x10], #0x00A4
  29:DBB4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DBB8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DBBC  58F1       MOV [--R15], R1
  29:DBBE  58F0       MOV [--R15], R0
> 29:DBC0  BD03 4010  SCALL 03:4010
  29:DBC4  50FA       ADD R15, #0xA
  29:DBC6  4802       MOV R0, #0x2
  29:DBC8  58F0       MOV [--R15], R0
  29:DBCA  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DBCE  0810       MOV R1, R0
  29:DBD0  5610       CMP R1, #0x0
  29:DBD2  DE03       RJMP SGE, 29:DBDA ; rel +3
  29:DBD4  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:DBD8  D001       RJMP ALWAYS, 29:DBDC ; rel +1
  29:DBDA  4800       MOV R0, #0x0
  29:DBDC  4C12       SL R1, #0x2
  29:DBDE  5C02       SLOSB R0, #0x2
```

### `29:DC00` in `sub_29_DB0A`

```text
  29:DBE4  68F2 0052  MOV REG[0xF2], #0x0052
  29:DBE8  1013       ADD R1, R3
  29:DBEA  1102       ADDC R0, R2
  29:DBEC  58F1       MOV [--R15], R1
  29:DBEE  58F0       MOV [--R15], R0
  29:DBF0  6810 00A4  MOV REG[0x10], #0x00A4
  29:DBF4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DBF8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DBFC  58F1       MOV [--R15], R1
  29:DBFE  58F0       MOV [--R15], R0
> 29:DC00  BD03 4010  SCALL 03:4010
  29:DC04  50FA       ADD R15, #0xA
  29:DC06  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DC0A  5001       ADD R0, #0x1
  29:DC0C  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DC10  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DC14  5601       CMP R0, #0x1
  29:DC16  AC09 DAEA  AJMP SL, 29:DAEA
  29:DC1A  4800       MOV R0, #0x0
  29:DC1C  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DC20  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DC24  793B FFEE  MOVB RB3, [R11+0xFFEE]
  29:DC28  1913       MOVZE R1, RB3
```

### `29:DC50` in `sub_29_DB0A`

```text
  29:DC34  081B       MOV R1, R11
  29:DC36  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:DC3A  4800       MOV R0, #0x0
  29:DC3C  58F1       MOV [--R15], R1
  29:DC3E  58F0       MOV [--R15], R0
  29:DC40  6810 00A4  MOV REG[0x10], #0x00A4
  29:DC44  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DC48  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DC4C  58F1       MOV [--R15], R1
  29:DC4E  58F0       MOV [--R15], R0
> 29:DC50  BD03 4010  SCALL 03:4010
  29:DC54  50FA       ADD R15, #0xA
  29:DC56  4801       MOV R0, #0x1
  29:DC58  58F0       MOV [--R15], R0
  29:DC5A  4816       MOV R1, #0x6
  29:DC5C  4800       MOV R0, #0x0
  29:DC5E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DC62  5630       CMP R3, #0x0
  29:DC64  DE03       RJMP SGE, 29:DC6C ; rel +3
  29:DC66  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DC6A  D001       RJMP ALWAYS, 29:DC6E ; rel +1
  29:DC6C  4820       MOV R2, #0x0
  29:DC6E  58F3       MOV [--R15], R3
```

### `29:DC9C` in `sub_29_DB0A`

```text
  29:DC80  68F2 0052  MOV REG[0xF2], #0x0052
  29:DC84  1013       ADD R1, R3
  29:DC86  1102       ADDC R0, R2
  29:DC88  58F1       MOV [--R15], R1
  29:DC8A  58F0       MOV [--R15], R0
  29:DC8C  6810 00A4  MOV REG[0x10], #0x00A4
  29:DC90  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DC94  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DC98  58F1       MOV [--R15], R1
  29:DC9A  58F0       MOV [--R15], R0
> 29:DC9C  BD03 4010  SCALL 03:4010
  29:DCA0  50FA       ADD R15, #0xA
  29:DCA2  4802       MOV R0, #0x2
  29:DCA4  58F0       MOV [--R15], R0
  29:DCA6  4816       MOV R1, #0x6
  29:DCA8  4800       MOV R0, #0x0
  29:DCAA  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DCAE  5630       CMP R3, #0x0
  29:DCB0  DE03       RJMP SGE, 29:DCB8 ; rel +3
  29:DCB2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DCB6  D001       RJMP ALWAYS, 29:DCBA ; rel +1
  29:DCB8  4820       MOV R2, #0x0
  29:DCBA  58F3       MOV [--R15], R3
```

### `29:DCE8` in `sub_29_DB0A`

```text
  29:DCCC  68F2 0052  MOV REG[0xF2], #0x0052
  29:DCD0  1013       ADD R1, R3
  29:DCD2  1102       ADDC R0, R2
  29:DCD4  58F1       MOV [--R15], R1
  29:DCD6  58F0       MOV [--R15], R0
  29:DCD8  6810 00A4  MOV REG[0x10], #0x00A4
  29:DCDC  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DCE0  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DCE4  58F1       MOV [--R15], R1
  29:DCE6  58F0       MOV [--R15], R0
> 29:DCE8  BD03 4010  SCALL 03:4010
  29:DCEC  50FA       ADD R15, #0xA
  29:DCEE  4801       MOV R0, #0x1
  29:DCF0  58F0       MOV [--R15], R0
  29:DCF2  4816       MOV R1, #0x6
  29:DCF4  4800       MOV R0, #0x0
  29:DCF6  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DCFA  5630       CMP R3, #0x0
  29:DCFC  DE03       RJMP SGE, 29:DD04 ; rel +3
  29:DCFE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DD02  D001       RJMP ALWAYS, 29:DD06 ; rel +1
  29:DD04  4820       MOV R2, #0x0
  29:DD06  58F3       MOV [--R15], R3
```

### `29:DD34` in `sub_29_DB0A`

```text
  29:DD18  68F2 0052  MOV REG[0xF2], #0x0052
  29:DD1C  1013       ADD R1, R3
  29:DD1E  1102       ADDC R0, R2
  29:DD20  58F1       MOV [--R15], R1
  29:DD22  58F0       MOV [--R15], R0
  29:DD24  6810 00A4  MOV REG[0x10], #0x00A4
  29:DD28  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DD2C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DD30  58F1       MOV [--R15], R1
  29:DD32  58F0       MOV [--R15], R0
> 29:DD34  BD03 4010  SCALL 03:4010
  29:DD38  50FA       ADD R15, #0xA
  29:DD3A  4802       MOV R0, #0x2
  29:DD3C  58F0       MOV [--R15], R0
  29:DD3E  4816       MOV R1, #0x6
  29:DD40  4800       MOV R0, #0x0
  29:DD42  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DD46  5630       CMP R3, #0x0
  29:DD48  DE03       RJMP SGE, 29:DD50 ; rel +3
  29:DD4A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DD4E  D001       RJMP ALWAYS, 29:DD52 ; rel +1
  29:DD50  4820       MOV R2, #0x0
  29:DD52  58F3       MOV [--R15], R3
```

### `29:DD80` in `sub_29_DB0A`

```text
  29:DD64  68F2 0052  MOV REG[0xF2], #0x0052
  29:DD68  1013       ADD R1, R3
  29:DD6A  1102       ADDC R0, R2
  29:DD6C  58F1       MOV [--R15], R1
  29:DD6E  58F0       MOV [--R15], R0
  29:DD70  6810 00A4  MOV REG[0x10], #0x00A4
  29:DD74  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DD78  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DD7C  58F1       MOV [--R15], R1
  29:DD7E  58F0       MOV [--R15], R0
> 29:DD80  BD03 4010  SCALL 03:4010
  29:DD84  50FA       ADD R15, #0xA
  29:DD86  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DD8A  5001       ADD R0, #0x1
  29:DD8C  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DD90  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DD94  5605       CMP R0, #0x5
  29:DD96  AC09 DC20  AJMP SL, 29:DC20
  29:DD9A  4800       MOV R0, #0x0
  29:DD9C  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DDA0  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DDA4  793B FFEF  MOVB RB3, [R11+0xFFEF]
  29:DDA8  1913       MOVZE R1, RB3
```

### `29:DDD0` in `sub_29_DB0A`

```text
  29:DDB4  081B       MOV R1, R11
  29:DDB6  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:DDBA  4800       MOV R0, #0x0
  29:DDBC  58F1       MOV [--R15], R1
  29:DDBE  58F0       MOV [--R15], R0
  29:DDC0  6810 00A4  MOV REG[0x10], #0x00A4
  29:DDC4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DDC8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DDCC  58F1       MOV [--R15], R1
  29:DDCE  58F0       MOV [--R15], R0
> 29:DDD0  BD03 4010  SCALL 03:4010
  29:DDD4  50FA       ADD R15, #0xA
  29:DDD6  4802       MOV R0, #0x2
  29:DDD8  58F0       MOV [--R15], R0
  29:DDDA  481A       MOV R1, #0xA
  29:DDDC  4800       MOV R0, #0x0
  29:DDDE  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DDE2  5630       CMP R3, #0x0
  29:DDE4  DE03       RJMP SGE, 29:DDEC ; rel +3
  29:DDE6  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DDEA  D001       RJMP ALWAYS, 29:DDEE ; rel +1
  29:DDEC  4820       MOV R2, #0x0
  29:DDEE  58F3       MOV [--R15], R3
```

### `29:DE1C` in `sub_29_DB0A`

```text
  29:DE00  68F2 0052  MOV REG[0xF2], #0x0052
  29:DE04  1013       ADD R1, R3
  29:DE06  1102       ADDC R0, R2
  29:DE08  58F1       MOV [--R15], R1
  29:DE0A  58F0       MOV [--R15], R0
  29:DE0C  6810 00A4  MOV REG[0x10], #0x00A4
  29:DE10  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DE14  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DE18  58F1       MOV [--R15], R1
  29:DE1A  58F0       MOV [--R15], R0
> 29:DE1C  BD03 4010  SCALL 03:4010
  29:DE20  50FA       ADD R15, #0xA
  29:DE22  4801       MOV R0, #0x1
  29:DE24  58F0       MOV [--R15], R0
  29:DE26  481A       MOV R1, #0xA
  29:DE28  4800       MOV R0, #0x0
  29:DE2A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DE2E  5630       CMP R3, #0x0
  29:DE30  DE03       RJMP SGE, 29:DE38 ; rel +3
  29:DE32  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DE36  D001       RJMP ALWAYS, 29:DE3A ; rel +1
  29:DE38  4820       MOV R2, #0x0
  29:DE3A  58F3       MOV [--R15], R3
```

### `29:DE68` in `sub_29_DB0A`

```text
  29:DE4C  68F2 0052  MOV REG[0xF2], #0x0052
  29:DE50  1013       ADD R1, R3
  29:DE52  1102       ADDC R0, R2
  29:DE54  58F1       MOV [--R15], R1
  29:DE56  58F0       MOV [--R15], R0
  29:DE58  6810 00A4  MOV REG[0x10], #0x00A4
  29:DE5C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DE60  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DE64  58F1       MOV [--R15], R1
  29:DE66  58F0       MOV [--R15], R0
> 29:DE68  BD03 4010  SCALL 03:4010
  29:DE6C  50FA       ADD R15, #0xA
  29:DE6E  4801       MOV R0, #0x1
  29:DE70  58F0       MOV [--R15], R0
  29:DE72  481A       MOV R1, #0xA
  29:DE74  4800       MOV R0, #0x0
  29:DE76  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DE7A  5630       CMP R3, #0x0
  29:DE7C  DE03       RJMP SGE, 29:DE84 ; rel +3
  29:DE7E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DE82  D001       RJMP ALWAYS, 29:DE86 ; rel +1
  29:DE84  4820       MOV R2, #0x0
  29:DE86  58F3       MOV [--R15], R3
```

### `29:DEB4` in `sub_29_DB0A`

```text
  29:DE98  68F2 0052  MOV REG[0xF2], #0x0052
  29:DE9C  1013       ADD R1, R3
  29:DE9E  1102       ADDC R0, R2
  29:DEA0  58F1       MOV [--R15], R1
  29:DEA2  58F0       MOV [--R15], R0
  29:DEA4  6810 00A4  MOV REG[0x10], #0x00A4
  29:DEA8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DEAC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DEB0  58F1       MOV [--R15], R1
  29:DEB2  58F0       MOV [--R15], R0
> 29:DEB4  BD03 4010  SCALL 03:4010
  29:DEB8  50FA       ADD R15, #0xA
  29:DEBA  4801       MOV R0, #0x1
  29:DEBC  58F0       MOV [--R15], R0
  29:DEBE  481A       MOV R1, #0xA
  29:DEC0  4800       MOV R0, #0x0
  29:DEC2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DEC6  5630       CMP R3, #0x0
  29:DEC8  DE03       RJMP SGE, 29:DED0 ; rel +3
  29:DECA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DECE  D001       RJMP ALWAYS, 29:DED2 ; rel +1
  29:DED0  4820       MOV R2, #0x0
  29:DED2  58F3       MOV [--R15], R3
```

### `29:DF00` in `sub_29_DB0A`

```text
  29:DEE4  68F2 0052  MOV REG[0xF2], #0x0052
  29:DEE8  1013       ADD R1, R3
  29:DEEA  1102       ADDC R0, R2
  29:DEEC  58F1       MOV [--R15], R1
  29:DEEE  58F0       MOV [--R15], R0
  29:DEF0  6810 00A4  MOV REG[0x10], #0x00A4
  29:DEF4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DEF8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DEFC  58F1       MOV [--R15], R1
  29:DEFE  58F0       MOV [--R15], R0
> 29:DF00  BD03 4010  SCALL 03:4010
  29:DF04  50FA       ADD R15, #0xA
  29:DF06  4801       MOV R0, #0x1
  29:DF08  58F0       MOV [--R15], R0
  29:DF0A  481A       MOV R1, #0xA
  29:DF0C  4800       MOV R0, #0x0
  29:DF0E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DF12  5630       CMP R3, #0x0
  29:DF14  DE03       RJMP SGE, 29:DF1C ; rel +3
  29:DF16  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DF1A  D001       RJMP ALWAYS, 29:DF1E ; rel +1
  29:DF1C  4820       MOV R2, #0x0
  29:DF1E  58F3       MOV [--R15], R3
```

### `29:DF4C` in `sub_29_DB0A`

```text
  29:DF30  68F2 0052  MOV REG[0xF2], #0x0052
  29:DF34  1013       ADD R1, R3
  29:DF36  1102       ADDC R0, R2
  29:DF38  58F1       MOV [--R15], R1
  29:DF3A  58F0       MOV [--R15], R0
  29:DF3C  6810 00A4  MOV REG[0x10], #0x00A4
  29:DF40  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DF44  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DF48  58F1       MOV [--R15], R1
  29:DF4A  58F0       MOV [--R15], R0
> 29:DF4C  BD03 4010  SCALL 03:4010
  29:DF50  50FA       ADD R15, #0xA
  29:DF52  4802       MOV R0, #0x2
  29:DF54  58F0       MOV [--R15], R0
  29:DF56  481A       MOV R1, #0xA
  29:DF58  4800       MOV R0, #0x0
  29:DF5A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DF5E  5630       CMP R3, #0x0
  29:DF60  DE03       RJMP SGE, 29:DF68 ; rel +3
  29:DF62  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:DF66  D001       RJMP ALWAYS, 29:DF6A ; rel +1
  29:DF68  4820       MOV R2, #0x0
  29:DF6A  58F3       MOV [--R15], R3
```

### `29:DF98` in `sub_29_DB0A`

```text
  29:DF7C  68F2 0052  MOV REG[0xF2], #0x0052
  29:DF80  1013       ADD R1, R3
  29:DF82  1102       ADDC R0, R2
  29:DF84  58F1       MOV [--R15], R1
  29:DF86  58F0       MOV [--R15], R0
  29:DF88  6810 00A4  MOV REG[0x10], #0x00A4
  29:DF8C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DF90  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DF94  58F1       MOV [--R15], R1
  29:DF96  58F0       MOV [--R15], R0
> 29:DF98  BD03 4010  SCALL 03:4010
  29:DF9C  50FA       ADD R15, #0xA
  29:DF9E  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DFA2  5001       ADD R0, #0x1
  29:DFA4  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DFA8  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DFAC  5602       CMP R0, #0x2
  29:DFAE  AC09 DDA0  AJMP SL, 29:DDA0
  29:DFB2  4800       MOV R0, #0x0
  29:DFB4  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:DFB8  780B FFFE  MOV R0, [R11+0xFFFE]
  29:DFBC  793B FFF0  MOVB RB3, [R11+0xFFF0]
  29:DFC0  1913       MOVZE R1, RB3
```

### `29:DFE8` in `sub_29_DB0A`

```text
  29:DFCC  081B       MOV R1, R11
  29:DFCE  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:DFD2  4800       MOV R0, #0x0
  29:DFD4  58F1       MOV [--R15], R1
  29:DFD6  58F0       MOV [--R15], R0
  29:DFD8  6810 00A4  MOV REG[0x10], #0x00A4
  29:DFDC  88F0 7992  MOV REG[0xF0], [0x7992]
  29:DFE0  88F1 7994  MOV REG[0xF1], [0x7994]
  29:DFE4  58F1       MOV [--R15], R1
  29:DFE6  58F0       MOV [--R15], R0
> 29:DFE8  BD03 4010  SCALL 03:4010
  29:DFEC  50FA       ADD R15, #0xA
  29:DFEE  4801       MOV R0, #0x1
  29:DFF0  58F0       MOV [--R15], R0
  29:DFF2  4816       MOV R1, #0x6
  29:DFF4  4800       MOV R0, #0x0
  29:DFF6  783B FFFE  MOV R3, [R11+0xFFFE]
  29:DFFA  5630       CMP R3, #0x0
  29:DFFC  DE03       RJMP SGE, 29:E004 ; rel +3
  29:DFFE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E002  D001       RJMP ALWAYS, 29:E006 ; rel +1
  29:E004  4820       MOV R2, #0x0
  29:E006  58F3       MOV [--R15], R3
```

### `29:E034` in `sub_29_DB0A`

```text
  29:E018  68F2 0052  MOV REG[0xF2], #0x0052
  29:E01C  1013       ADD R1, R3
  29:E01E  1102       ADDC R0, R2
  29:E020  58F1       MOV [--R15], R1
  29:E022  58F0       MOV [--R15], R0
  29:E024  6810 00A4  MOV REG[0x10], #0x00A4
  29:E028  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E02C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E030  58F1       MOV [--R15], R1
  29:E032  58F0       MOV [--R15], R0
> 29:E034  BD03 4010  SCALL 03:4010
  29:E038  50FA       ADD R15, #0xA
  29:E03A  4801       MOV R0, #0x1
  29:E03C  58F0       MOV [--R15], R0
  29:E03E  4816       MOV R1, #0x6
  29:E040  4800       MOV R0, #0x0
  29:E042  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E046  5630       CMP R3, #0x0
  29:E048  DE03       RJMP SGE, 29:E050 ; rel +3
  29:E04A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E04E  D001       RJMP ALWAYS, 29:E052 ; rel +1
  29:E050  4820       MOV R2, #0x0
  29:E052  58F3       MOV [--R15], R3
```

### `29:E080` in `sub_29_DB0A`

```text
  29:E064  68F2 0052  MOV REG[0xF2], #0x0052
  29:E068  1013       ADD R1, R3
  29:E06A  1102       ADDC R0, R2
  29:E06C  58F1       MOV [--R15], R1
  29:E06E  58F0       MOV [--R15], R0
  29:E070  6810 00A4  MOV REG[0x10], #0x00A4
  29:E074  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E078  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E07C  58F1       MOV [--R15], R1
  29:E07E  58F0       MOV [--R15], R0
> 29:E080  BD03 4010  SCALL 03:4010
  29:E084  50FA       ADD R15, #0xA
  29:E086  4801       MOV R0, #0x1
  29:E088  58F0       MOV [--R15], R0
  29:E08A  4816       MOV R1, #0x6
  29:E08C  4800       MOV R0, #0x0
  29:E08E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E092  5630       CMP R3, #0x0
  29:E094  DE03       RJMP SGE, 29:E09C ; rel +3
  29:E096  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E09A  D001       RJMP ALWAYS, 29:E09E ; rel +1
  29:E09C  4820       MOV R2, #0x0
  29:E09E  58F3       MOV [--R15], R3
```

### `29:E0CC` in `sub_29_DB0A`

```text
  29:E0B0  68F2 0052  MOV REG[0xF2], #0x0052
  29:E0B4  1013       ADD R1, R3
  29:E0B6  1102       ADDC R0, R2
  29:E0B8  58F1       MOV [--R15], R1
  29:E0BA  58F0       MOV [--R15], R0
  29:E0BC  6810 00A4  MOV REG[0x10], #0x00A4
  29:E0C0  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E0C4  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E0C8  58F1       MOV [--R15], R1
  29:E0CA  58F0       MOV [--R15], R0
> 29:E0CC  BD03 4010  SCALL 03:4010
  29:E0D0  50FA       ADD R15, #0xA
  29:E0D2  4802       MOV R0, #0x2
  29:E0D4  58F0       MOV [--R15], R0
  29:E0D6  4816       MOV R1, #0x6
  29:E0D8  4800       MOV R0, #0x0
  29:E0DA  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E0DE  5630       CMP R3, #0x0
  29:E0E0  DE03       RJMP SGE, 29:E0E8 ; rel +3
  29:E0E2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E0E6  D001       RJMP ALWAYS, 29:E0EA ; rel +1
  29:E0E8  4820       MOV R2, #0x0
  29:E0EA  58F3       MOV [--R15], R3
```

### `29:E118` in `sub_29_DB0A`

```text
  29:E0FC  68F2 0052  MOV REG[0xF2], #0x0052
  29:E100  1013       ADD R1, R3
  29:E102  1102       ADDC R0, R2
  29:E104  58F1       MOV [--R15], R1
  29:E106  58F0       MOV [--R15], R0
  29:E108  6810 00A4  MOV REG[0x10], #0x00A4
  29:E10C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E110  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E114  58F1       MOV [--R15], R1
  29:E116  58F0       MOV [--R15], R0
> 29:E118  BD03 4010  SCALL 03:4010
  29:E11C  50FA       ADD R15, #0xA
  29:E11E  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E122  5001       ADD R0, #0x1
  29:E124  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:E128  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E12C  5603       CMP R0, #0x3
  29:E12E  AC09 DFB8  AJMP SL, 29:DFB8
  29:E132  4800       MOV R0, #0x0
  29:E134  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:E138  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E13C  793B FFF1  MOVB RB3, [R11+0xFFF1]
  29:E140  1913       MOVZE R1, RB3
```

### `29:E168` in `sub_29_DB0A`

```text
  29:E14C  081B       MOV R1, R11
  29:E14E  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E152  4800       MOV R0, #0x0
  29:E154  58F1       MOV [--R15], R1
  29:E156  58F0       MOV [--R15], R0
  29:E158  6810 00A4  MOV REG[0x10], #0x00A4
  29:E15C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E160  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E164  58F1       MOV [--R15], R1
  29:E166  58F0       MOV [--R15], R0
> 29:E168  BD03 4010  SCALL 03:4010
  29:E16C  50FA       ADD R15, #0xA
  29:E16E  4802       MOV R0, #0x2
  29:E170  58F0       MOV [--R15], R0
  29:E172  481C       MOV R1, #0xC
  29:E174  4800       MOV R0, #0x0
  29:E176  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E17A  5630       CMP R3, #0x0
  29:E17C  DE03       RJMP SGE, 29:E184 ; rel +3
  29:E17E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E182  D001       RJMP ALWAYS, 29:E186 ; rel +1
  29:E184  4820       MOV R2, #0x0
  29:E186  58F3       MOV [--R15], R3
```

### `29:E1B4` in `sub_29_DB0A`

```text
  29:E198  68F2 0052  MOV REG[0xF2], #0x0052
  29:E19C  1013       ADD R1, R3
  29:E19E  1102       ADDC R0, R2
  29:E1A0  58F1       MOV [--R15], R1
  29:E1A2  58F0       MOV [--R15], R0
  29:E1A4  6810 00A4  MOV REG[0x10], #0x00A4
  29:E1A8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E1AC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E1B0  58F1       MOV [--R15], R1
  29:E1B2  58F0       MOV [--R15], R0
> 29:E1B4  BD03 4010  SCALL 03:4010
  29:E1B8  50FA       ADD R15, #0xA
  29:E1BA  4802       MOV R0, #0x2
  29:E1BC  58F0       MOV [--R15], R0
  29:E1BE  481C       MOV R1, #0xC
  29:E1C0  4800       MOV R0, #0x0
  29:E1C2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E1C6  5630       CMP R3, #0x0
  29:E1C8  DE03       RJMP SGE, 29:E1D0 ; rel +3
  29:E1CA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E1CE  D001       RJMP ALWAYS, 29:E1D2 ; rel +1
  29:E1D0  4820       MOV R2, #0x0
  29:E1D2  58F3       MOV [--R15], R3
```

### `29:E200` in `sub_29_DB0A`

```text
  29:E1E4  68F2 0052  MOV REG[0xF2], #0x0052
  29:E1E8  1013       ADD R1, R3
  29:E1EA  1102       ADDC R0, R2
  29:E1EC  58F1       MOV [--R15], R1
  29:E1EE  58F0       MOV [--R15], R0
  29:E1F0  6810 00A4  MOV REG[0x10], #0x00A4
  29:E1F4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E1F8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E1FC  58F1       MOV [--R15], R1
  29:E1FE  58F0       MOV [--R15], R0
> 29:E200  BD03 4010  SCALL 03:4010
  29:E204  50FA       ADD R15, #0xA
  29:E206  4801       MOV R0, #0x1
  29:E208  58F0       MOV [--R15], R0
  29:E20A  481C       MOV R1, #0xC
  29:E20C  4800       MOV R0, #0x0
  29:E20E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E212  5630       CMP R3, #0x0
  29:E214  DE03       RJMP SGE, 29:E21C ; rel +3
  29:E216  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E21A  D001       RJMP ALWAYS, 29:E21E ; rel +1
  29:E21C  4820       MOV R2, #0x0
  29:E21E  58F3       MOV [--R15], R3
```

### `29:E24C` in `sub_29_DB0A`

```text
  29:E230  68F2 0052  MOV REG[0xF2], #0x0052
  29:E234  1013       ADD R1, R3
  29:E236  1102       ADDC R0, R2
  29:E238  58F1       MOV [--R15], R1
  29:E23A  58F0       MOV [--R15], R0
  29:E23C  6810 00A4  MOV REG[0x10], #0x00A4
  29:E240  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E244  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E248  58F1       MOV [--R15], R1
  29:E24A  58F0       MOV [--R15], R0
> 29:E24C  BD03 4010  SCALL 03:4010
  29:E250  50FA       ADD R15, #0xA
  29:E252  4802       MOV R0, #0x2
  29:E254  58F0       MOV [--R15], R0
  29:E256  481C       MOV R1, #0xC
  29:E258  4800       MOV R0, #0x0
  29:E25A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E25E  5630       CMP R3, #0x0
  29:E260  DE03       RJMP SGE, 29:E268 ; rel +3
  29:E262  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E266  D001       RJMP ALWAYS, 29:E26A ; rel +1
  29:E268  4820       MOV R2, #0x0
  29:E26A  58F3       MOV [--R15], R3
```

### `29:E298` in `sub_29_DB0A`

```text
  29:E27C  68F2 0052  MOV REG[0xF2], #0x0052
  29:E280  1013       ADD R1, R3
  29:E282  1102       ADDC R0, R2
  29:E284  58F1       MOV [--R15], R1
  29:E286  58F0       MOV [--R15], R0
  29:E288  6810 00A4  MOV REG[0x10], #0x00A4
  29:E28C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E290  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E294  58F1       MOV [--R15], R1
  29:E296  58F0       MOV [--R15], R0
> 29:E298  BD03 4010  SCALL 03:4010
  29:E29C  50FA       ADD R15, #0xA
  29:E29E  4801       MOV R0, #0x1
  29:E2A0  58F0       MOV [--R15], R0
  29:E2A2  481C       MOV R1, #0xC
  29:E2A4  4800       MOV R0, #0x0
  29:E2A6  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E2AA  5630       CMP R3, #0x0
  29:E2AC  DE03       RJMP SGE, 29:E2B4 ; rel +3
  29:E2AE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E2B2  D001       RJMP ALWAYS, 29:E2B6 ; rel +1
  29:E2B4  4820       MOV R2, #0x0
  29:E2B6  58F3       MOV [--R15], R3
```

### `29:E2E4` in `sub_29_DB0A`

```text
  29:E2C8  68F2 0052  MOV REG[0xF2], #0x0052
  29:E2CC  1013       ADD R1, R3
  29:E2CE  1102       ADDC R0, R2
  29:E2D0  58F1       MOV [--R15], R1
  29:E2D2  58F0       MOV [--R15], R0
  29:E2D4  6810 00A4  MOV REG[0x10], #0x00A4
  29:E2D8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E2DC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E2E0  58F1       MOV [--R15], R1
  29:E2E2  58F0       MOV [--R15], R0
> 29:E2E4  BD03 4010  SCALL 03:4010
  29:E2E8  50FA       ADD R15, #0xA
  29:E2EA  4801       MOV R0, #0x1
  29:E2EC  58F0       MOV [--R15], R0
  29:E2EE  481C       MOV R1, #0xC
  29:E2F0  4800       MOV R0, #0x0
  29:E2F2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E2F6  5630       CMP R3, #0x0
  29:E2F8  DE03       RJMP SGE, 29:E300 ; rel +3
  29:E2FA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E2FE  D001       RJMP ALWAYS, 29:E302 ; rel +1
  29:E300  4820       MOV R2, #0x0
  29:E302  58F3       MOV [--R15], R3
```

### `29:E330` in `sub_29_DB0A`

```text
  29:E314  68F2 0052  MOV REG[0xF2], #0x0052
  29:E318  1013       ADD R1, R3
  29:E31A  1102       ADDC R0, R2
  29:E31C  58F1       MOV [--R15], R1
  29:E31E  58F0       MOV [--R15], R0
  29:E320  6810 00A4  MOV REG[0x10], #0x00A4
  29:E324  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E328  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E32C  58F1       MOV [--R15], R1
  29:E32E  58F0       MOV [--R15], R0
> 29:E330  BD03 4010  SCALL 03:4010
  29:E334  50FA       ADD R15, #0xA
  29:E336  4802       MOV R0, #0x2
  29:E338  58F0       MOV [--R15], R0
  29:E33A  481C       MOV R1, #0xC
  29:E33C  4800       MOV R0, #0x0
  29:E33E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E342  5630       CMP R3, #0x0
  29:E344  DE03       RJMP SGE, 29:E34C ; rel +3
  29:E346  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E34A  D001       RJMP ALWAYS, 29:E34E ; rel +1
  29:E34C  4820       MOV R2, #0x0
  29:E34E  58F3       MOV [--R15], R3
```

### `29:E37C` in `sub_29_DB0A`

```text
  29:E360  68F2 0052  MOV REG[0xF2], #0x0052
  29:E364  1013       ADD R1, R3
  29:E366  1102       ADDC R0, R2
  29:E368  58F1       MOV [--R15], R1
  29:E36A  58F0       MOV [--R15], R0
  29:E36C  6810 00A4  MOV REG[0x10], #0x00A4
  29:E370  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E374  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E378  58F1       MOV [--R15], R1
  29:E37A  58F0       MOV [--R15], R0
> 29:E37C  BD03 4010  SCALL 03:4010
  29:E380  50FA       ADD R15, #0xA
  29:E382  AC00 E3C2  AJMP ALWAYS, 29:E3C2
  29:E386  481C       MOV R1, #0xC
  29:E388  4800       MOV R0, #0x0
  29:E38A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E38E  5630       CMP R3, #0x0
  29:E390  DE03       RJMP SGE, 29:E398 ; rel +3
  29:E392  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E396  D001       RJMP ALWAYS, 29:E39A ; rel +1
  29:E398  4820       MOV R2, #0x0
  29:E39A  58F3       MOV [--R15], R3
  29:E39C  58F2       MOV [--R15], R2
```

### `29:E40C` in `sub_29_DB0A`

```text
  29:E3F0  081B       MOV R1, R11
  29:E3F2  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E3F6  4800       MOV R0, #0x0
  29:E3F8  58F1       MOV [--R15], R1
  29:E3FA  58F0       MOV [--R15], R0
  29:E3FC  6810 00A4  MOV REG[0x10], #0x00A4
  29:E400  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E404  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E408  58F1       MOV [--R15], R1
  29:E40A  58F0       MOV [--R15], R0
> 29:E40C  BD03 4010  SCALL 03:4010
  29:E410  50FA       ADD R15, #0xA
  29:E412  4802       MOV R0, #0x2
  29:E414  58F0       MOV [--R15], R0
  29:E416  081B       MOV R1, R11
  29:E418  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E41C  4800       MOV R0, #0x0
  29:E41E  58F1       MOV [--R15], R1
  29:E420  58F0       MOV [--R15], R0
  29:E422  6810 00A4  MOV REG[0x10], #0x00A4
  29:E426  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E42A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E42E  58F1       MOV [--R15], R1
```

### `29:E432` in `sub_29_DB0A`

```text
  29:E416  081B       MOV R1, R11
  29:E418  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E41C  4800       MOV R0, #0x0
  29:E41E  58F1       MOV [--R15], R1
  29:E420  58F0       MOV [--R15], R0
  29:E422  6810 00A4  MOV REG[0x10], #0x00A4
  29:E426  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E42A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E42E  58F1       MOV [--R15], R1
  29:E430  58F0       MOV [--R15], R0
> 29:E432  BD03 4010  SCALL 03:4010
  29:E436  50FA       ADD R15, #0xA
  29:E438  4801       MOV R0, #0x1
  29:E43A  58F0       MOV [--R15], R0
  29:E43C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E440  0810       MOV R1, R0
  29:E442  5610       CMP R1, #0x0
  29:E444  DE03       RJMP SGE, 29:E44C ; rel +3
  29:E446  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E44A  D001       RJMP ALWAYS, 29:E44E ; rel +1
  29:E44C  4800       MOV R0, #0x0
  29:E44E  4C13       SL R1, #0x3
  29:E450  5C03       SLOSB R0, #0x3
```

### `29:E472` in `sub_29_DB0A`

```text
  29:E456  68F2 0052  MOV REG[0xF2], #0x0052
  29:E45A  1013       ADD R1, R3
  29:E45C  1102       ADDC R0, R2
  29:E45E  58F1       MOV [--R15], R1
  29:E460  58F0       MOV [--R15], R0
  29:E462  6810 00A4  MOV REG[0x10], #0x00A4
  29:E466  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E46A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E46E  58F1       MOV [--R15], R1
  29:E470  58F0       MOV [--R15], R0
> 29:E472  BD03 4010  SCALL 03:4010
  29:E476  50FA       ADD R15, #0xA
  29:E478  4801       MOV R0, #0x1
  29:E47A  58F0       MOV [--R15], R0
  29:E47C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E480  0810       MOV R1, R0
  29:E482  5610       CMP R1, #0x0
  29:E484  DE03       RJMP SGE, 29:E48C ; rel +3
  29:E486  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E48A  D001       RJMP ALWAYS, 29:E48E ; rel +1
  29:E48C  4800       MOV R0, #0x0
  29:E48E  4C13       SL R1, #0x3
  29:E490  5C03       SLOSB R0, #0x3
```

### `29:E4B2` in `sub_29_DB0A`

```text
  29:E496  68F2 0052  MOV REG[0xF2], #0x0052
  29:E49A  1013       ADD R1, R3
  29:E49C  1102       ADDC R0, R2
  29:E49E  58F1       MOV [--R15], R1
  29:E4A0  58F0       MOV [--R15], R0
  29:E4A2  6810 00A4  MOV REG[0x10], #0x00A4
  29:E4A6  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E4AA  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E4AE  58F1       MOV [--R15], R1
  29:E4B0  58F0       MOV [--R15], R0
> 29:E4B2  BD03 4010  SCALL 03:4010
  29:E4B6  50FA       ADD R15, #0xA
  29:E4B8  4802       MOV R0, #0x2
  29:E4BA  58F0       MOV [--R15], R0
  29:E4BC  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E4C0  0810       MOV R1, R0
  29:E4C2  5610       CMP R1, #0x0
  29:E4C4  DE03       RJMP SGE, 29:E4CC ; rel +3
  29:E4C6  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E4CA  D001       RJMP ALWAYS, 29:E4CE ; rel +1
  29:E4CC  4800       MOV R0, #0x0
  29:E4CE  4C13       SL R1, #0x3
  29:E4D0  5C03       SLOSB R0, #0x3
```

### `29:E4F2` in `sub_29_DB0A`

```text
  29:E4D6  68F2 0052  MOV REG[0xF2], #0x0052
  29:E4DA  1013       ADD R1, R3
  29:E4DC  1102       ADDC R0, R2
  29:E4DE  58F1       MOV [--R15], R1
  29:E4E0  58F0       MOV [--R15], R0
  29:E4E2  6810 00A4  MOV REG[0x10], #0x00A4
  29:E4E6  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E4EA  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E4EE  58F1       MOV [--R15], R1
  29:E4F0  58F0       MOV [--R15], R0
> 29:E4F2  BD03 4010  SCALL 03:4010
  29:E4F6  50FA       ADD R15, #0xA
  29:E4F8  4801       MOV R0, #0x1
  29:E4FA  58F0       MOV [--R15], R0
  29:E4FC  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E500  0810       MOV R1, R0
  29:E502  5610       CMP R1, #0x0
  29:E504  DE03       RJMP SGE, 29:E50C ; rel +3
  29:E506  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E50A  D001       RJMP ALWAYS, 29:E50E ; rel +1
  29:E50C  4800       MOV R0, #0x0
  29:E50E  4C13       SL R1, #0x3
  29:E510  5C03       SLOSB R0, #0x3
```

### `29:E532` in `sub_29_DB0A`

```text
  29:E516  68F2 0052  MOV REG[0xF2], #0x0052
  29:E51A  1013       ADD R1, R3
  29:E51C  1102       ADDC R0, R2
  29:E51E  58F1       MOV [--R15], R1
  29:E520  58F0       MOV [--R15], R0
  29:E522  6810 00A4  MOV REG[0x10], #0x00A4
  29:E526  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E52A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E52E  58F1       MOV [--R15], R1
  29:E530  58F0       MOV [--R15], R0
> 29:E532  BD03 4010  SCALL 03:4010
  29:E536  50FA       ADD R15, #0xA
  29:E538  4802       MOV R0, #0x2
  29:E53A  58F0       MOV [--R15], R0
  29:E53C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E540  0810       MOV R1, R0
  29:E542  5610       CMP R1, #0x0
  29:E544  DE03       RJMP SGE, 29:E54C ; rel +3
  29:E546  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E54A  D001       RJMP ALWAYS, 29:E54E ; rel +1
  29:E54C  4800       MOV R0, #0x0
  29:E54E  4C13       SL R1, #0x3
  29:E550  5C03       SLOSB R0, #0x3
```

### `29:E572` in `sub_29_E552`

```text
  29:E556  68F2 0052  MOV REG[0xF2], #0x0052
  29:E55A  1013       ADD R1, R3
  29:E55C  1102       ADDC R0, R2
  29:E55E  58F1       MOV [--R15], R1
  29:E560  58F0       MOV [--R15], R0
  29:E562  6810 00A4  MOV REG[0x10], #0x00A4
  29:E566  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E56A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E56E  58F1       MOV [--R15], R1
  29:E570  58F0       MOV [--R15], R0
> 29:E572  BD03 4010  SCALL 03:4010
  29:E576  50FA       ADD R15, #0xA
  29:E578  AC00 E5B6  AJMP ALWAYS, 29:E5B6
  29:E57C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E580  0810       MOV R1, R0
  29:E582  5610       CMP R1, #0x0
  29:E584  DE03       RJMP SGE, 29:E58C ; rel +3
  29:E586  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:E58A  D001       RJMP ALWAYS, 29:E58E ; rel +1
  29:E58C  4800       MOV R0, #0x0
  29:E58E  4C13       SL R1, #0x3
  29:E590  5C03       SLOSB R0, #0x3
  29:E592  68F3 77FC  MOV REG[0xF3], #0x77FC
```

### `29:E600` in `sub_29_E552`

```text
  29:E5E4  081B       MOV R1, R11
  29:E5E6  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E5EA  4800       MOV R0, #0x0
  29:E5EC  58F1       MOV [--R15], R1
  29:E5EE  58F0       MOV [--R15], R0
  29:E5F0  6810 00A4  MOV REG[0x10], #0x00A4
  29:E5F4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E5F8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E5FC  58F1       MOV [--R15], R1
  29:E5FE  58F0       MOV [--R15], R0
> 29:E600  BD03 4010  SCALL 03:4010
  29:E604  50FA       ADD R15, #0xA
  29:E606  4801       MOV R0, #0x1
  29:E608  58F0       MOV [--R15], R0
  29:E60A  481A       MOV R1, #0xA
  29:E60C  4800       MOV R0, #0x0
  29:E60E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E612  5630       CMP R3, #0x0
  29:E614  DE03       RJMP SGE, 29:E61C ; rel +3
  29:E616  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E61A  D001       RJMP ALWAYS, 29:E61E ; rel +1
  29:E61C  4820       MOV R2, #0x0
  29:E61E  58F3       MOV [--R15], R3
```

### `29:E64C` in `sub_29_E552`

```text
  29:E630  68F2 0052  MOV REG[0xF2], #0x0052
  29:E634  1013       ADD R1, R3
  29:E636  1102       ADDC R0, R2
  29:E638  58F1       MOV [--R15], R1
  29:E63A  58F0       MOV [--R15], R0
  29:E63C  6810 00A4  MOV REG[0x10], #0x00A4
  29:E640  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E644  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E648  58F1       MOV [--R15], R1
  29:E64A  58F0       MOV [--R15], R0
> 29:E64C  BD03 4010  SCALL 03:4010
  29:E650  50FA       ADD R15, #0xA
  29:E652  4801       MOV R0, #0x1
  29:E654  58F0       MOV [--R15], R0
  29:E656  081B       MOV R1, R11
  29:E658  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E65C  4800       MOV R0, #0x0
  29:E65E  58F1       MOV [--R15], R1
  29:E660  58F0       MOV [--R15], R0
  29:E662  6810 00A4  MOV REG[0x10], #0x00A4
  29:E666  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E66A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E66E  58F1       MOV [--R15], R1
```

### `29:E672` in `sub_29_E552`

```text
  29:E656  081B       MOV R1, R11
  29:E658  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:E65C  4800       MOV R0, #0x0
  29:E65E  58F1       MOV [--R15], R1
  29:E660  58F0       MOV [--R15], R0
  29:E662  6810 00A4  MOV REG[0x10], #0x00A4
  29:E666  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E66A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E66E  58F1       MOV [--R15], R1
  29:E670  58F0       MOV [--R15], R0
> 29:E672  BD03 4010  SCALL 03:4010
  29:E676  50FA       ADD R15, #0xA
  29:E678  4801       MOV R0, #0x1
  29:E67A  58F0       MOV [--R15], R0
  29:E67C  081B       MOV R1, R11
  29:E67E  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E682  4800       MOV R0, #0x0
  29:E684  58F1       MOV [--R15], R1
  29:E686  58F0       MOV [--R15], R0
  29:E688  6810 00A4  MOV REG[0x10], #0x00A4
  29:E68C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E690  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E694  58F1       MOV [--R15], R1
```

### `29:E698` in `sub_29_E552`

```text
  29:E67C  081B       MOV R1, R11
  29:E67E  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E682  4800       MOV R0, #0x0
  29:E684  58F1       MOV [--R15], R1
  29:E686  58F0       MOV [--R15], R0
  29:E688  6810 00A4  MOV REG[0x10], #0x00A4
  29:E68C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E690  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E694  58F1       MOV [--R15], R1
  29:E696  58F0       MOV [--R15], R0
> 29:E698  BD03 4010  SCALL 03:4010
  29:E69C  50FA       ADD R15, #0xA
  29:E69E  481A       MOV R1, #0xA
  29:E6A0  4800       MOV R0, #0x0
  29:E6A2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E6A6  5630       CMP R3, #0x0
  29:E6A8  DE03       RJMP SGE, 29:E6B0 ; rel +3
  29:E6AA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E6AE  D001       RJMP ALWAYS, 29:E6B2 ; rel +1
  29:E6B0  4820       MOV R2, #0x0
  29:E6B2  58F3       MOV [--R15], R3
  29:E6B4  58F2       MOV [--R15], R2
  29:E6B6  58F1       MOV [--R15], R1
```

### `29:E6FE` in `sub_29_E552`

```text
  29:E6E2  081B       MOV R1, R11
  29:E6E4  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E6E8  4800       MOV R0, #0x0
  29:E6EA  58F1       MOV [--R15], R1
  29:E6EC  58F0       MOV [--R15], R0
  29:E6EE  6810 00A4  MOV REG[0x10], #0x00A4
  29:E6F2  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E6F6  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E6FA  58F1       MOV [--R15], R1
  29:E6FC  58F0       MOV [--R15], R0
> 29:E6FE  BD03 4010  SCALL 03:4010
  29:E702  50FA       ADD R15, #0xA
  29:E704  481A       MOV R1, #0xA
  29:E706  4800       MOV R0, #0x0
  29:E708  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E70C  5630       CMP R3, #0x0
  29:E70E  DE03       RJMP SGE, 29:E716 ; rel +3
  29:E710  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E714  D001       RJMP ALWAYS, 29:E718 ; rel +1
  29:E716  4820       MOV R2, #0x0
  29:E718  58F3       MOV [--R15], R3
  29:E71A  58F2       MOV [--R15], R2
  29:E71C  58F1       MOV [--R15], R1
```

### `29:E78C` in `sub_29_E552`

```text
  29:E770  68F2 0052  MOV REG[0xF2], #0x0052
  29:E774  1013       ADD R1, R3
  29:E776  1102       ADDC R0, R2
  29:E778  58F1       MOV [--R15], R1
  29:E77A  58F0       MOV [--R15], R0
  29:E77C  6810 00A4  MOV REG[0x10], #0x00A4
  29:E780  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E784  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E788  58F1       MOV [--R15], R1
  29:E78A  58F0       MOV [--R15], R0
> 29:E78C  BD03 4010  SCALL 03:4010
  29:E790  50FA       ADD R15, #0xA
  29:E792  4802       MOV R0, #0x2
  29:E794  58F0       MOV [--R15], R0
  29:E796  481A       MOV R1, #0xA
  29:E798  4800       MOV R0, #0x0
  29:E79A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E79E  5630       CMP R3, #0x0
  29:E7A0  DE03       RJMP SGE, 29:E7A8 ; rel +3
  29:E7A2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E7A6  D001       RJMP ALWAYS, 29:E7AA ; rel +1
  29:E7A8  4820       MOV R2, #0x0
  29:E7AA  58F3       MOV [--R15], R3
```

### `29:E7D8` in `sub_29_E552`

```text
  29:E7BC  68F2 0052  MOV REG[0xF2], #0x0052
  29:E7C0  1013       ADD R1, R3
  29:E7C2  1102       ADDC R0, R2
  29:E7C4  58F1       MOV [--R15], R1
  29:E7C6  58F0       MOV [--R15], R0
  29:E7C8  6810 00A4  MOV REG[0x10], #0x00A4
  29:E7CC  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E7D0  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E7D4  58F1       MOV [--R15], R1
  29:E7D6  58F0       MOV [--R15], R0
> 29:E7D8  BD03 4010  SCALL 03:4010
  29:E7DC  50FA       ADD R15, #0xA
  29:E7DE  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E7E2  5001       ADD R0, #0x1
  29:E7E4  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:E7E8  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E7EC  5604       CMP R0, #0x4
  29:E7EE  AC09 E5D0  AJMP SL, 29:E5D0
  29:E7F2  4800       MOV R0, #0x0
  29:E7F4  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:E7F8  780B FFFE  MOV R0, [R11+0xFFFE]
  29:E7FC  793B FFF4  MOVB RB3, [R11+0xFFF4]
  29:E800  1913       MOVZE R1, RB3
```

### `29:E84E` in `sub_29_E552`

```text
  29:E832  68F2 0052  MOV REG[0xF2], #0x0052
  29:E836  1013       ADD R1, R3
  29:E838  1102       ADDC R0, R2
  29:E83A  58F1       MOV [--R15], R1
  29:E83C  58F0       MOV [--R15], R0
  29:E83E  6810 00A4  MOV REG[0x10], #0x00A4
  29:E842  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E846  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E84A  58F1       MOV [--R15], R1
  29:E84C  58F0       MOV [--R15], R0
> 29:E84E  BD03 4010  SCALL 03:4010
  29:E852  50FA       ADD R15, #0xA
  29:E854  4802       MOV R0, #0x2
  29:E856  58F0       MOV [--R15], R0
  29:E858  481E       MOV R1, #0xE
  29:E85A  4800       MOV R0, #0x0
  29:E85C  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E860  5630       CMP R3, #0x0
  29:E862  DE03       RJMP SGE, 29:E86A ; rel +3
  29:E864  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E868  D001       RJMP ALWAYS, 29:E86C ; rel +1
  29:E86A  4820       MOV R2, #0x0
  29:E86C  58F3       MOV [--R15], R3
```

### `29:E89A` in `sub_29_E552`

```text
  29:E87E  68F2 0052  MOV REG[0xF2], #0x0052
  29:E882  1013       ADD R1, R3
  29:E884  1102       ADDC R0, R2
  29:E886  58F1       MOV [--R15], R1
  29:E888  58F0       MOV [--R15], R0
  29:E88A  6810 00A4  MOV REG[0x10], #0x00A4
  29:E88E  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E892  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E896  58F1       MOV [--R15], R1
  29:E898  58F0       MOV [--R15], R0
> 29:E89A  BD03 4010  SCALL 03:4010
  29:E89E  50FA       ADD R15, #0xA
  29:E8A0  4802       MOV R0, #0x2
  29:E8A2  58F0       MOV [--R15], R0
  29:E8A4  481E       MOV R1, #0xE
  29:E8A6  4800       MOV R0, #0x0
  29:E8A8  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E8AC  5630       CMP R3, #0x0
  29:E8AE  DE03       RJMP SGE, 29:E8B6 ; rel +3
  29:E8B0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E8B4  D001       RJMP ALWAYS, 29:E8B8 ; rel +1
  29:E8B6  4820       MOV R2, #0x0
  29:E8B8  58F3       MOV [--R15], R3
```

### `29:E8E6` in `sub_29_E552`

```text
  29:E8CA  68F2 0052  MOV REG[0xF2], #0x0052
  29:E8CE  1013       ADD R1, R3
  29:E8D0  1102       ADDC R0, R2
  29:E8D2  58F1       MOV [--R15], R1
  29:E8D4  58F0       MOV [--R15], R0
  29:E8D6  6810 00A4  MOV REG[0x10], #0x00A4
  29:E8DA  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E8DE  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E8E2  58F1       MOV [--R15], R1
  29:E8E4  58F0       MOV [--R15], R0
> 29:E8E6  BD03 4010  SCALL 03:4010
  29:E8EA  50FA       ADD R15, #0xA
  29:E8EC  4802       MOV R0, #0x2
  29:E8EE  58F0       MOV [--R15], R0
  29:E8F0  481E       MOV R1, #0xE
  29:E8F2  4800       MOV R0, #0x0
  29:E8F4  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E8F8  5630       CMP R3, #0x0
  29:E8FA  DE03       RJMP SGE, 29:E902 ; rel +3
  29:E8FC  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E900  D001       RJMP ALWAYS, 29:E904 ; rel +1
  29:E902  4820       MOV R2, #0x0
  29:E904  58F3       MOV [--R15], R3
```

### `29:E932` in `sub_29_E552`

```text
  29:E916  68F2 0052  MOV REG[0xF2], #0x0052
  29:E91A  1013       ADD R1, R3
  29:E91C  1102       ADDC R0, R2
  29:E91E  58F1       MOV [--R15], R1
  29:E920  58F0       MOV [--R15], R0
  29:E922  6810 00A4  MOV REG[0x10], #0x00A4
  29:E926  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E92A  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E92E  58F1       MOV [--R15], R1
  29:E930  58F0       MOV [--R15], R0
> 29:E932  BD03 4010  SCALL 03:4010
  29:E936  50FA       ADD R15, #0xA
  29:E938  4801       MOV R0, #0x1
  29:E93A  58F0       MOV [--R15], R0
  29:E93C  081B       MOV R1, R11
  29:E93E  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E942  4800       MOV R0, #0x0
  29:E944  58F1       MOV [--R15], R1
  29:E946  58F0       MOV [--R15], R0
  29:E948  6810 00A4  MOV REG[0x10], #0x00A4
  29:E94C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E950  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E954  58F1       MOV [--R15], R1
```

### `29:E958` in `sub_29_E552`

```text
  29:E93C  081B       MOV R1, R11
  29:E93E  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E942  4800       MOV R0, #0x0
  29:E944  58F1       MOV [--R15], R1
  29:E946  58F0       MOV [--R15], R0
  29:E948  6810 00A4  MOV REG[0x10], #0x00A4
  29:E94C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E950  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E954  58F1       MOV [--R15], R1
  29:E956  58F0       MOV [--R15], R0
> 29:E958  BD03 4010  SCALL 03:4010
  29:E95C  50FA       ADD R15, #0xA
  29:E95E  481E       MOV R1, #0xE
  29:E960  4800       MOV R0, #0x0
  29:E962  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E966  5630       CMP R3, #0x0
  29:E968  DE03       RJMP SGE, 29:E970 ; rel +3
  29:E96A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E96E  D001       RJMP ALWAYS, 29:E972 ; rel +1
  29:E970  4820       MOV R2, #0x0
  29:E972  58F3       MOV [--R15], R3
  29:E974  58F2       MOV [--R15], R2
  29:E976  58F1       MOV [--R15], R1
```

### `29:E9BE` in `sub_29_E552`

```text
  29:E9A2  081B       MOV R1, R11
  29:E9A4  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  29:E9A8  4800       MOV R0, #0x0
  29:E9AA  58F1       MOV [--R15], R1
  29:E9AC  58F0       MOV [--R15], R0
  29:E9AE  6810 00A4  MOV REG[0x10], #0x00A4
  29:E9B2  88F0 7992  MOV REG[0xF0], [0x7992]
  29:E9B6  88F1 7994  MOV REG[0xF1], [0x7994]
  29:E9BA  58F1       MOV [--R15], R1
  29:E9BC  58F0       MOV [--R15], R0
> 29:E9BE  BD03 4010  SCALL 03:4010
  29:E9C2  50FA       ADD R15, #0xA
  29:E9C4  481E       MOV R1, #0xE
  29:E9C6  4800       MOV R0, #0x0
  29:E9C8  783B FFFE  MOV R3, [R11+0xFFFE]
  29:E9CC  5630       CMP R3, #0x0
  29:E9CE  DE03       RJMP SGE, 29:E9D6 ; rel +3
  29:E9D0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:E9D4  D001       RJMP ALWAYS, 29:E9D8 ; rel +1
  29:E9D6  4820       MOV R2, #0x0
  29:E9D8  58F3       MOV [--R15], R3
  29:E9DA  58F2       MOV [--R15], R2
  29:E9DC  58F1       MOV [--R15], R1
```

### `29:EAD8` in `sub_29_E552`

```text
  29:EABC  081B       MOV R1, R11
  29:EABE  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:EAC2  4800       MOV R0, #0x0
  29:EAC4  58F1       MOV [--R15], R1
  29:EAC6  58F0       MOV [--R15], R0
  29:EAC8  6810 00A4  MOV REG[0x10], #0x00A4
  29:EACC  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EAD0  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EAD4  58F1       MOV [--R15], R1
  29:EAD6  58F0       MOV [--R15], R0
> 29:EAD8  BD03 4010  SCALL 03:4010
  29:EADC  50FA       ADD R15, #0xA
  29:EADE  4802       MOV R0, #0x2
  29:EAE0  58F0       MOV [--R15], R0
  29:EAE2  4816       MOV R1, #0x6
  29:EAE4  4800       MOV R0, #0x0
  29:EAE6  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EAEA  5630       CMP R3, #0x0
  29:EAEC  DE03       RJMP SGE, 29:EAF4 ; rel +3
  29:EAEE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EAF2  D001       RJMP ALWAYS, 29:EAF6 ; rel +1
  29:EAF4  4820       MOV R2, #0x0
  29:EAF6  58F3       MOV [--R15], R3
```

### `29:EB24` in `sub_29_E552`

```text
  29:EB08  68F2 0052  MOV REG[0xF2], #0x0052
  29:EB0C  1013       ADD R1, R3
  29:EB0E  1102       ADDC R0, R2
  29:EB10  58F1       MOV [--R15], R1
  29:EB12  58F0       MOV [--R15], R0
  29:EB14  6810 00A4  MOV REG[0x10], #0x00A4
  29:EB18  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EB1C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EB20  58F1       MOV [--R15], R1
  29:EB22  58F0       MOV [--R15], R0
> 29:EB24  BD03 4010  SCALL 03:4010
  29:EB28  50FA       ADD R15, #0xA
  29:EB2A  4801       MOV R0, #0x1
  29:EB2C  58F0       MOV [--R15], R0
  29:EB2E  4816       MOV R1, #0x6
  29:EB30  4800       MOV R0, #0x0
  29:EB32  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EB36  5630       CMP R3, #0x0
  29:EB38  DE03       RJMP SGE, 29:EB40 ; rel +3
  29:EB3A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EB3E  D001       RJMP ALWAYS, 29:EB42 ; rel +1
  29:EB40  4820       MOV R2, #0x0
  29:EB42  58F3       MOV [--R15], R3
```

### `29:EB70` in `sub_29_E552`

```text
  29:EB54  68F2 0052  MOV REG[0xF2], #0x0052
  29:EB58  1013       ADD R1, R3
  29:EB5A  1102       ADDC R0, R2
  29:EB5C  58F1       MOV [--R15], R1
  29:EB5E  58F0       MOV [--R15], R0
  29:EB60  6810 00A4  MOV REG[0x10], #0x00A4
  29:EB64  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EB68  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EB6C  58F1       MOV [--R15], R1
  29:EB6E  58F0       MOV [--R15], R0
> 29:EB70  BD03 4010  SCALL 03:4010
  29:EB74  50FA       ADD R15, #0xA
  29:EB76  4802       MOV R0, #0x2
  29:EB78  58F0       MOV [--R15], R0
  29:EB7A  4816       MOV R1, #0x6
  29:EB7C  4800       MOV R0, #0x0
  29:EB7E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EB82  5630       CMP R3, #0x0
  29:EB84  DE03       RJMP SGE, 29:EB8C ; rel +3
  29:EB86  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EB8A  D001       RJMP ALWAYS, 29:EB8E ; rel +1
  29:EB8C  4820       MOV R2, #0x0
  29:EB8E  58F3       MOV [--R15], R3
```

### `29:EBBC` in `sub_29_E552`

```text
  29:EBA0  68F2 0052  MOV REG[0xF2], #0x0052
  29:EBA4  1013       ADD R1, R3
  29:EBA6  1102       ADDC R0, R2
  29:EBA8  58F1       MOV [--R15], R1
  29:EBAA  58F0       MOV [--R15], R0
  29:EBAC  6810 00A4  MOV REG[0x10], #0x00A4
  29:EBB0  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EBB4  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EBB8  58F1       MOV [--R15], R1
  29:EBBA  58F0       MOV [--R15], R0
> 29:EBBC  BD03 4010  SCALL 03:4010
  29:EBC0  50FA       ADD R15, #0xA
  29:EBC2  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EBC6  5001       ADD R0, #0x1
  29:EBC8  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:EBCC  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EBD0  560F       CMP R0, #0xF
  29:EBD2  AC09 EAA8  AJMP SL, 29:EAA8
  29:EBD6  4800       MOV R0, #0x0
  29:EBD8  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:EBDC  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EBE0  793B FFF6  MOVB RB3, [R11+0xFFF6]
  29:EBE4  1913       MOVZE R1, RB3
```

### `29:EC0C` in `sub_29_E552`

```text
  29:EBF0  081B       MOV R1, R11
  29:EBF2  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:EBF6  4800       MOV R0, #0x0
  29:EBF8  58F1       MOV [--R15], R1
  29:EBFA  58F0       MOV [--R15], R0
  29:EBFC  6810 00A4  MOV REG[0x10], #0x00A4
  29:EC00  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EC04  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EC08  58F1       MOV [--R15], R1
  29:EC0A  58F0       MOV [--R15], R0
> 29:EC0C  BD03 4010  SCALL 03:4010
  29:EC10  50FA       ADD R15, #0xA
  29:EC12  4801       MOV R0, #0x1
  29:EC14  58F0       MOV [--R15], R0
  29:EC16  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EC1A  0810       MOV R1, R0
  29:EC1C  5610       CMP R1, #0x0
  29:EC1E  DE03       RJMP SGE, 29:EC26 ; rel +3
  29:EC20  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:EC24  D001       RJMP ALWAYS, 29:EC28 ; rel +1
  29:EC26  4800       MOV R0, #0x0
  29:EC28  4C13       SL R1, #0x3
  29:EC2A  5C03       SLOSB R0, #0x3
```

### `29:EC4C` in `sub_29_E552`

```text
  29:EC30  68F2 0052  MOV REG[0xF2], #0x0052
  29:EC34  1013       ADD R1, R3
  29:EC36  1102       ADDC R0, R2
  29:EC38  58F1       MOV [--R15], R1
  29:EC3A  58F0       MOV [--R15], R0
  29:EC3C  6810 00A4  MOV REG[0x10], #0x00A4
  29:EC40  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EC44  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EC48  58F1       MOV [--R15], R1
  29:EC4A  58F0       MOV [--R15], R0
> 29:EC4C  BD03 4010  SCALL 03:4010
  29:EC50  50FA       ADD R15, #0xA
  29:EC52  4802       MOV R0, #0x2
  29:EC54  58F0       MOV [--R15], R0
  29:EC56  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EC5A  0810       MOV R1, R0
  29:EC5C  5610       CMP R1, #0x0
  29:EC5E  DE03       RJMP SGE, 29:EC66 ; rel +3
  29:EC60  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:EC64  D001       RJMP ALWAYS, 29:EC68 ; rel +1
  29:EC66  4800       MOV R0, #0x0
  29:EC68  4C13       SL R1, #0x3
  29:EC6A  5C03       SLOSB R0, #0x3
```

### `29:EC8C` in `sub_29_E552`

```text
  29:EC70  68F2 0052  MOV REG[0xF2], #0x0052
  29:EC74  1013       ADD R1, R3
  29:EC76  1102       ADDC R0, R2
  29:EC78  58F1       MOV [--R15], R1
  29:EC7A  58F0       MOV [--R15], R0
  29:EC7C  6810 00A4  MOV REG[0x10], #0x00A4
  29:EC80  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EC84  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EC88  58F1       MOV [--R15], R1
  29:EC8A  58F0       MOV [--R15], R0
> 29:EC8C  BD03 4010  SCALL 03:4010
  29:EC90  50FA       ADD R15, #0xA
  29:EC92  4801       MOV R0, #0x1
  29:EC94  58F0       MOV [--R15], R0
  29:EC96  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EC9A  0810       MOV R1, R0
  29:EC9C  5610       CMP R1, #0x0
  29:EC9E  DE03       RJMP SGE, 29:ECA6 ; rel +3
  29:ECA0  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:ECA4  D001       RJMP ALWAYS, 29:ECA8 ; rel +1
  29:ECA6  4800       MOV R0, #0x0
  29:ECA8  4C13       SL R1, #0x3
  29:ECAA  5C03       SLOSB R0, #0x3
```

### `29:ECCC` in `sub_29_E552`

```text
  29:ECB0  68F2 0052  MOV REG[0xF2], #0x0052
  29:ECB4  1013       ADD R1, R3
  29:ECB6  1102       ADDC R0, R2
  29:ECB8  58F1       MOV [--R15], R1
  29:ECBA  58F0       MOV [--R15], R0
  29:ECBC  6810 00A4  MOV REG[0x10], #0x00A4
  29:ECC0  88F0 7992  MOV REG[0xF0], [0x7992]
  29:ECC4  88F1 7994  MOV REG[0xF1], [0x7994]
  29:ECC8  58F1       MOV [--R15], R1
  29:ECCA  58F0       MOV [--R15], R0
> 29:ECCC  BD03 4010  SCALL 03:4010
  29:ECD0  50FA       ADD R15, #0xA
  29:ECD2  4802       MOV R0, #0x2
  29:ECD4  58F0       MOV [--R15], R0
  29:ECD6  780B FFFE  MOV R0, [R11+0xFFFE]
  29:ECDA  0810       MOV R1, R0
  29:ECDC  5610       CMP R1, #0x0
  29:ECDE  DE03       RJMP SGE, 29:ECE6 ; rel +3
  29:ECE0  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:ECE4  D001       RJMP ALWAYS, 29:ECE8 ; rel +1
  29:ECE6  4800       MOV R0, #0x0
  29:ECE8  4C13       SL R1, #0x3
  29:ECEA  5C03       SLOSB R0, #0x3
```

### `29:ED0C` in `sub_29_E552`

```text
  29:ECF0  68F2 0052  MOV REG[0xF2], #0x0052
  29:ECF4  1013       ADD R1, R3
  29:ECF6  1102       ADDC R0, R2
  29:ECF8  58F1       MOV [--R15], R1
  29:ECFA  58F0       MOV [--R15], R0
  29:ECFC  6810 00A4  MOV REG[0x10], #0x00A4
  29:ED00  88F0 7992  MOV REG[0xF0], [0x7992]
  29:ED04  88F1 7994  MOV REG[0xF1], [0x7994]
  29:ED08  58F1       MOV [--R15], R1
  29:ED0A  58F0       MOV [--R15], R0
> 29:ED0C  BD03 4010  SCALL 03:4010
  29:ED10  50FA       ADD R15, #0xA
  29:ED12  780B FFFE  MOV R0, [R11+0xFFFE]
  29:ED16  5001       ADD R0, #0x1
  29:ED18  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:ED1C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:ED20  5605       CMP R0, #0x5
  29:ED22  AC09 EBDC  AJMP SL, 29:EBDC
  29:ED26  4800       MOV R0, #0x0
  29:ED28  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:ED2C  780B FFFE  MOV R0, [R11+0xFFFE]
  29:ED30  793B FFF7  MOVB RB3, [R11+0xFFF7]
  29:ED34  1913       MOVZE R1, RB3
```

### `29:ED74` in `sub_29_E552`

```text
  29:ED58  68F2 0052  MOV REG[0xF2], #0x0052
  29:ED5C  1013       ADD R1, R3
  29:ED5E  1102       ADDC R0, R2
  29:ED60  58F1       MOV [--R15], R1
  29:ED62  58F0       MOV [--R15], R0
  29:ED64  6810 00A4  MOV REG[0x10], #0x00A4
  29:ED68  88F0 7992  MOV REG[0xF0], [0x7992]
  29:ED6C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:ED70  58F1       MOV [--R15], R1
  29:ED72  58F0       MOV [--R15], R0
> 29:ED74  BD03 4010  SCALL 03:4010
  29:ED78  50FA       ADD R15, #0xA
  29:ED7A  4801       MOV R0, #0x1
  29:ED7C  58F0       MOV [--R15], R0
  29:ED7E  780B FFFE  MOV R0, [R11+0xFFFE]
  29:ED82  0810       MOV R1, R0
  29:ED84  5610       CMP R1, #0x0
  29:ED86  DE03       RJMP SGE, 29:ED8E ; rel +3
  29:ED88  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:ED8C  D001       RJMP ALWAYS, 29:ED90 ; rel +1
  29:ED8E  4800       MOV R0, #0x0
  29:ED90  4C13       SL R1, #0x3
  29:ED92  5C03       SLOSB R0, #0x3
```

### `29:EDB4` in `sub_29_E552`

```text
  29:ED98  68F2 0052  MOV REG[0xF2], #0x0052
  29:ED9C  1013       ADD R1, R3
  29:ED9E  1102       ADDC R0, R2
  29:EDA0  58F1       MOV [--R15], R1
  29:EDA2  58F0       MOV [--R15], R0
  29:EDA4  6810 00A4  MOV REG[0x10], #0x00A4
  29:EDA8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EDAC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EDB0  58F1       MOV [--R15], R1
  29:EDB2  58F0       MOV [--R15], R0
> 29:EDB4  BD03 4010  SCALL 03:4010
  29:EDB8  50FA       ADD R15, #0xA
  29:EDBA  4802       MOV R0, #0x2
  29:EDBC  58F0       MOV [--R15], R0
  29:EDBE  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EDC2  0810       MOV R1, R0
  29:EDC4  5610       CMP R1, #0x0
  29:EDC6  DE03       RJMP SGE, 29:EDCE ; rel +3
  29:EDC8  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:EDCC  D001       RJMP ALWAYS, 29:EDD0 ; rel +1
  29:EDCE  4800       MOV R0, #0x0
  29:EDD0  4C13       SL R1, #0x3
  29:EDD2  5C03       SLOSB R0, #0x3
```

### `29:EDF4` in `sub_29_E552`

```text
  29:EDD8  68F2 0052  MOV REG[0xF2], #0x0052
  29:EDDC  1013       ADD R1, R3
  29:EDDE  1102       ADDC R0, R2
  29:EDE0  58F1       MOV [--R15], R1
  29:EDE2  58F0       MOV [--R15], R0
  29:EDE4  6810 00A4  MOV REG[0x10], #0x00A4
  29:EDE8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EDEC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EDF0  58F1       MOV [--R15], R1
  29:EDF2  58F0       MOV [--R15], R0
> 29:EDF4  BD03 4010  SCALL 03:4010
  29:EDF8  50FA       ADD R15, #0xA
  29:EDFA  4801       MOV R0, #0x1
  29:EDFC  58F0       MOV [--R15], R0
  29:EDFE  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EE02  0810       MOV R1, R0
  29:EE04  5610       CMP R1, #0x0
  29:EE06  DE03       RJMP SGE, 29:EE0E ; rel +3
  29:EE08  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:EE0C  D001       RJMP ALWAYS, 29:EE10 ; rel +1
  29:EE0E  4800       MOV R0, #0x0
  29:EE10  4C13       SL R1, #0x3
  29:EE12  5C03       SLOSB R0, #0x3
```

### `29:EE34` in `sub_29_E552`

```text
  29:EE18  68F2 0052  MOV REG[0xF2], #0x0052
  29:EE1C  1013       ADD R1, R3
  29:EE1E  1102       ADDC R0, R2
  29:EE20  58F1       MOV [--R15], R1
  29:EE22  58F0       MOV [--R15], R0
  29:EE24  6810 00A4  MOV REG[0x10], #0x00A4
  29:EE28  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EE2C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EE30  58F1       MOV [--R15], R1
  29:EE32  58F0       MOV [--R15], R0
> 29:EE34  BD03 4010  SCALL 03:4010
  29:EE38  50FA       ADD R15, #0xA
  29:EE3A  4802       MOV R0, #0x2
  29:EE3C  58F0       MOV [--R15], R0
  29:EE3E  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EE42  0810       MOV R1, R0
  29:EE44  5610       CMP R1, #0x0
  29:EE46  DE03       RJMP SGE, 29:EE4E ; rel +3
  29:EE48  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  29:EE4C  D001       RJMP ALWAYS, 29:EE50 ; rel +1
  29:EE4E  4800       MOV R0, #0x0
  29:EE50  4C13       SL R1, #0x3
  29:EE52  5C03       SLOSB R0, #0x3
```

### `29:EE74` in `sub_29_E552`

```text
  29:EE58  68F2 0052  MOV REG[0xF2], #0x0052
  29:EE5C  1013       ADD R1, R3
  29:EE5E  1102       ADDC R0, R2
  29:EE60  58F1       MOV [--R15], R1
  29:EE62  58F0       MOV [--R15], R0
  29:EE64  6810 00A4  MOV REG[0x10], #0x00A4
  29:EE68  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EE6C  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EE70  58F1       MOV [--R15], R1
  29:EE72  58F0       MOV [--R15], R0
> 29:EE74  BD03 4010  SCALL 03:4010
  29:EE78  50FA       ADD R15, #0xA
  29:EE7A  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EE7E  5001       ADD R0, #0x1
  29:EE80  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:EE84  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EE88  5605       CMP R0, #0x5
  29:EE8A  AC09 ED2C  AJMP SL, 29:ED2C
  29:EE8E  4800       MOV R0, #0x0
  29:EE90  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:EE94  780B FFFE  MOV R0, [R11+0xFFFE]
  29:EE98  793B FFF8  MOVB RB3, [R11+0xFFF8]
  29:EE9C  1913       MOVZE R1, RB3
```

### `29:EEC4` in `sub_29_E552`

```text
  29:EEA8  081B       MOV R1, R11
  29:EEAA  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:EEAE  4800       MOV R0, #0x0
  29:EEB0  58F1       MOV [--R15], R1
  29:EEB2  58F0       MOV [--R15], R0
  29:EEB4  6810 00A4  MOV REG[0x10], #0x00A4
  29:EEB8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EEBC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EEC0  58F1       MOV [--R15], R1
  29:EEC2  58F0       MOV [--R15], R0
> 29:EEC4  BD03 4010  SCALL 03:4010
  29:EEC8  50FA       ADD R15, #0xA
  29:EECA  4802       MOV R0, #0x2
  29:EECC  58F0       MOV [--R15], R0
  29:EECE  481A       MOV R1, #0xA
  29:EED0  4800       MOV R0, #0x0
  29:EED2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EED6  5630       CMP R3, #0x0
  29:EED8  DE03       RJMP SGE, 29:EEE0 ; rel +3
  29:EEDA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EEDE  D001       RJMP ALWAYS, 29:EEE2 ; rel +1
  29:EEE0  4820       MOV R2, #0x0
  29:EEE2  58F3       MOV [--R15], R3
```

### `29:EF10` in `sub_29_E552`

```text
  29:EEF4  68F2 0052  MOV REG[0xF2], #0x0052
  29:EEF8  1013       ADD R1, R3
  29:EEFA  1102       ADDC R0, R2
  29:EEFC  58F1       MOV [--R15], R1
  29:EEFE  58F0       MOV [--R15], R0
  29:EF00  6810 00A4  MOV REG[0x10], #0x00A4
  29:EF04  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EF08  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EF0C  58F1       MOV [--R15], R1
  29:EF0E  58F0       MOV [--R15], R0
> 29:EF10  BD03 4010  SCALL 03:4010
  29:EF14  50FA       ADD R15, #0xA
  29:EF16  4801       MOV R0, #0x1
  29:EF18  58F0       MOV [--R15], R0
  29:EF1A  481A       MOV R1, #0xA
  29:EF1C  4800       MOV R0, #0x0
  29:EF1E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EF22  5630       CMP R3, #0x0
  29:EF24  DE03       RJMP SGE, 29:EF2C ; rel +3
  29:EF26  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EF2A  D001       RJMP ALWAYS, 29:EF2E ; rel +1
  29:EF2C  4820       MOV R2, #0x0
  29:EF2E  58F3       MOV [--R15], R3
```

### `29:EF5C` in `sub_29_E552`

```text
  29:EF40  68F2 0052  MOV REG[0xF2], #0x0052
  29:EF44  1013       ADD R1, R3
  29:EF46  1102       ADDC R0, R2
  29:EF48  58F1       MOV [--R15], R1
  29:EF4A  58F0       MOV [--R15], R0
  29:EF4C  6810 00A4  MOV REG[0x10], #0x00A4
  29:EF50  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EF54  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EF58  58F1       MOV [--R15], R1
  29:EF5A  58F0       MOV [--R15], R0
> 29:EF5C  BD03 4010  SCALL 03:4010
  29:EF60  50FA       ADD R15, #0xA
  29:EF62  4802       MOV R0, #0x2
  29:EF64  58F0       MOV [--R15], R0
  29:EF66  481A       MOV R1, #0xA
  29:EF68  4800       MOV R0, #0x0
  29:EF6A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EF6E  5630       CMP R3, #0x0
  29:EF70  DE03       RJMP SGE, 29:EF78 ; rel +3
  29:EF72  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EF76  D001       RJMP ALWAYS, 29:EF7A ; rel +1
  29:EF78  4820       MOV R2, #0x0
  29:EF7A  58F3       MOV [--R15], R3
```

### `29:EFA8` in `sub_29_E552`

```text
  29:EF8C  68F2 0052  MOV REG[0xF2], #0x0052
  29:EF90  1013       ADD R1, R3
  29:EF92  1102       ADDC R0, R2
  29:EF94  58F1       MOV [--R15], R1
  29:EF96  58F0       MOV [--R15], R0
  29:EF98  6810 00A4  MOV REG[0x10], #0x00A4
  29:EF9C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EFA0  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EFA4  58F1       MOV [--R15], R1
  29:EFA6  58F0       MOV [--R15], R0
> 29:EFA8  BD03 4010  SCALL 03:4010
  29:EFAC  50FA       ADD R15, #0xA
  29:EFAE  4802       MOV R0, #0x2
  29:EFB0  58F0       MOV [--R15], R0
  29:EFB2  481A       MOV R1, #0xA
  29:EFB4  4800       MOV R0, #0x0
  29:EFB6  783B FFFE  MOV R3, [R11+0xFFFE]
  29:EFBA  5630       CMP R3, #0x0
  29:EFBC  DE03       RJMP SGE, 29:EFC4 ; rel +3
  29:EFBE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:EFC2  D001       RJMP ALWAYS, 29:EFC6 ; rel +1
  29:EFC4  4820       MOV R2, #0x0
  29:EFC6  58F3       MOV [--R15], R3
```

### `29:EFF4` in `sub_29_E552`

```text
  29:EFD8  68F2 0052  MOV REG[0xF2], #0x0052
  29:EFDC  1013       ADD R1, R3
  29:EFDE  1102       ADDC R0, R2
  29:EFE0  58F1       MOV [--R15], R1
  29:EFE2  58F0       MOV [--R15], R0
  29:EFE4  6810 00A4  MOV REG[0x10], #0x00A4
  29:EFE8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:EFEC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:EFF0  58F1       MOV [--R15], R1
  29:EFF2  58F0       MOV [--R15], R0
> 29:EFF4  BD03 4010  SCALL 03:4010
  29:EFF8  50FA       ADD R15, #0xA
  29:EFFA  4802       MOV R0, #0x2
  29:EFFC  58F0       MOV [--R15], R0
  29:EFFE  481A       MOV R1, #0xA
  29:F000  4800       MOV R0, #0x0
  29:F002  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F006  5630       CMP R3, #0x0
  29:F008  DE03       RJMP SGE, 29:F010 ; rel +3
  29:F00A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F00E  D001       RJMP ALWAYS, 29:F012 ; rel +1
  29:F010  4820       MOV R2, #0x0
  29:F012  58F3       MOV [--R15], R3
```

### `29:F040` in `sub_29_E552`

```text
  29:F024  68F2 0052  MOV REG[0xF2], #0x0052
  29:F028  1013       ADD R1, R3
  29:F02A  1102       ADDC R0, R2
  29:F02C  58F1       MOV [--R15], R1
  29:F02E  58F0       MOV [--R15], R0
  29:F030  6810 00A4  MOV REG[0x10], #0x00A4
  29:F034  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F038  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F03C  58F1       MOV [--R15], R1
  29:F03E  58F0       MOV [--R15], R0
> 29:F040  BD03 4010  SCALL 03:4010
  29:F044  50FA       ADD R15, #0xA
  29:F046  AC00 F086  AJMP ALWAYS, 29:F086
  29:F04A  481A       MOV R1, #0xA
  29:F04C  4800       MOV R0, #0x0
  29:F04E  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F052  5630       CMP R3, #0x0
  29:F054  DE03       RJMP SGE, 29:F05C ; rel +3
  29:F056  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F05A  D001       RJMP ALWAYS, 29:F05E ; rel +1
  29:F05C  4820       MOV R2, #0x0
  29:F05E  58F3       MOV [--R15], R3
  29:F060  58F2       MOV [--R15], R2
```

### `29:F0D0` in `sub_29_E552`

```text
  29:F0B4  081B       MOV R1, R11
  29:F0B6  70F1 FFE8  ADD REG[0xF1], #0xFFE8
  29:F0BA  4800       MOV R0, #0x0
  29:F0BC  58F1       MOV [--R15], R1
  29:F0BE  58F0       MOV [--R15], R0
  29:F0C0  6810 00A4  MOV REG[0x10], #0x00A4
  29:F0C4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F0C8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F0CC  58F1       MOV [--R15], R1
  29:F0CE  58F0       MOV [--R15], R0
> 29:F0D0  BD03 4010  SCALL 03:4010
  29:F0D4  50FA       ADD R15, #0xA
  29:F0D6  4801       MOV R0, #0x1
  29:F0D8  58F0       MOV [--R15], R0
  29:F0DA  4816       MOV R1, #0x6
  29:F0DC  4800       MOV R0, #0x0
  29:F0DE  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F0E2  5630       CMP R3, #0x0
  29:F0E4  DE03       RJMP SGE, 29:F0EC ; rel +3
  29:F0E6  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F0EA  D001       RJMP ALWAYS, 29:F0EE ; rel +1
  29:F0EC  4820       MOV R2, #0x0
  29:F0EE  58F3       MOV [--R15], R3
```

### `29:F11C` in `sub_29_E552`

```text
  29:F100  68F2 0052  MOV REG[0xF2], #0x0052
  29:F104  1013       ADD R1, R3
  29:F106  1102       ADDC R0, R2
  29:F108  58F1       MOV [--R15], R1
  29:F10A  58F0       MOV [--R15], R0
  29:F10C  6810 00A4  MOV REG[0x10], #0x00A4
  29:F110  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F114  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F118  58F1       MOV [--R15], R1
  29:F11A  58F0       MOV [--R15], R0
> 29:F11C  BD03 4010  SCALL 03:4010
  29:F120  50FA       ADD R15, #0xA
  29:F122  4801       MOV R0, #0x1
  29:F124  58F0       MOV [--R15], R0
  29:F126  4816       MOV R1, #0x6
  29:F128  4800       MOV R0, #0x0
  29:F12A  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F12E  5630       CMP R3, #0x0
  29:F130  DE03       RJMP SGE, 29:F138 ; rel +3
  29:F132  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F136  D001       RJMP ALWAYS, 29:F13A ; rel +1
  29:F138  4820       MOV R2, #0x0
  29:F13A  58F3       MOV [--R15], R3
```

### `29:F168` in `sub_29_E552`

```text
  29:F14C  68F2 0052  MOV REG[0xF2], #0x0052
  29:F150  1013       ADD R1, R3
  29:F152  1102       ADDC R0, R2
  29:F154  58F1       MOV [--R15], R1
  29:F156  58F0       MOV [--R15], R0
  29:F158  6810 00A4  MOV REG[0x10], #0x00A4
  29:F15C  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F160  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F164  58F1       MOV [--R15], R1
  29:F166  58F0       MOV [--R15], R0
> 29:F168  BD03 4010  SCALL 03:4010
  29:F16C  50FA       ADD R15, #0xA
  29:F16E  4801       MOV R0, #0x1
  29:F170  58F0       MOV [--R15], R0
  29:F172  4816       MOV R1, #0x6
  29:F174  4800       MOV R0, #0x0
  29:F176  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F17A  5630       CMP R3, #0x0
  29:F17C  DE03       RJMP SGE, 29:F184 ; rel +3
  29:F17E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F182  D001       RJMP ALWAYS, 29:F186 ; rel +1
  29:F184  4820       MOV R2, #0x0
  29:F186  58F3       MOV [--R15], R3
```

### `29:F1B4` in `sub_29_E552`

```text
  29:F198  68F2 0052  MOV REG[0xF2], #0x0052
  29:F19C  1013       ADD R1, R3
  29:F19E  1102       ADDC R0, R2
  29:F1A0  58F1       MOV [--R15], R1
  29:F1A2  58F0       MOV [--R15], R0
  29:F1A4  6810 00A4  MOV REG[0x10], #0x00A4
  29:F1A8  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F1AC  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F1B0  58F1       MOV [--R15], R1
  29:F1B2  58F0       MOV [--R15], R0
> 29:F1B4  BD03 4010  SCALL 03:4010
  29:F1B8  50FA       ADD R15, #0xA
  29:F1BA  4802       MOV R0, #0x2
  29:F1BC  58F0       MOV [--R15], R0
  29:F1BE  4816       MOV R1, #0x6
  29:F1C0  4800       MOV R0, #0x0
  29:F1C2  783B FFFE  MOV R3, [R11+0xFFFE]
  29:F1C6  5630       CMP R3, #0x0
  29:F1C8  DE03       RJMP SGE, 29:F1D0 ; rel +3
  29:F1CA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  29:F1CE  D001       RJMP ALWAYS, 29:F1D2 ; rel +1
  29:F1D0  4820       MOV R2, #0x0
  29:F1D2  58F3       MOV [--R15], R3
```

### `29:F200` in `sub_29_E552`

```text
  29:F1E4  68F2 0052  MOV REG[0xF2], #0x0052
  29:F1E8  1013       ADD R1, R3
  29:F1EA  1102       ADDC R0, R2
  29:F1EC  58F1       MOV [--R15], R1
  29:F1EE  58F0       MOV [--R15], R0
  29:F1F0  6810 00A4  MOV REG[0x10], #0x00A4
  29:F1F4  88F0 7992  MOV REG[0xF0], [0x7992]
  29:F1F8  88F1 7994  MOV REG[0xF1], [0x7994]
  29:F1FC  58F1       MOV [--R15], R1
  29:F1FE  58F0       MOV [--R15], R0
> 29:F200  BD03 4010  SCALL 03:4010
  29:F204  50FA       ADD R15, #0xA
  29:F206  780B FFFE  MOV R0, [R11+0xFFFE]
  29:F20A  5001       ADD R0, #0x1
  29:F20C  6A0B FFFE  MOV [R11+0xFFFE], R0
  29:F210  780B FFFE  MOV R0, [R11+0xFFFE]
  29:F214  5602       CMP R0, #0x2
  29:F216  AC09 F0A0  AJMP SL, 29:F0A0
  29:F21A  6810 00A4  MOV REG[0x10], #0x00A4
  29:F21E  98F0 7916  MOVSE REG[0xF0], [0x7916]
  29:F222  5600       CMP R0, #0x0
  29:F224  AC0D F238  AJMP SLE, 29:F238
  29:F228  4801       MOV R0, #0x1
```

### `2C:C066` in `sub_2C_B70A`

```text
  2C:C04A  081B       MOV R1, R11
  2C:C04C  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C050  4800       MOV R0, #0x0
  2C:C052  58F1       MOV [--R15], R1
  2C:C054  58F0       MOV [--R15], R0
  2C:C056  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C05A  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C05E  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C062  58F1       MOV [--R15], R1
  2C:C064  58F0       MOV [--R15], R0
> 2C:C066  BD03 4010  SCALL 03:4010
  2C:C06A  50FA       ADD R15, #0xA
  2C:C06C  780B FFE6  MOV R0, [R11+0xFFE6]
  2C:C070  76F0 00FE  CMP REG[0xF0], #0x00FE
  2C:C074  AC02 C07C  AJMP NZ/NE, 2C:C07C
  2C:C078  AC00 C088  AJMP ALWAYS, 2C:C088
  2C:C07C  791B FFFF  MOVB RB1, [R11+0xFFFF]
```

### `2C:C188` in `sub_2C_C07E`

```text
  2C:C16C  081B       MOV R1, R11
  2C:C16E  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C172  4800       MOV R0, #0x0
  2C:C174  58F1       MOV [--R15], R1
  2C:C176  58F0       MOV [--R15], R0
  2C:C178  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C17C  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C180  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C184  58F1       MOV [--R15], R1
  2C:C186  58F0       MOV [--R15], R0
> 2C:C188  BD03 4010  SCALL 03:4010
  2C:C18C  50FA       ADD R15, #0xA
  2C:C18E  4910       MOVB RB1, #0x0
  2C:C190  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C194  C700       NOP
  2C:C196  A9F1 7AD8  MOVB [0x7AD8], REG[0xF1]
  2C:C19A  AC00 C222  AJMP ALWAYS, 2C:C222
  2C:C19E  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C1A2  99F0 7AD8  MOVZE REG[0xF0], [0x7AD8]
  2C:C1A6  0810       MOV R1, R0
  2C:C1A8  5011       ADD R1, #0x1
  2C:C1AA  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C1AE  C700       NOP
```

### `2C:C208` in `sub_2C_C07E`

```text
  2C:C1EC  081B       MOV R1, R11
  2C:C1EE  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C1F2  4800       MOV R0, #0x0
  2C:C1F4  58F1       MOV [--R15], R1
  2C:C1F6  58F0       MOV [--R15], R0
  2C:C1F8  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C1FC  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C200  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C204  58F1       MOV [--R15], R1
  2C:C206  58F0       MOV [--R15], R0
> 2C:C208  BD03 4010  SCALL 03:4010
  2C:C20C  50FA       ADD R15, #0xA
  2C:C20E  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C212  99F0 7AD8  MOVZE REG[0xF0], [0x7AD8]
  2C:C216  76F0 0028  CMP REG[0xF0], #0x0028
  2C:C21A  AC02 C222  AJMP NZ/NE, 2C:C222
  2C:C21E  AC00 C22E  AJMP ALWAYS, 2C:C22E
  2C:C222  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2C:C226  1801       MOVSE R0, RB1
  2C:C228  5600       CMP R0, #0x0
  2C:C22A  AC02 C19E  AJMP NZ/NE, 2C:C19E
  2C:C22E  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C232  99F0 7AD8  MOVZE REG[0xF0], [0x7AD8]
```

### `2C:C2AC` in `sub_2C_C07E`

```text
  2C:C290  081B       MOV R1, R11
  2C:C292  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C296  4800       MOV R0, #0x0
  2C:C298  58F1       MOV [--R15], R1
  2C:C29A  58F0       MOV [--R15], R0
  2C:C29C  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C2A0  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C2A4  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C2A8  58F1       MOV [--R15], R1
  2C:C2AA  58F0       MOV [--R15], R0
> 2C:C2AC  BD03 4010  SCALL 03:4010
  2C:C2B0  50FA       ADD R15, #0xA
  2C:C2B2  4910       MOVB RB1, #0x0
  2C:C2B4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C2B8  C700       NOP
  2C:C2BA  A9F1 7AD6  MOVB [0x7AD6], REG[0xF1]
  2C:C2BE  AC00 C346  AJMP ALWAYS, 2C:C346
  2C:C2C2  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C2C6  99F0 7AD6  MOVZE REG[0xF0], [0x7AD6]
  2C:C2CA  0810       MOV R1, R0
  2C:C2CC  5011       ADD R1, #0x1
  2C:C2CE  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C2D2  C700       NOP
```

### `2C:C32C` in `sub_2C_C07E`

```text
  2C:C310  081B       MOV R1, R11
  2C:C312  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C316  4800       MOV R0, #0x0
  2C:C318  58F1       MOV [--R15], R1
  2C:C31A  58F0       MOV [--R15], R0
  2C:C31C  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C320  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C324  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C328  58F1       MOV [--R15], R1
  2C:C32A  58F0       MOV [--R15], R0
> 2C:C32C  BD03 4010  SCALL 03:4010
  2C:C330  50FA       ADD R15, #0xA
  2C:C332  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C336  99F0 7AD6  MOVZE REG[0xF0], [0x7AD6]
  2C:C33A  76F0 0028  CMP REG[0xF0], #0x0028
  2C:C33E  AC02 C346  AJMP NZ/NE, 2C:C346
  2C:C342  AC00 C352  AJMP ALWAYS, 2C:C352
  2C:C346  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2C:C34A  1801       MOVSE R0, RB1
  2C:C34C  5600       CMP R0, #0x0
  2C:C34E  AC02 C2C2  AJMP NZ/NE, 2C:C2C2
  2C:C352  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C356  99F0 7AD6  MOVZE REG[0xF0], [0x7AD6]
```

### `2C:C3D0` in `sub_2C_C07E`

```text
  2C:C3B4  081B       MOV R1, R11
  2C:C3B6  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C3BA  4800       MOV R0, #0x0
  2C:C3BC  58F1       MOV [--R15], R1
  2C:C3BE  58F0       MOV [--R15], R0
  2C:C3C0  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C3C4  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C3C8  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C3CC  58F1       MOV [--R15], R1
  2C:C3CE  58F0       MOV [--R15], R0
> 2C:C3D0  BD03 4010  SCALL 03:4010
  2C:C3D4  50FA       ADD R15, #0xA
  2C:C3D6  4910       MOVB RB1, #0x0
  2C:C3D8  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C3DC  C700       NOP
  2C:C3DE  A9F1 7AD4  MOVB [0x7AD4], REG[0xF1]
  2C:C3E2  AC00 C46A  AJMP ALWAYS, 2C:C46A
  2C:C3E6  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C3EA  99F0 7AD4  MOVZE REG[0xF0], [0x7AD4]
  2C:C3EE  0810       MOV R1, R0
  2C:C3F0  5011       ADD R1, #0x1
  2C:C3F2  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C3F6  C700       NOP
```

### `2C:C450` in `sub_2C_C07E`

```text
  2C:C434  081B       MOV R1, R11
  2C:C436  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C43A  4800       MOV R0, #0x0
  2C:C43C  58F1       MOV [--R15], R1
  2C:C43E  58F0       MOV [--R15], R0
  2C:C440  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C444  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C448  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C44C  58F1       MOV [--R15], R1
  2C:C44E  58F0       MOV [--R15], R0
> 2C:C450  BD03 4010  SCALL 03:4010
  2C:C454  50FA       ADD R15, #0xA
  2C:C456  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C45A  99F0 7AD4  MOVZE REG[0xF0], [0x7AD4]
  2C:C45E  76F0 0028  CMP REG[0xF0], #0x0028
  2C:C462  AC02 C46A  AJMP NZ/NE, 2C:C46A
  2C:C466  AC00 C476  AJMP ALWAYS, 2C:C476
  2C:C46A  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2C:C46E  1801       MOVSE R0, RB1
  2C:C470  5600       CMP R0, #0x0
  2C:C472  AC02 C3E6  AJMP NZ/NE, 2C:C3E6
  2C:C476  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C47A  99F0 7AD4  MOVZE REG[0xF0], [0x7AD4]
```

### `2C:C4F4` in `sub_2C_C07E`

```text
  2C:C4D8  081B       MOV R1, R11
  2C:C4DA  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C4DE  4800       MOV R0, #0x0
  2C:C4E0  58F1       MOV [--R15], R1
  2C:C4E2  58F0       MOV [--R15], R0
  2C:C4E4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C4E8  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C4EC  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C4F0  58F1       MOV [--R15], R1
  2C:C4F2  58F0       MOV [--R15], R0
> 2C:C4F4  BD03 4010  SCALL 03:4010
  2C:C4F8  50FA       ADD R15, #0xA
  2C:C4FA  4910       MOVB RB1, #0x0
  2C:C4FC  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C500  C700       NOP
  2C:C502  A9F1 7AD2  MOVB [0x7AD2], REG[0xF1]
  2C:C506  AC00 C58E  AJMP ALWAYS, 2C:C58E
  2C:C50A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C50E  99F0 7AD2  MOVZE REG[0xF0], [0x7AD2]
  2C:C512  0810       MOV R1, R0
  2C:C514  5011       ADD R1, #0x1
  2C:C516  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C51A  C700       NOP
```

### `2C:C574` in `sub_2C_C07E`

```text
  2C:C558  081B       MOV R1, R11
  2C:C55A  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C55E  4800       MOV R0, #0x0
  2C:C560  58F1       MOV [--R15], R1
  2C:C562  58F0       MOV [--R15], R0
  2C:C564  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C568  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C56C  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C570  58F1       MOV [--R15], R1
  2C:C572  58F0       MOV [--R15], R0
> 2C:C574  BD03 4010  SCALL 03:4010
  2C:C578  50FA       ADD R15, #0xA
  2C:C57A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C57E  99F0 7AD2  MOVZE REG[0xF0], [0x7AD2]
  2C:C582  76F0 0028  CMP REG[0xF0], #0x0028
  2C:C586  AC02 C58E  AJMP NZ/NE, 2C:C58E
  2C:C58A  AC00 C59A  AJMP ALWAYS, 2C:C59A
  2C:C58E  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2C:C592  1801       MOVSE R0, RB1
  2C:C594  5600       CMP R0, #0x0
  2C:C596  AC02 C50A  AJMP NZ/NE, 2C:C50A
  2C:C59A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C59E  99F0 7AD2  MOVZE REG[0xF0], [0x7AD2]
```

### `2C:C5F4` in `sub_2C_C07E`

```text
  2C:C5D6  58F2       MOV [--R15], R2
  2C:C5D8  68F1 7A96  MOV REG[0xF1], #0x7A96
  2C:C5DC  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C5E0  58F1       MOV [--R15], R1
  2C:C5E2  58F0       MOV [--R15], R0
  2C:C5E4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C5E8  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C5EC  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C5F0  58F1       MOV [--R15], R1
  2C:C5F2  58F0       MOV [--R15], R0
> 2C:C5F4  BD03 4010  SCALL 03:4010
  2C:C5F8  50FA       ADD R15, #0xA
  2C:C5FA  4801       MOV R0, #0x1
  2C:C5FC  58F0       MOV [--R15], R0
  2C:C5FE  68F1 7A0A  MOV REG[0xF1], #0x7A0A
  2C:C602  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C606  58F1       MOV [--R15], R1
  2C:C608  58F0       MOV [--R15], R0
  2C:C60A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C60E  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C612  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C616  58F1       MOV [--R15], R1
  2C:C618  58F0       MOV [--R15], R0
```

### `2C:C61A` in `sub_2C_C07E`

```text
  2C:C5FC  58F0       MOV [--R15], R0
  2C:C5FE  68F1 7A0A  MOV REG[0xF1], #0x7A0A
  2C:C602  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C606  58F1       MOV [--R15], R1
  2C:C608  58F0       MOV [--R15], R0
  2C:C60A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C60E  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C612  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C616  58F1       MOV [--R15], R1
  2C:C618  58F0       MOV [--R15], R0
> 2C:C61A  BD03 4010  SCALL 03:4010
  2C:C61E  50FA       ADD R15, #0xA
  2C:C620  4802       MOV R0, #0x2
  2C:C622  58F0       MOV [--R15], R0
  2C:C624  68F1 7A82  MOV REG[0xF1], #0x7A82
  2C:C628  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C62C  58F1       MOV [--R15], R1
  2C:C62E  58F0       MOV [--R15], R0
  2C:C630  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C634  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C638  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C63C  58F1       MOV [--R15], R1
  2C:C63E  58F0       MOV [--R15], R0
```

### `2C:C640` in `sub_2C_C07E`

```text
  2C:C622  58F0       MOV [--R15], R0
  2C:C624  68F1 7A82  MOV REG[0xF1], #0x7A82
  2C:C628  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C62C  58F1       MOV [--R15], R1
  2C:C62E  58F0       MOV [--R15], R0
  2C:C630  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C634  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C638  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C63C  58F1       MOV [--R15], R1
  2C:C63E  58F0       MOV [--R15], R0
> 2C:C640  BD03 4010  SCALL 03:4010
  2C:C644  50FA       ADD R15, #0xA
  2C:C646  4801       MOV R0, #0x1
  2C:C648  58F0       MOV [--R15], R0
  2C:C64A  68F1 7A08  MOV REG[0xF1], #0x7A08
  2C:C64E  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C652  58F1       MOV [--R15], R1
  2C:C654  58F0       MOV [--R15], R0
  2C:C656  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C65A  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C65E  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C662  58F1       MOV [--R15], R1
  2C:C664  58F0       MOV [--R15], R0
```

### `2C:C666` in `sub_2C_C07E`

```text
  2C:C648  58F0       MOV [--R15], R0
  2C:C64A  68F1 7A08  MOV REG[0xF1], #0x7A08
  2C:C64E  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C652  58F1       MOV [--R15], R1
  2C:C654  58F0       MOV [--R15], R0
  2C:C656  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C65A  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C65E  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C662  58F1       MOV [--R15], R1
  2C:C664  58F0       MOV [--R15], R0
> 2C:C666  BD03 4010  SCALL 03:4010
  2C:C66A  50FA       ADD R15, #0xA
  2C:C66C  4802       MOV R0, #0x2
  2C:C66E  58F0       MOV [--R15], R0
  2C:C670  68F1 7A80  MOV REG[0xF1], #0x7A80
  2C:C674  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C678  58F1       MOV [--R15], R1
  2C:C67A  58F0       MOV [--R15], R0
  2C:C67C  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C680  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C684  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C688  58F1       MOV [--R15], R1
  2C:C68A  58F0       MOV [--R15], R0
```

### `2C:C68C` in `sub_2C_C07E`

```text
  2C:C66E  58F0       MOV [--R15], R0
  2C:C670  68F1 7A80  MOV REG[0xF1], #0x7A80
  2C:C674  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C678  58F1       MOV [--R15], R1
  2C:C67A  58F0       MOV [--R15], R0
  2C:C67C  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C680  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C684  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C688  58F1       MOV [--R15], R1
  2C:C68A  58F0       MOV [--R15], R0
> 2C:C68C  BD03 4010  SCALL 03:4010
  2C:C690  50FA       ADD R15, #0xA
  2C:C692  4801       MOV R0, #0x1
  2C:C694  58F0       MOV [--R15], R0
  2C:C696  68F1 7AE0  MOV REG[0xF1], #0x7AE0
  2C:C69A  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C69E  58F1       MOV [--R15], R1
  2C:C6A0  58F0       MOV [--R15], R0
  2C:C6A2  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C6A6  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C6AA  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C6AE  58F1       MOV [--R15], R1
  2C:C6B0  58F0       MOV [--R15], R0
```

### `2C:C6B2` in `sub_2C_C07E`

```text
  2C:C694  58F0       MOV [--R15], R0
  2C:C696  68F1 7AE0  MOV REG[0xF1], #0x7AE0
  2C:C69A  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C69E  58F1       MOV [--R15], R1
  2C:C6A0  58F0       MOV [--R15], R0
  2C:C6A2  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C6A6  88F0 7992  MOV REG[0xF0], [0x7992]
  2C:C6AA  88F1 7994  MOV REG[0xF1], [0x7994]
  2C:C6AE  58F1       MOV [--R15], R1
  2C:C6B0  58F0       MOV [--R15], R0
> 2C:C6B2  BD03 4010  SCALL 03:4010
  2C:C6B6  50FA       ADD R15, #0xA
  2C:C6B8  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C6BC  99F0 7AE0  MOVZE REG[0xF0], [0x7AE0]
  2C:C6C0  5600       CMP R0, #0x0
  2C:C6C2  AC02 C786  AJMP NZ/NE, 2C:C786
  2C:C6C6  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C6CA  58F0       MOV [--R15], R0
  2C:C6CC  780B FFDE  MOV R0, [R11+0xFFDE]
  2C:C6D0  781B FFE0  MOV R1, [R11+0xFFE0]
  2C:C6D4  58F1       MOV [--R15], R1
  2C:C6D6  58F0       MOV [--R15], R0
  2C:C6D8  68F0 0054  MOV REG[0xF0], #0x0054
```

### `2E:733C` in `sub_2E_63A8`

```text
  2E:7320  081B       MOV R1, R11
  2E:7322  70F1 FFFA  ADD REG[0xF1], #0xFFFA
  2E:7326  4800       MOV R0, #0x0
  2E:7328  58F1       MOV [--R15], R1
  2E:732A  58F0       MOV [--R15], R0
  2E:732C  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7330  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7334  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7338  58F1       MOV [--R15], R1
  2E:733A  58F0       MOV [--R15], R0
> 2E:733C  BD03 4010  SCALL 03:4010
  2E:7340  50FA       ADD R15, #0xA
  2E:7342  4800       MOV R0, #0x0
  2E:7344  58F0       MOV [--R15], R0
  2E:7346  6810 00A4  MOV REG[0x10], #0x00A4
  2E:734A  88F0 79BA  MOV REG[0xF0], [0x79BA]
  2E:734E  88F1 79BC  MOV REG[0xF1], [0x79BC]
  2E:7352  782B FFFA  MOV R2, [R11+0xFFFA]
  2E:7356  783B FFFC  MOV R3, [R11+0xFFFC]
  2E:735A  1013       ADD R1, R3
  2E:735C  1102       ADDC R0, R2
  2E:735E  58F1       MOV [--R15], R1
  2E:7360  58F0       MOV [--R15], R0
```

### `2E:73C2` in `sub_2E_63A8`

```text
  2E:73A6  68F2 0052  MOV REG[0xF2], #0x0052
  2E:73AA  1013       ADD R1, R3
  2E:73AC  1102       ADDC R0, R2
  2E:73AE  58F1       MOV [--R15], R1
  2E:73B0  58F0       MOV [--R15], R0
  2E:73B2  6810 00A4  MOV REG[0x10], #0x00A4
  2E:73B6  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:73BA  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:73BE  58F1       MOV [--R15], R1
  2E:73C0  58F0       MOV [--R15], R0
> 2E:73C2  BD03 4010  SCALL 03:4010
  2E:73C6  50FA       ADD R15, #0xA
  2E:73C8  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2E:73CC  1901       MOVZE R0, RB1
  2E:73CE  6A0B FFF8  MOV [R11+0xFFF8], R0
  2E:73D2  68F3 0094  MOV REG[0xF3], #0x0094
  2E:73D6  4820       MOV R2, #0x0
  2E:73D8  0850       MOV R5, R0
  2E:73DA  5650       CMP R5, #0x0
  2E:73DC  DE03       RJMP SGE, 2E:73E4 ; rel +3
  2E:73DE  68F4 FFFF  MOV REG[0xF4], #0xFFFF
  2E:73E2  D001       RJMP ALWAYS, 2E:73E6 ; rel +1
  2E:73E4  4840       MOV R4, #0x0
```

### `2E:7468` in `sub_2E_63A8`

```text
  2E:744C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7450  1013       ADD R1, R3
  2E:7452  1102       ADDC R0, R2
  2E:7454  58F1       MOV [--R15], R1
  2E:7456  58F0       MOV [--R15], R0
  2E:7458  6810 00A4  MOV REG[0x10], #0x00A4
  2E:745C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7460  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7464  58F1       MOV [--R15], R1
  2E:7466  58F0       MOV [--R15], R0
> 2E:7468  BD03 4010  SCALL 03:4010
  2E:746C  50FA       ADD R15, #0xA
  2E:746E  4801       MOV R0, #0x1
  2E:7470  58F0       MOV [--R15], R0
  2E:7472  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7476  4800       MOV R0, #0x0
  2E:7478  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:747C  1937       MOVZE R3, RB7
  2E:747E  5630       CMP R3, #0x0
  2E:7480  DE03       RJMP SGE, 2E:7488 ; rel +3
  2E:7482  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7486  D001       RJMP ALWAYS, 2E:748A ; rel +1
  2E:7488  4820       MOV R2, #0x0
```

### `2E:74B8` in `sub_2E_63A8`

```text
  2E:749C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:74A0  1013       ADD R1, R3
  2E:74A2  1102       ADDC R0, R2
  2E:74A4  58F1       MOV [--R15], R1
  2E:74A6  58F0       MOV [--R15], R0
  2E:74A8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:74AC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:74B0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:74B4  58F1       MOV [--R15], R1
  2E:74B6  58F0       MOV [--R15], R0
> 2E:74B8  BD03 4010  SCALL 03:4010
  2E:74BC  50FA       ADD R15, #0xA
  2E:74BE  4801       MOV R0, #0x1
  2E:74C0  58F0       MOV [--R15], R0
  2E:74C2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:74C6  4800       MOV R0, #0x0
  2E:74C8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:74CC  1937       MOVZE R3, RB7
  2E:74CE  5630       CMP R3, #0x0
  2E:74D0  DE03       RJMP SGE, 2E:74D8 ; rel +3
  2E:74D2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:74D6  D001       RJMP ALWAYS, 2E:74DA ; rel +1
  2E:74D8  4820       MOV R2, #0x0
```

### `2E:7508` in `sub_2E_63A8`

```text
  2E:74EC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:74F0  1013       ADD R1, R3
  2E:74F2  1102       ADDC R0, R2
  2E:74F4  58F1       MOV [--R15], R1
  2E:74F6  58F0       MOV [--R15], R0
  2E:74F8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:74FC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7500  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7504  58F1       MOV [--R15], R1
  2E:7506  58F0       MOV [--R15], R0
> 2E:7508  BD03 4010  SCALL 03:4010
  2E:750C  50FA       ADD R15, #0xA
  2E:750E  4801       MOV R0, #0x1
  2E:7510  58F0       MOV [--R15], R0
  2E:7512  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7516  4800       MOV R0, #0x0
  2E:7518  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:751C  1937       MOVZE R3, RB7
  2E:751E  5630       CMP R3, #0x0
  2E:7520  DE03       RJMP SGE, 2E:7528 ; rel +3
  2E:7522  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7526  D001       RJMP ALWAYS, 2E:752A ; rel +1
  2E:7528  4820       MOV R2, #0x0
```

### `2E:7558` in `sub_2E_63A8`

```text
  2E:753C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7540  1013       ADD R1, R3
  2E:7542  1102       ADDC R0, R2
  2E:7544  58F1       MOV [--R15], R1
  2E:7546  58F0       MOV [--R15], R0
  2E:7548  6810 00A4  MOV REG[0x10], #0x00A4
  2E:754C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7550  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7554  58F1       MOV [--R15], R1
  2E:7556  58F0       MOV [--R15], R0
> 2E:7558  BD03 4010  SCALL 03:4010
  2E:755C  50FA       ADD R15, #0xA
  2E:755E  4801       MOV R0, #0x1
  2E:7560  58F0       MOV [--R15], R0
  2E:7562  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7566  4800       MOV R0, #0x0
  2E:7568  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:756C  1937       MOVZE R3, RB7
  2E:756E  5630       CMP R3, #0x0
  2E:7570  DE03       RJMP SGE, 2E:7578 ; rel +3
  2E:7572  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7576  D001       RJMP ALWAYS, 2E:757A ; rel +1
  2E:7578  4820       MOV R2, #0x0
```

### `2E:75A8` in `sub_2E_63A8`

```text
  2E:758C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7590  1013       ADD R1, R3
  2E:7592  1102       ADDC R0, R2
  2E:7594  58F1       MOV [--R15], R1
  2E:7596  58F0       MOV [--R15], R0
  2E:7598  6810 00A4  MOV REG[0x10], #0x00A4
  2E:759C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:75A0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:75A4  58F1       MOV [--R15], R1
  2E:75A6  58F0       MOV [--R15], R0
> 2E:75A8  BD03 4010  SCALL 03:4010
  2E:75AC  50FA       ADD R15, #0xA
  2E:75AE  4801       MOV R0, #0x1
  2E:75B0  58F0       MOV [--R15], R0
  2E:75B2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:75B6  4800       MOV R0, #0x0
  2E:75B8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:75BC  1937       MOVZE R3, RB7
  2E:75BE  5630       CMP R3, #0x0
  2E:75C0  DE03       RJMP SGE, 2E:75C8 ; rel +3
  2E:75C2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:75C6  D001       RJMP ALWAYS, 2E:75CA ; rel +1
  2E:75C8  4820       MOV R2, #0x0
```

### `2E:75F8` in `sub_2E_63A8`

```text
  2E:75DC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:75E0  1013       ADD R1, R3
  2E:75E2  1102       ADDC R0, R2
  2E:75E4  58F1       MOV [--R15], R1
  2E:75E6  58F0       MOV [--R15], R0
  2E:75E8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:75EC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:75F0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:75F4  58F1       MOV [--R15], R1
  2E:75F6  58F0       MOV [--R15], R0
> 2E:75F8  BD03 4010  SCALL 03:4010
  2E:75FC  50FA       ADD R15, #0xA
  2E:75FE  4801       MOV R0, #0x1
  2E:7600  58F0       MOV [--R15], R0
  2E:7602  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7606  4800       MOV R0, #0x0
  2E:7608  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:760C  1937       MOVZE R3, RB7
  2E:760E  5630       CMP R3, #0x0
  2E:7610  DE03       RJMP SGE, 2E:7618 ; rel +3
  2E:7612  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7616  D001       RJMP ALWAYS, 2E:761A ; rel +1
  2E:7618  4820       MOV R2, #0x0
```

### `2E:7648` in `sub_2E_63A8`

```text
  2E:762C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7630  1013       ADD R1, R3
  2E:7632  1102       ADDC R0, R2
  2E:7634  58F1       MOV [--R15], R1
  2E:7636  58F0       MOV [--R15], R0
  2E:7638  6810 00A4  MOV REG[0x10], #0x00A4
  2E:763C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7640  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7644  58F1       MOV [--R15], R1
  2E:7646  58F0       MOV [--R15], R0
> 2E:7648  BD03 4010  SCALL 03:4010
  2E:764C  50FA       ADD R15, #0xA
  2E:764E  4802       MOV R0, #0x2
  2E:7650  58F0       MOV [--R15], R0
  2E:7652  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7656  4800       MOV R0, #0x0
  2E:7658  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:765C  1937       MOVZE R3, RB7
  2E:765E  5630       CMP R3, #0x0
  2E:7660  DE03       RJMP SGE, 2E:7668 ; rel +3
  2E:7662  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7666  D001       RJMP ALWAYS, 2E:766A ; rel +1
  2E:7668  4820       MOV R2, #0x0
```

### `2E:7698` in `sub_2E_63A8`

```text
  2E:767C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7680  1013       ADD R1, R3
  2E:7682  1102       ADDC R0, R2
  2E:7684  58F1       MOV [--R15], R1
  2E:7686  58F0       MOV [--R15], R0
  2E:7688  6810 00A4  MOV REG[0x10], #0x00A4
  2E:768C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7690  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7694  58F1       MOV [--R15], R1
  2E:7696  58F0       MOV [--R15], R0
> 2E:7698  BD03 4010  SCALL 03:4010
  2E:769C  50FA       ADD R15, #0xA
  2E:769E  4802       MOV R0, #0x2
  2E:76A0  58F0       MOV [--R15], R0
  2E:76A2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:76A6  4800       MOV R0, #0x0
  2E:76A8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:76AC  1937       MOVZE R3, RB7
  2E:76AE  5630       CMP R3, #0x0
  2E:76B0  DE03       RJMP SGE, 2E:76B8 ; rel +3
  2E:76B2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:76B6  D001       RJMP ALWAYS, 2E:76BA ; rel +1
  2E:76B8  4820       MOV R2, #0x0
```

### `2E:76E8` in `sub_2E_63A8`

```text
  2E:76CC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:76D0  1013       ADD R1, R3
  2E:76D2  1102       ADDC R0, R2
  2E:76D4  58F1       MOV [--R15], R1
  2E:76D6  58F0       MOV [--R15], R0
  2E:76D8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:76DC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:76E0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:76E4  58F1       MOV [--R15], R1
  2E:76E6  58F0       MOV [--R15], R0
> 2E:76E8  BD03 4010  SCALL 03:4010
  2E:76EC  50FA       ADD R15, #0xA
  2E:76EE  4802       MOV R0, #0x2
  2E:76F0  58F0       MOV [--R15], R0
  2E:76F2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:76F6  4800       MOV R0, #0x0
  2E:76F8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:76FC  1937       MOVZE R3, RB7
  2E:76FE  5630       CMP R3, #0x0
  2E:7700  DE03       RJMP SGE, 2E:7708 ; rel +3
  2E:7702  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7706  D001       RJMP ALWAYS, 2E:770A ; rel +1
  2E:7708  4820       MOV R2, #0x0
```

### `2E:7738` in `sub_2E_63A8`

```text
  2E:771C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7720  1013       ADD R1, R3
  2E:7722  1102       ADDC R0, R2
  2E:7724  58F1       MOV [--R15], R1
  2E:7726  58F0       MOV [--R15], R0
  2E:7728  6810 00A4  MOV REG[0x10], #0x00A4
  2E:772C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7730  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7734  58F1       MOV [--R15], R1
  2E:7736  58F0       MOV [--R15], R0
> 2E:7738  BD03 4010  SCALL 03:4010
  2E:773C  50FA       ADD R15, #0xA
  2E:773E  4802       MOV R0, #0x2
  2E:7740  58F0       MOV [--R15], R0
  2E:7742  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7746  4800       MOV R0, #0x0
  2E:7748  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:774C  1937       MOVZE R3, RB7
  2E:774E  5630       CMP R3, #0x0
  2E:7750  DE03       RJMP SGE, 2E:7758 ; rel +3
  2E:7752  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7756  D001       RJMP ALWAYS, 2E:775A ; rel +1
  2E:7758  4820       MOV R2, #0x0
```

### `2E:7788` in `sub_2E_63A8`

```text
  2E:776C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7770  1013       ADD R1, R3
  2E:7772  1102       ADDC R0, R2
  2E:7774  58F1       MOV [--R15], R1
  2E:7776  58F0       MOV [--R15], R0
  2E:7778  6810 00A4  MOV REG[0x10], #0x00A4
  2E:777C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7780  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7784  58F1       MOV [--R15], R1
  2E:7786  58F0       MOV [--R15], R0
> 2E:7788  BD03 4010  SCALL 03:4010
  2E:778C  50FA       ADD R15, #0xA
  2E:778E  4802       MOV R0, #0x2
  2E:7790  58F0       MOV [--R15], R0
  2E:7792  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7796  4800       MOV R0, #0x0
  2E:7798  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:779C  1937       MOVZE R3, RB7
  2E:779E  5630       CMP R3, #0x0
  2E:77A0  DE03       RJMP SGE, 2E:77A8 ; rel +3
  2E:77A2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:77A6  D001       RJMP ALWAYS, 2E:77AA ; rel +1
  2E:77A8  4820       MOV R2, #0x0
```

### `2E:77D8` in `sub_2E_63A8`

```text
  2E:77BC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:77C0  1013       ADD R1, R3
  2E:77C2  1102       ADDC R0, R2
  2E:77C4  58F1       MOV [--R15], R1
  2E:77C6  58F0       MOV [--R15], R0
  2E:77C8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:77CC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:77D0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:77D4  58F1       MOV [--R15], R1
  2E:77D6  58F0       MOV [--R15], R0
> 2E:77D8  BD03 4010  SCALL 03:4010
  2E:77DC  50FA       ADD R15, #0xA
  2E:77DE  4802       MOV R0, #0x2
  2E:77E0  58F0       MOV [--R15], R0
  2E:77E2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:77E6  4800       MOV R0, #0x0
  2E:77E8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:77EC  1937       MOVZE R3, RB7
  2E:77EE  5630       CMP R3, #0x0
  2E:77F0  DE03       RJMP SGE, 2E:77F8 ; rel +3
  2E:77F2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:77F6  D001       RJMP ALWAYS, 2E:77FA ; rel +1
  2E:77F8  4820       MOV R2, #0x0
```

### `2E:7828` in `sub_2E_63A8`

```text
  2E:780C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7810  1013       ADD R1, R3
  2E:7812  1102       ADDC R0, R2
  2E:7814  58F1       MOV [--R15], R1
  2E:7816  58F0       MOV [--R15], R0
  2E:7818  6810 00A4  MOV REG[0x10], #0x00A4
  2E:781C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7820  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7824  58F1       MOV [--R15], R1
  2E:7826  58F0       MOV [--R15], R0
> 2E:7828  BD03 4010  SCALL 03:4010
  2E:782C  50FA       ADD R15, #0xA
  2E:782E  4802       MOV R0, #0x2
  2E:7830  58F0       MOV [--R15], R0
  2E:7832  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7836  4800       MOV R0, #0x0
  2E:7838  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:783C  1937       MOVZE R3, RB7
  2E:783E  5630       CMP R3, #0x0
  2E:7840  DE03       RJMP SGE, 2E:7848 ; rel +3
  2E:7842  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7846  D001       RJMP ALWAYS, 2E:784A ; rel +1
  2E:7848  4820       MOV R2, #0x0
```

### `2E:7878` in `sub_2E_63A8`

```text
  2E:785C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7860  1013       ADD R1, R3
  2E:7862  1102       ADDC R0, R2
  2E:7864  58F1       MOV [--R15], R1
  2E:7866  58F0       MOV [--R15], R0
  2E:7868  6810 00A4  MOV REG[0x10], #0x00A4
  2E:786C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7870  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7874  58F1       MOV [--R15], R1
  2E:7876  58F0       MOV [--R15], R0
> 2E:7878  BD03 4010  SCALL 03:4010
  2E:787C  50FA       ADD R15, #0xA
```

### `2E:78C8` in `sub_2E_787E`

```text
  2E:78AC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:78B0  1013       ADD R1, R3
  2E:78B2  1102       ADDC R0, R2
  2E:78B4  58F1       MOV [--R15], R1
  2E:78B6  58F0       MOV [--R15], R0
  2E:78B8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:78BC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:78C0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:78C4  58F1       MOV [--R15], R1
  2E:78C6  58F0       MOV [--R15], R0
> 2E:78C8  BD03 4010  SCALL 03:4010
  2E:78CC  50FA       ADD R15, #0xA
  2E:78CE  4801       MOV R0, #0x1
  2E:78D0  58F0       MOV [--R15], R0
  2E:78D2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:78D6  4800       MOV R0, #0x0
  2E:78D8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:78DC  1937       MOVZE R3, RB7
  2E:78DE  5630       CMP R3, #0x0
  2E:78E0  DE03       RJMP SGE, 2E:78E8 ; rel +3
  2E:78E2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:78E6  D001       RJMP ALWAYS, 2E:78EA ; rel +1
  2E:78E8  4820       MOV R2, #0x0
```

### `2E:7918` in `sub_2E_787E`

```text
  2E:78FC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7900  1013       ADD R1, R3
  2E:7902  1102       ADDC R0, R2
  2E:7904  58F1       MOV [--R15], R1
  2E:7906  58F0       MOV [--R15], R0
  2E:7908  6810 00A4  MOV REG[0x10], #0x00A4
  2E:790C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7910  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7914  58F1       MOV [--R15], R1
  2E:7916  58F0       MOV [--R15], R0
> 2E:7918  BD03 4010  SCALL 03:4010
  2E:791C  50FA       ADD R15, #0xA
  2E:791E  4802       MOV R0, #0x2
  2E:7920  58F0       MOV [--R15], R0
  2E:7922  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7926  4800       MOV R0, #0x0
  2E:7928  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:792C  1937       MOVZE R3, RB7
  2E:792E  5630       CMP R3, #0x0
  2E:7930  DE03       RJMP SGE, 2E:7938 ; rel +3
  2E:7932  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7936  D001       RJMP ALWAYS, 2E:793A ; rel +1
  2E:7938  4820       MOV R2, #0x0
```

### `2E:7968` in `sub_2E_787E`

```text
  2E:794C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7950  1013       ADD R1, R3
  2E:7952  1102       ADDC R0, R2
  2E:7954  58F1       MOV [--R15], R1
  2E:7956  58F0       MOV [--R15], R0
  2E:7958  6810 00A4  MOV REG[0x10], #0x00A4
  2E:795C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7960  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7964  58F1       MOV [--R15], R1
  2E:7966  58F0       MOV [--R15], R0
> 2E:7968  BD03 4010  SCALL 03:4010
  2E:796C  50FA       ADD R15, #0xA
  2E:796E  4802       MOV R0, #0x2
  2E:7970  58F0       MOV [--R15], R0
  2E:7972  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7976  4800       MOV R0, #0x0
  2E:7978  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:797C  1937       MOVZE R3, RB7
  2E:797E  5630       CMP R3, #0x0
  2E:7980  DE03       RJMP SGE, 2E:7988 ; rel +3
  2E:7982  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7986  D001       RJMP ALWAYS, 2E:798A ; rel +1
  2E:7988  4820       MOV R2, #0x0
```

### `2E:79B8` in `sub_2E_787E`

```text
  2E:799C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:79A0  1013       ADD R1, R3
  2E:79A2  1102       ADDC R0, R2
  2E:79A4  58F1       MOV [--R15], R1
  2E:79A6  58F0       MOV [--R15], R0
  2E:79A8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:79AC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:79B0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:79B4  58F1       MOV [--R15], R1
  2E:79B6  58F0       MOV [--R15], R0
> 2E:79B8  BD03 4010  SCALL 03:4010
  2E:79BC  50FA       ADD R15, #0xA
  2E:79BE  4802       MOV R0, #0x2
  2E:79C0  58F0       MOV [--R15], R0
  2E:79C2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:79C6  4800       MOV R0, #0x0
  2E:79C8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:79CC  1937       MOVZE R3, RB7
  2E:79CE  5630       CMP R3, #0x0
  2E:79D0  DE03       RJMP SGE, 2E:79D8 ; rel +3
  2E:79D2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:79D6  D001       RJMP ALWAYS, 2E:79DA ; rel +1
  2E:79D8  4820       MOV R2, #0x0
```

### `2E:7A08` in `sub_2E_787E`

```text
  2E:79EC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:79F0  1013       ADD R1, R3
  2E:79F2  1102       ADDC R0, R2
  2E:79F4  58F1       MOV [--R15], R1
  2E:79F6  58F0       MOV [--R15], R0
  2E:79F8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:79FC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7A00  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7A04  58F1       MOV [--R15], R1
  2E:7A06  58F0       MOV [--R15], R0
> 2E:7A08  BD03 4010  SCALL 03:4010
  2E:7A0C  50FA       ADD R15, #0xA
  2E:7A0E  4802       MOV R0, #0x2
  2E:7A10  58F0       MOV [--R15], R0
  2E:7A12  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7A16  4800       MOV R0, #0x0
  2E:7A18  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7A1C  1937       MOVZE R3, RB7
  2E:7A1E  5630       CMP R3, #0x0
  2E:7A20  DE03       RJMP SGE, 2E:7A28 ; rel +3
  2E:7A22  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7A26  D001       RJMP ALWAYS, 2E:7A2A ; rel +1
  2E:7A28  4820       MOV R2, #0x0
```

### `2E:7A58` in `sub_2E_787E`

```text
  2E:7A3C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7A40  1013       ADD R1, R3
  2E:7A42  1102       ADDC R0, R2
  2E:7A44  58F1       MOV [--R15], R1
  2E:7A46  58F0       MOV [--R15], R0
  2E:7A48  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7A4C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7A50  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7A54  58F1       MOV [--R15], R1
  2E:7A56  58F0       MOV [--R15], R0
> 2E:7A58  BD03 4010  SCALL 03:4010
  2E:7A5C  50FA       ADD R15, #0xA
  2E:7A5E  4802       MOV R0, #0x2
  2E:7A60  58F0       MOV [--R15], R0
  2E:7A62  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7A66  4800       MOV R0, #0x0
  2E:7A68  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7A6C  1937       MOVZE R3, RB7
  2E:7A6E  5630       CMP R3, #0x0
  2E:7A70  DE03       RJMP SGE, 2E:7A78 ; rel +3
  2E:7A72  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7A76  D001       RJMP ALWAYS, 2E:7A7A ; rel +1
  2E:7A78  4820       MOV R2, #0x0
```

### `2E:7AA8` in `sub_2E_787E`

```text
  2E:7A8C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7A90  1013       ADD R1, R3
  2E:7A92  1102       ADDC R0, R2
  2E:7A94  58F1       MOV [--R15], R1
  2E:7A96  58F0       MOV [--R15], R0
  2E:7A98  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7A9C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7AA0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7AA4  58F1       MOV [--R15], R1
  2E:7AA6  58F0       MOV [--R15], R0
> 2E:7AA8  BD03 4010  SCALL 03:4010
  2E:7AAC  50FA       ADD R15, #0xA
  2E:7AAE  4802       MOV R0, #0x2
  2E:7AB0  58F0       MOV [--R15], R0
  2E:7AB2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7AB6  4800       MOV R0, #0x0
  2E:7AB8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7ABC  1937       MOVZE R3, RB7
  2E:7ABE  5630       CMP R3, #0x0
  2E:7AC0  DE03       RJMP SGE, 2E:7AC8 ; rel +3
  2E:7AC2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7AC6  D001       RJMP ALWAYS, 2E:7ACA ; rel +1
  2E:7AC8  4820       MOV R2, #0x0
```

### `2E:7AF8` in `sub_2E_787E`

```text
  2E:7ADC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7AE0  1013       ADD R1, R3
  2E:7AE2  1102       ADDC R0, R2
  2E:7AE4  58F1       MOV [--R15], R1
  2E:7AE6  58F0       MOV [--R15], R0
  2E:7AE8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7AEC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7AF0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7AF4  58F1       MOV [--R15], R1
  2E:7AF6  58F0       MOV [--R15], R0
> 2E:7AF8  BD03 4010  SCALL 03:4010
  2E:7AFC  50FA       ADD R15, #0xA
  2E:7AFE  4802       MOV R0, #0x2
  2E:7B00  58F0       MOV [--R15], R0
  2E:7B02  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7B06  4800       MOV R0, #0x0
  2E:7B08  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7B0C  1937       MOVZE R3, RB7
  2E:7B0E  5630       CMP R3, #0x0
  2E:7B10  DE03       RJMP SGE, 2E:7B18 ; rel +3
  2E:7B12  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7B16  D001       RJMP ALWAYS, 2E:7B1A ; rel +1
  2E:7B18  4820       MOV R2, #0x0
```

### `2E:7B48` in `sub_2E_787E`

```text
  2E:7B2C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7B30  1013       ADD R1, R3
  2E:7B32  1102       ADDC R0, R2
  2E:7B34  58F1       MOV [--R15], R1
  2E:7B36  58F0       MOV [--R15], R0
  2E:7B38  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7B3C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7B40  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7B44  58F1       MOV [--R15], R1
  2E:7B46  58F0       MOV [--R15], R0
> 2E:7B48  BD03 4010  SCALL 03:4010
  2E:7B4C  50FA       ADD R15, #0xA
  2E:7B4E  4802       MOV R0, #0x2
  2E:7B50  58F0       MOV [--R15], R0
  2E:7B52  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7B56  4800       MOV R0, #0x0
  2E:7B58  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7B5C  1937       MOVZE R3, RB7
  2E:7B5E  5630       CMP R3, #0x0
  2E:7B60  DE03       RJMP SGE, 2E:7B68 ; rel +3
  2E:7B62  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7B66  D001       RJMP ALWAYS, 2E:7B6A ; rel +1
  2E:7B68  4820       MOV R2, #0x0
```

### `2E:7B98` in `sub_2E_787E`

```text
  2E:7B7C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7B80  1013       ADD R1, R3
  2E:7B82  1102       ADDC R0, R2
  2E:7B84  58F1       MOV [--R15], R1
  2E:7B86  58F0       MOV [--R15], R0
  2E:7B88  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7B8C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7B90  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7B94  58F1       MOV [--R15], R1
  2E:7B96  58F0       MOV [--R15], R0
> 2E:7B98  BD03 4010  SCALL 03:4010
  2E:7B9C  50FA       ADD R15, #0xA
  2E:7B9E  4802       MOV R0, #0x2
  2E:7BA0  58F0       MOV [--R15], R0
  2E:7BA2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7BA6  4800       MOV R0, #0x0
  2E:7BA8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7BAC  1937       MOVZE R3, RB7
  2E:7BAE  5630       CMP R3, #0x0
  2E:7BB0  DE03       RJMP SGE, 2E:7BB8 ; rel +3
  2E:7BB2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7BB6  D001       RJMP ALWAYS, 2E:7BBA ; rel +1
  2E:7BB8  4820       MOV R2, #0x0
```

### `2E:7BE8` in `sub_2E_787E`

```text
  2E:7BCC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7BD0  1013       ADD R1, R3
  2E:7BD2  1102       ADDC R0, R2
  2E:7BD4  58F1       MOV [--R15], R1
  2E:7BD6  58F0       MOV [--R15], R0
  2E:7BD8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7BDC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7BE0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7BE4  58F1       MOV [--R15], R1
  2E:7BE6  58F0       MOV [--R15], R0
> 2E:7BE8  BD03 4010  SCALL 03:4010
  2E:7BEC  50FA       ADD R15, #0xA
  2E:7BEE  4802       MOV R0, #0x2
  2E:7BF0  58F0       MOV [--R15], R0
  2E:7BF2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7BF6  4800       MOV R0, #0x0
  2E:7BF8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7BFC  1937       MOVZE R3, RB7
  2E:7BFE  5630       CMP R3, #0x0
  2E:7C00  DE03       RJMP SGE, 2E:7C08 ; rel +3
  2E:7C02  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7C06  D001       RJMP ALWAYS, 2E:7C0A ; rel +1
  2E:7C08  4820       MOV R2, #0x0
```

### `2E:7C38` in `sub_2E_787E`

```text
  2E:7C1C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7C20  1013       ADD R1, R3
  2E:7C22  1102       ADDC R0, R2
  2E:7C24  58F1       MOV [--R15], R1
  2E:7C26  58F0       MOV [--R15], R0
  2E:7C28  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7C2C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7C30  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7C34  58F1       MOV [--R15], R1
  2E:7C36  58F0       MOV [--R15], R0
> 2E:7C38  BD03 4010  SCALL 03:4010
  2E:7C3C  50FA       ADD R15, #0xA
  2E:7C3E  4802       MOV R0, #0x2
  2E:7C40  58F0       MOV [--R15], R0
  2E:7C42  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7C46  4800       MOV R0, #0x0
  2E:7C48  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7C4C  1937       MOVZE R3, RB7
  2E:7C4E  5630       CMP R3, #0x0
  2E:7C50  DE03       RJMP SGE, 2E:7C58 ; rel +3
  2E:7C52  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7C56  D001       RJMP ALWAYS, 2E:7C5A ; rel +1
  2E:7C58  4820       MOV R2, #0x0
```

### `2E:7C88` in `sub_2E_787E`

```text
  2E:7C6C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7C70  1013       ADD R1, R3
  2E:7C72  1102       ADDC R0, R2
  2E:7C74  58F1       MOV [--R15], R1
  2E:7C76  58F0       MOV [--R15], R0
  2E:7C78  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7C7C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7C80  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7C84  58F1       MOV [--R15], R1
  2E:7C86  58F0       MOV [--R15], R0
> 2E:7C88  BD03 4010  SCALL 03:4010
  2E:7C8C  50FA       ADD R15, #0xA
  2E:7C8E  4801       MOV R0, #0x1
  2E:7C90  58F0       MOV [--R15], R0
  2E:7C92  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7C96  4800       MOV R0, #0x0
  2E:7C98  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7C9C  1937       MOVZE R3, RB7
  2E:7C9E  5630       CMP R3, #0x0
  2E:7CA0  DE03       RJMP SGE, 2E:7CA8 ; rel +3
  2E:7CA2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7CA6  D001       RJMP ALWAYS, 2E:7CAA ; rel +1
  2E:7CA8  4820       MOV R2, #0x0
```

### `2E:7CD8` in `sub_2E_787E`

```text
  2E:7CBC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7CC0  1013       ADD R1, R3
  2E:7CC2  1102       ADDC R0, R2
  2E:7CC4  58F1       MOV [--R15], R1
  2E:7CC6  58F0       MOV [--R15], R0
  2E:7CC8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7CCC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7CD0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7CD4  58F1       MOV [--R15], R1
  2E:7CD6  58F0       MOV [--R15], R0
> 2E:7CD8  BD03 4010  SCALL 03:4010
  2E:7CDC  50FA       ADD R15, #0xA
  2E:7CDE  4801       MOV R0, #0x1
  2E:7CE0  58F0       MOV [--R15], R0
  2E:7CE2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7CE6  4800       MOV R0, #0x0
  2E:7CE8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7CEC  1937       MOVZE R3, RB7
  2E:7CEE  5630       CMP R3, #0x0
  2E:7CF0  DE03       RJMP SGE, 2E:7CF8 ; rel +3
  2E:7CF2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7CF6  D001       RJMP ALWAYS, 2E:7CFA ; rel +1
  2E:7CF8  4820       MOV R2, #0x0
```

### `2E:7D28` in `sub_2E_787E`

```text
  2E:7D0C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7D10  1013       ADD R1, R3
  2E:7D12  1102       ADDC R0, R2
  2E:7D14  58F1       MOV [--R15], R1
  2E:7D16  58F0       MOV [--R15], R0
  2E:7D18  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7D1C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7D20  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7D24  58F1       MOV [--R15], R1
  2E:7D26  58F0       MOV [--R15], R0
> 2E:7D28  BD03 4010  SCALL 03:4010
  2E:7D2C  50FA       ADD R15, #0xA
  2E:7D2E  4801       MOV R0, #0x1
  2E:7D30  58F0       MOV [--R15], R0
  2E:7D32  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7D36  4800       MOV R0, #0x0
  2E:7D38  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7D3C  1937       MOVZE R3, RB7
  2E:7D3E  5630       CMP R3, #0x0
  2E:7D40  DE03       RJMP SGE, 2E:7D48 ; rel +3
  2E:7D42  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7D46  D001       RJMP ALWAYS, 2E:7D4A ; rel +1
  2E:7D48  4820       MOV R2, #0x0
```

### `2E:7D78` in `sub_2E_787E`

```text
  2E:7D5C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7D60  1013       ADD R1, R3
  2E:7D62  1102       ADDC R0, R2
  2E:7D64  58F1       MOV [--R15], R1
  2E:7D66  58F0       MOV [--R15], R0
  2E:7D68  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7D6C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7D70  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7D74  58F1       MOV [--R15], R1
  2E:7D76  58F0       MOV [--R15], R0
> 2E:7D78  BD03 4010  SCALL 03:4010
  2E:7D7C  50FA       ADD R15, #0xA
  2E:7D7E  4801       MOV R0, #0x1
  2E:7D80  58F0       MOV [--R15], R0
  2E:7D82  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7D86  4800       MOV R0, #0x0
  2E:7D88  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7D8C  1937       MOVZE R3, RB7
  2E:7D8E  5630       CMP R3, #0x0
  2E:7D90  DE03       RJMP SGE, 2E:7D98 ; rel +3
  2E:7D92  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7D96  D001       RJMP ALWAYS, 2E:7D9A ; rel +1
  2E:7D98  4820       MOV R2, #0x0
```

### `2E:7DC8` in `sub_2E_787E`

```text
  2E:7DAC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7DB0  1013       ADD R1, R3
  2E:7DB2  1102       ADDC R0, R2
  2E:7DB4  58F1       MOV [--R15], R1
  2E:7DB6  58F0       MOV [--R15], R0
  2E:7DB8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7DBC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7DC0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7DC4  58F1       MOV [--R15], R1
  2E:7DC6  58F0       MOV [--R15], R0
> 2E:7DC8  BD03 4010  SCALL 03:4010
  2E:7DCC  50FA       ADD R15, #0xA
  2E:7DCE  4801       MOV R0, #0x1
  2E:7DD0  58F0       MOV [--R15], R0
  2E:7DD2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7DD6  4800       MOV R0, #0x0
  2E:7DD8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7DDC  1937       MOVZE R3, RB7
  2E:7DDE  5630       CMP R3, #0x0
  2E:7DE0  DE03       RJMP SGE, 2E:7DE8 ; rel +3
  2E:7DE2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7DE6  D001       RJMP ALWAYS, 2E:7DEA ; rel +1
  2E:7DE8  4820       MOV R2, #0x0
```

### `2E:7E18` in `sub_2E_787E`

```text
  2E:7DFC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7E00  1013       ADD R1, R3
  2E:7E02  1102       ADDC R0, R2
  2E:7E04  58F1       MOV [--R15], R1
  2E:7E06  58F0       MOV [--R15], R0
  2E:7E08  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7E0C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7E10  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7E14  58F1       MOV [--R15], R1
  2E:7E16  58F0       MOV [--R15], R0
> 2E:7E18  BD03 4010  SCALL 03:4010
  2E:7E1C  50FA       ADD R15, #0xA
  2E:7E1E  4801       MOV R0, #0x1
  2E:7E20  58F0       MOV [--R15], R0
  2E:7E22  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7E26  4800       MOV R0, #0x0
  2E:7E28  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7E2C  1937       MOVZE R3, RB7
  2E:7E2E  5630       CMP R3, #0x0
  2E:7E30  DE03       RJMP SGE, 2E:7E38 ; rel +3
  2E:7E32  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7E36  D001       RJMP ALWAYS, 2E:7E3A ; rel +1
  2E:7E38  4820       MOV R2, #0x0
```

### `2E:7E68` in `sub_2E_787E`

```text
  2E:7E4C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7E50  1013       ADD R1, R3
  2E:7E52  1102       ADDC R0, R2
  2E:7E54  58F1       MOV [--R15], R1
  2E:7E56  58F0       MOV [--R15], R0
  2E:7E58  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7E5C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7E60  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7E64  58F1       MOV [--R15], R1
  2E:7E66  58F0       MOV [--R15], R0
> 2E:7E68  BD03 4010  SCALL 03:4010
  2E:7E6C  50FA       ADD R15, #0xA
  2E:7E6E  4801       MOV R0, #0x1
  2E:7E70  58F0       MOV [--R15], R0
  2E:7E72  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7E76  4800       MOV R0, #0x0
  2E:7E78  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7E7C  1937       MOVZE R3, RB7
  2E:7E7E  5630       CMP R3, #0x0
  2E:7E80  DE03       RJMP SGE, 2E:7E88 ; rel +3
  2E:7E82  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7E86  D001       RJMP ALWAYS, 2E:7E8A ; rel +1
  2E:7E88  4820       MOV R2, #0x0
```

### `2E:7EB8` in `sub_2E_787E`

```text
  2E:7E9C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7EA0  1013       ADD R1, R3
  2E:7EA2  1102       ADDC R0, R2
  2E:7EA4  58F1       MOV [--R15], R1
  2E:7EA6  58F0       MOV [--R15], R0
  2E:7EA8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7EAC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7EB0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7EB4  58F1       MOV [--R15], R1
  2E:7EB6  58F0       MOV [--R15], R0
> 2E:7EB8  BD03 4010  SCALL 03:4010
  2E:7EBC  50FA       ADD R15, #0xA
  2E:7EBE  4801       MOV R0, #0x1
  2E:7EC0  58F0       MOV [--R15], R0
  2E:7EC2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7EC6  4800       MOV R0, #0x0
  2E:7EC8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7ECC  1937       MOVZE R3, RB7
  2E:7ECE  5630       CMP R3, #0x0
  2E:7ED0  DE03       RJMP SGE, 2E:7ED8 ; rel +3
  2E:7ED2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7ED6  D001       RJMP ALWAYS, 2E:7EDA ; rel +1
  2E:7ED8  4820       MOV R2, #0x0
```

### `2E:7F08` in `sub_2E_787E`

```text
  2E:7EEC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7EF0  1013       ADD R1, R3
  2E:7EF2  1102       ADDC R0, R2
  2E:7EF4  58F1       MOV [--R15], R1
  2E:7EF6  58F0       MOV [--R15], R0
  2E:7EF8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7EFC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7F00  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7F04  58F1       MOV [--R15], R1
  2E:7F06  58F0       MOV [--R15], R0
> 2E:7F08  BD03 4010  SCALL 03:4010
  2E:7F0C  50FA       ADD R15, #0xA
  2E:7F0E  4801       MOV R0, #0x1
  2E:7F10  58F0       MOV [--R15], R0
  2E:7F12  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7F16  4800       MOV R0, #0x0
  2E:7F18  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7F1C  1937       MOVZE R3, RB7
  2E:7F1E  5630       CMP R3, #0x0
  2E:7F20  DE03       RJMP SGE, 2E:7F28 ; rel +3
  2E:7F22  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7F26  D001       RJMP ALWAYS, 2E:7F2A ; rel +1
  2E:7F28  4820       MOV R2, #0x0
```

### `2E:7F58` in `sub_2E_787E`

```text
  2E:7F3C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7F40  1013       ADD R1, R3
  2E:7F42  1102       ADDC R0, R2
  2E:7F44  58F1       MOV [--R15], R1
  2E:7F46  58F0       MOV [--R15], R0
  2E:7F48  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7F4C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7F50  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7F54  58F1       MOV [--R15], R1
  2E:7F56  58F0       MOV [--R15], R0
> 2E:7F58  BD03 4010  SCALL 03:4010
  2E:7F5C  50FA       ADD R15, #0xA
  2E:7F5E  4801       MOV R0, #0x1
  2E:7F60  58F0       MOV [--R15], R0
  2E:7F62  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7F66  4800       MOV R0, #0x0
  2E:7F68  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7F6C  1937       MOVZE R3, RB7
  2E:7F6E  5630       CMP R3, #0x0
  2E:7F70  DE03       RJMP SGE, 2E:7F78 ; rel +3
  2E:7F72  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7F76  D001       RJMP ALWAYS, 2E:7F7A ; rel +1
  2E:7F78  4820       MOV R2, #0x0
```

### `2E:7FA8` in `sub_2E_787E`

```text
  2E:7F8C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7F90  1013       ADD R1, R3
  2E:7F92  1102       ADDC R0, R2
  2E:7F94  58F1       MOV [--R15], R1
  2E:7F96  58F0       MOV [--R15], R0
  2E:7F98  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7F9C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7FA0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7FA4  58F1       MOV [--R15], R1
  2E:7FA6  58F0       MOV [--R15], R0
> 2E:7FA8  BD03 4010  SCALL 03:4010
  2E:7FAC  50FA       ADD R15, #0xA
  2E:7FAE  4801       MOV R0, #0x1
  2E:7FB0  58F0       MOV [--R15], R0
  2E:7FB2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7FB6  4800       MOV R0, #0x0
  2E:7FB8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7FBC  1937       MOVZE R3, RB7
  2E:7FBE  5630       CMP R3, #0x0
  2E:7FC0  DE03       RJMP SGE, 2E:7FC8 ; rel +3
  2E:7FC2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7FC6  D001       RJMP ALWAYS, 2E:7FCA ; rel +1
  2E:7FC8  4820       MOV R2, #0x0
```

### `2E:7FF8` in `sub_2E_787E`

```text
  2E:7FDC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:7FE0  1013       ADD R1, R3
  2E:7FE2  1102       ADDC R0, R2
  2E:7FE4  58F1       MOV [--R15], R1
  2E:7FE6  58F0       MOV [--R15], R0
  2E:7FE8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7FEC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7FF0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7FF4  58F1       MOV [--R15], R1
  2E:7FF6  58F0       MOV [--R15], R0
> 2E:7FF8  BD03 4010  SCALL 03:4010
  2E:7FFC  50FA       ADD R15, #0xA
  2E:7FFE  4801       MOV R0, #0x1
  2E:8000  58F0       MOV [--R15], R0
  2E:8002  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8006  4800       MOV R0, #0x0
  2E:8008  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:800C  1937       MOVZE R3, RB7
  2E:800E  5630       CMP R3, #0x0
  2E:8010  DE03       RJMP SGE, 2E:8018 ; rel +3
  2E:8012  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8016  D001       RJMP ALWAYS, 2E:801A ; rel +1
  2E:8018  4820       MOV R2, #0x0
```

### `2E:8048` in `sub_2E_787E`

```text
  2E:802C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8030  1013       ADD R1, R3
  2E:8032  1102       ADDC R0, R2
  2E:8034  58F1       MOV [--R15], R1
  2E:8036  58F0       MOV [--R15], R0
  2E:8038  6810 00A4  MOV REG[0x10], #0x00A4
  2E:803C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8040  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8044  58F1       MOV [--R15], R1
  2E:8046  58F0       MOV [--R15], R0
> 2E:8048  BD03 4010  SCALL 03:4010
  2E:804C  50FA       ADD R15, #0xA
  2E:804E  4801       MOV R0, #0x1
  2E:8050  58F0       MOV [--R15], R0
  2E:8052  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8056  4800       MOV R0, #0x0
  2E:8058  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:805C  1937       MOVZE R3, RB7
  2E:805E  5630       CMP R3, #0x0
  2E:8060  DE03       RJMP SGE, 2E:8068 ; rel +3
  2E:8062  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8066  D001       RJMP ALWAYS, 2E:806A ; rel +1
  2E:8068  4820       MOV R2, #0x0
```

### `2E:8098` in `sub_2E_787E`

```text
  2E:807C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8080  1013       ADD R1, R3
  2E:8082  1102       ADDC R0, R2
  2E:8084  58F1       MOV [--R15], R1
  2E:8086  58F0       MOV [--R15], R0
  2E:8088  6810 00A4  MOV REG[0x10], #0x00A4
  2E:808C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8090  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8094  58F1       MOV [--R15], R1
  2E:8096  58F0       MOV [--R15], R0
> 2E:8098  BD03 4010  SCALL 03:4010
  2E:809C  50FA       ADD R15, #0xA
  2E:809E  4801       MOV R0, #0x1
  2E:80A0  58F0       MOV [--R15], R0
  2E:80A2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:80A6  4800       MOV R0, #0x0
  2E:80A8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:80AC  1937       MOVZE R3, RB7
  2E:80AE  5630       CMP R3, #0x0
  2E:80B0  DE03       RJMP SGE, 2E:80B8 ; rel +3
  2E:80B2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:80B6  D001       RJMP ALWAYS, 2E:80BA ; rel +1
  2E:80B8  4820       MOV R2, #0x0
```

### `2E:80E8` in `sub_2E_787E`

```text
  2E:80CC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:80D0  1013       ADD R1, R3
  2E:80D2  1102       ADDC R0, R2
  2E:80D4  58F1       MOV [--R15], R1
  2E:80D6  58F0       MOV [--R15], R0
  2E:80D8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:80DC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:80E0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:80E4  58F1       MOV [--R15], R1
  2E:80E6  58F0       MOV [--R15], R0
> 2E:80E8  BD03 4010  SCALL 03:4010
  2E:80EC  50FA       ADD R15, #0xA
  2E:80EE  4801       MOV R0, #0x1
  2E:80F0  58F0       MOV [--R15], R0
  2E:80F2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:80F6  4800       MOV R0, #0x0
  2E:80F8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:80FC  1937       MOVZE R3, RB7
  2E:80FE  5630       CMP R3, #0x0
  2E:8100  DE03       RJMP SGE, 2E:8108 ; rel +3
  2E:8102  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8106  D001       RJMP ALWAYS, 2E:810A ; rel +1
  2E:8108  4820       MOV R2, #0x0
```

### `2E:8138` in `sub_2E_787E`

```text
  2E:811C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8120  1013       ADD R1, R3
  2E:8122  1102       ADDC R0, R2
  2E:8124  58F1       MOV [--R15], R1
  2E:8126  58F0       MOV [--R15], R0
  2E:8128  6810 00A4  MOV REG[0x10], #0x00A4
  2E:812C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8130  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8134  58F1       MOV [--R15], R1
  2E:8136  58F0       MOV [--R15], R0
> 2E:8138  BD03 4010  SCALL 03:4010
  2E:813C  50FA       ADD R15, #0xA
  2E:813E  4801       MOV R0, #0x1
  2E:8140  58F0       MOV [--R15], R0
  2E:8142  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8146  4800       MOV R0, #0x0
  2E:8148  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:814C  1937       MOVZE R3, RB7
  2E:814E  5630       CMP R3, #0x0
  2E:8150  DE03       RJMP SGE, 2E:8158 ; rel +3
  2E:8152  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8156  D001       RJMP ALWAYS, 2E:815A ; rel +1
  2E:8158  4820       MOV R2, #0x0
```

### `2E:8188` in `sub_2E_787E`

```text
  2E:816C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8170  1013       ADD R1, R3
  2E:8172  1102       ADDC R0, R2
  2E:8174  58F1       MOV [--R15], R1
  2E:8176  58F0       MOV [--R15], R0
  2E:8178  6810 00A4  MOV REG[0x10], #0x00A4
  2E:817C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8180  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8184  58F1       MOV [--R15], R1
  2E:8186  58F0       MOV [--R15], R0
> 2E:8188  BD03 4010  SCALL 03:4010
  2E:818C  50FA       ADD R15, #0xA
  2E:818E  4801       MOV R0, #0x1
  2E:8190  58F0       MOV [--R15], R0
  2E:8192  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8196  4800       MOV R0, #0x0
  2E:8198  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:819C  1937       MOVZE R3, RB7
  2E:819E  5630       CMP R3, #0x0
  2E:81A0  DE03       RJMP SGE, 2E:81A8 ; rel +3
  2E:81A2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:81A6  D001       RJMP ALWAYS, 2E:81AA ; rel +1
  2E:81A8  4820       MOV R2, #0x0
```

### `2E:81D8` in `sub_2E_787E`

```text
  2E:81BC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:81C0  1013       ADD R1, R3
  2E:81C2  1102       ADDC R0, R2
  2E:81C4  58F1       MOV [--R15], R1
  2E:81C6  58F0       MOV [--R15], R0
  2E:81C8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:81CC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:81D0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:81D4  58F1       MOV [--R15], R1
  2E:81D6  58F0       MOV [--R15], R0
> 2E:81D8  BD03 4010  SCALL 03:4010
  2E:81DC  50FA       ADD R15, #0xA
  2E:81DE  4801       MOV R0, #0x1
  2E:81E0  58F0       MOV [--R15], R0
  2E:81E2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:81E6  4800       MOV R0, #0x0
  2E:81E8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:81EC  1937       MOVZE R3, RB7
  2E:81EE  5630       CMP R3, #0x0
  2E:81F0  DE03       RJMP SGE, 2E:81F8 ; rel +3
  2E:81F2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:81F6  D001       RJMP ALWAYS, 2E:81FA ; rel +1
  2E:81F8  4820       MOV R2, #0x0
```

### `2E:8228` in `sub_2E_787E`

```text
  2E:820C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8210  1013       ADD R1, R3
  2E:8212  1102       ADDC R0, R2
  2E:8214  58F1       MOV [--R15], R1
  2E:8216  58F0       MOV [--R15], R0
  2E:8218  6810 00A4  MOV REG[0x10], #0x00A4
  2E:821C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8220  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8224  58F1       MOV [--R15], R1
  2E:8226  58F0       MOV [--R15], R0
> 2E:8228  BD03 4010  SCALL 03:4010
  2E:822C  50FA       ADD R15, #0xA
  2E:822E  4801       MOV R0, #0x1
  2E:8230  58F0       MOV [--R15], R0
  2E:8232  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8236  4800       MOV R0, #0x0
  2E:8238  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:823C  1937       MOVZE R3, RB7
  2E:823E  5630       CMP R3, #0x0
  2E:8240  DE03       RJMP SGE, 2E:8248 ; rel +3
  2E:8242  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8246  D001       RJMP ALWAYS, 2E:824A ; rel +1
  2E:8248  4820       MOV R2, #0x0
```

### `2E:8278` in `sub_2E_787E`

```text
  2E:825C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8260  1013       ADD R1, R3
  2E:8262  1102       ADDC R0, R2
  2E:8264  58F1       MOV [--R15], R1
  2E:8266  58F0       MOV [--R15], R0
  2E:8268  6810 00A4  MOV REG[0x10], #0x00A4
  2E:826C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8270  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8274  58F1       MOV [--R15], R1
  2E:8276  58F0       MOV [--R15], R0
> 2E:8278  BD03 4010  SCALL 03:4010
  2E:827C  50FA       ADD R15, #0xA
  2E:827E  4802       MOV R0, #0x2
  2E:8280  58F0       MOV [--R15], R0
  2E:8282  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8286  4800       MOV R0, #0x0
  2E:8288  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:828C  1937       MOVZE R3, RB7
  2E:828E  5630       CMP R3, #0x0
  2E:8290  DE03       RJMP SGE, 2E:8298 ; rel +3
  2E:8292  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8296  D001       RJMP ALWAYS, 2E:829A ; rel +1
  2E:8298  4820       MOV R2, #0x0
```

### `2E:82C8` in `sub_2E_787E`

```text
  2E:82AC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:82B0  1013       ADD R1, R3
  2E:82B2  1102       ADDC R0, R2
  2E:82B4  58F1       MOV [--R15], R1
  2E:82B6  58F0       MOV [--R15], R0
  2E:82B8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:82BC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:82C0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:82C4  58F1       MOV [--R15], R1
  2E:82C6  58F0       MOV [--R15], R0
> 2E:82C8  BD03 4010  SCALL 03:4010
  2E:82CC  50FA       ADD R15, #0xA
  2E:82CE  4801       MOV R0, #0x1
  2E:82D0  58F0       MOV [--R15], R0
  2E:82D2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:82D6  4800       MOV R0, #0x0
  2E:82D8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:82DC  1937       MOVZE R3, RB7
  2E:82DE  5630       CMP R3, #0x0
  2E:82E0  DE03       RJMP SGE, 2E:82E8 ; rel +3
  2E:82E2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:82E6  D001       RJMP ALWAYS, 2E:82EA ; rel +1
  2E:82E8  4820       MOV R2, #0x0
```

### `2E:8318` in `sub_2E_787E`

```text
  2E:82FC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8300  1013       ADD R1, R3
  2E:8302  1102       ADDC R0, R2
  2E:8304  58F1       MOV [--R15], R1
  2E:8306  58F0       MOV [--R15], R0
  2E:8308  6810 00A4  MOV REG[0x10], #0x00A4
  2E:830C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8310  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8314  58F1       MOV [--R15], R1
  2E:8316  58F0       MOV [--R15], R0
> 2E:8318  BD03 4010  SCALL 03:4010
  2E:831C  50FA       ADD R15, #0xA
  2E:831E  4801       MOV R0, #0x1
  2E:8320  58F0       MOV [--R15], R0
  2E:8322  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8326  4800       MOV R0, #0x0
  2E:8328  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:832C  1937       MOVZE R3, RB7
  2E:832E  5630       CMP R3, #0x0
  2E:8330  DE03       RJMP SGE, 2E:8338 ; rel +3
  2E:8332  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8336  D001       RJMP ALWAYS, 2E:833A ; rel +1
  2E:8338  4820       MOV R2, #0x0
```

### `2E:8368` in `sub_2E_787E`

```text
  2E:834C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8350  1013       ADD R1, R3
  2E:8352  1102       ADDC R0, R2
  2E:8354  58F1       MOV [--R15], R1
  2E:8356  58F0       MOV [--R15], R0
  2E:8358  6810 00A4  MOV REG[0x10], #0x00A4
  2E:835C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8360  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8364  58F1       MOV [--R15], R1
  2E:8366  58F0       MOV [--R15], R0
> 2E:8368  BD03 4010  SCALL 03:4010
  2E:836C  50FA       ADD R15, #0xA
  2E:836E  4801       MOV R0, #0x1
  2E:8370  58F0       MOV [--R15], R0
  2E:8372  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8376  4800       MOV R0, #0x0
  2E:8378  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:837C  1937       MOVZE R3, RB7
  2E:837E  5630       CMP R3, #0x0
  2E:8380  DE03       RJMP SGE, 2E:8388 ; rel +3
  2E:8382  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8386  D001       RJMP ALWAYS, 2E:838A ; rel +1
  2E:8388  4820       MOV R2, #0x0
```

### `2E:83B8` in `sub_2E_787E`

```text
  2E:839C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:83A0  1013       ADD R1, R3
  2E:83A2  1102       ADDC R0, R2
  2E:83A4  58F1       MOV [--R15], R1
  2E:83A6  58F0       MOV [--R15], R0
  2E:83A8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:83AC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:83B0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:83B4  58F1       MOV [--R15], R1
  2E:83B6  58F0       MOV [--R15], R0
> 2E:83B8  BD03 4010  SCALL 03:4010
  2E:83BC  50FA       ADD R15, #0xA
  2E:83BE  4802       MOV R0, #0x2
  2E:83C0  58F0       MOV [--R15], R0
  2E:83C2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:83C6  4800       MOV R0, #0x0
  2E:83C8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:83CC  1937       MOVZE R3, RB7
  2E:83CE  5630       CMP R3, #0x0
  2E:83D0  DE03       RJMP SGE, 2E:83D8 ; rel +3
  2E:83D2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:83D6  D001       RJMP ALWAYS, 2E:83DA ; rel +1
  2E:83D8  4820       MOV R2, #0x0
```

### `2E:8408` in `sub_2E_787E`

```text
  2E:83EC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:83F0  1013       ADD R1, R3
  2E:83F2  1102       ADDC R0, R2
  2E:83F4  58F1       MOV [--R15], R1
  2E:83F6  58F0       MOV [--R15], R0
  2E:83F8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:83FC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8400  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8404  58F1       MOV [--R15], R1
  2E:8406  58F0       MOV [--R15], R0
> 2E:8408  BD03 4010  SCALL 03:4010
  2E:840C  50FA       ADD R15, #0xA
  2E:840E  4801       MOV R0, #0x1
  2E:8410  58F0       MOV [--R15], R0
  2E:8412  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8416  4800       MOV R0, #0x0
  2E:8418  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:841C  1937       MOVZE R3, RB7
  2E:841E  5630       CMP R3, #0x0
  2E:8420  DE03       RJMP SGE, 2E:8428 ; rel +3
  2E:8422  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8426  D001       RJMP ALWAYS, 2E:842A ; rel +1
  2E:8428  4820       MOV R2, #0x0
```

### `2E:8458` in `sub_2E_787E`

```text
  2E:843C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8440  1013       ADD R1, R3
  2E:8442  1102       ADDC R0, R2
  2E:8444  58F1       MOV [--R15], R1
  2E:8446  58F0       MOV [--R15], R0
  2E:8448  6810 00A4  MOV REG[0x10], #0x00A4
  2E:844C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8450  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8454  58F1       MOV [--R15], R1
  2E:8456  58F0       MOV [--R15], R0
> 2E:8458  BD03 4010  SCALL 03:4010
  2E:845C  50FA       ADD R15, #0xA
  2E:845E  4801       MOV R0, #0x1
  2E:8460  58F0       MOV [--R15], R0
  2E:8462  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8466  4800       MOV R0, #0x0
  2E:8468  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:846C  1937       MOVZE R3, RB7
  2E:846E  5630       CMP R3, #0x0
  2E:8470  DE03       RJMP SGE, 2E:8478 ; rel +3
  2E:8472  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8476  D001       RJMP ALWAYS, 2E:847A ; rel +1
  2E:8478  4820       MOV R2, #0x0
```

### `2E:84A8` in `sub_2E_787E`

```text
  2E:848C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8490  1013       ADD R1, R3
  2E:8492  1102       ADDC R0, R2
  2E:8494  58F1       MOV [--R15], R1
  2E:8496  58F0       MOV [--R15], R0
  2E:8498  6810 00A4  MOV REG[0x10], #0x00A4
  2E:849C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:84A0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:84A4  58F1       MOV [--R15], R1
  2E:84A6  58F0       MOV [--R15], R0
> 2E:84A8  BD03 4010  SCALL 03:4010
  2E:84AC  50FA       ADD R15, #0xA
  2E:84AE  4801       MOV R0, #0x1
  2E:84B0  58F0       MOV [--R15], R0
  2E:84B2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:84B6  4800       MOV R0, #0x0
  2E:84B8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:84BC  1937       MOVZE R3, RB7
  2E:84BE  5630       CMP R3, #0x0
  2E:84C0  DE03       RJMP SGE, 2E:84C8 ; rel +3
  2E:84C2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:84C6  D001       RJMP ALWAYS, 2E:84CA ; rel +1
  2E:84C8  4820       MOV R2, #0x0
```

### `2E:84F8` in `sub_2E_787E`

```text
  2E:84DC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:84E0  1013       ADD R1, R3
  2E:84E2  1102       ADDC R0, R2
  2E:84E4  58F1       MOV [--R15], R1
  2E:84E6  58F0       MOV [--R15], R0
  2E:84E8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:84EC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:84F0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:84F4  58F1       MOV [--R15], R1
  2E:84F6  58F0       MOV [--R15], R0
> 2E:84F8  BD03 4010  SCALL 03:4010
  2E:84FC  50FA       ADD R15, #0xA
  2E:84FE  4801       MOV R0, #0x1
  2E:8500  58F0       MOV [--R15], R0
  2E:8502  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8506  4800       MOV R0, #0x0
  2E:8508  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:850C  1937       MOVZE R3, RB7
  2E:850E  5630       CMP R3, #0x0
  2E:8510  DE03       RJMP SGE, 2E:8518 ; rel +3
  2E:8512  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8516  D001       RJMP ALWAYS, 2E:851A ; rel +1
  2E:8518  4820       MOV R2, #0x0
```

### `2E:8548` in `sub_2E_787E`

```text
  2E:852C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8530  1013       ADD R1, R3
  2E:8532  1102       ADDC R0, R2
  2E:8534  58F1       MOV [--R15], R1
  2E:8536  58F0       MOV [--R15], R0
  2E:8538  6810 00A4  MOV REG[0x10], #0x00A4
  2E:853C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8540  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8544  58F1       MOV [--R15], R1
  2E:8546  58F0       MOV [--R15], R0
> 2E:8548  BD03 4010  SCALL 03:4010
  2E:854C  50FA       ADD R15, #0xA
  2E:854E  4801       MOV R0, #0x1
  2E:8550  58F0       MOV [--R15], R0
  2E:8552  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8556  4800       MOV R0, #0x0
  2E:8558  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:855C  1937       MOVZE R3, RB7
  2E:855E  5630       CMP R3, #0x0
  2E:8560  DE03       RJMP SGE, 2E:8568 ; rel +3
  2E:8562  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8566  D001       RJMP ALWAYS, 2E:856A ; rel +1
  2E:8568  4820       MOV R2, #0x0
```

### `2E:8598` in `sub_2E_787E`

```text
  2E:857C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8580  1013       ADD R1, R3
  2E:8582  1102       ADDC R0, R2
  2E:8584  58F1       MOV [--R15], R1
  2E:8586  58F0       MOV [--R15], R0
  2E:8588  6810 00A4  MOV REG[0x10], #0x00A4
  2E:858C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8590  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8594  58F1       MOV [--R15], R1
  2E:8596  58F0       MOV [--R15], R0
> 2E:8598  BD03 4010  SCALL 03:4010
  2E:859C  50FA       ADD R15, #0xA
  2E:859E  4801       MOV R0, #0x1
  2E:85A0  58F0       MOV [--R15], R0
  2E:85A2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:85A6  4800       MOV R0, #0x0
  2E:85A8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:85AC  1937       MOVZE R3, RB7
  2E:85AE  5630       CMP R3, #0x0
  2E:85B0  DE03       RJMP SGE, 2E:85B8 ; rel +3
  2E:85B2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:85B6  D001       RJMP ALWAYS, 2E:85BA ; rel +1
  2E:85B8  4820       MOV R2, #0x0
```

### `2E:85E8` in `sub_2E_787E`

```text
  2E:85CC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:85D0  1013       ADD R1, R3
  2E:85D2  1102       ADDC R0, R2
  2E:85D4  58F1       MOV [--R15], R1
  2E:85D6  58F0       MOV [--R15], R0
  2E:85D8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:85DC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:85E0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:85E4  58F1       MOV [--R15], R1
  2E:85E6  58F0       MOV [--R15], R0
> 2E:85E8  BD03 4010  SCALL 03:4010
  2E:85EC  50FA       ADD R15, #0xA
  2E:85EE  4801       MOV R0, #0x1
  2E:85F0  58F0       MOV [--R15], R0
  2E:85F2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:85F6  4800       MOV R0, #0x0
  2E:85F8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:85FC  1937       MOVZE R3, RB7
  2E:85FE  5630       CMP R3, #0x0
  2E:8600  DE03       RJMP SGE, 2E:8608 ; rel +3
  2E:8602  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8606  D001       RJMP ALWAYS, 2E:860A ; rel +1
  2E:8608  4820       MOV R2, #0x0
```

### `2E:8638` in `sub_2E_787E`

```text
  2E:861C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8620  1013       ADD R1, R3
  2E:8622  1102       ADDC R0, R2
  2E:8624  58F1       MOV [--R15], R1
  2E:8626  58F0       MOV [--R15], R0
  2E:8628  6810 00A4  MOV REG[0x10], #0x00A4
  2E:862C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8630  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8634  58F1       MOV [--R15], R1
  2E:8636  58F0       MOV [--R15], R0
> 2E:8638  BD03 4010  SCALL 03:4010
  2E:863C  50FA       ADD R15, #0xA
  2E:863E  4801       MOV R0, #0x1
  2E:8640  58F0       MOV [--R15], R0
  2E:8642  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8646  4800       MOV R0, #0x0
  2E:8648  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:864C  1937       MOVZE R3, RB7
  2E:864E  5630       CMP R3, #0x0
  2E:8650  DE03       RJMP SGE, 2E:8658 ; rel +3
  2E:8652  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8656  D001       RJMP ALWAYS, 2E:865A ; rel +1
  2E:8658  4820       MOV R2, #0x0
```

### `2E:8688` in `sub_2E_787E`

```text
  2E:866C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8670  1013       ADD R1, R3
  2E:8672  1102       ADDC R0, R2
  2E:8674  58F1       MOV [--R15], R1
  2E:8676  58F0       MOV [--R15], R0
  2E:8678  6810 00A4  MOV REG[0x10], #0x00A4
  2E:867C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8680  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8684  58F1       MOV [--R15], R1
  2E:8686  58F0       MOV [--R15], R0
> 2E:8688  BD03 4010  SCALL 03:4010
  2E:868C  50FA       ADD R15, #0xA
  2E:868E  4801       MOV R0, #0x1
  2E:8690  58F0       MOV [--R15], R0
  2E:8692  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8696  4800       MOV R0, #0x0
  2E:8698  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:869C  1937       MOVZE R3, RB7
  2E:869E  5630       CMP R3, #0x0
  2E:86A0  DE03       RJMP SGE, 2E:86A8 ; rel +3
  2E:86A2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:86A6  D001       RJMP ALWAYS, 2E:86AA ; rel +1
  2E:86A8  4820       MOV R2, #0x0
```

### `2E:86D8` in `sub_2E_787E`

```text
  2E:86BC  68F2 0052  MOV REG[0xF2], #0x0052
  2E:86C0  1013       ADD R1, R3
  2E:86C2  1102       ADDC R0, R2
  2E:86C4  58F1       MOV [--R15], R1
  2E:86C6  58F0       MOV [--R15], R0
  2E:86C8  6810 00A4  MOV REG[0x10], #0x00A4
  2E:86CC  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:86D0  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:86D4  58F1       MOV [--R15], R1
  2E:86D6  58F0       MOV [--R15], R0
> 2E:86D8  BD03 4010  SCALL 03:4010
  2E:86DC  50FA       ADD R15, #0xA
  2E:86DE  4801       MOV R0, #0x1
  2E:86E0  58F0       MOV [--R15], R0
  2E:86E2  68F1 0094  MOV REG[0xF1], #0x0094
  2E:86E6  4800       MOV R0, #0x0
  2E:86E8  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:86EC  1937       MOVZE R3, RB7
  2E:86EE  5630       CMP R3, #0x0
  2E:86F0  DE03       RJMP SGE, 2E:86F8 ; rel +3
  2E:86F2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:86F6  D001       RJMP ALWAYS, 2E:86FA ; rel +1
  2E:86F8  4820       MOV R2, #0x0
```

### `2E:8728` in `sub_2E_787E`

```text
  2E:870C  68F2 0052  MOV REG[0xF2], #0x0052
  2E:8710  1013       ADD R1, R3
  2E:8712  1102       ADDC R0, R2
  2E:8714  58F1       MOV [--R15], R1
  2E:8716  58F0       MOV [--R15], R0
  2E:8718  6810 00A4  MOV REG[0x10], #0x00A4
  2E:871C  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:8720  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:8724  58F1       MOV [--R15], R1
  2E:8726  58F0       MOV [--R15], R0
> 2E:8728  BD03 4010  SCALL 03:4010
  2E:872C  50FA       ADD R15, #0xA
  2E:872E  68F1 0094  MOV REG[0xF1], #0x0094
  2E:8732  4800       MOV R0, #0x0
  2E:8734  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:8738  1937       MOVZE R3, RB7
  2E:873A  5630       CMP R3, #0x0
  2E:873C  DE03       RJMP SGE, 2E:8744 ; rel +3
  2E:873E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:8742  D001       RJMP ALWAYS, 2E:8746 ; rel +1
  2E:8744  4820       MOV R2, #0x0
  2E:8746  58F3       MOV [--R15], R3
  2E:8748  58F2       MOV [--R15], R2
```

### `31:C9AC` in `sub_31_C7A4`

```text
  31:C990  081B       MOV R1, R11
  31:C992  70F1 FFF6  ADD REG[0xF1], #0xFFF6
  31:C996  4800       MOV R0, #0x0
  31:C998  58F1       MOV [--R15], R1
  31:C99A  58F0       MOV [--R15], R0
  31:C99C  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9A0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:C9A4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:C9A8  58F1       MOV [--R15], R1
  31:C9AA  58F0       MOV [--R15], R0
> 31:C9AC  BD03 4010  SCALL 03:4010
  31:C9B0  50FA       ADD R15, #0xA
  31:C9B2  4800       MOV R0, #0x0
  31:C9B4  58F0       MOV [--R15], R0
  31:C9B6  780B FFF6  MOV R0, [R11+0xFFF6]
  31:C9BA  781B FFF8  MOV R1, [R11+0xFFF8]
  31:C9BE  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9C2  90F1 79B8  ADD REG[0xF1], [0x79B8]
  31:C9C6  91F0 79B6  ADDC REG[0xF0], [0x79B6]
  31:C9CA  58F1       MOV [--R15], R1
  31:C9CC  58F0       MOV [--R15], R0
  31:C9CE  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9D2  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `31:CA2C` in `sub_31_C7A4`

```text
  31:CA10  68F2 0052  MOV REG[0xF2], #0x0052
  31:CA14  1013       ADD R1, R3
  31:CA16  1102       ADDC R0, R2
  31:CA18  58F1       MOV [--R15], R1
  31:CA1A  58F0       MOV [--R15], R0
  31:CA1C  6810 00A4  MOV REG[0x10], #0x00A4
  31:CA20  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CA24  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CA28  58F1       MOV [--R15], R1
  31:CA2A  58F0       MOV [--R15], R0
> 31:CA2C  BD03 4010  SCALL 03:4010
  31:CA30  50FA       ADD R15, #0xA
  31:CA32  4802       MOV R0, #0x2
  31:CA34  58F0       MOV [--R15], R0
  31:CA36  68F1 0094  MOV REG[0xF1], #0x0094
  31:CA3A  4800       MOV R0, #0x0
  31:CA3C  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CA40  5630       CMP R3, #0x0
  31:CA42  DE03       RJMP SGE, 31:CA4A ; rel +3
  31:CA44  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CA48  D001       RJMP ALWAYS, 31:CA4C ; rel +1
  31:CA4A  4820       MOV R2, #0x0
  31:CA4C  58F3       MOV [--R15], R3
```

### `31:CA7A` in `sub_31_C7A4`

```text
  31:CA5E  68F2 0052  MOV REG[0xF2], #0x0052
  31:CA62  1013       ADD R1, R3
  31:CA64  1102       ADDC R0, R2
  31:CA66  58F1       MOV [--R15], R1
  31:CA68  58F0       MOV [--R15], R0
  31:CA6A  6810 00A4  MOV REG[0x10], #0x00A4
  31:CA6E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CA72  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CA76  58F1       MOV [--R15], R1
  31:CA78  58F0       MOV [--R15], R0
> 31:CA7A  BD03 4010  SCALL 03:4010
  31:CA7E  50FA       ADD R15, #0xA
  31:CA80  4801       MOV R0, #0x1
  31:CA82  58F0       MOV [--R15], R0
  31:CA84  081B       MOV R1, R11
  31:CA86  70F1 FFF5  ADD REG[0xF1], #0xFFF5
  31:CA8A  4800       MOV R0, #0x0
  31:CA8C  58F1       MOV [--R15], R1
  31:CA8E  58F0       MOV [--R15], R0
  31:CA90  6810 00A4  MOV REG[0x10], #0x00A4
  31:CA94  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CA98  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CA9C  58F1       MOV [--R15], R1
```

### `31:CAA0` in `sub_31_C7A4`

```text
  31:CA84  081B       MOV R1, R11
  31:CA86  70F1 FFF5  ADD REG[0xF1], #0xFFF5
  31:CA8A  4800       MOV R0, #0x0
  31:CA8C  58F1       MOV [--R15], R1
  31:CA8E  58F0       MOV [--R15], R0
  31:CA90  6810 00A4  MOV REG[0x10], #0x00A4
  31:CA94  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CA98  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CA9C  58F1       MOV [--R15], R1
  31:CA9E  58F0       MOV [--R15], R0
> 31:CAA0  BD03 4010  SCALL 03:4010
  31:CAA4  50FA       ADD R15, #0xA
  31:CAA6  68F1 0094  MOV REG[0xF1], #0x0094
  31:CAAA  4800       MOV R0, #0x0
  31:CAAC  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CAB0  5630       CMP R3, #0x0
  31:CAB2  DE03       RJMP SGE, 31:CABA ; rel +3
  31:CAB4  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CAB8  D001       RJMP ALWAYS, 31:CABC ; rel +1
  31:CABA  4820       MOV R2, #0x0
  31:CABC  58F3       MOV [--R15], R3
  31:CABE  58F2       MOV [--R15], R2
  31:CAC0  58F1       MOV [--R15], R1
```

### `31:CB3A` in `sub_31_C7A4`

```text
  31:CB1E  68F2 0052  MOV REG[0xF2], #0x0052
  31:CB22  1013       ADD R1, R3
  31:CB24  1102       ADDC R0, R2
  31:CB26  58F1       MOV [--R15], R1
  31:CB28  58F0       MOV [--R15], R0
  31:CB2A  6810 00A4  MOV REG[0x10], #0x00A4
  31:CB2E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CB32  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CB36  58F1       MOV [--R15], R1
  31:CB38  58F0       MOV [--R15], R0
> 31:CB3A  BD03 4010  SCALL 03:4010
  31:CB3E  50FA       ADD R15, #0xA
  31:CB40  68F1 0094  MOV REG[0xF1], #0x0094
  31:CB44  4800       MOV R0, #0x0
  31:CB46  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CB4A  5630       CMP R3, #0x0
  31:CB4C  DE03       RJMP SGE, 31:CB54 ; rel +3
  31:CB4E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CB52  D001       RJMP ALWAYS, 31:CB56 ; rel +1
  31:CB54  4820       MOV R2, #0x0
  31:CB56  58F3       MOV [--R15], R3
  31:CB58  58F2       MOV [--R15], R2
  31:CB5A  58F1       MOV [--R15], R1
```

### `31:CBE0` in `sub_31_C7A4`

```text
  31:CBC4  68F2 0052  MOV REG[0xF2], #0x0052
  31:CBC8  1013       ADD R1, R3
  31:CBCA  1102       ADDC R0, R2
  31:CBCC  58F1       MOV [--R15], R1
  31:CBCE  58F0       MOV [--R15], R0
  31:CBD0  6810 00A4  MOV REG[0x10], #0x00A4
  31:CBD4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CBD8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CBDC  58F1       MOV [--R15], R1
  31:CBDE  58F0       MOV [--R15], R0
> 31:CBE0  BD03 4010  SCALL 03:4010
  31:CBE4  50FA       ADD R15, #0xA
  31:CBE6  68F1 0094  MOV REG[0xF1], #0x0094
  31:CBEA  4800       MOV R0, #0x0
  31:CBEC  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CBF0  5630       CMP R3, #0x0
  31:CBF2  DE03       RJMP SGE, 31:CBFA ; rel +3
  31:CBF4  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CBF8  D001       RJMP ALWAYS, 31:CBFC ; rel +1
  31:CBFA  4820       MOV R2, #0x0
  31:CBFC  58F3       MOV [--R15], R3
  31:CBFE  58F2       MOV [--R15], R2
  31:CC00  58F1       MOV [--R15], R1
```

### `31:CC86` in `sub_31_C7A4`

```text
  31:CC6A  68F2 0052  MOV REG[0xF2], #0x0052
  31:CC6E  1013       ADD R1, R3
  31:CC70  1102       ADDC R0, R2
  31:CC72  58F1       MOV [--R15], R1
  31:CC74  58F0       MOV [--R15], R0
  31:CC76  6810 00A4  MOV REG[0x10], #0x00A4
  31:CC7A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CC7E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CC82  58F1       MOV [--R15], R1
  31:CC84  58F0       MOV [--R15], R0
> 31:CC86  BD03 4010  SCALL 03:4010
  31:CC8A  50FA       ADD R15, #0xA
  31:CC8C  68F1 0094  MOV REG[0xF1], #0x0094
  31:CC90  4800       MOV R0, #0x0
  31:CC92  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CC96  5630       CMP R3, #0x0
  31:CC98  DE03       RJMP SGE, 31:CCA0 ; rel +3
  31:CC9A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CC9E  D001       RJMP ALWAYS, 31:CCA2 ; rel +1
  31:CCA0  4820       MOV R2, #0x0
  31:CCA2  58F3       MOV [--R15], R3
  31:CCA4  58F2       MOV [--R15], R2
  31:CCA6  58F1       MOV [--R15], R1
```

### `31:CD2C` in `sub_31_CD1E`

```text
  31:CD1E  00A4       ADDB RB10, RB4
  31:CD20  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CD24  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CD28  58F1       MOV [--R15], R1
  31:CD2A  58F0       MOV [--R15], R0
> 31:CD2C  BD03 4010  SCALL 03:4010
  31:CD30  50FA       ADD R15, #0xA
  31:CD32  68F1 0094  MOV REG[0xF1], #0x0094
  31:CD36  4800       MOV R0, #0x0
  31:CD38  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CD3C  5630       CMP R3, #0x0
  31:CD3E  DE03       RJMP SGE, 31:CD46 ; rel +3
  31:CD40  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CD44  D001       RJMP ALWAYS, 31:CD48 ; rel +1
  31:CD46  4820       MOV R2, #0x0
  31:CD48  58F3       MOV [--R15], R3
  31:CD4A  58F2       MOV [--R15], R2
  31:CD4C  58F1       MOV [--R15], R1
```

### `31:CDD2` in `sub_31_CD1E`

```text
  31:CDB6  68F2 0052  MOV REG[0xF2], #0x0052
  31:CDBA  1013       ADD R1, R3
  31:CDBC  1102       ADDC R0, R2
  31:CDBE  58F1       MOV [--R15], R1
  31:CDC0  58F0       MOV [--R15], R0
  31:CDC2  6810 00A4  MOV REG[0x10], #0x00A4
  31:CDC6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CDCA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CDCE  58F1       MOV [--R15], R1
  31:CDD0  58F0       MOV [--R15], R0
> 31:CDD2  BD03 4010  SCALL 03:4010
  31:CDD6  50FA       ADD R15, #0xA
  31:CDD8  4802       MOV R0, #0x2
  31:CDDA  58F0       MOV [--R15], R0
  31:CDDC  68F1 0094  MOV REG[0xF1], #0x0094
  31:CDE0  4800       MOV R0, #0x0
  31:CDE2  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CDE6  5630       CMP R3, #0x0
  31:CDE8  DE03       RJMP SGE, 31:CDF0 ; rel +3
  31:CDEA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CDEE  D001       RJMP ALWAYS, 31:CDF2 ; rel +1
  31:CDF0  4820       MOV R2, #0x0
  31:CDF2  58F3       MOV [--R15], R3
```

### `31:CE20` in `sub_31_CD1E`

```text
  31:CE04  68F2 0052  MOV REG[0xF2], #0x0052
  31:CE08  1013       ADD R1, R3
  31:CE0A  1102       ADDC R0, R2
  31:CE0C  58F1       MOV [--R15], R1
  31:CE0E  58F0       MOV [--R15], R0
  31:CE10  6810 00A4  MOV REG[0x10], #0x00A4
  31:CE14  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CE18  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CE1C  58F1       MOV [--R15], R1
  31:CE1E  58F0       MOV [--R15], R0
> 31:CE20  BD03 4010  SCALL 03:4010
  31:CE24  50FA       ADD R15, #0xA
  31:CE26  4802       MOV R0, #0x2
  31:CE28  58F0       MOV [--R15], R0
  31:CE2A  68F1 0094  MOV REG[0xF1], #0x0094
  31:CE2E  4800       MOV R0, #0x0
  31:CE30  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CE34  5630       CMP R3, #0x0
  31:CE36  DE03       RJMP SGE, 31:CE3E ; rel +3
  31:CE38  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CE3C  D001       RJMP ALWAYS, 31:CE40 ; rel +1
  31:CE3E  4820       MOV R2, #0x0
  31:CE40  58F3       MOV [--R15], R3
```

### `31:CE6E` in `sub_31_CE52`

```text
  31:CE52  68F2 0052  MOV REG[0xF2], #0x0052
  31:CE56  1013       ADD R1, R3
  31:CE58  1102       ADDC R0, R2
  31:CE5A  58F1       MOV [--R15], R1
  31:CE5C  58F0       MOV [--R15], R0
  31:CE5E  6810 00A4  MOV REG[0x10], #0x00A4
  31:CE62  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CE66  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CE6A  58F1       MOV [--R15], R1
  31:CE6C  58F0       MOV [--R15], R0
> 31:CE6E  BD03 4010  SCALL 03:4010
  31:CE72  50FA       ADD R15, #0xA
  31:CE74  4800       MOV R0, #0x0
  31:CE76  6A0B FFFE  MOV [R11+0xFFFE], R0
  31:CE7A  4801       MOV R0, #0x1
  31:CE7C  58F0       MOV [--R15], R0
  31:CE7E  081B       MOV R1, R11
  31:CE80  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  31:CE84  4800       MOV R0, #0x0
  31:CE86  58F1       MOV [--R15], R1
  31:CE88  58F0       MOV [--R15], R0
  31:CE8A  6810 00A4  MOV REG[0x10], #0x00A4
  31:CE8E  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `31:CE9A` in `sub_31_CE52`

```text
  31:CE7E  081B       MOV R1, R11
  31:CE80  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  31:CE84  4800       MOV R0, #0x0
  31:CE86  58F1       MOV [--R15], R1
  31:CE88  58F0       MOV [--R15], R0
  31:CE8A  6810 00A4  MOV REG[0x10], #0x00A4
  31:CE8E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CE92  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CE96  58F1       MOV [--R15], R1
  31:CE98  58F0       MOV [--R15], R0
> 31:CE9A  BD03 4010  SCALL 03:4010
  31:CE9E  50FA       ADD R15, #0xA
  31:CEA0  780B FFFE  MOV R0, [R11+0xFFFE]
  31:CEA4  0810       MOV R1, R0
  31:CEA6  5610       CMP R1, #0x0
  31:CEA8  DE03       RJMP SGE, 31:CEB0 ; rel +3
  31:CEAA  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  31:CEAE  D001       RJMP ALWAYS, 31:CEB2 ; rel +1
  31:CEB0  4800       MOV R0, #0x0
  31:CEB2  6A0B FFF0  MOV [R11+0xFFF0], R0
  31:CEB6  6A1B FFF2  MOV [R11+0xFFF2], R1
  31:CEBA  68F3 0094  MOV REG[0xF3], #0x0094
  31:CEBE  4820       MOV R2, #0x0
```

### `31:CF6C` in `sub_31_CE52`

```text
  31:CF50  68F2 0052  MOV REG[0xF2], #0x0052
  31:CF54  1013       ADD R1, R3
  31:CF56  1102       ADDC R0, R2
  31:CF58  58F1       MOV [--R15], R1
  31:CF5A  58F0       MOV [--R15], R0
  31:CF5C  6810 00A4  MOV REG[0x10], #0x00A4
  31:CF60  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CF64  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CF68  58F1       MOV [--R15], R1
  31:CF6A  58F0       MOV [--R15], R0
> 31:CF6C  BD03 4010  SCALL 03:4010
  31:CF70  50FA       ADD R15, #0xA
  31:CF72  4801       MOV R0, #0x1
  31:CF74  58F0       MOV [--R15], R0
  31:CF76  68F1 0094  MOV REG[0xF1], #0x0094
  31:CF7A  4800       MOV R0, #0x0
  31:CF7C  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CF80  5630       CMP R3, #0x0
  31:CF82  DE03       RJMP SGE, 31:CF8A ; rel +3
  31:CF84  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CF88  D001       RJMP ALWAYS, 31:CF8C ; rel +1
  31:CF8A  4820       MOV R2, #0x0
  31:CF8C  58F3       MOV [--R15], R3
```

### `31:CFBA` in `sub_31_CE52`

```text
  31:CF9E  68F2 0052  MOV REG[0xF2], #0x0052
  31:CFA2  1013       ADD R1, R3
  31:CFA4  1102       ADDC R0, R2
  31:CFA6  58F1       MOV [--R15], R1
  31:CFA8  58F0       MOV [--R15], R0
  31:CFAA  6810 00A4  MOV REG[0x10], #0x00A4
  31:CFAE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:CFB2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:CFB6  58F1       MOV [--R15], R1
  31:CFB8  58F0       MOV [--R15], R0
> 31:CFBA  BD03 4010  SCALL 03:4010
  31:CFBE  50FA       ADD R15, #0xA
  31:CFC0  4802       MOV R0, #0x2
  31:CFC2  58F0       MOV [--R15], R0
  31:CFC4  68F1 0094  MOV REG[0xF1], #0x0094
  31:CFC8  4800       MOV R0, #0x0
  31:CFCA  783B FFFC  MOV R3, [R11+0xFFFC]
  31:CFCE  5630       CMP R3, #0x0
  31:CFD0  DE03       RJMP SGE, 31:CFD8 ; rel +3
  31:CFD2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:CFD6  D001       RJMP ALWAYS, 31:CFDA ; rel +1
  31:CFD8  4820       MOV R2, #0x0
  31:CFDA  58F3       MOV [--R15], R3
```

### `31:D008` in `sub_31_CE52`

```text
  31:CFEC  68F2 0052  MOV REG[0xF2], #0x0052
  31:CFF0  1013       ADD R1, R3
  31:CFF2  1102       ADDC R0, R2
  31:CFF4  58F1       MOV [--R15], R1
  31:CFF6  58F0       MOV [--R15], R0
  31:CFF8  6810 00A4  MOV REG[0x10], #0x00A4
  31:CFFC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:D000  88F1 7994  MOV REG[0xF1], [0x7994]
  31:D004  58F1       MOV [--R15], R1
  31:D006  58F0       MOV [--R15], R0
> 31:D008  BD03 4010  SCALL 03:4010
  31:D00C  50FA       ADD R15, #0xA
  31:D00E  4802       MOV R0, #0x2
  31:D010  58F0       MOV [--R15], R0
  31:D012  68F1 0094  MOV REG[0xF1], #0x0094
  31:D016  4800       MOV R0, #0x0
  31:D018  783B FFFC  MOV R3, [R11+0xFFFC]
  31:D01C  5630       CMP R3, #0x0
  31:D01E  DE03       RJMP SGE, 31:D026 ; rel +3
  31:D020  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:D024  D001       RJMP ALWAYS, 31:D028 ; rel +1
  31:D026  4820       MOV R2, #0x0
  31:D028  58F3       MOV [--R15], R3
```

### `31:D056` in `sub_31_CE52`

```text
  31:D03A  68F2 0052  MOV REG[0xF2], #0x0052
  31:D03E  1013       ADD R1, R3
  31:D040  1102       ADDC R0, R2
  31:D042  58F1       MOV [--R15], R1
  31:D044  58F0       MOV [--R15], R0
  31:D046  6810 00A4  MOV REG[0x10], #0x00A4
  31:D04A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:D04E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:D052  58F1       MOV [--R15], R1
  31:D054  58F0       MOV [--R15], R0
> 31:D056  BD03 4010  SCALL 03:4010
  31:D05A  50FA       ADD R15, #0xA
  31:D05C  4801       MOV R0, #0x1
  31:D05E  58F0       MOV [--R15], R0
  31:D060  68F1 0094  MOV REG[0xF1], #0x0094
  31:D064  4800       MOV R0, #0x0
  31:D066  783B FFFC  MOV R3, [R11+0xFFFC]
  31:D06A  5630       CMP R3, #0x0
  31:D06C  DE03       RJMP SGE, 31:D074 ; rel +3
  31:D06E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:D072  D001       RJMP ALWAYS, 31:D076 ; rel +1
  31:D074  4820       MOV R2, #0x0
  31:D076  58F3       MOV [--R15], R3
```

### `31:D0A4` in `sub_31_CE52`

```text
  31:D088  68F2 0052  MOV REG[0xF2], #0x0052
  31:D08C  1013       ADD R1, R3
  31:D08E  1102       ADDC R0, R2
  31:D090  58F1       MOV [--R15], R1
  31:D092  58F0       MOV [--R15], R0
  31:D094  6810 00A4  MOV REG[0x10], #0x00A4
  31:D098  88F0 7992  MOV REG[0xF0], [0x7992]
  31:D09C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:D0A0  58F1       MOV [--R15], R1
  31:D0A2  58F0       MOV [--R15], R0
> 31:D0A4  BD03 4010  SCALL 03:4010
  31:D0A8  50FA       ADD R15, #0xA
  31:D0AA  4800       MOV R0, #0x0
  31:D0AC  6A0B FFFE  MOV [R11+0xFFFE], R0
  31:D0B0  780B FFFE  MOV R0, [R11+0xFFFE]
  31:D0B4  0810       MOV R1, R0
  31:D0B6  5610       CMP R1, #0x0
  31:D0B8  DE03       RJMP SGE, 31:D0C0 ; rel +3
  31:D0BA  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  31:D0BE  D001       RJMP ALWAYS, 31:D0C2 ; rel +1
  31:D0C0  4800       MOV R0, #0x0
  31:D0C2  4C11       SL R1, #0x1
  31:D0C4  5C01       SLOSB R0, #0x1
```

### `31:EA0E` in `sub_31_E9FE`

```text
  31:E9FE  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA02  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA06  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA0A  58F1       MOV [--R15], R1
  31:EA0C  58F0       MOV [--R15], R0
> 31:EA0E  BD03 4010  SCALL 03:4010
  31:EA12  50FA       ADD R15, #0xA
  31:EA14  4802       MOV R0, #0x2
  31:EA16  58F0       MOV [--R15], R0
  31:EA18  68F1 7AE4  MOV REG[0xF1], #0x7AE4
  31:EA1C  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA20  58F1       MOV [--R15], R1
  31:EA22  58F0       MOV [--R15], R0
  31:EA24  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA28  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA2C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA30  58F1       MOV [--R15], R1
  31:EA32  58F0       MOV [--R15], R0
```

### `31:EA34` in `sub_31_E9FE`

```text
  31:EA16  58F0       MOV [--R15], R0
  31:EA18  68F1 7AE4  MOV REG[0xF1], #0x7AE4
  31:EA1C  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA20  58F1       MOV [--R15], R1
  31:EA22  58F0       MOV [--R15], R0
  31:EA24  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA28  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA2C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA30  58F1       MOV [--R15], R1
  31:EA32  58F0       MOV [--R15], R0
> 31:EA34  BD03 4010  SCALL 03:4010
  31:EA38  50FA       ADD R15, #0xA
  31:EA3A  4802       MOV R0, #0x2
  31:EA3C  58F0       MOV [--R15], R0
  31:EA3E  68F1 7AF8  MOV REG[0xF1], #0x7AF8
  31:EA42  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA46  58F1       MOV [--R15], R1
  31:EA48  58F0       MOV [--R15], R0
  31:EA4A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA4E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA52  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA56  58F1       MOV [--R15], R1
  31:EA58  58F0       MOV [--R15], R0
```

### `31:EA5A` in `sub_31_E9FE`

```text
  31:EA3C  58F0       MOV [--R15], R0
  31:EA3E  68F1 7AF8  MOV REG[0xF1], #0x7AF8
  31:EA42  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA46  58F1       MOV [--R15], R1
  31:EA48  58F0       MOV [--R15], R0
  31:EA4A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA4E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA52  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA56  58F1       MOV [--R15], R1
  31:EA58  58F0       MOV [--R15], R0
> 31:EA5A  BD03 4010  SCALL 03:4010
  31:EA5E  50FA       ADD R15, #0xA
  31:EA60  4802       MOV R0, #0x2
  31:EA62  58F0       MOV [--R15], R0
  31:EA64  68F1 7AEC  MOV REG[0xF1], #0x7AEC
  31:EA68  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA6C  58F1       MOV [--R15], R1
  31:EA6E  58F0       MOV [--R15], R0
  31:EA70  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA74  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA78  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA7C  58F1       MOV [--R15], R1
  31:EA7E  58F0       MOV [--R15], R0
```

### `31:EA80` in `sub_31_E9FE`

```text
  31:EA62  58F0       MOV [--R15], R0
  31:EA64  68F1 7AEC  MOV REG[0xF1], #0x7AEC
  31:EA68  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA6C  58F1       MOV [--R15], R1
  31:EA6E  58F0       MOV [--R15], R0
  31:EA70  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA74  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA78  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EA7C  58F1       MOV [--R15], R1
  31:EA7E  58F0       MOV [--R15], R0
> 31:EA80  BD03 4010  SCALL 03:4010
  31:EA84  50FA       ADD R15, #0xA
  31:EA86  4802       MOV R0, #0x2
  31:EA88  58F0       MOV [--R15], R0
  31:EA8A  68F1 7AEA  MOV REG[0xF1], #0x7AEA
  31:EA8E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA92  58F1       MOV [--R15], R1
  31:EA94  58F0       MOV [--R15], R0
  31:EA96  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA9A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA9E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAA2  58F1       MOV [--R15], R1
  31:EAA4  58F0       MOV [--R15], R0
```

### `31:EAA6` in `sub_31_E9FE`

```text
  31:EA88  58F0       MOV [--R15], R0
  31:EA8A  68F1 7AEA  MOV REG[0xF1], #0x7AEA
  31:EA8E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EA92  58F1       MOV [--R15], R1
  31:EA94  58F0       MOV [--R15], R0
  31:EA96  6810 00A4  MOV REG[0x10], #0x00A4
  31:EA9A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EA9E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAA2  58F1       MOV [--R15], R1
  31:EAA4  58F0       MOV [--R15], R0
> 31:EAA6  BD03 4010  SCALL 03:4010
  31:EAAA  50FA       ADD R15, #0xA
  31:EAAC  4802       MOV R0, #0x2
  31:EAAE  58F0       MOV [--R15], R0
  31:EAB0  081B       MOV R1, R11
  31:EAB2  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EAB6  4800       MOV R0, #0x0
  31:EAB8  58F1       MOV [--R15], R1
  31:EABA  58F0       MOV [--R15], R0
  31:EABC  6810 00A4  MOV REG[0x10], #0x00A4
  31:EAC0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EAC4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAC8  58F1       MOV [--R15], R1
```

### `31:EACC` in `sub_31_E9FE`

```text
  31:EAB0  081B       MOV R1, R11
  31:EAB2  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EAB6  4800       MOV R0, #0x0
  31:EAB8  58F1       MOV [--R15], R1
  31:EABA  58F0       MOV [--R15], R0
  31:EABC  6810 00A4  MOV REG[0x10], #0x00A4
  31:EAC0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EAC4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAC8  58F1       MOV [--R15], R1
  31:EACA  58F0       MOV [--R15], R0
> 31:EACC  BD03 4010  SCALL 03:4010
  31:EAD0  50FA       ADD R15, #0xA
  31:EAD2  4802       MOV R0, #0x2
  31:EAD4  58F0       MOV [--R15], R0
  31:EAD6  081B       MOV R1, R11
  31:EAD8  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EADC  4800       MOV R0, #0x0
  31:EADE  58F1       MOV [--R15], R1
  31:EAE0  58F0       MOV [--R15], R0
  31:EAE2  6810 00A4  MOV REG[0x10], #0x00A4
  31:EAE6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EAEA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAEE  58F1       MOV [--R15], R1
```

### `31:EAF2` in `sub_31_E9FE`

```text
  31:EAD6  081B       MOV R1, R11
  31:EAD8  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EADC  4800       MOV R0, #0x0
  31:EADE  58F1       MOV [--R15], R1
  31:EAE0  58F0       MOV [--R15], R0
  31:EAE2  6810 00A4  MOV REG[0x10], #0x00A4
  31:EAE6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EAEA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EAEE  58F1       MOV [--R15], R1
  31:EAF0  58F0       MOV [--R15], R0
> 31:EAF2  BD03 4010  SCALL 03:4010
  31:EAF6  50FA       ADD R15, #0xA
  31:EAF8  4802       MOV R0, #0x2
  31:EAFA  58F0       MOV [--R15], R0
  31:EAFC  081B       MOV R1, R11
  31:EAFE  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB02  4800       MOV R0, #0x0
  31:EB04  58F1       MOV [--R15], R1
  31:EB06  58F0       MOV [--R15], R0
  31:EB08  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB0C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB10  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB14  58F1       MOV [--R15], R1
```

### `31:EB18` in `sub_31_E9FE`

```text
  31:EAFC  081B       MOV R1, R11
  31:EAFE  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB02  4800       MOV R0, #0x0
  31:EB04  58F1       MOV [--R15], R1
  31:EB06  58F0       MOV [--R15], R0
  31:EB08  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB0C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB10  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB14  58F1       MOV [--R15], R1
  31:EB16  58F0       MOV [--R15], R0
> 31:EB18  BD03 4010  SCALL 03:4010
  31:EB1C  50FA       ADD R15, #0xA
  31:EB1E  4802       MOV R0, #0x2
  31:EB20  58F0       MOV [--R15], R0
  31:EB22  081B       MOV R1, R11
  31:EB24  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB28  4800       MOV R0, #0x0
  31:EB2A  58F1       MOV [--R15], R1
  31:EB2C  58F0       MOV [--R15], R0
  31:EB2E  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB32  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB36  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB3A  58F1       MOV [--R15], R1
```

### `31:EB3E` in `sub_31_E9FE`

```text
  31:EB22  081B       MOV R1, R11
  31:EB24  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB28  4800       MOV R0, #0x0
  31:EB2A  58F1       MOV [--R15], R1
  31:EB2C  58F0       MOV [--R15], R0
  31:EB2E  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB32  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB36  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB3A  58F1       MOV [--R15], R1
  31:EB3C  58F0       MOV [--R15], R0
> 31:EB3E  BD03 4010  SCALL 03:4010
  31:EB42  50FA       ADD R15, #0xA
  31:EB44  4802       MOV R0, #0x2
  31:EB46  58F0       MOV [--R15], R0
  31:EB48  081B       MOV R1, R11
  31:EB4A  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB4E  4800       MOV R0, #0x0
  31:EB50  58F1       MOV [--R15], R1
  31:EB52  58F0       MOV [--R15], R0
  31:EB54  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB58  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB5C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB60  58F1       MOV [--R15], R1
```

### `31:EB64` in `sub_31_E9FE`

```text
  31:EB48  081B       MOV R1, R11
  31:EB4A  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB4E  4800       MOV R0, #0x0
  31:EB50  58F1       MOV [--R15], R1
  31:EB52  58F0       MOV [--R15], R0
  31:EB54  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB58  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB5C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB60  58F1       MOV [--R15], R1
  31:EB62  58F0       MOV [--R15], R0
> 31:EB64  BD03 4010  SCALL 03:4010
  31:EB68  50FA       ADD R15, #0xA
  31:EB6A  4802       MOV R0, #0x2
  31:EB6C  58F0       MOV [--R15], R0
  31:EB6E  081B       MOV R1, R11
  31:EB70  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB74  4800       MOV R0, #0x0
  31:EB76  58F1       MOV [--R15], R1
  31:EB78  58F0       MOV [--R15], R0
  31:EB7A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB7E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB82  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB86  58F1       MOV [--R15], R1
```

### `31:EB8A` in `sub_31_E9FE`

```text
  31:EB6E  081B       MOV R1, R11
  31:EB70  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EB74  4800       MOV R0, #0x0
  31:EB76  58F1       MOV [--R15], R1
  31:EB78  58F0       MOV [--R15], R0
  31:EB7A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EB7E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EB82  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EB86  58F1       MOV [--R15], R1
  31:EB88  58F0       MOV [--R15], R0
> 31:EB8A  BD03 4010  SCALL 03:4010
  31:EB8E  50FA       ADD R15, #0xA
  31:EB90  4804       MOV R0, #0x4
  31:EB92  58F0       MOV [--R15], R0
  31:EB94  68F1 79D2  MOV REG[0xF1], #0x79D2
  31:EB98  68F0 0052  MOV REG[0xF0], #0x0052
  31:EB9C  58F1       MOV [--R15], R1
  31:EB9E  58F0       MOV [--R15], R0
  31:EBA0  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBA4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBA8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBAC  58F1       MOV [--R15], R1
  31:EBAE  58F0       MOV [--R15], R0
```

### `31:EBB0` in `sub_31_E9FE`

```text
  31:EB92  58F0       MOV [--R15], R0
  31:EB94  68F1 79D2  MOV REG[0xF1], #0x79D2
  31:EB98  68F0 0052  MOV REG[0xF0], #0x0052
  31:EB9C  58F1       MOV [--R15], R1
  31:EB9E  58F0       MOV [--R15], R0
  31:EBA0  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBA4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBA8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBAC  58F1       MOV [--R15], R1
  31:EBAE  58F0       MOV [--R15], R0
> 31:EBB0  BD03 4010  SCALL 03:4010
  31:EBB4  50FA       ADD R15, #0xA
  31:EBB6  4804       MOV R0, #0x4
  31:EBB8  58F0       MOV [--R15], R0
  31:EBBA  68F1 79CA  MOV REG[0xF1], #0x79CA
  31:EBBE  68F0 0052  MOV REG[0xF0], #0x0052
  31:EBC2  58F1       MOV [--R15], R1
  31:EBC4  58F0       MOV [--R15], R0
  31:EBC6  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBCA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBCE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBD2  58F1       MOV [--R15], R1
  31:EBD4  58F0       MOV [--R15], R0
```

### `31:EBD6` in `sub_31_E9FE`

```text
  31:EBB8  58F0       MOV [--R15], R0
  31:EBBA  68F1 79CA  MOV REG[0xF1], #0x79CA
  31:EBBE  68F0 0052  MOV REG[0xF0], #0x0052
  31:EBC2  58F1       MOV [--R15], R1
  31:EBC4  58F0       MOV [--R15], R0
  31:EBC6  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBCA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBCE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBD2  58F1       MOV [--R15], R1
  31:EBD4  58F0       MOV [--R15], R0
> 31:EBD6  BD03 4010  SCALL 03:4010
  31:EBDA  50FA       ADD R15, #0xA
  31:EBDC  4804       MOV R0, #0x4
  31:EBDE  58F0       MOV [--R15], R0
  31:EBE0  68F1 79C6  MOV REG[0xF1], #0x79C6
  31:EBE4  68F0 0052  MOV REG[0xF0], #0x0052
  31:EBE8  58F1       MOV [--R15], R1
  31:EBEA  58F0       MOV [--R15], R0
  31:EBEC  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBF0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBF4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBF8  58F1       MOV [--R15], R1
  31:EBFA  58F0       MOV [--R15], R0
```

### `31:EBFC` in `sub_31_E9FE`

```text
  31:EBDE  58F0       MOV [--R15], R0
  31:EBE0  68F1 79C6  MOV REG[0xF1], #0x79C6
  31:EBE4  68F0 0052  MOV REG[0xF0], #0x0052
  31:EBE8  58F1       MOV [--R15], R1
  31:EBEA  58F0       MOV [--R15], R0
  31:EBEC  6810 00A4  MOV REG[0x10], #0x00A4
  31:EBF0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EBF4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EBF8  58F1       MOV [--R15], R1
  31:EBFA  58F0       MOV [--R15], R0
> 31:EBFC  BD03 4010  SCALL 03:4010
  31:EC00  50FA       ADD R15, #0xA
  31:EC02  4804       MOV R0, #0x4
  31:EC04  58F0       MOV [--R15], R0
  31:EC06  68F1 79CE  MOV REG[0xF1], #0x79CE
  31:EC0A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC0E  58F1       MOV [--R15], R1
  31:EC10  58F0       MOV [--R15], R0
  31:EC12  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC16  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC1A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC1E  58F1       MOV [--R15], R1
  31:EC20  58F0       MOV [--R15], R0
```

### `31:EC22` in `sub_31_E9FE`

```text
  31:EC04  58F0       MOV [--R15], R0
  31:EC06  68F1 79CE  MOV REG[0xF1], #0x79CE
  31:EC0A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC0E  58F1       MOV [--R15], R1
  31:EC10  58F0       MOV [--R15], R0
  31:EC12  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC16  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC1A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC1E  58F1       MOV [--R15], R1
  31:EC20  58F0       MOV [--R15], R0
> 31:EC22  BD03 4010  SCALL 03:4010
  31:EC26  50FA       ADD R15, #0xA
  31:EC28  4804       MOV R0, #0x4
  31:EC2A  58F0       MOV [--R15], R0
  31:EC2C  081B       MOV R1, R11
  31:EC2E  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EC32  4800       MOV R0, #0x0
  31:EC34  58F1       MOV [--R15], R1
  31:EC36  58F0       MOV [--R15], R0
  31:EC38  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC3C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC40  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC44  58F1       MOV [--R15], R1
```

### `31:EC48` in `sub_31_E9FE`

```text
  31:EC2C  081B       MOV R1, R11
  31:EC2E  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EC32  4800       MOV R0, #0x0
  31:EC34  58F1       MOV [--R15], R1
  31:EC36  58F0       MOV [--R15], R0
  31:EC38  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC3C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC40  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC44  58F1       MOV [--R15], R1
  31:EC46  58F0       MOV [--R15], R0
> 31:EC48  BD03 4010  SCALL 03:4010
  31:EC4C  50FA       ADD R15, #0xA
  31:EC4E  4804       MOV R0, #0x4
  31:EC50  58F0       MOV [--R15], R0
  31:EC52  68F1 79EE  MOV REG[0xF1], #0x79EE
  31:EC56  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC5A  58F1       MOV [--R15], R1
  31:EC5C  58F0       MOV [--R15], R0
  31:EC5E  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC62  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC66  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC6A  58F1       MOV [--R15], R1
  31:EC6C  58F0       MOV [--R15], R0
```

### `31:EC6E` in `sub_31_E9FE`

```text
  31:EC50  58F0       MOV [--R15], R0
  31:EC52  68F1 79EE  MOV REG[0xF1], #0x79EE
  31:EC56  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC5A  58F1       MOV [--R15], R1
  31:EC5C  58F0       MOV [--R15], R0
  31:EC5E  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC62  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC66  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC6A  58F1       MOV [--R15], R1
  31:EC6C  58F0       MOV [--R15], R0
> 31:EC6E  BD03 4010  SCALL 03:4010
  31:EC72  50FA       ADD R15, #0xA
  31:EC74  4804       MOV R0, #0x4
  31:EC76  58F0       MOV [--R15], R0
  31:EC78  68F1 79EA  MOV REG[0xF1], #0x79EA
  31:EC7C  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC80  58F1       MOV [--R15], R1
  31:EC82  58F0       MOV [--R15], R0
  31:EC84  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC88  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC8C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC90  58F1       MOV [--R15], R1
  31:EC92  58F0       MOV [--R15], R0
```

### `31:EC94` in `sub_31_E9FE`

```text
  31:EC76  58F0       MOV [--R15], R0
  31:EC78  68F1 79EA  MOV REG[0xF1], #0x79EA
  31:EC7C  68F0 0052  MOV REG[0xF0], #0x0052
  31:EC80  58F1       MOV [--R15], R1
  31:EC82  58F0       MOV [--R15], R0
  31:EC84  6810 00A4  MOV REG[0x10], #0x00A4
  31:EC88  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EC8C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EC90  58F1       MOV [--R15], R1
  31:EC92  58F0       MOV [--R15], R0
> 31:EC94  BD03 4010  SCALL 03:4010
  31:EC98  50FA       ADD R15, #0xA
  31:EC9A  4804       MOV R0, #0x4
  31:EC9C  58F0       MOV [--R15], R0
  31:EC9E  68F1 79E6  MOV REG[0xF1], #0x79E6
  31:ECA2  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECA6  58F1       MOV [--R15], R1
  31:ECA8  58F0       MOV [--R15], R0
  31:ECAA  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECAE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECB2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ECB6  58F1       MOV [--R15], R1
  31:ECB8  58F0       MOV [--R15], R0
```

### `31:ECBA` in `sub_31_E9FE`

```text
  31:EC9C  58F0       MOV [--R15], R0
  31:EC9E  68F1 79E6  MOV REG[0xF1], #0x79E6
  31:ECA2  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECA6  58F1       MOV [--R15], R1
  31:ECA8  58F0       MOV [--R15], R0
  31:ECAA  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECAE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECB2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ECB6  58F1       MOV [--R15], R1
  31:ECB8  58F0       MOV [--R15], R0
> 31:ECBA  BD03 4010  SCALL 03:4010
  31:ECBE  50FA       ADD R15, #0xA
  31:ECC0  4804       MOV R0, #0x4
  31:ECC2  58F0       MOV [--R15], R0
  31:ECC4  68F1 79DA  MOV REG[0xF1], #0x79DA
  31:ECC8  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECCC  58F1       MOV [--R15], R1
  31:ECCE  58F0       MOV [--R15], R0
  31:ECD0  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECD4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECD8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ECDC  58F1       MOV [--R15], R1
  31:ECDE  58F0       MOV [--R15], R0
```

### `31:ECE0` in `sub_31_E9FE`

```text
  31:ECC2  58F0       MOV [--R15], R0
  31:ECC4  68F1 79DA  MOV REG[0xF1], #0x79DA
  31:ECC8  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECCC  58F1       MOV [--R15], R1
  31:ECCE  58F0       MOV [--R15], R0
  31:ECD0  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECD4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECD8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ECDC  58F1       MOV [--R15], R1
  31:ECDE  58F0       MOV [--R15], R0
> 31:ECE0  BD03 4010  SCALL 03:4010
  31:ECE4  50FA       ADD R15, #0xA
  31:ECE6  4804       MOV R0, #0x4
  31:ECE8  58F0       MOV [--R15], R0
  31:ECEA  68F1 79B6  MOV REG[0xF1], #0x79B6
  31:ECEE  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECF2  58F1       MOV [--R15], R1
  31:ECF4  58F0       MOV [--R15], R0
  31:ECF6  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECFA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECFE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED02  58F1       MOV [--R15], R1
  31:ED04  58F0       MOV [--R15], R0
```

### `31:ED06` in `sub_31_E9FE`

```text
  31:ECE8  58F0       MOV [--R15], R0
  31:ECEA  68F1 79B6  MOV REG[0xF1], #0x79B6
  31:ECEE  68F0 0052  MOV REG[0xF0], #0x0052
  31:ECF2  58F1       MOV [--R15], R1
  31:ECF4  58F0       MOV [--R15], R0
  31:ECF6  6810 00A4  MOV REG[0x10], #0x00A4
  31:ECFA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ECFE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED02  58F1       MOV [--R15], R1
  31:ED04  58F0       MOV [--R15], R0
> 31:ED06  BD03 4010  SCALL 03:4010
  31:ED0A  50FA       ADD R15, #0xA
  31:ED0C  4804       MOV R0, #0x4
  31:ED0E  58F0       MOV [--R15], R0
  31:ED10  081B       MOV R1, R11
  31:ED12  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:ED16  4800       MOV R0, #0x0
  31:ED18  58F1       MOV [--R15], R1
  31:ED1A  58F0       MOV [--R15], R0
  31:ED1C  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED20  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED24  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED28  58F1       MOV [--R15], R1
```

### `31:ED2C` in `sub_31_E9FE`

```text
  31:ED10  081B       MOV R1, R11
  31:ED12  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:ED16  4800       MOV R0, #0x0
  31:ED18  58F1       MOV [--R15], R1
  31:ED1A  58F0       MOV [--R15], R0
  31:ED1C  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED20  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED24  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED28  58F1       MOV [--R15], R1
  31:ED2A  58F0       MOV [--R15], R0
> 31:ED2C  BD03 4010  SCALL 03:4010
  31:ED30  50FA       ADD R15, #0xA
  31:ED32  4804       MOV R0, #0x4
  31:ED34  58F0       MOV [--R15], R0
  31:ED36  68F1 79F2  MOV REG[0xF1], #0x79F2
  31:ED3A  68F0 0052  MOV REG[0xF0], #0x0052
  31:ED3E  58F1       MOV [--R15], R1
  31:ED40  58F0       MOV [--R15], R0
  31:ED42  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED46  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED4A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED4E  58F1       MOV [--R15], R1
  31:ED50  58F0       MOV [--R15], R0
```

### `31:ED52` in `sub_31_E9FE`

```text
  31:ED34  58F0       MOV [--R15], R0
  31:ED36  68F1 79F2  MOV REG[0xF1], #0x79F2
  31:ED3A  68F0 0052  MOV REG[0xF0], #0x0052
  31:ED3E  58F1       MOV [--R15], R1
  31:ED40  58F0       MOV [--R15], R0
  31:ED42  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED46  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED4A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED4E  58F1       MOV [--R15], R1
  31:ED50  58F0       MOV [--R15], R0
> 31:ED52  BD03 4010  SCALL 03:4010
  31:ED56  50FA       ADD R15, #0xA
  31:ED58  4804       MOV R0, #0x4
  31:ED5A  58F0       MOV [--R15], R0
  31:ED5C  081B       MOV R1, R11
  31:ED5E  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:ED62  4800       MOV R0, #0x0
  31:ED64  58F1       MOV [--R15], R1
  31:ED66  58F0       MOV [--R15], R0
  31:ED68  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED6C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED70  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED74  58F1       MOV [--R15], R1
```

### `31:ED78` in `sub_31_E9FE`

```text
  31:ED5C  081B       MOV R1, R11
  31:ED5E  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:ED62  4800       MOV R0, #0x0
  31:ED64  58F1       MOV [--R15], R1
  31:ED66  58F0       MOV [--R15], R0
  31:ED68  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED6C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED70  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED74  58F1       MOV [--R15], R1
  31:ED76  58F0       MOV [--R15], R0
> 31:ED78  BD03 4010  SCALL 03:4010
  31:ED7C  50FA       ADD R15, #0xA
  31:ED7E  4804       MOV R0, #0x4
  31:ED80  58F0       MOV [--R15], R0
  31:ED82  68F1 79DE  MOV REG[0xF1], #0x79DE
  31:ED86  68F0 0052  MOV REG[0xF0], #0x0052
  31:ED8A  58F1       MOV [--R15], R1
  31:ED8C  58F0       MOV [--R15], R0
  31:ED8E  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED92  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED96  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED9A  58F1       MOV [--R15], R1
  31:ED9C  58F0       MOV [--R15], R0
```

### `31:ED9E` in `sub_31_E9FE`

```text
  31:ED80  58F0       MOV [--R15], R0
  31:ED82  68F1 79DE  MOV REG[0xF1], #0x79DE
  31:ED86  68F0 0052  MOV REG[0xF0], #0x0052
  31:ED8A  58F1       MOV [--R15], R1
  31:ED8C  58F0       MOV [--R15], R0
  31:ED8E  6810 00A4  MOV REG[0x10], #0x00A4
  31:ED92  88F0 7992  MOV REG[0xF0], [0x7992]
  31:ED96  88F1 7994  MOV REG[0xF1], [0x7994]
  31:ED9A  58F1       MOV [--R15], R1
  31:ED9C  58F0       MOV [--R15], R0
> 31:ED9E  BD03 4010  SCALL 03:4010
  31:EDA2  50FA       ADD R15, #0xA
  31:EDA4  4804       MOV R0, #0x4
  31:EDA6  58F0       MOV [--R15], R0
  31:EDA8  081B       MOV R1, R11
  31:EDAA  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EDAE  4800       MOV R0, #0x0
  31:EDB0  58F1       MOV [--R15], R1
  31:EDB2  58F0       MOV [--R15], R0
  31:EDB4  6810 00A4  MOV REG[0x10], #0x00A4
  31:EDB8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EDBC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EDC0  58F1       MOV [--R15], R1
```

### `31:EDC4` in `sub_31_E9FE`

```text
  31:EDA8  081B       MOV R1, R11
  31:EDAA  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EDAE  4800       MOV R0, #0x0
  31:EDB0  58F1       MOV [--R15], R1
  31:EDB2  58F0       MOV [--R15], R0
  31:EDB4  6810 00A4  MOV REG[0x10], #0x00A4
  31:EDB8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EDBC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EDC0  58F1       MOV [--R15], R1
  31:EDC2  58F0       MOV [--R15], R0
> 31:EDC4  BD03 4010  SCALL 03:4010
  31:EDC8  50FA       ADD R15, #0xA
  31:EDCA  4804       MOV R0, #0x4
  31:EDCC  58F0       MOV [--R15], R0
  31:EDCE  68F1 79E2  MOV REG[0xF1], #0x79E2
  31:EDD2  68F0 0052  MOV REG[0xF0], #0x0052
  31:EDD6  58F1       MOV [--R15], R1
  31:EDD8  58F0       MOV [--R15], R0
  31:EDDA  6810 00A4  MOV REG[0x10], #0x00A4
  31:EDDE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EDE2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EDE6  58F1       MOV [--R15], R1
  31:EDE8  58F0       MOV [--R15], R0
```

### `31:EDEA` in `sub_31_E9FE`

```text
  31:EDCC  58F0       MOV [--R15], R0
  31:EDCE  68F1 79E2  MOV REG[0xF1], #0x79E2
  31:EDD2  68F0 0052  MOV REG[0xF0], #0x0052
  31:EDD6  58F1       MOV [--R15], R1
  31:EDD8  58F0       MOV [--R15], R0
  31:EDDA  6810 00A4  MOV REG[0x10], #0x00A4
  31:EDDE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EDE2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EDE6  58F1       MOV [--R15], R1
  31:EDE8  58F0       MOV [--R15], R0
> 31:EDEA  BD03 4010  SCALL 03:4010
  31:EDEE  50FA       ADD R15, #0xA
  31:EDF0  4804       MOV R0, #0x4
  31:EDF2  58F0       MOV [--R15], R0
  31:EDF4  081B       MOV R1, R11
  31:EDF6  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EDFA  4800       MOV R0, #0x0
  31:EDFC  58F1       MOV [--R15], R1
  31:EDFE  58F0       MOV [--R15], R0
  31:EE00  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE04  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE08  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE0C  58F1       MOV [--R15], R1
```

### `31:EE10` in `sub_31_E9FE`

```text
  31:EDF4  081B       MOV R1, R11
  31:EDF6  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EDFA  4800       MOV R0, #0x0
  31:EDFC  58F1       MOV [--R15], R1
  31:EDFE  58F0       MOV [--R15], R0
  31:EE00  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE04  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE08  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE0C  58F1       MOV [--R15], R1
  31:EE0E  58F0       MOV [--R15], R0
> 31:EE10  BD03 4010  SCALL 03:4010
  31:EE14  50FA       ADD R15, #0xA
  31:EE16  4804       MOV R0, #0x4
  31:EE18  58F0       MOV [--R15], R0
  31:EE1A  68F1 79D6  MOV REG[0xF1], #0x79D6
  31:EE1E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE22  58F1       MOV [--R15], R1
  31:EE24  58F0       MOV [--R15], R0
  31:EE26  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE2A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE2E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE32  58F1       MOV [--R15], R1
  31:EE34  58F0       MOV [--R15], R0
```

### `31:EE36` in `sub_31_E9FE`

```text
  31:EE18  58F0       MOV [--R15], R0
  31:EE1A  68F1 79D6  MOV REG[0xF1], #0x79D6
  31:EE1E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE22  58F1       MOV [--R15], R1
  31:EE24  58F0       MOV [--R15], R0
  31:EE26  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE2A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE2E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE32  58F1       MOV [--R15], R1
  31:EE34  58F0       MOV [--R15], R0
> 31:EE36  BD03 4010  SCALL 03:4010
  31:EE3A  50FA       ADD R15, #0xA
  31:EE3C  4804       MOV R0, #0x4
  31:EE3E  58F0       MOV [--R15], R0
  31:EE40  081B       MOV R1, R11
  31:EE42  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EE46  4800       MOV R0, #0x0
  31:EE48  58F1       MOV [--R15], R1
  31:EE4A  58F0       MOV [--R15], R0
  31:EE4C  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE50  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE54  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE58  58F1       MOV [--R15], R1
```

### `31:EE5C` in `sub_31_E9FE`

```text
  31:EE40  081B       MOV R1, R11
  31:EE42  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EE46  4800       MOV R0, #0x0
  31:EE48  58F1       MOV [--R15], R1
  31:EE4A  58F0       MOV [--R15], R0
  31:EE4C  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE50  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE54  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE58  58F1       MOV [--R15], R1
  31:EE5A  58F0       MOV [--R15], R0
> 31:EE5C  BD03 4010  SCALL 03:4010
  31:EE60  50FA       ADD R15, #0xA
  31:EE62  4804       MOV R0, #0x4
  31:EE64  58F0       MOV [--R15], R0
  31:EE66  68F1 79C2  MOV REG[0xF1], #0x79C2
  31:EE6A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE6E  58F1       MOV [--R15], R1
  31:EE70  58F0       MOV [--R15], R0
  31:EE72  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE76  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE7A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE7E  58F1       MOV [--R15], R1
  31:EE80  58F0       MOV [--R15], R0
```

### `31:EE82` in `sub_31_E9FE`

```text
  31:EE64  58F0       MOV [--R15], R0
  31:EE66  68F1 79C2  MOV REG[0xF1], #0x79C2
  31:EE6A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE6E  58F1       MOV [--R15], R1
  31:EE70  58F0       MOV [--R15], R0
  31:EE72  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE76  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EE7A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EE7E  58F1       MOV [--R15], R1
  31:EE80  58F0       MOV [--R15], R0
> 31:EE82  BD03 4010  SCALL 03:4010
  31:EE86  50FA       ADD R15, #0xA
  31:EE88  4804       MOV R0, #0x4
  31:EE8A  58F0       MOV [--R15], R0
  31:EE8C  68F1 79BE  MOV REG[0xF1], #0x79BE
  31:EE90  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE94  58F1       MOV [--R15], R1
  31:EE96  58F0       MOV [--R15], R0
  31:EE98  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE9C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEA0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EEA4  58F1       MOV [--R15], R1
  31:EEA6  58F0       MOV [--R15], R0
```

### `31:EEA8` in `sub_31_E9FE`

```text
  31:EE8A  58F0       MOV [--R15], R0
  31:EE8C  68F1 79BE  MOV REG[0xF1], #0x79BE
  31:EE90  68F0 0052  MOV REG[0xF0], #0x0052
  31:EE94  58F1       MOV [--R15], R1
  31:EE96  58F0       MOV [--R15], R0
  31:EE98  6810 00A4  MOV REG[0x10], #0x00A4
  31:EE9C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEA0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EEA4  58F1       MOV [--R15], R1
  31:EEA6  58F0       MOV [--R15], R0
> 31:EEA8  BD03 4010  SCALL 03:4010
  31:EEAC  50FA       ADD R15, #0xA
  31:EEAE  4804       MOV R0, #0x4
  31:EEB0  58F0       MOV [--R15], R0
  31:EEB2  68F1 79AE  MOV REG[0xF1], #0x79AE
  31:EEB6  68F0 0052  MOV REG[0xF0], #0x0052
  31:EEBA  58F1       MOV [--R15], R1
  31:EEBC  58F0       MOV [--R15], R0
  31:EEBE  6810 00A4  MOV REG[0x10], #0x00A4
  31:EEC2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEC6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EECA  58F1       MOV [--R15], R1
  31:EECC  58F0       MOV [--R15], R0
```

### `31:EECE` in `sub_31_E9FE`

```text
  31:EEB0  58F0       MOV [--R15], R0
  31:EEB2  68F1 79AE  MOV REG[0xF1], #0x79AE
  31:EEB6  68F0 0052  MOV REG[0xF0], #0x0052
  31:EEBA  58F1       MOV [--R15], R1
  31:EEBC  58F0       MOV [--R15], R0
  31:EEBE  6810 00A4  MOV REG[0x10], #0x00A4
  31:EEC2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEC6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EECA  58F1       MOV [--R15], R1
  31:EECC  58F0       MOV [--R15], R0
> 31:EECE  BD03 4010  SCALL 03:4010
  31:EED2  50FA       ADD R15, #0xA
  31:EED4  4804       MOV R0, #0x4
  31:EED6  58F0       MOV [--R15], R0
  31:EED8  081B       MOV R1, R11
  31:EEDA  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EEDE  4800       MOV R0, #0x0
  31:EEE0  58F1       MOV [--R15], R1
  31:EEE2  58F0       MOV [--R15], R0
  31:EEE4  6810 00A4  MOV REG[0x10], #0x00A4
  31:EEE8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEEC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EEF0  58F1       MOV [--R15], R1
```

### `31:EEF4` in `sub_31_E9FE`

```text
  31:EED8  081B       MOV R1, R11
  31:EEDA  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EEDE  4800       MOV R0, #0x0
  31:EEE0  58F1       MOV [--R15], R1
  31:EEE2  58F0       MOV [--R15], R0
  31:EEE4  6810 00A4  MOV REG[0x10], #0x00A4
  31:EEE8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EEEC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EEF0  58F1       MOV [--R15], R1
  31:EEF2  58F0       MOV [--R15], R0
> 31:EEF4  BD03 4010  SCALL 03:4010
  31:EEF8  50FA       ADD R15, #0xA
  31:EEFA  4804       MOV R0, #0x4
  31:EEFC  58F0       MOV [--R15], R0
  31:EEFE  68F1 79B2  MOV REG[0xF1], #0x79B2
  31:EF02  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF06  58F1       MOV [--R15], R1
  31:EF08  58F0       MOV [--R15], R0
  31:EF0A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF0E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF12  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF16  58F1       MOV [--R15], R1
  31:EF18  58F0       MOV [--R15], R0
```

### `31:EF1A` in `sub_31_E9FE`

```text
  31:EEFC  58F0       MOV [--R15], R0
  31:EEFE  68F1 79B2  MOV REG[0xF1], #0x79B2
  31:EF02  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF06  58F1       MOV [--R15], R1
  31:EF08  58F0       MOV [--R15], R0
  31:EF0A  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF0E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF12  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF16  58F1       MOV [--R15], R1
  31:EF18  58F0       MOV [--R15], R0
> 31:EF1A  BD03 4010  SCALL 03:4010
  31:EF1E  50FA       ADD R15, #0xA
  31:EF20  4804       MOV R0, #0x4
  31:EF22  58F0       MOV [--R15], R0
  31:EF24  081B       MOV R1, R11
  31:EF26  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EF2A  4800       MOV R0, #0x0
  31:EF2C  58F1       MOV [--R15], R1
  31:EF2E  58F0       MOV [--R15], R0
  31:EF30  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF34  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF38  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF3C  58F1       MOV [--R15], R1
```

### `31:EF40` in `sub_31_E9FE`

```text
  31:EF24  081B       MOV R1, R11
  31:EF26  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EF2A  4800       MOV R0, #0x0
  31:EF2C  58F1       MOV [--R15], R1
  31:EF2E  58F0       MOV [--R15], R0
  31:EF30  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF34  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF38  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF3C  58F1       MOV [--R15], R1
  31:EF3E  58F0       MOV [--R15], R0
> 31:EF40  BD03 4010  SCALL 03:4010
  31:EF44  50FA       ADD R15, #0xA
  31:EF46  4804       MOV R0, #0x4
  31:EF48  58F0       MOV [--R15], R0
  31:EF4A  68F1 79BA  MOV REG[0xF1], #0x79BA
  31:EF4E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF52  58F1       MOV [--R15], R1
  31:EF54  58F0       MOV [--R15], R0
  31:EF56  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF5A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF5E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF62  58F1       MOV [--R15], R1
  31:EF64  58F0       MOV [--R15], R0
```

### `31:EF66` in `sub_31_E9FE`

```text
  31:EF48  58F0       MOV [--R15], R0
  31:EF4A  68F1 79BA  MOV REG[0xF1], #0x79BA
  31:EF4E  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF52  58F1       MOV [--R15], R1
  31:EF54  58F0       MOV [--R15], R0
  31:EF56  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF5A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF5E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF62  58F1       MOV [--R15], R1
  31:EF64  58F0       MOV [--R15], R0
> 31:EF66  BD03 4010  SCALL 03:4010
  31:EF6A  50FA       ADD R15, #0xA
  31:EF6C  4804       MOV R0, #0x4
  31:EF6E  58F0       MOV [--R15], R0
  31:EF70  081B       MOV R1, R11
  31:EF72  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EF76  4800       MOV R0, #0x0
  31:EF78  58F1       MOV [--R15], R1
  31:EF7A  58F0       MOV [--R15], R0
  31:EF7C  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF80  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF84  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF88  58F1       MOV [--R15], R1
```

### `31:EF8C` in `sub_31_E9FE`

```text
  31:EF70  081B       MOV R1, R11
  31:EF72  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EF76  4800       MOV R0, #0x0
  31:EF78  58F1       MOV [--R15], R1
  31:EF7A  58F0       MOV [--R15], R0
  31:EF7C  6810 00A4  MOV REG[0x10], #0x00A4
  31:EF80  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EF84  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EF88  58F1       MOV [--R15], R1
  31:EF8A  58F0       MOV [--R15], R0
> 31:EF8C  BD03 4010  SCALL 03:4010
  31:EF90  50FA       ADD R15, #0xA
  31:EF92  4804       MOV R0, #0x4
  31:EF94  58F0       MOV [--R15], R0
  31:EF96  68F1 79F6  MOV REG[0xF1], #0x79F6
  31:EF9A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF9E  58F1       MOV [--R15], R1
  31:EFA0  58F0       MOV [--R15], R0
  31:EFA2  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFA6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFAA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFAE  58F1       MOV [--R15], R1
  31:EFB0  58F0       MOV [--R15], R0
```

### `31:EFB2` in `sub_31_E9FE`

```text
  31:EF94  58F0       MOV [--R15], R0
  31:EF96  68F1 79F6  MOV REG[0xF1], #0x79F6
  31:EF9A  68F0 0052  MOV REG[0xF0], #0x0052
  31:EF9E  58F1       MOV [--R15], R1
  31:EFA0  58F0       MOV [--R15], R0
  31:EFA2  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFA6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFAA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFAE  58F1       MOV [--R15], R1
  31:EFB0  58F0       MOV [--R15], R0
> 31:EFB2  BD03 4010  SCALL 03:4010
  31:EFB6  50FA       ADD R15, #0xA
  31:EFB8  4804       MOV R0, #0x4
  31:EFBA  58F0       MOV [--R15], R0
  31:EFBC  081B       MOV R1, R11
  31:EFBE  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EFC2  4800       MOV R0, #0x0
  31:EFC4  58F1       MOV [--R15], R1
  31:EFC6  58F0       MOV [--R15], R0
  31:EFC8  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFCC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFD0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFD4  58F1       MOV [--R15], R1
```

### `31:EFD8` in `sub_31_E9FE`

```text
  31:EFBC  081B       MOV R1, R11
  31:EFBE  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:EFC2  4800       MOV R0, #0x0
  31:EFC4  58F1       MOV [--R15], R1
  31:EFC6  58F0       MOV [--R15], R0
  31:EFC8  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFCC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFD0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFD4  58F1       MOV [--R15], R1
  31:EFD6  58F0       MOV [--R15], R0
> 31:EFD8  BD03 4010  SCALL 03:4010
  31:EFDC  50FA       ADD R15, #0xA
  31:EFDE  4804       MOV R0, #0x4
  31:EFE0  58F0       MOV [--R15], R0
  31:EFE2  68F1 79FA  MOV REG[0xF1], #0x79FA
  31:EFE6  68F0 0052  MOV REG[0xF0], #0x0052
  31:EFEA  58F1       MOV [--R15], R1
  31:EFEC  58F0       MOV [--R15], R0
  31:EFEE  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFF2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFF6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFFA  58F1       MOV [--R15], R1
  31:EFFC  58F0       MOV [--R15], R0
```

### `31:EFFE` in `sub_31_E9FE`

```text
  31:EFE0  58F0       MOV [--R15], R0
  31:EFE2  68F1 79FA  MOV REG[0xF1], #0x79FA
  31:EFE6  68F0 0052  MOV REG[0xF0], #0x0052
  31:EFEA  58F1       MOV [--R15], R1
  31:EFEC  58F0       MOV [--R15], R0
  31:EFEE  6810 00A4  MOV REG[0x10], #0x00A4
  31:EFF2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:EFF6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:EFFA  58F1       MOV [--R15], R1
  31:EFFC  58F0       MOV [--R15], R0
> 31:EFFE  BD03 4010  SCALL 03:4010
  31:F002  50FA       ADD R15, #0xA
  31:F004  4804       MOV R0, #0x4
  31:F006  58F0       MOV [--R15], R0
  31:F008  081B       MOV R1, R11
  31:F00A  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:F00E  4800       MOV R0, #0x0
  31:F010  58F1       MOV [--R15], R1
  31:F012  58F0       MOV [--R15], R0
  31:F014  6810 00A4  MOV REG[0x10], #0x00A4
  31:F018  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F01C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F020  58F1       MOV [--R15], R1
```

### `31:F024` in `sub_31_E9FE`

```text
  31:F008  081B       MOV R1, R11
  31:F00A  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:F00E  4800       MOV R0, #0x0
  31:F010  58F1       MOV [--R15], R1
  31:F012  58F0       MOV [--R15], R0
  31:F014  6810 00A4  MOV REG[0x10], #0x00A4
  31:F018  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F01C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F020  58F1       MOV [--R15], R1
  31:F022  58F0       MOV [--R15], R0
> 31:F024  BD03 4010  SCALL 03:4010
  31:F028  50FA       ADD R15, #0xA
  31:F02A  4804       MOV R0, #0x4
  31:F02C  58F0       MOV [--R15], R0
  31:F02E  68F1 79FE  MOV REG[0xF1], #0x79FE
  31:F032  68F0 0052  MOV REG[0xF0], #0x0052
  31:F036  58F1       MOV [--R15], R1
  31:F038  58F0       MOV [--R15], R0
  31:F03A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F03E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F042  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F046  58F1       MOV [--R15], R1
  31:F048  58F0       MOV [--R15], R0
```

### `31:F04A` in `sub_31_E9FE`

```text
  31:F02C  58F0       MOV [--R15], R0
  31:F02E  68F1 79FE  MOV REG[0xF1], #0x79FE
  31:F032  68F0 0052  MOV REG[0xF0], #0x0052
  31:F036  58F1       MOV [--R15], R1
  31:F038  58F0       MOV [--R15], R0
  31:F03A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F03E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F042  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F046  58F1       MOV [--R15], R1
  31:F048  58F0       MOV [--R15], R0
> 31:F04A  BD03 4010  SCALL 03:4010
  31:F04E  50FA       ADD R15, #0xA
  31:F050  4804       MOV R0, #0x4
  31:F052  58F0       MOV [--R15], R0
  31:F054  081B       MOV R1, R11
  31:F056  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:F05A  4800       MOV R0, #0x0
  31:F05C  58F1       MOV [--R15], R1
  31:F05E  58F0       MOV [--R15], R0
  31:F060  6810 00A4  MOV REG[0x10], #0x00A4
  31:F064  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F068  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F06C  58F1       MOV [--R15], R1
```

### `31:F070` in `sub_31_E9FE`

```text
  31:F054  081B       MOV R1, R11
  31:F056  70F1 FFFC  ADD REG[0xF1], #0xFFFC
  31:F05A  4800       MOV R0, #0x0
  31:F05C  58F1       MOV [--R15], R1
  31:F05E  58F0       MOV [--R15], R0
  31:F060  6810 00A4  MOV REG[0x10], #0x00A4
  31:F064  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F068  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F06C  58F1       MOV [--R15], R1
  31:F06E  58F0       MOV [--R15], R0
> 31:F070  BD03 4010  SCALL 03:4010
  31:F074  50FA       ADD R15, #0xA
  31:F076  4804       MOV R0, #0x4
  31:F078  58F0       MOV [--R15], R0
  31:F07A  68F1 78D4  MOV REG[0xF1], #0x78D4
  31:F07E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F082  58F1       MOV [--R15], R1
  31:F084  58F0       MOV [--R15], R0
  31:F086  6810 00A4  MOV REG[0x10], #0x00A4
  31:F08A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F08E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F092  58F1       MOV [--R15], R1
  31:F094  58F0       MOV [--R15], R0
```

### `31:F096` in `sub_31_E9FE`

```text
  31:F078  58F0       MOV [--R15], R0
  31:F07A  68F1 78D4  MOV REG[0xF1], #0x78D4
  31:F07E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F082  58F1       MOV [--R15], R1
  31:F084  58F0       MOV [--R15], R0
  31:F086  6810 00A4  MOV REG[0x10], #0x00A4
  31:F08A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F08E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F092  58F1       MOV [--R15], R1
  31:F094  58F0       MOV [--R15], R0
> 31:F096  BD03 4010  SCALL 03:4010
  31:F09A  50FA       ADD R15, #0xA
  31:F09C  4804       MOV R0, #0x4
  31:F09E  58F0       MOV [--R15], R0
  31:F0A0  68F1 78C4  MOV REG[0xF1], #0x78C4
  31:F0A4  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0A8  58F1       MOV [--R15], R1
  31:F0AA  58F0       MOV [--R15], R0
  31:F0AC  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0B0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F0B4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F0B8  58F1       MOV [--R15], R1
  31:F0BA  58F0       MOV [--R15], R0
```

### `31:F0BC` in `sub_31_E9FE`

```text
  31:F09E  58F0       MOV [--R15], R0
  31:F0A0  68F1 78C4  MOV REG[0xF1], #0x78C4
  31:F0A4  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0A8  58F1       MOV [--R15], R1
  31:F0AA  58F0       MOV [--R15], R0
  31:F0AC  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0B0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F0B4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F0B8  58F1       MOV [--R15], R1
  31:F0BA  58F0       MOV [--R15], R0
> 31:F0BC  BD03 4010  SCALL 03:4010
  31:F0C0  50FA       ADD R15, #0xA
  31:F0C2  4804       MOV R0, #0x4
  31:F0C4  58F0       MOV [--R15], R0
  31:F0C6  68F1 78D8  MOV REG[0xF1], #0x78D8
  31:F0CA  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0CE  58F1       MOV [--R15], R1
  31:F0D0  58F0       MOV [--R15], R0
  31:F0D2  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0D6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F0DA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F0DE  58F1       MOV [--R15], R1
  31:F0E0  58F0       MOV [--R15], R0
```

### `31:F0E2` in `sub_31_E9FE`

```text
  31:F0C4  58F0       MOV [--R15], R0
  31:F0C6  68F1 78D8  MOV REG[0xF1], #0x78D8
  31:F0CA  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0CE  58F1       MOV [--R15], R1
  31:F0D0  58F0       MOV [--R15], R0
  31:F0D2  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0D6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F0DA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F0DE  58F1       MOV [--R15], R1
  31:F0E0  58F0       MOV [--R15], R0
> 31:F0E2  BD03 4010  SCALL 03:4010
  31:F0E6  50FA       ADD R15, #0xA
  31:F0E8  4804       MOV R0, #0x4
  31:F0EA  58F0       MOV [--R15], R0
  31:F0EC  68F1 78C8  MOV REG[0xF1], #0x78C8
  31:F0F0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0F4  58F1       MOV [--R15], R1
  31:F0F6  58F0       MOV [--R15], R0
  31:F0F8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0FC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F100  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F104  58F1       MOV [--R15], R1
  31:F106  58F0       MOV [--R15], R0
```

### `31:F108` in `sub_31_E9FE`

```text
  31:F0EA  58F0       MOV [--R15], R0
  31:F0EC  68F1 78C8  MOV REG[0xF1], #0x78C8
  31:F0F0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F0F4  58F1       MOV [--R15], R1
  31:F0F6  58F0       MOV [--R15], R0
  31:F0F8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F0FC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F100  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F104  58F1       MOV [--R15], R1
  31:F106  58F0       MOV [--R15], R0
> 31:F108  BD03 4010  SCALL 03:4010
  31:F10C  50FA       ADD R15, #0xA
  31:F10E  4804       MOV R0, #0x4
  31:F110  58F0       MOV [--R15], R0
  31:F112  68F1 78DC  MOV REG[0xF1], #0x78DC
  31:F116  68F0 0052  MOV REG[0xF0], #0x0052
  31:F11A  58F1       MOV [--R15], R1
  31:F11C  58F0       MOV [--R15], R0
  31:F11E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F122  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F126  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F12A  58F1       MOV [--R15], R1
  31:F12C  58F0       MOV [--R15], R0
```

### `31:F12E` in `sub_31_E9FE`

```text
  31:F110  58F0       MOV [--R15], R0
  31:F112  68F1 78DC  MOV REG[0xF1], #0x78DC
  31:F116  68F0 0052  MOV REG[0xF0], #0x0052
  31:F11A  58F1       MOV [--R15], R1
  31:F11C  58F0       MOV [--R15], R0
  31:F11E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F122  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F126  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F12A  58F1       MOV [--R15], R1
  31:F12C  58F0       MOV [--R15], R0
> 31:F12E  BD03 4010  SCALL 03:4010
  31:F132  50FA       ADD R15, #0xA
  31:F134  4804       MOV R0, #0x4
  31:F136  58F0       MOV [--R15], R0
  31:F138  68F1 78CC  MOV REG[0xF1], #0x78CC
  31:F13C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F140  58F1       MOV [--R15], R1
  31:F142  58F0       MOV [--R15], R0
  31:F144  6810 00A4  MOV REG[0x10], #0x00A4
  31:F148  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F14C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F150  58F1       MOV [--R15], R1
  31:F152  58F0       MOV [--R15], R0
```

### `31:F154` in `sub_31_E9FE`

```text
  31:F136  58F0       MOV [--R15], R0
  31:F138  68F1 78CC  MOV REG[0xF1], #0x78CC
  31:F13C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F140  58F1       MOV [--R15], R1
  31:F142  58F0       MOV [--R15], R0
  31:F144  6810 00A4  MOV REG[0x10], #0x00A4
  31:F148  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F14C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F150  58F1       MOV [--R15], R1
  31:F152  58F0       MOV [--R15], R0
> 31:F154  BD03 4010  SCALL 03:4010
  31:F158  50FA       ADD R15, #0xA
  31:F15A  4804       MOV R0, #0x4
  31:F15C  58F0       MOV [--R15], R0
  31:F15E  68F1 78E0  MOV REG[0xF1], #0x78E0
  31:F162  68F0 0052  MOV REG[0xF0], #0x0052
  31:F166  58F1       MOV [--R15], R1
  31:F168  58F0       MOV [--R15], R0
  31:F16A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F16E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F172  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F176  58F1       MOV [--R15], R1
  31:F178  58F0       MOV [--R15], R0
```

### `31:F17A` in `sub_31_E9FE`

```text
  31:F15C  58F0       MOV [--R15], R0
  31:F15E  68F1 78E0  MOV REG[0xF1], #0x78E0
  31:F162  68F0 0052  MOV REG[0xF0], #0x0052
  31:F166  58F1       MOV [--R15], R1
  31:F168  58F0       MOV [--R15], R0
  31:F16A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F16E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F172  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F176  58F1       MOV [--R15], R1
  31:F178  58F0       MOV [--R15], R0
> 31:F17A  BD03 4010  SCALL 03:4010
  31:F17E  50FA       ADD R15, #0xA
  31:F180  4804       MOV R0, #0x4
  31:F182  58F0       MOV [--R15], R0
  31:F184  68F1 78D0  MOV REG[0xF1], #0x78D0
  31:F188  68F0 0052  MOV REG[0xF0], #0x0052
  31:F18C  58F1       MOV [--R15], R1
  31:F18E  58F0       MOV [--R15], R0
  31:F190  6810 00A4  MOV REG[0x10], #0x00A4
  31:F194  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F198  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F19C  58F1       MOV [--R15], R1
  31:F19E  58F0       MOV [--R15], R0
```

### `31:F1A0` in `sub_31_E9FE`

```text
  31:F182  58F0       MOV [--R15], R0
  31:F184  68F1 78D0  MOV REG[0xF1], #0x78D0
  31:F188  68F0 0052  MOV REG[0xF0], #0x0052
  31:F18C  58F1       MOV [--R15], R1
  31:F18E  58F0       MOV [--R15], R0
  31:F190  6810 00A4  MOV REG[0x10], #0x00A4
  31:F194  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F198  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F19C  58F1       MOV [--R15], R1
  31:F19E  58F0       MOV [--R15], R0
> 31:F1A0  BD03 4010  SCALL 03:4010
  31:F1A4  50FA       ADD R15, #0xA
  31:F1A6  4804       MOV R0, #0x4
  31:F1A8  58F0       MOV [--R15], R0
  31:F1AA  68F1 78FE  MOV REG[0xF1], #0x78FE
  31:F1AE  68F0 0052  MOV REG[0xF0], #0x0052
  31:F1B2  58F1       MOV [--R15], R1
  31:F1B4  58F0       MOV [--R15], R0
  31:F1B6  6810 00A4  MOV REG[0x10], #0x00A4
  31:F1BA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F1BE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F1C2  58F1       MOV [--R15], R1
  31:F1C4  58F0       MOV [--R15], R0
```

### `31:F1C6` in `sub_31_E9FE`

```text
  31:F1A8  58F0       MOV [--R15], R0
  31:F1AA  68F1 78FE  MOV REG[0xF1], #0x78FE
  31:F1AE  68F0 0052  MOV REG[0xF0], #0x0052
  31:F1B2  58F1       MOV [--R15], R1
  31:F1B4  58F0       MOV [--R15], R0
  31:F1B6  6810 00A4  MOV REG[0x10], #0x00A4
  31:F1BA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F1BE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F1C2  58F1       MOV [--R15], R1
  31:F1C4  58F0       MOV [--R15], R0
> 31:F1C6  BD03 4010  SCALL 03:4010
  31:F1CA  50FA       ADD R15, #0xA
  31:F1CC  4804       MOV R0, #0x4
  31:F1CE  58F0       MOV [--R15], R0
  31:F1D0  68F1 78F2  MOV REG[0xF1], #0x78F2
  31:F1D4  68F0 0052  MOV REG[0xF0], #0x0052
  31:F1D8  58F1       MOV [--R15], R1
  31:F1DA  58F0       MOV [--R15], R0
  31:F1DC  6810 00A4  MOV REG[0x10], #0x00A4
  31:F1E0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F1E4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F1E8  58F1       MOV [--R15], R1
  31:F1EA  58F0       MOV [--R15], R0
```

### `31:F1EC` in `sub_31_E9FE`

```text
  31:F1CE  58F0       MOV [--R15], R0
  31:F1D0  68F1 78F2  MOV REG[0xF1], #0x78F2
  31:F1D4  68F0 0052  MOV REG[0xF0], #0x0052
  31:F1D8  58F1       MOV [--R15], R1
  31:F1DA  58F0       MOV [--R15], R0
  31:F1DC  6810 00A4  MOV REG[0x10], #0x00A4
  31:F1E0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F1E4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F1E8  58F1       MOV [--R15], R1
  31:F1EA  58F0       MOV [--R15], R0
> 31:F1EC  BD03 4010  SCALL 03:4010
  31:F1F0  50FA       ADD R15, #0xA
```

### `31:F212` in `sub_31_F1F2`

```text
  31:F1F4  58F0       MOV [--R15], R0
  31:F1F6  68F1 7902  MOV REG[0xF1], #0x7902
  31:F1FA  68F0 0052  MOV REG[0xF0], #0x0052
  31:F1FE  58F1       MOV [--R15], R1
  31:F200  58F0       MOV [--R15], R0
  31:F202  6810 00A4  MOV REG[0x10], #0x00A4
  31:F206  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F20A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F20E  58F1       MOV [--R15], R1
  31:F210  58F0       MOV [--R15], R0
> 31:F212  BD03 4010  SCALL 03:4010
  31:F216  50FA       ADD R15, #0xA
  31:F218  4804       MOV R0, #0x4
  31:F21A  58F0       MOV [--R15], R0
  31:F21C  68F1 78F6  MOV REG[0xF1], #0x78F6
  31:F220  68F0 0052  MOV REG[0xF0], #0x0052
  31:F224  58F1       MOV [--R15], R1
  31:F226  58F0       MOV [--R15], R0
  31:F228  6810 00A4  MOV REG[0x10], #0x00A4
  31:F22C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F230  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F234  58F1       MOV [--R15], R1
  31:F236  58F0       MOV [--R15], R0
```

### `31:F238` in `sub_31_F1F2`

```text
  31:F21A  58F0       MOV [--R15], R0
  31:F21C  68F1 78F6  MOV REG[0xF1], #0x78F6
  31:F220  68F0 0052  MOV REG[0xF0], #0x0052
  31:F224  58F1       MOV [--R15], R1
  31:F226  58F0       MOV [--R15], R0
  31:F228  6810 00A4  MOV REG[0x10], #0x00A4
  31:F22C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F230  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F234  58F1       MOV [--R15], R1
  31:F236  58F0       MOV [--R15], R0
> 31:F238  BD03 4010  SCALL 03:4010
  31:F23C  50FA       ADD R15, #0xA
  31:F23E  4804       MOV R0, #0x4
  31:F240  58F0       MOV [--R15], R0
  31:F242  68F1 7906  MOV REG[0xF1], #0x7906
  31:F246  68F0 0052  MOV REG[0xF0], #0x0052
  31:F24A  58F1       MOV [--R15], R1
  31:F24C  58F0       MOV [--R15], R0
  31:F24E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F252  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F256  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F25A  58F1       MOV [--R15], R1
  31:F25C  58F0       MOV [--R15], R0
```

### `31:F25E` in `sub_31_F1F2`

```text
  31:F240  58F0       MOV [--R15], R0
  31:F242  68F1 7906  MOV REG[0xF1], #0x7906
  31:F246  68F0 0052  MOV REG[0xF0], #0x0052
  31:F24A  58F1       MOV [--R15], R1
  31:F24C  58F0       MOV [--R15], R0
  31:F24E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F252  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F256  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F25A  58F1       MOV [--R15], R1
  31:F25C  58F0       MOV [--R15], R0
> 31:F25E  BD03 4010  SCALL 03:4010
  31:F262  50FA       ADD R15, #0xA
  31:F264  4804       MOV R0, #0x4
  31:F266  58F0       MOV [--R15], R0
  31:F268  68F1 78FA  MOV REG[0xF1], #0x78FA
  31:F26C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F270  58F1       MOV [--R15], R1
  31:F272  58F0       MOV [--R15], R0
  31:F274  6810 00A4  MOV REG[0x10], #0x00A4
  31:F278  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F27C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F280  58F1       MOV [--R15], R1
  31:F282  58F0       MOV [--R15], R0
```

### `31:F284` in `sub_31_F1F2`

```text
  31:F266  58F0       MOV [--R15], R0
  31:F268  68F1 78FA  MOV REG[0xF1], #0x78FA
  31:F26C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F270  58F1       MOV [--R15], R1
  31:F272  58F0       MOV [--R15], R0
  31:F274  6810 00A4  MOV REG[0x10], #0x00A4
  31:F278  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F27C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F280  58F1       MOV [--R15], R1
  31:F282  58F0       MOV [--R15], R0
> 31:F284  BD03 4010  SCALL 03:4010
  31:F288  50FA       ADD R15, #0xA
  31:F28A  4804       MOV R0, #0x4
  31:F28C  58F0       MOV [--R15], R0
  31:F28E  68F1 7872  MOV REG[0xF1], #0x7872
  31:F292  68F0 0052  MOV REG[0xF0], #0x0052
  31:F296  58F1       MOV [--R15], R1
  31:F298  58F0       MOV [--R15], R0
  31:F29A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F29E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2A2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2A6  58F1       MOV [--R15], R1
  31:F2A8  58F0       MOV [--R15], R0
```

### `31:F2AA` in `sub_31_F1F2`

```text
  31:F28C  58F0       MOV [--R15], R0
  31:F28E  68F1 7872  MOV REG[0xF1], #0x7872
  31:F292  68F0 0052  MOV REG[0xF0], #0x0052
  31:F296  58F1       MOV [--R15], R1
  31:F298  58F0       MOV [--R15], R0
  31:F29A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F29E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2A2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2A6  58F1       MOV [--R15], R1
  31:F2A8  58F0       MOV [--R15], R0
> 31:F2AA  BD03 4010  SCALL 03:4010
  31:F2AE  50FA       ADD R15, #0xA
  31:F2B0  4804       MOV R0, #0x4
  31:F2B2  58F0       MOV [--R15], R0
  31:F2B4  68F1 7856  MOV REG[0xF1], #0x7856
  31:F2B8  68F0 0052  MOV REG[0xF0], #0x0052
  31:F2BC  58F1       MOV [--R15], R1
  31:F2BE  58F0       MOV [--R15], R0
  31:F2C0  6810 00A4  MOV REG[0x10], #0x00A4
  31:F2C4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2C8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2CC  58F1       MOV [--R15], R1
  31:F2CE  58F0       MOV [--R15], R0
```

### `31:F2D0` in `sub_31_F1F2`

```text
  31:F2B2  58F0       MOV [--R15], R0
  31:F2B4  68F1 7856  MOV REG[0xF1], #0x7856
  31:F2B8  68F0 0052  MOV REG[0xF0], #0x0052
  31:F2BC  58F1       MOV [--R15], R1
  31:F2BE  58F0       MOV [--R15], R0
  31:F2C0  6810 00A4  MOV REG[0x10], #0x00A4
  31:F2C4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2C8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2CC  58F1       MOV [--R15], R1
  31:F2CE  58F0       MOV [--R15], R0
> 31:F2D0  BD03 4010  SCALL 03:4010
  31:F2D4  50FA       ADD R15, #0xA
  31:F2D6  4804       MOV R0, #0x4
  31:F2D8  58F0       MOV [--R15], R0
  31:F2DA  68F1 7876  MOV REG[0xF1], #0x7876
  31:F2DE  68F0 0052  MOV REG[0xF0], #0x0052
  31:F2E2  58F1       MOV [--R15], R1
  31:F2E4  58F0       MOV [--R15], R0
  31:F2E6  6810 00A4  MOV REG[0x10], #0x00A4
  31:F2EA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2EE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2F2  58F1       MOV [--R15], R1
  31:F2F4  58F0       MOV [--R15], R0
```

### `31:F2F6` in `sub_31_F1F2`

```text
  31:F2D8  58F0       MOV [--R15], R0
  31:F2DA  68F1 7876  MOV REG[0xF1], #0x7876
  31:F2DE  68F0 0052  MOV REG[0xF0], #0x0052
  31:F2E2  58F1       MOV [--R15], R1
  31:F2E4  58F0       MOV [--R15], R0
  31:F2E6  6810 00A4  MOV REG[0x10], #0x00A4
  31:F2EA  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F2EE  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F2F2  58F1       MOV [--R15], R1
  31:F2F4  58F0       MOV [--R15], R0
> 31:F2F6  BD03 4010  SCALL 03:4010
  31:F2FA  50FA       ADD R15, #0xA
  31:F2FC  4804       MOV R0, #0x4
  31:F2FE  58F0       MOV [--R15], R0
  31:F300  68F1 785A  MOV REG[0xF1], #0x785A
  31:F304  68F0 0052  MOV REG[0xF0], #0x0052
  31:F308  58F1       MOV [--R15], R1
  31:F30A  58F0       MOV [--R15], R0
  31:F30C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F310  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F314  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F318  58F1       MOV [--R15], R1
  31:F31A  58F0       MOV [--R15], R0
```

### `31:F31C` in `sub_31_F1F2`

```text
  31:F2FE  58F0       MOV [--R15], R0
  31:F300  68F1 785A  MOV REG[0xF1], #0x785A
  31:F304  68F0 0052  MOV REG[0xF0], #0x0052
  31:F308  58F1       MOV [--R15], R1
  31:F30A  58F0       MOV [--R15], R0
  31:F30C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F310  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F314  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F318  58F1       MOV [--R15], R1
  31:F31A  58F0       MOV [--R15], R0
> 31:F31C  BD03 4010  SCALL 03:4010
  31:F320  50FA       ADD R15, #0xA
  31:F322  4804       MOV R0, #0x4
  31:F324  58F0       MOV [--R15], R0
  31:F326  68F1 787A  MOV REG[0xF1], #0x787A
  31:F32A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F32E  58F1       MOV [--R15], R1
  31:F330  58F0       MOV [--R15], R0
  31:F332  6810 00A4  MOV REG[0x10], #0x00A4
  31:F336  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F33A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F33E  58F1       MOV [--R15], R1
  31:F340  58F0       MOV [--R15], R0
```

### `31:F342` in `sub_31_F1F2`

```text
  31:F324  58F0       MOV [--R15], R0
  31:F326  68F1 787A  MOV REG[0xF1], #0x787A
  31:F32A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F32E  58F1       MOV [--R15], R1
  31:F330  58F0       MOV [--R15], R0
  31:F332  6810 00A4  MOV REG[0x10], #0x00A4
  31:F336  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F33A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F33E  58F1       MOV [--R15], R1
  31:F340  58F0       MOV [--R15], R0
> 31:F342  BD03 4010  SCALL 03:4010
  31:F346  50FA       ADD R15, #0xA
  31:F348  4804       MOV R0, #0x4
  31:F34A  58F0       MOV [--R15], R0
  31:F34C  68F1 785E  MOV REG[0xF1], #0x785E
  31:F350  68F0 0052  MOV REG[0xF0], #0x0052
  31:F354  58F1       MOV [--R15], R1
  31:F356  58F0       MOV [--R15], R0
  31:F358  6810 00A4  MOV REG[0x10], #0x00A4
  31:F35C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F360  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F364  58F1       MOV [--R15], R1
  31:F366  58F0       MOV [--R15], R0
```

### `31:F368` in `sub_31_F1F2`

```text
  31:F34A  58F0       MOV [--R15], R0
  31:F34C  68F1 785E  MOV REG[0xF1], #0x785E
  31:F350  68F0 0052  MOV REG[0xF0], #0x0052
  31:F354  58F1       MOV [--R15], R1
  31:F356  58F0       MOV [--R15], R0
  31:F358  6810 00A4  MOV REG[0x10], #0x00A4
  31:F35C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F360  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F364  58F1       MOV [--R15], R1
  31:F366  58F0       MOV [--R15], R0
> 31:F368  BD03 4010  SCALL 03:4010
  31:F36C  50FA       ADD R15, #0xA
  31:F36E  4804       MOV R0, #0x4
  31:F370  58F0       MOV [--R15], R0
  31:F372  68F1 787E  MOV REG[0xF1], #0x787E
  31:F376  68F0 0052  MOV REG[0xF0], #0x0052
  31:F37A  58F1       MOV [--R15], R1
  31:F37C  58F0       MOV [--R15], R0
  31:F37E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F382  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F386  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F38A  58F1       MOV [--R15], R1
  31:F38C  58F0       MOV [--R15], R0
```

### `31:F38E` in `sub_31_F1F2`

```text
  31:F370  58F0       MOV [--R15], R0
  31:F372  68F1 787E  MOV REG[0xF1], #0x787E
  31:F376  68F0 0052  MOV REG[0xF0], #0x0052
  31:F37A  58F1       MOV [--R15], R1
  31:F37C  58F0       MOV [--R15], R0
  31:F37E  6810 00A4  MOV REG[0x10], #0x00A4
  31:F382  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F386  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F38A  58F1       MOV [--R15], R1
  31:F38C  58F0       MOV [--R15], R0
> 31:F38E  BD03 4010  SCALL 03:4010
  31:F392  50FA       ADD R15, #0xA
  31:F394  4804       MOV R0, #0x4
  31:F396  58F0       MOV [--R15], R0
  31:F398  68F1 7862  MOV REG[0xF1], #0x7862
  31:F39C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3A0  58F1       MOV [--R15], R1
  31:F3A2  58F0       MOV [--R15], R0
  31:F3A4  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3A8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3AC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3B0  58F1       MOV [--R15], R1
  31:F3B2  58F0       MOV [--R15], R0
```

### `31:F3B4` in `sub_31_F1F2`

```text
  31:F396  58F0       MOV [--R15], R0
  31:F398  68F1 7862  MOV REG[0xF1], #0x7862
  31:F39C  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3A0  58F1       MOV [--R15], R1
  31:F3A2  58F0       MOV [--R15], R0
  31:F3A4  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3A8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3AC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3B0  58F1       MOV [--R15], R1
  31:F3B2  58F0       MOV [--R15], R0
> 31:F3B4  BD03 4010  SCALL 03:4010
  31:F3B8  50FA       ADD R15, #0xA
  31:F3BA  4804       MOV R0, #0x4
  31:F3BC  58F0       MOV [--R15], R0
  31:F3BE  68F1 7882  MOV REG[0xF1], #0x7882
  31:F3C2  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3C6  58F1       MOV [--R15], R1
  31:F3C8  58F0       MOV [--R15], R0
  31:F3CA  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3CE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3D2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3D6  58F1       MOV [--R15], R1
  31:F3D8  58F0       MOV [--R15], R0
```

### `31:F3DA` in `sub_31_F1F2`

```text
  31:F3BC  58F0       MOV [--R15], R0
  31:F3BE  68F1 7882  MOV REG[0xF1], #0x7882
  31:F3C2  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3C6  58F1       MOV [--R15], R1
  31:F3C8  58F0       MOV [--R15], R0
  31:F3CA  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3CE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3D2  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3D6  58F1       MOV [--R15], R1
  31:F3D8  58F0       MOV [--R15], R0
> 31:F3DA  BD03 4010  SCALL 03:4010
  31:F3DE  50FA       ADD R15, #0xA
  31:F3E0  4804       MOV R0, #0x4
  31:F3E2  58F0       MOV [--R15], R0
  31:F3E4  68F1 7866  MOV REG[0xF1], #0x7866
  31:F3E8  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3EC  58F1       MOV [--R15], R1
  31:F3EE  58F0       MOV [--R15], R0
  31:F3F0  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3F4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3F8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3FC  58F1       MOV [--R15], R1
  31:F3FE  58F0       MOV [--R15], R0
```

### `31:F400` in `sub_31_F1F2`

```text
  31:F3E2  58F0       MOV [--R15], R0
  31:F3E4  68F1 7866  MOV REG[0xF1], #0x7866
  31:F3E8  68F0 0052  MOV REG[0xF0], #0x0052
  31:F3EC  58F1       MOV [--R15], R1
  31:F3EE  58F0       MOV [--R15], R0
  31:F3F0  6810 00A4  MOV REG[0x10], #0x00A4
  31:F3F4  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F3F8  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F3FC  58F1       MOV [--R15], R1
  31:F3FE  58F0       MOV [--R15], R0
> 31:F400  BD03 4010  SCALL 03:4010
  31:F404  50FA       ADD R15, #0xA
  31:F406  4804       MOV R0, #0x4
  31:F408  58F0       MOV [--R15], R0
  31:F40A  68F1 7886  MOV REG[0xF1], #0x7886
  31:F40E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F412  58F1       MOV [--R15], R1
  31:F414  58F0       MOV [--R15], R0
  31:F416  6810 00A4  MOV REG[0x10], #0x00A4
  31:F41A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F41E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F422  58F1       MOV [--R15], R1
  31:F424  58F0       MOV [--R15], R0
```

### `31:F426` in `sub_31_F1F2`

```text
  31:F408  58F0       MOV [--R15], R0
  31:F40A  68F1 7886  MOV REG[0xF1], #0x7886
  31:F40E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F412  58F1       MOV [--R15], R1
  31:F414  58F0       MOV [--R15], R0
  31:F416  6810 00A4  MOV REG[0x10], #0x00A4
  31:F41A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F41E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F422  58F1       MOV [--R15], R1
  31:F424  58F0       MOV [--R15], R0
> 31:F426  BD03 4010  SCALL 03:4010
  31:F42A  50FA       ADD R15, #0xA
  31:F42C  4804       MOV R0, #0x4
  31:F42E  58F0       MOV [--R15], R0
  31:F430  68F1 786A  MOV REG[0xF1], #0x786A
  31:F434  68F0 0052  MOV REG[0xF0], #0x0052
  31:F438  58F1       MOV [--R15], R1
  31:F43A  58F0       MOV [--R15], R0
  31:F43C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F440  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F444  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F448  58F1       MOV [--R15], R1
  31:F44A  58F0       MOV [--R15], R0
```

### `31:F44C` in `sub_31_F1F2`

```text
  31:F42E  58F0       MOV [--R15], R0
  31:F430  68F1 786A  MOV REG[0xF1], #0x786A
  31:F434  68F0 0052  MOV REG[0xF0], #0x0052
  31:F438  58F1       MOV [--R15], R1
  31:F43A  58F0       MOV [--R15], R0
  31:F43C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F440  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F444  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F448  58F1       MOV [--R15], R1
  31:F44A  58F0       MOV [--R15], R0
> 31:F44C  BD03 4010  SCALL 03:4010
  31:F450  50FA       ADD R15, #0xA
  31:F452  4804       MOV R0, #0x4
  31:F454  58F0       MOV [--R15], R0
  31:F456  68F1 788A  MOV REG[0xF1], #0x788A
  31:F45A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F45E  58F1       MOV [--R15], R1
  31:F460  58F0       MOV [--R15], R0
  31:F462  6810 00A4  MOV REG[0x10], #0x00A4
  31:F466  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F46A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F46E  58F1       MOV [--R15], R1
  31:F470  58F0       MOV [--R15], R0
```

### `31:F472` in `sub_31_F1F2`

```text
  31:F454  58F0       MOV [--R15], R0
  31:F456  68F1 788A  MOV REG[0xF1], #0x788A
  31:F45A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F45E  58F1       MOV [--R15], R1
  31:F460  58F0       MOV [--R15], R0
  31:F462  6810 00A4  MOV REG[0x10], #0x00A4
  31:F466  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F46A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F46E  58F1       MOV [--R15], R1
  31:F470  58F0       MOV [--R15], R0
> 31:F472  BD03 4010  SCALL 03:4010
  31:F476  50FA       ADD R15, #0xA
  31:F478  4804       MOV R0, #0x4
  31:F47A  58F0       MOV [--R15], R0
  31:F47C  68F1 786E  MOV REG[0xF1], #0x786E
  31:F480  68F0 0052  MOV REG[0xF0], #0x0052
  31:F484  58F1       MOV [--R15], R1
  31:F486  58F0       MOV [--R15], R0
  31:F488  6810 00A4  MOV REG[0x10], #0x00A4
  31:F48C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F490  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F494  58F1       MOV [--R15], R1
  31:F496  58F0       MOV [--R15], R0
```

### `31:F498` in `sub_31_F1F2`

```text
  31:F47A  58F0       MOV [--R15], R0
  31:F47C  68F1 786E  MOV REG[0xF1], #0x786E
  31:F480  68F0 0052  MOV REG[0xF0], #0x0052
  31:F484  58F1       MOV [--R15], R1
  31:F486  58F0       MOV [--R15], R0
  31:F488  6810 00A4  MOV REG[0x10], #0x00A4
  31:F48C  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F490  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F494  58F1       MOV [--R15], R1
  31:F496  58F0       MOV [--R15], R0
> 31:F498  BD03 4010  SCALL 03:4010
  31:F49C  50FA       ADD R15, #0xA
  31:F49E  4804       MOV R0, #0x4
  31:F4A0  58F0       MOV [--R15], R0
  31:F4A2  68F1 794E  MOV REG[0xF1], #0x794E
  31:F4A6  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4AA  58F1       MOV [--R15], R1
  31:F4AC  58F0       MOV [--R15], R0
  31:F4AE  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4B2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F4B6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F4BA  58F1       MOV [--R15], R1
  31:F4BC  58F0       MOV [--R15], R0
```

### `31:F4BE` in `sub_31_F1F2`

```text
  31:F4A0  58F0       MOV [--R15], R0
  31:F4A2  68F1 794E  MOV REG[0xF1], #0x794E
  31:F4A6  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4AA  58F1       MOV [--R15], R1
  31:F4AC  58F0       MOV [--R15], R0
  31:F4AE  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4B2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F4B6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F4BA  58F1       MOV [--R15], R1
  31:F4BC  58F0       MOV [--R15], R0
> 31:F4BE  BD03 4010  SCALL 03:4010
  31:F4C2  50FA       ADD R15, #0xA
  31:F4C4  4804       MOV R0, #0x4
  31:F4C6  58F0       MOV [--R15], R0
  31:F4C8  68F1 794A  MOV REG[0xF1], #0x794A
  31:F4CC  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4D0  58F1       MOV [--R15], R1
  31:F4D2  58F0       MOV [--R15], R0
  31:F4D4  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4D8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F4DC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F4E0  58F1       MOV [--R15], R1
  31:F4E2  58F0       MOV [--R15], R0
```

### `31:F4E4` in `sub_31_F1F2`

```text
  31:F4C6  58F0       MOV [--R15], R0
  31:F4C8  68F1 794A  MOV REG[0xF1], #0x794A
  31:F4CC  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4D0  58F1       MOV [--R15], R1
  31:F4D2  58F0       MOV [--R15], R0
  31:F4D4  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4D8  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F4DC  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F4E0  58F1       MOV [--R15], R1
  31:F4E2  58F0       MOV [--R15], R0
> 31:F4E4  BD03 4010  SCALL 03:4010
  31:F4E8  50FA       ADD R15, #0xA
  31:F4EA  4804       MOV R0, #0x4
  31:F4EC  58F0       MOV [--R15], R0
  31:F4EE  68F1 7976  MOV REG[0xF1], #0x7976
  31:F4F2  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4F6  58F1       MOV [--R15], R1
  31:F4F8  58F0       MOV [--R15], R0
  31:F4FA  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4FE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F502  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F506  58F1       MOV [--R15], R1
  31:F508  58F0       MOV [--R15], R0
```

### `31:F50A` in `sub_31_F1F2`

```text
  31:F4EC  58F0       MOV [--R15], R0
  31:F4EE  68F1 7976  MOV REG[0xF1], #0x7976
  31:F4F2  68F0 0052  MOV REG[0xF0], #0x0052
  31:F4F6  58F1       MOV [--R15], R1
  31:F4F8  58F0       MOV [--R15], R0
  31:F4FA  6810 00A4  MOV REG[0x10], #0x00A4
  31:F4FE  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F502  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F506  58F1       MOV [--R15], R1
  31:F508  58F0       MOV [--R15], R0
> 31:F50A  BD03 4010  SCALL 03:4010
  31:F50E  50FA       ADD R15, #0xA
  31:F510  4804       MOV R0, #0x4
  31:F512  58F0       MOV [--R15], R0
  31:F514  68F1 7972  MOV REG[0xF1], #0x7972
  31:F518  68F0 0052  MOV REG[0xF0], #0x0052
  31:F51C  58F1       MOV [--R15], R1
  31:F51E  58F0       MOV [--R15], R0
  31:F520  6810 00A4  MOV REG[0x10], #0x00A4
  31:F524  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F528  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F52C  58F1       MOV [--R15], R1
  31:F52E  58F0       MOV [--R15], R0
```

### `31:F530` in `sub_31_F1F2`

```text
  31:F512  58F0       MOV [--R15], R0
  31:F514  68F1 7972  MOV REG[0xF1], #0x7972
  31:F518  68F0 0052  MOV REG[0xF0], #0x0052
  31:F51C  58F1       MOV [--R15], R1
  31:F51E  58F0       MOV [--R15], R0
  31:F520  6810 00A4  MOV REG[0x10], #0x00A4
  31:F524  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F528  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F52C  58F1       MOV [--R15], R1
  31:F52E  58F0       MOV [--R15], R0
> 31:F530  BD03 4010  SCALL 03:4010
  31:F534  50FA       ADD R15, #0xA
  31:F536  4804       MOV R0, #0x4
  31:F538  58F0       MOV [--R15], R0
  31:F53A  68F1 796E  MOV REG[0xF1], #0x796E
  31:F53E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F542  58F1       MOV [--R15], R1
  31:F544  58F0       MOV [--R15], R0
  31:F546  6810 00A4  MOV REG[0x10], #0x00A4
  31:F54A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F54E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F552  58F1       MOV [--R15], R1
  31:F554  58F0       MOV [--R15], R0
```

### `31:F556` in `sub_31_F1F2`

```text
  31:F538  58F0       MOV [--R15], R0
  31:F53A  68F1 796E  MOV REG[0xF1], #0x796E
  31:F53E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F542  58F1       MOV [--R15], R1
  31:F544  58F0       MOV [--R15], R0
  31:F546  6810 00A4  MOV REG[0x10], #0x00A4
  31:F54A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F54E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F552  58F1       MOV [--R15], R1
  31:F554  58F0       MOV [--R15], R0
> 31:F556  BD03 4010  SCALL 03:4010
  31:F55A  50FA       ADD R15, #0xA
  31:F55C  4804       MOV R0, #0x4
  31:F55E  58F0       MOV [--R15], R0
  31:F560  68F1 796A  MOV REG[0xF1], #0x796A
  31:F564  68F0 0052  MOV REG[0xF0], #0x0052
  31:F568  58F1       MOV [--R15], R1
  31:F56A  58F0       MOV [--R15], R0
  31:F56C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F570  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F574  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F578  58F1       MOV [--R15], R1
  31:F57A  58F0       MOV [--R15], R0
```

### `31:F57C` in `sub_31_F1F2`

```text
  31:F55E  58F0       MOV [--R15], R0
  31:F560  68F1 796A  MOV REG[0xF1], #0x796A
  31:F564  68F0 0052  MOV REG[0xF0], #0x0052
  31:F568  58F1       MOV [--R15], R1
  31:F56A  58F0       MOV [--R15], R0
  31:F56C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F570  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F574  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F578  58F1       MOV [--R15], R1
  31:F57A  58F0       MOV [--R15], R0
> 31:F57C  BD03 4010  SCALL 03:4010
  31:F580  50FA       ADD R15, #0xA
  31:F582  4804       MOV R0, #0x4
  31:F584  58F0       MOV [--R15], R0
  31:F586  68F1 7966  MOV REG[0xF1], #0x7966
  31:F58A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F58E  58F1       MOV [--R15], R1
  31:F590  58F0       MOV [--R15], R0
  31:F592  6810 00A4  MOV REG[0x10], #0x00A4
  31:F596  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F59A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F59E  58F1       MOV [--R15], R1
  31:F5A0  58F0       MOV [--R15], R0
```

### `31:F5A2` in `sub_31_F1F2`

```text
  31:F584  58F0       MOV [--R15], R0
  31:F586  68F1 7966  MOV REG[0xF1], #0x7966
  31:F58A  68F0 0052  MOV REG[0xF0], #0x0052
  31:F58E  58F1       MOV [--R15], R1
  31:F590  58F0       MOV [--R15], R0
  31:F592  6810 00A4  MOV REG[0x10], #0x00A4
  31:F596  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F59A  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F59E  58F1       MOV [--R15], R1
  31:F5A0  58F0       MOV [--R15], R0
> 31:F5A2  BD03 4010  SCALL 03:4010
  31:F5A6  50FA       ADD R15, #0xA
  31:F5A8  4804       MOV R0, #0x4
  31:F5AA  58F0       MOV [--R15], R0
  31:F5AC  68F1 7962  MOV REG[0xF1], #0x7962
  31:F5B0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F5B4  58F1       MOV [--R15], R1
  31:F5B6  58F0       MOV [--R15], R0
  31:F5B8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F5BC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F5C0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F5C4  58F1       MOV [--R15], R1
  31:F5C6  58F0       MOV [--R15], R0
```

### `31:F5C8` in `sub_31_F1F2`

```text
  31:F5AA  58F0       MOV [--R15], R0
  31:F5AC  68F1 7962  MOV REG[0xF1], #0x7962
  31:F5B0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F5B4  58F1       MOV [--R15], R1
  31:F5B6  58F0       MOV [--R15], R0
  31:F5B8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F5BC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F5C0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F5C4  58F1       MOV [--R15], R1
  31:F5C6  58F0       MOV [--R15], R0
> 31:F5C8  BD03 4010  SCALL 03:4010
  31:F5CC  50FA       ADD R15, #0xA
  31:F5CE  4804       MOV R0, #0x4
  31:F5D0  58F0       MOV [--R15], R0
  31:F5D2  68F1 795E  MOV REG[0xF1], #0x795E
  31:F5D6  68F0 0052  MOV REG[0xF0], #0x0052
  31:F5DA  58F1       MOV [--R15], R1
  31:F5DC  58F0       MOV [--R15], R0
  31:F5DE  6810 00A4  MOV REG[0x10], #0x00A4
  31:F5E2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F5E6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F5EA  58F1       MOV [--R15], R1
  31:F5EC  58F0       MOV [--R15], R0
```

### `31:F5EE` in `sub_31_F1F2`

```text
  31:F5D0  58F0       MOV [--R15], R0
  31:F5D2  68F1 795E  MOV REG[0xF1], #0x795E
  31:F5D6  68F0 0052  MOV REG[0xF0], #0x0052
  31:F5DA  58F1       MOV [--R15], R1
  31:F5DC  58F0       MOV [--R15], R0
  31:F5DE  6810 00A4  MOV REG[0x10], #0x00A4
  31:F5E2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F5E6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F5EA  58F1       MOV [--R15], R1
  31:F5EC  58F0       MOV [--R15], R0
> 31:F5EE  BD03 4010  SCALL 03:4010
  31:F5F2  50FA       ADD R15, #0xA
  31:F5F4  4804       MOV R0, #0x4
  31:F5F6  58F0       MOV [--R15], R0
  31:F5F8  68F1 795A  MOV REG[0xF1], #0x795A
  31:F5FC  68F0 0052  MOV REG[0xF0], #0x0052
  31:F600  58F1       MOV [--R15], R1
  31:F602  58F0       MOV [--R15], R0
  31:F604  6810 00A4  MOV REG[0x10], #0x00A4
  31:F608  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F60C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F610  58F1       MOV [--R15], R1
  31:F612  58F0       MOV [--R15], R0
```

### `31:F614` in `sub_31_F1F2`

```text
  31:F5F6  58F0       MOV [--R15], R0
  31:F5F8  68F1 795A  MOV REG[0xF1], #0x795A
  31:F5FC  68F0 0052  MOV REG[0xF0], #0x0052
  31:F600  58F1       MOV [--R15], R1
  31:F602  58F0       MOV [--R15], R0
  31:F604  6810 00A4  MOV REG[0x10], #0x00A4
  31:F608  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F60C  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F610  58F1       MOV [--R15], R1
  31:F612  58F0       MOV [--R15], R0
> 31:F614  BD03 4010  SCALL 03:4010
  31:F618  50FA       ADD R15, #0xA
  31:F61A  4804       MOV R0, #0x4
  31:F61C  58F0       MOV [--R15], R0
  31:F61E  68F1 7956  MOV REG[0xF1], #0x7956
  31:F622  68F0 0052  MOV REG[0xF0], #0x0052
  31:F626  58F1       MOV [--R15], R1
  31:F628  58F0       MOV [--R15], R0
  31:F62A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F62E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F632  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F636  58F1       MOV [--R15], R1
  31:F638  58F0       MOV [--R15], R0
```

### `31:F63A` in `sub_31_F1F2`

```text
  31:F61C  58F0       MOV [--R15], R0
  31:F61E  68F1 7956  MOV REG[0xF1], #0x7956
  31:F622  68F0 0052  MOV REG[0xF0], #0x0052
  31:F626  58F1       MOV [--R15], R1
  31:F628  58F0       MOV [--R15], R0
  31:F62A  6810 00A4  MOV REG[0x10], #0x00A4
  31:F62E  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F632  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F636  58F1       MOV [--R15], R1
  31:F638  58F0       MOV [--R15], R0
> 31:F63A  BD03 4010  SCALL 03:4010
  31:F63E  50FA       ADD R15, #0xA
  31:F640  4804       MOV R0, #0x4
  31:F642  58F0       MOV [--R15], R0
  31:F644  68F1 7952  MOV REG[0xF1], #0x7952
  31:F648  68F0 0052  MOV REG[0xF0], #0x0052
  31:F64C  58F1       MOV [--R15], R1
  31:F64E  58F0       MOV [--R15], R0
  31:F650  6810 00A4  MOV REG[0x10], #0x00A4
  31:F654  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F658  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F65C  58F1       MOV [--R15], R1
  31:F65E  58F0       MOV [--R15], R0
```

### `31:F660` in `sub_31_F1F2`

```text
  31:F642  58F0       MOV [--R15], R0
  31:F644  68F1 7952  MOV REG[0xF1], #0x7952
  31:F648  68F0 0052  MOV REG[0xF0], #0x0052
  31:F64C  58F1       MOV [--R15], R1
  31:F64E  58F0       MOV [--R15], R0
  31:F650  6810 00A4  MOV REG[0x10], #0x00A4
  31:F654  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F658  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F65C  58F1       MOV [--R15], R1
  31:F65E  58F0       MOV [--R15], R0
> 31:F660  BD03 4010  SCALL 03:4010
  31:F664  50FA       ADD R15, #0xA
  31:F666  4804       MOV R0, #0x4
  31:F668  58F0       MOV [--R15], R0
  31:F66A  68F1 7946  MOV REG[0xF1], #0x7946
  31:F66E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F672  58F1       MOV [--R15], R1
  31:F674  58F0       MOV [--R15], R0
  31:F676  6810 00A4  MOV REG[0x10], #0x00A4
  31:F67A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F67E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F682  58F1       MOV [--R15], R1
  31:F684  58F0       MOV [--R15], R0
```

### `31:F686` in `sub_31_F1F2`

```text
  31:F668  58F0       MOV [--R15], R0
  31:F66A  68F1 7946  MOV REG[0xF1], #0x7946
  31:F66E  68F0 0052  MOV REG[0xF0], #0x0052
  31:F672  58F1       MOV [--R15], R1
  31:F674  58F0       MOV [--R15], R0
  31:F676  6810 00A4  MOV REG[0x10], #0x00A4
  31:F67A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F67E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F682  58F1       MOV [--R15], R1
  31:F684  58F0       MOV [--R15], R0
> 31:F686  BD03 4010  SCALL 03:4010
  31:F68A  50FA       ADD R15, #0xA
  31:F68C  4804       MOV R0, #0x4
  31:F68E  58F0       MOV [--R15], R0
  31:F690  68F1 7942  MOV REG[0xF1], #0x7942
  31:F694  68F0 0052  MOV REG[0xF0], #0x0052
  31:F698  58F1       MOV [--R15], R1
  31:F69A  58F0       MOV [--R15], R0
  31:F69C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6A0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6A4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6A8  58F1       MOV [--R15], R1
  31:F6AA  58F0       MOV [--R15], R0
```

### `31:F6AC` in `sub_31_F1F2`

```text
  31:F68E  58F0       MOV [--R15], R0
  31:F690  68F1 7942  MOV REG[0xF1], #0x7942
  31:F694  68F0 0052  MOV REG[0xF0], #0x0052
  31:F698  58F1       MOV [--R15], R1
  31:F69A  58F0       MOV [--R15], R0
  31:F69C  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6A0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6A4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6A8  58F1       MOV [--R15], R1
  31:F6AA  58F0       MOV [--R15], R0
> 31:F6AC  BD03 4010  SCALL 03:4010
  31:F6B0  50FA       ADD R15, #0xA
  31:F6B2  4804       MOV R0, #0x4
  31:F6B4  58F0       MOV [--R15], R0
  31:F6B6  68F1 793E  MOV REG[0xF1], #0x793E
  31:F6BA  68F0 0052  MOV REG[0xF0], #0x0052
  31:F6BE  58F1       MOV [--R15], R1
  31:F6C0  58F0       MOV [--R15], R0
  31:F6C2  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6C6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6CA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6CE  58F1       MOV [--R15], R1
  31:F6D0  58F0       MOV [--R15], R0
```

### `31:F6D2` in `sub_31_F1F2`

```text
  31:F6B4  58F0       MOV [--R15], R0
  31:F6B6  68F1 793E  MOV REG[0xF1], #0x793E
  31:F6BA  68F0 0052  MOV REG[0xF0], #0x0052
  31:F6BE  58F1       MOV [--R15], R1
  31:F6C0  58F0       MOV [--R15], R0
  31:F6C2  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6C6  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6CA  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6CE  58F1       MOV [--R15], R1
  31:F6D0  58F0       MOV [--R15], R0
> 31:F6D2  BD03 4010  SCALL 03:4010
  31:F6D6  50FA       ADD R15, #0xA
  31:F6D8  4804       MOV R0, #0x4
  31:F6DA  58F0       MOV [--R15], R0
  31:F6DC  68F1 793A  MOV REG[0xF1], #0x793A
  31:F6E0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F6E4  58F1       MOV [--R15], R1
  31:F6E6  58F0       MOV [--R15], R0
  31:F6E8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6EC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6F0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6F4  58F1       MOV [--R15], R1
  31:F6F6  58F0       MOV [--R15], R0
```

### `31:F6F8` in `sub_31_F1F2`

```text
  31:F6DA  58F0       MOV [--R15], R0
  31:F6DC  68F1 793A  MOV REG[0xF1], #0x793A
  31:F6E0  68F0 0052  MOV REG[0xF0], #0x0052
  31:F6E4  58F1       MOV [--R15], R1
  31:F6E6  58F0       MOV [--R15], R0
  31:F6E8  6810 00A4  MOV REG[0x10], #0x00A4
  31:F6EC  88F0 7992  MOV REG[0xF0], [0x7992]
  31:F6F0  88F1 7994  MOV REG[0xF1], [0x7994]
  31:F6F4  58F1       MOV [--R15], R1
  31:F6F6  58F0       MOV [--R15], R0
> 31:F6F8  BD03 4010  SCALL 03:4010
  31:F6FC  50FA       ADD R15, #0xA
  31:F6FE  386F       MOV R6, [R15++]
  31:F700  381F       MOV R1, [R15++]
  31:F702  380F       MOV R0, [R15++]
  31:F704  2F00       UNLINK
  31:F706  C620       RETS
```

### `32:8B9C` in `sub_32_8A88`

```text
  32:8B80  081B       MOV R1, R11
  32:8B82  70F1 FFF6  ADD REG[0xF1], #0xFFF6
  32:8B86  4800       MOV R0, #0x0
  32:8B88  58F1       MOV [--R15], R1
  32:8B8A  58F0       MOV [--R15], R0
  32:8B8C  6810 00A4  MOV REG[0x10], #0x00A4
  32:8B90  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8B94  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8B98  58F1       MOV [--R15], R1
  32:8B9A  58F0       MOV [--R15], R0
> 32:8B9C  BD03 4010  SCALL 03:4010
  32:8BA0  50FA       ADD R15, #0xA
  32:8BA2  4800       MOV R0, #0x0
  32:8BA4  58F0       MOV [--R15], R0
  32:8BA6  780B FFF6  MOV R0, [R11+0xFFF6]
  32:8BAA  781B FFF8  MOV R1, [R11+0xFFF8]
  32:8BAE  6810 00A4  MOV REG[0x10], #0x00A4
  32:8BB2  90F1 79B8  ADD REG[0xF1], [0x79B8]
  32:8BB6  91F0 79B6  ADDC REG[0xF0], [0x79B6]
  32:8BBA  58F1       MOV [--R15], R1
  32:8BBC  58F0       MOV [--R15], R0
  32:8BBE  6810 00A4  MOV REG[0x10], #0x00A4
  32:8BC2  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `32:8C1C` in `sub_32_8A88`

```text
  32:8C00  68F2 0052  MOV REG[0xF2], #0x0052
  32:8C04  1013       ADD R1, R3
  32:8C06  1102       ADDC R0, R2
  32:8C08  58F1       MOV [--R15], R1
  32:8C0A  58F0       MOV [--R15], R0
  32:8C0C  6810 00A4  MOV REG[0x10], #0x00A4
  32:8C10  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8C14  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8C18  58F1       MOV [--R15], R1
  32:8C1A  58F0       MOV [--R15], R0
> 32:8C1C  BD03 4010  SCALL 03:4010
  32:8C20  50FA       ADD R15, #0xA
  32:8C22  4802       MOV R0, #0x2
  32:8C24  58F0       MOV [--R15], R0
  32:8C26  68F1 0094  MOV REG[0xF1], #0x0094
  32:8C2A  4800       MOV R0, #0x0
  32:8C2C  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8C30  5630       CMP R3, #0x0
  32:8C32  DE03       RJMP SGE, 32:8C3A ; rel +3
  32:8C34  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8C38  D001       RJMP ALWAYS, 32:8C3C ; rel +1
  32:8C3A  4820       MOV R2, #0x0
  32:8C3C  58F3       MOV [--R15], R3
```

### `32:8C6A` in `sub_32_8A88`

```text
  32:8C4E  68F2 0052  MOV REG[0xF2], #0x0052
  32:8C52  1013       ADD R1, R3
  32:8C54  1102       ADDC R0, R2
  32:8C56  58F1       MOV [--R15], R1
  32:8C58  58F0       MOV [--R15], R0
  32:8C5A  6810 00A4  MOV REG[0x10], #0x00A4
  32:8C5E  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8C62  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8C66  58F1       MOV [--R15], R1
  32:8C68  58F0       MOV [--R15], R0
> 32:8C6A  BD03 4010  SCALL 03:4010
  32:8C6E  50FA       ADD R15, #0xA
  32:8C70  4801       MOV R0, #0x1
  32:8C72  58F0       MOV [--R15], R0
  32:8C74  081B       MOV R1, R11
  32:8C76  70F1 FFF5  ADD REG[0xF1], #0xFFF5
  32:8C7A  4800       MOV R0, #0x0
  32:8C7C  58F1       MOV [--R15], R1
  32:8C7E  58F0       MOV [--R15], R0
  32:8C80  6810 00A4  MOV REG[0x10], #0x00A4
  32:8C84  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8C88  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8C8C  58F1       MOV [--R15], R1
```

### `32:8C90` in `sub_32_8A88`

```text
  32:8C74  081B       MOV R1, R11
  32:8C76  70F1 FFF5  ADD REG[0xF1], #0xFFF5
  32:8C7A  4800       MOV R0, #0x0
  32:8C7C  58F1       MOV [--R15], R1
  32:8C7E  58F0       MOV [--R15], R0
  32:8C80  6810 00A4  MOV REG[0x10], #0x00A4
  32:8C84  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8C88  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8C8C  58F1       MOV [--R15], R1
  32:8C8E  58F0       MOV [--R15], R0
> 32:8C90  BD03 4010  SCALL 03:4010
  32:8C94  50FA       ADD R15, #0xA
  32:8C96  68F1 0094  MOV REG[0xF1], #0x0094
  32:8C9A  4800       MOV R0, #0x0
  32:8C9C  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8CA0  5630       CMP R3, #0x0
  32:8CA2  DE03       RJMP SGE, 32:8CAA ; rel +3
  32:8CA4  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8CA8  D001       RJMP ALWAYS, 32:8CAC ; rel +1
  32:8CAA  4820       MOV R2, #0x0
  32:8CAC  58F3       MOV [--R15], R3
  32:8CAE  58F2       MOV [--R15], R2
  32:8CB0  58F1       MOV [--R15], R1
```

### `32:8D2A` in `sub_32_8CD4`

```text
  32:8D0E  68F2 0052  MOV REG[0xF2], #0x0052
  32:8D12  1013       ADD R1, R3
  32:8D14  1102       ADDC R0, R2
  32:8D16  58F1       MOV [--R15], R1
  32:8D18  58F0       MOV [--R15], R0
  32:8D1A  6810 00A4  MOV REG[0x10], #0x00A4
  32:8D1E  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8D22  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8D26  58F1       MOV [--R15], R1
  32:8D28  58F0       MOV [--R15], R0
> 32:8D2A  BD03 4010  SCALL 03:4010
  32:8D2E  50FA       ADD R15, #0xA
  32:8D30  68F1 0094  MOV REG[0xF1], #0x0094
  32:8D34  4800       MOV R0, #0x0
```

### `32:8DD0` in `sub_32_8D36`

```text
  32:8DB4  68F2 0052  MOV REG[0xF2], #0x0052
  32:8DB8  1013       ADD R1, R3
  32:8DBA  1102       ADDC R0, R2
  32:8DBC  58F1       MOV [--R15], R1
  32:8DBE  58F0       MOV [--R15], R0
  32:8DC0  6810 00A4  MOV REG[0x10], #0x00A4
  32:8DC4  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8DC8  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8DCC  58F1       MOV [--R15], R1
  32:8DCE  58F0       MOV [--R15], R0
> 32:8DD0  BD03 4010  SCALL 03:4010
  32:8DD4  50FA       ADD R15, #0xA
  32:8DD6  68F1 0094  MOV REG[0xF1], #0x0094
  32:8DDA  4800       MOV R0, #0x0
  32:8DDC  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8DE0  5630       CMP R3, #0x0
  32:8DE2  DE03       RJMP SGE, 32:8DEA ; rel +3
  32:8DE4  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8DE8  D001       RJMP ALWAYS, 32:8DEC ; rel +1
  32:8DEA  4820       MOV R2, #0x0
  32:8DEC  58F3       MOV [--R15], R3
  32:8DEE  58F2       MOV [--R15], R2
  32:8DF0  58F1       MOV [--R15], R1
```

### `32:8E76` in `sub_32_8E5C`

```text
  32:8E5C  0052       ADDB RB5, RB2
  32:8E5E  1013       ADD R1, R3
  32:8E60  1102       ADDC R0, R2
  32:8E62  58F1       MOV [--R15], R1
  32:8E64  58F0       MOV [--R15], R0
  32:8E66  6810 00A4  MOV REG[0x10], #0x00A4
  32:8E6A  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8E6E  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8E72  58F1       MOV [--R15], R1
  32:8E74  58F0       MOV [--R15], R0
> 32:8E76  BD03 4010  SCALL 03:4010
  32:8E7A  50FA       ADD R15, #0xA
  32:8E7C  68F1 0094  MOV REG[0xF1], #0x0094
  32:8E80  4800       MOV R0, #0x0
  32:8E82  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8E86  5630       CMP R3, #0x0
  32:8E88  DE03       RJMP SGE, 32:8E90 ; rel +3
  32:8E8A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8E8E  D001       RJMP ALWAYS, 32:8E92 ; rel +1
  32:8E90  4820       MOV R2, #0x0
  32:8E92  58F3       MOV [--R15], R3
  32:8E94  58F2       MOV [--R15], R2
  32:8E96  58F1       MOV [--R15], R1
```

### `32:8F1C` in `sub_32_8E5C`

```text
  32:8F00  68F2 0052  MOV REG[0xF2], #0x0052
  32:8F04  1013       ADD R1, R3
  32:8F06  1102       ADDC R0, R2
  32:8F08  58F1       MOV [--R15], R1
  32:8F0A  58F0       MOV [--R15], R0
  32:8F0C  6810 00A4  MOV REG[0x10], #0x00A4
  32:8F10  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8F14  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8F18  58F1       MOV [--R15], R1
  32:8F1A  58F0       MOV [--R15], R0
> 32:8F1C  BD03 4010  SCALL 03:4010
  32:8F20  50FA       ADD R15, #0xA
  32:8F22  68F1 0094  MOV REG[0xF1], #0x0094
  32:8F26  4800       MOV R0, #0x0
  32:8F28  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8F2C  5630       CMP R3, #0x0
  32:8F2E  DE03       RJMP SGE, 32:8F36 ; rel +3
  32:8F30  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8F34  D001       RJMP ALWAYS, 32:8F38 ; rel +1
  32:8F36  4820       MOV R2, #0x0
  32:8F38  58F3       MOV [--R15], R3
  32:8F3A  58F2       MOV [--R15], R2
  32:8F3C  58F1       MOV [--R15], R1
```

### `32:8FC2` in `sub_32_8E5C`

```text
  32:8FA6  68F2 0052  MOV REG[0xF2], #0x0052
  32:8FAA  1013       ADD R1, R3
  32:8FAC  1102       ADDC R0, R2
  32:8FAE  58F1       MOV [--R15], R1
  32:8FB0  58F0       MOV [--R15], R0
  32:8FB2  6810 00A4  MOV REG[0x10], #0x00A4
  32:8FB6  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8FBA  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8FBE  58F1       MOV [--R15], R1
  32:8FC0  58F0       MOV [--R15], R0
> 32:8FC2  BD03 4010  SCALL 03:4010
  32:8FC6  50FA       ADD R15, #0xA
  32:8FC8  4802       MOV R0, #0x2
  32:8FCA  58F0       MOV [--R15], R0
  32:8FCC  68F1 0094  MOV REG[0xF1], #0x0094
  32:8FD0  4800       MOV R0, #0x0
  32:8FD2  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8FD6  5630       CMP R3, #0x0
  32:8FD8  DE03       RJMP SGE, 32:8FE0 ; rel +3
  32:8FDA  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8FDE  D001       RJMP ALWAYS, 32:8FE2 ; rel +1
  32:8FE0  4820       MOV R2, #0x0
  32:8FE2  58F3       MOV [--R15], R3
```

### `32:9010` in `sub_32_8E5C`

```text
  32:8FF4  68F2 0052  MOV REG[0xF2], #0x0052
  32:8FF8  1013       ADD R1, R3
  32:8FFA  1102       ADDC R0, R2
  32:8FFC  58F1       MOV [--R15], R1
  32:8FFE  58F0       MOV [--R15], R0
  32:9000  6810 00A4  MOV REG[0x10], #0x00A4
  32:9004  88F0 7992  MOV REG[0xF0], [0x7992]
  32:9008  88F1 7994  MOV REG[0xF1], [0x7994]
  32:900C  58F1       MOV [--R15], R1
  32:900E  58F0       MOV [--R15], R0
> 32:9010  BD03 4010  SCALL 03:4010
  32:9014  50FA       ADD R15, #0xA
  32:9016  4802       MOV R0, #0x2
  32:9018  58F0       MOV [--R15], R0
  32:901A  68F1 0094  MOV REG[0xF1], #0x0094
  32:901E  4800       MOV R0, #0x0
  32:9020  783B FFFC  MOV R3, [R11+0xFFFC]
  32:9024  5630       CMP R3, #0x0
  32:9026  DE03       RJMP SGE, 32:902E ; rel +3
  32:9028  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:902C  D001       RJMP ALWAYS, 32:9030 ; rel +1
  32:902E  4820       MOV R2, #0x0
  32:9030  58F3       MOV [--R15], R3
```

### `32:905E` in `sub_32_8E5C`

```text
  32:9042  68F2 0052  MOV REG[0xF2], #0x0052
  32:9046  1013       ADD R1, R3
  32:9048  1102       ADDC R0, R2
  32:904A  58F1       MOV [--R15], R1
  32:904C  58F0       MOV [--R15], R0
  32:904E  6810 00A4  MOV REG[0x10], #0x00A4
  32:9052  88F0 7992  MOV REG[0xF0], [0x7992]
  32:9056  88F1 7994  MOV REG[0xF1], [0x7994]
  32:905A  58F1       MOV [--R15], R1
  32:905C  58F0       MOV [--R15], R0
> 32:905E  BD03 4010  SCALL 03:4010
  32:9062  50FA       ADD R15, #0xA
  32:9064  4800       MOV R0, #0x0
  32:9066  6A0B FFFE  MOV [R11+0xFFFE], R0
  32:906A  4801       MOV R0, #0x1
  32:906C  58F0       MOV [--R15], R0
  32:906E  081B       MOV R1, R11
  32:9070  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  32:9074  4800       MOV R0, #0x0
  32:9076  58F1       MOV [--R15], R1
  32:9078  58F0       MOV [--R15], R0
  32:907A  6810 00A4  MOV REG[0x10], #0x00A4
  32:907E  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `32:908A` in `sub_32_8E5C`

```text
  32:906E  081B       MOV R1, R11
  32:9070  70F1 FFFB  ADD REG[0xF1], #0xFFFB
  32:9074  4800       MOV R0, #0x0
  32:9076  58F1       MOV [--R15], R1
  32:9078  58F0       MOV [--R15], R0
  32:907A  6810 00A4  MOV REG[0x10], #0x00A4
  32:907E  88F0 7992  MOV REG[0xF0], [0x7992]
  32:9082  88F1 7994  MOV REG[0xF1], [0x7994]
  32:9086  58F1       MOV [--R15], R1
  32:9088  58F0       MOV [--R15], R0
> 32:908A  BD03 4010  SCALL 03:4010
  32:908E  50FA       ADD R15, #0xA
  32:9090  780B FFFE  MOV R0, [R11+0xFFFE]
  32:9094  0810       MOV R1, R0
  32:9096  5610       CMP R1, #0x0
  32:9098  DE03       RJMP SGE, 32:90A0 ; rel +3
  32:909A  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  32:909E  D001       RJMP ALWAYS, 32:90A2 ; rel +1
  32:90A0  4800       MOV R0, #0x0
  32:90A2  6A0B FFF0  MOV [R11+0xFFF0], R0
  32:90A6  6A1B FFF2  MOV [R11+0xFFF2], R1
  32:90AA  68F3 0094  MOV REG[0xF3], #0x0094
  32:90AE  4820       MOV R2, #0x0
```

### `32:915C` in `sub_32_8E5C`

```text
  32:9140  68F2 0052  MOV REG[0xF2], #0x0052
  32:9144  1013       ADD R1, R3
  32:9146  1102       ADDC R0, R2
  32:9148  58F1       MOV [--R15], R1
  32:914A  58F0       MOV [--R15], R0
  32:914C  6810 00A4  MOV REG[0x10], #0x00A4
  32:9150  88F0 7992  MOV REG[0xF0], [0x7992]
  32:9154  88F1 7994  MOV REG[0xF1], [0x7994]
  32:9158  58F1       MOV [--R15], R1
  32:915A  58F0       MOV [--R15], R0
> 32:915C  BD03 4010  SCALL 03:4010
  32:9160  50FA       ADD R15, #0xA
  32:9162  4801       MOV R0, #0x1
  32:9164  58F0       MOV [--R15], R0
  32:9166  68F1 0094  MOV REG[0xF1], #0x0094
  32:916A  4800       MOV R0, #0x0
  32:916C  783B FFFC  MOV R3, [R11+0xFFFC]
  32:9170  5630       CMP R3, #0x0
  32:9172  DE03       RJMP SGE, 32:917A ; rel +3
  32:9174  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:9178  D001       RJMP ALWAYS, 32:917C ; rel +1
  32:917A  4820       MOV R2, #0x0
  32:917C  58F3       MOV [--R15], R3
```

### `32:91AA` in `sub_32_8E5C`

```text
  32:918E  68F2 0052  MOV REG[0xF2], #0x0052
  32:9192  1013       ADD R1, R3
  32:9194  1102       ADDC R0, R2
  32:9196  58F1       MOV [--R15], R1
  32:9198  58F0       MOV [--R15], R0
  32:919A  6810 00A4  MOV REG[0x10], #0x00A4
  32:919E  88F0 7992  MOV REG[0xF0], [0x7992]
  32:91A2  88F1 7994  MOV REG[0xF1], [0x7994]
  32:91A6  58F1       MOV [--R15], R1
  32:91A8  58F0       MOV [--R15], R0
> 32:91AA  BD03 4010  SCALL 03:4010
  32:91AE  50FA       ADD R15, #0xA
  32:91B0  4802       MOV R0, #0x2
  32:91B2  58F0       MOV [--R15], R0
  32:91B4  68F1 0094  MOV REG[0xF1], #0x0094
  32:91B8  4800       MOV R0, #0x0
  32:91BA  783B FFFC  MOV R3, [R11+0xFFFC]
  32:91BE  5630       CMP R3, #0x0
  32:91C0  DE03       RJMP SGE, 32:91C8 ; rel +3
```

### `32:91F8` in `sub_32_91C2`

```text
  32:91DC  68F2 0052  MOV REG[0xF2], #0x0052
  32:91E0  1013       ADD R1, R3
  32:91E2  1102       ADDC R0, R2
  32:91E4  58F1       MOV [--R15], R1
  32:91E6  58F0       MOV [--R15], R0
  32:91E8  6810 00A4  MOV REG[0x10], #0x00A4
  32:91EC  88F0 7992  MOV REG[0xF0], [0x7992]
  32:91F0  88F1 7994  MOV REG[0xF1], [0x7994]
  32:91F4  58F1       MOV [--R15], R1
  32:91F6  58F0       MOV [--R15], R0
> 32:91F8  BD03 4010  SCALL 03:4010
  32:91FC  50FA       ADD R15, #0xA
  32:91FE  4802       MOV R0, #0x2
  32:9200  58F0       MOV [--R15], R0
  32:9202  68F1 0094  MOV REG[0xF1], #0x0094
  32:9206  4800       MOV R0, #0x0
  32:9208  783B FFFC  MOV R3, [R11+0xFFFC]
  32:920C  5630       CMP R3, #0x0
  32:920E  DE03       RJMP SGE, 32:9216 ; rel +3
  32:9210  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:9214  D001       RJMP ALWAYS, 32:9218 ; rel +1
  32:9216  4820       MOV R2, #0x0
  32:9218  58F3       MOV [--R15], R3
```

### `32:9246` in `sub_32_91C2`

```text
  32:922A  68F2 0052  MOV REG[0xF2], #0x0052
  32:922E  1013       ADD R1, R3
  32:9230  1102       ADDC R0, R2
  32:9232  58F1       MOV [--R15], R1
  32:9234  58F0       MOV [--R15], R0
  32:9236  6810 00A4  MOV REG[0x10], #0x00A4
  32:923A  88F0 7992  MOV REG[0xF0], [0x7992]
  32:923E  88F1 7994  MOV REG[0xF1], [0x7994]
  32:9242  58F1       MOV [--R15], R1
  32:9244  58F0       MOV [--R15], R0
> 32:9246  BD03 4010  SCALL 03:4010
  32:924A  50FA       ADD R15, #0xA
  32:924C  4801       MOV R0, #0x1
  32:924E  58F0       MOV [--R15], R0
  32:9250  68F1 0094  MOV REG[0xF1], #0x0094
  32:9254  4800       MOV R0, #0x0
  32:9256  783B FFFC  MOV R3, [R11+0xFFFC]
  32:925A  5630       CMP R3, #0x0
  32:925C  DE03       RJMP SGE, 32:9264 ; rel +3
  32:925E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:9262  D001       RJMP ALWAYS, 32:9266 ; rel +1
  32:9264  4820       MOV R2, #0x0
  32:9266  58F3       MOV [--R15], R3
```

### `32:9294` in `sub_32_91C2`

```text
  32:9278  68F2 0052  MOV REG[0xF2], #0x0052
  32:927C  1013       ADD R1, R3
  32:927E  1102       ADDC R0, R2
  32:9280  58F1       MOV [--R15], R1
  32:9282  58F0       MOV [--R15], R0
  32:9284  6810 00A4  MOV REG[0x10], #0x00A4
  32:9288  88F0 7992  MOV REG[0xF0], [0x7992]
  32:928C  88F1 7994  MOV REG[0xF1], [0x7994]
  32:9290  58F1       MOV [--R15], R1
  32:9292  58F0       MOV [--R15], R0
> 32:9294  BD03 4010  SCALL 03:4010
  32:9298  50FA       ADD R15, #0xA
  32:929A  4800       MOV R0, #0x0
  32:929C  6A0B FFFE  MOV [R11+0xFFFE], R0
  32:92A0  780B FFFE  MOV R0, [R11+0xFFFE]
  32:92A4  0810       MOV R1, R0
  32:92A6  5610       CMP R1, #0x0
  32:92A8  DE03       RJMP SGE, 32:92B0 ; rel +3
  32:92AA  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  32:92AE  D001       RJMP ALWAYS, 32:92B2 ; rel +1
  32:92B0  4800       MOV R0, #0x0
  32:92B2  4C11       SL R1, #0x1
  32:92B4  5C01       SLOSB R0, #0x1
```

## `03:401C`

Call sites: `2E:7316`, `2E:7372`, `31:C986`, `31:C9DE`, `32:8B76`, `32:8BCE`

### `2E:7316` in `sub_2E_63A8`

```text
  2E:72FC  4820       MOV R2, #0x0
  2E:72FE  1013       ADD R1, R3
  2E:7300  1102       ADDC R0, R2
  2E:7302  58F1       MOV [--R15], R1
  2E:7304  58F0       MOV [--R15], R0
  2E:7306  6810 00A4  MOV REG[0x10], #0x00A4
  2E:730A  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:730E  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7312  58F1       MOV [--R15], R1
  2E:7314  58F0       MOV [--R15], R0
> 2E:7316  BD03 401C  SCALL 03:401C
  2E:731A  50FA       ADD R15, #0xA
  2E:731C  4804       MOV R0, #0x4
  2E:731E  58F0       MOV [--R15], R0
  2E:7320  081B       MOV R1, R11
  2E:7322  70F1 FFFA  ADD REG[0xF1], #0xFFFA
  2E:7326  4800       MOV R0, #0x0
  2E:7328  58F1       MOV [--R15], R1
  2E:732A  58F0       MOV [--R15], R0
  2E:732C  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7330  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:7334  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:7338  58F1       MOV [--R15], R1
```

### `2E:7372` in `sub_2E_63A8`

```text
  2E:7356  783B FFFC  MOV R3, [R11+0xFFFC]
  2E:735A  1013       ADD R1, R3
  2E:735C  1102       ADDC R0, R2
  2E:735E  58F1       MOV [--R15], R1
  2E:7360  58F0       MOV [--R15], R0
  2E:7362  6810 00A4  MOV REG[0x10], #0x00A4
  2E:7366  88F0 7992  MOV REG[0xF0], [0x7992]
  2E:736A  88F1 7994  MOV REG[0xF1], [0x7994]
  2E:736E  58F1       MOV [--R15], R1
  2E:7370  58F0       MOV [--R15], R0
> 2E:7372  BD03 401C  SCALL 03:401C
  2E:7376  50FA       ADD R15, #0xA
  2E:7378  480C       MOV R0, #0xC
  2E:737A  58F0       MOV [--R15], R0
  2E:737C  68F1 0094  MOV REG[0xF1], #0x0094
  2E:7380  4800       MOV R0, #0x0
  2E:7382  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2E:7386  1937       MOVZE R3, RB7
  2E:7388  5630       CMP R3, #0x0
  2E:738A  DE03       RJMP SGE, 2E:7392 ; rel +3
  2E:738C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2E:7390  D001       RJMP ALWAYS, 2E:7394 ; rel +1
  2E:7392  4820       MOV R2, #0x0
```

### `31:C986` in `sub_31_C7A4`

```text
  31:C968  58F0       MOV [--R15], R0
  31:C96A  780B FFF6  MOV R0, [R11+0xFFF6]
  31:C96E  781B FFF8  MOV R1, [R11+0xFFF8]
  31:C972  58F1       MOV [--R15], R1
  31:C974  58F0       MOV [--R15], R0
  31:C976  6810 00A4  MOV REG[0x10], #0x00A4
  31:C97A  88F0 7992  MOV REG[0xF0], [0x7992]
  31:C97E  88F1 7994  MOV REG[0xF1], [0x7994]
  31:C982  58F1       MOV [--R15], R1
  31:C984  58F0       MOV [--R15], R0
> 31:C986  BD03 401C  SCALL 03:401C
  31:C98A  50FA       ADD R15, #0xA
  31:C98C  4804       MOV R0, #0x4
  31:C98E  58F0       MOV [--R15], R0
  31:C990  081B       MOV R1, R11
  31:C992  70F1 FFF6  ADD REG[0xF1], #0xFFF6
  31:C996  4800       MOV R0, #0x0
  31:C998  58F1       MOV [--R15], R1
  31:C99A  58F0       MOV [--R15], R0
  31:C99C  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9A0  88F0 7992  MOV REG[0xF0], [0x7992]
  31:C9A4  88F1 7994  MOV REG[0xF1], [0x7994]
  31:C9A8  58F1       MOV [--R15], R1
```

### `31:C9DE` in `sub_31_C7A4`

```text
  31:C9BE  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9C2  90F1 79B8  ADD REG[0xF1], [0x79B8]
  31:C9C6  91F0 79B6  ADDC REG[0xF0], [0x79B6]
  31:C9CA  58F1       MOV [--R15], R1
  31:C9CC  58F0       MOV [--R15], R0
  31:C9CE  6810 00A4  MOV REG[0x10], #0x00A4
  31:C9D2  88F0 7992  MOV REG[0xF0], [0x7992]
  31:C9D6  88F1 7994  MOV REG[0xF1], [0x7994]
  31:C9DA  58F1       MOV [--R15], R1
  31:C9DC  58F0       MOV [--R15], R0
> 31:C9DE  BD03 401C  SCALL 03:401C
  31:C9E2  50FA       ADD R15, #0xA
  31:C9E4  480C       MOV R0, #0xC
  31:C9E6  58F0       MOV [--R15], R0
  31:C9E8  68F1 0094  MOV REG[0xF1], #0x0094
  31:C9EC  4800       MOV R0, #0x0
  31:C9EE  783B FFFC  MOV R3, [R11+0xFFFC]
  31:C9F2  5630       CMP R3, #0x0
  31:C9F4  DE03       RJMP SGE, 31:C9FC ; rel +3
  31:C9F6  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:C9FA  D001       RJMP ALWAYS, 31:C9FE ; rel +1
  31:C9FC  4820       MOV R2, #0x0
  31:C9FE  58F3       MOV [--R15], R3
```

### `32:8B76` in `sub_32_8A88`

```text
  32:8B58  58F0       MOV [--R15], R0
  32:8B5A  780B FFF6  MOV R0, [R11+0xFFF6]
  32:8B5E  781B FFF8  MOV R1, [R11+0xFFF8]
  32:8B62  58F1       MOV [--R15], R1
  32:8B64  58F0       MOV [--R15], R0
  32:8B66  6810 00A4  MOV REG[0x10], #0x00A4
  32:8B6A  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8B6E  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8B72  58F1       MOV [--R15], R1
  32:8B74  58F0       MOV [--R15], R0
> 32:8B76  BD03 401C  SCALL 03:401C
  32:8B7A  50FA       ADD R15, #0xA
  32:8B7C  4804       MOV R0, #0x4
  32:8B7E  58F0       MOV [--R15], R0
  32:8B80  081B       MOV R1, R11
  32:8B82  70F1 FFF6  ADD REG[0xF1], #0xFFF6
  32:8B86  4800       MOV R0, #0x0
  32:8B88  58F1       MOV [--R15], R1
  32:8B8A  58F0       MOV [--R15], R0
  32:8B8C  6810 00A4  MOV REG[0x10], #0x00A4
  32:8B90  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8B94  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8B98  58F1       MOV [--R15], R1
```

### `32:8BCE` in `sub_32_8A88`

```text
  32:8BAE  6810 00A4  MOV REG[0x10], #0x00A4
  32:8BB2  90F1 79B8  ADD REG[0xF1], [0x79B8]
  32:8BB6  91F0 79B6  ADDC REG[0xF0], [0x79B6]
  32:8BBA  58F1       MOV [--R15], R1
  32:8BBC  58F0       MOV [--R15], R0
  32:8BBE  6810 00A4  MOV REG[0x10], #0x00A4
  32:8BC2  88F0 7992  MOV REG[0xF0], [0x7992]
  32:8BC6  88F1 7994  MOV REG[0xF1], [0x7994]
  32:8BCA  58F1       MOV [--R15], R1
  32:8BCC  58F0       MOV [--R15], R0
> 32:8BCE  BD03 401C  SCALL 03:401C
  32:8BD2  50FA       ADD R15, #0xA
  32:8BD4  480C       MOV R0, #0xC
  32:8BD6  58F0       MOV [--R15], R0
  32:8BD8  68F1 0094  MOV REG[0xF1], #0x0094
  32:8BDC  4800       MOV R0, #0x0
  32:8BDE  783B FFFC  MOV R3, [R11+0xFFFC]
  32:8BE2  5630       CMP R3, #0x0
  32:8BE4  DE03       RJMP SGE, 32:8BEC ; rel +3
  32:8BE6  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:8BEA  D001       RJMP ALWAYS, 32:8BEE ; rel +1
  32:8BEC  4820       MOV R2, #0x0
  32:8BEE  58F3       MOV [--R15], R3
```

## `03:4068`

Call sites: `2F:C230`

### `2F:C230` in `sub_2F_C216`

```text
  2F:C218  1053       ADD R5, R3
  2F:C21A  1142       ADDC R4, R2
  2F:C21C  58F5       MOV [--R15], R5
  2F:C21E  58F4       MOV [--R15], R4
  2F:C220  68F5 69C6  MOV REG[0xF5], #0x69C6
  2F:C224  68F4 0052  MOV REG[0xF4], #0x0052
  2F:C228  1015       ADD R1, R5
  2F:C22A  1104       ADDC R0, R4
  2F:C22C  58F1       MOV [--R15], R1
  2F:C22E  58F0       MOV [--R15], R0
> 2F:C230  BD03 4068  SCALL 03:4068
  2F:C234  50FA       ADD R15, #0xA
  2F:C236  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:C23A  5001       ADD R0, #0x1
  2F:C23C  6A0B FFFE  MOV [R11+0xFFFE], R0
  2F:C240  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:C244  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C248  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  2F:C24C  1601       CMP R0, R1
  2F:C24E  AC09 C1E2  AJMP SL, 2F:C1E2
  2F:C252  AC00 C914  AJMP ALWAYS, 2F:C914
  2F:C256  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C25A  99F1 7A9A  MOVZE REG[0xF1], [0x7A9A]
```

## `03:407C`

Call sites: `2C:C7E4`, `2C:C806`, `30:18AC`, `30:18D8`, `30:1946`, `30:1976`, `30:1BDC`, `30:1C08`, `30:1C76`, `30:1CDA`, `30:1D06`, `30:1D74`, `30:1DD8`, `30:1E04`, `30:1E72`, `30:1ED6`, `30:1F02`, `30:1F70`, `30:1FD4`, `30:20F2`, `30:211A`, `30:2188`, `30:21EC`, `30:2218`, `30:2286`, `30:22EA`, `30:2316`, `30:2384`, `30:23E8`, `30:2414`, `30:2482`, `30:24E6`, `30:251C`

### `2C:C7E4` in `sub_2C_C07E`

```text
  2C:C7C6  5600       CMP R0, #0x0
  2C:C7C8  AC02 C7EE  AJMP NZ/NE, 2C:C7EE
  2C:C7CC  780B FFDE  MOV R0, [R11+0xFFDE]
  2C:C7D0  781B FFE0  MOV R1, [R11+0xFFE0]
  2C:C7D4  58F1       MOV [--R15], R1
  2C:C7D6  58F0       MOV [--R15], R0
  2C:C7D8  68F1 77BC  MOV REG[0xF1], #0x77BC
  2C:C7DC  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C7E0  58F1       MOV [--R15], R1
  2C:C7E2  58F0       MOV [--R15], R0
> 2C:C7E4  BD03 407C  SCALL 03:407C
  2C:C7E8  50F8       ADD R15, #0x8
  2C:C7EA  AC00 C80C  AJMP ALWAYS, 2C:C80C
  2C:C7EE  780B FFDA  MOV R0, [R11+0xFFDA]
  2C:C7F2  781B FFDC  MOV R1, [R11+0xFFDC]
  2C:C7F6  58F1       MOV [--R15], R1
  2C:C7F8  58F0       MOV [--R15], R0
  2C:C7FA  68F1 77BC  MOV REG[0xF1], #0x77BC
  2C:C7FE  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C802  58F1       MOV [--R15], R1
  2C:C804  58F0       MOV [--R15], R0
  2C:C806  BD03 407C  SCALL 03:407C
  2C:C80A  50F8       ADD R15, #0x8
```

### `2C:C806` in `sub_2C_C07E`

```text
  2C:C7E8  50F8       ADD R15, #0x8
  2C:C7EA  AC00 C80C  AJMP ALWAYS, 2C:C80C
  2C:C7EE  780B FFDA  MOV R0, [R11+0xFFDA]
  2C:C7F2  781B FFDC  MOV R1, [R11+0xFFDC]
  2C:C7F6  58F1       MOV [--R15], R1
  2C:C7F8  58F0       MOV [--R15], R0
  2C:C7FA  68F1 77BC  MOV REG[0xF1], #0x77BC
  2C:C7FE  68F0 0052  MOV REG[0xF0], #0x0052
  2C:C802  58F1       MOV [--R15], R1
  2C:C804  58F0       MOV [--R15], R0
> 2C:C806  BD03 407C  SCALL 03:407C
  2C:C80A  50F8       ADD R15, #0x8
  2C:C80C  68F0 0054  MOV REG[0xF0], #0x0054
  2C:C810  58F0       MOV [--R15], R0
  2C:C812  68F1 00F0  MOV REG[0xF1], #0x00F0
  2C:C816  58F1       MOV [--R15], R1
  2C:C818  58F0       MOV [--R15], R0
  2C:C81A  4800       MOV R0, #0x0
  2C:C81C  58F0       MOV [--R15], R0
  2C:C81E  BD03 420C  SCALL 03:420C
  2C:C822  50F8       ADD R15, #0x8
  2C:C824  68F0 0028  MOV REG[0xF0], #0x0028
  2C:C828  58F0       MOV [--R15], R0
```

### `30:18AC` in `sub_30_15FC`

```text
  30:1890  AC02 18B6  AJMP NZ/NE, 30:18B6
  30:1894  68F1 DBDA  MOV REG[0xF1], #0xDBDA
  30:1898  68F0 0031  MOV REG[0xF0], #0x0031
  30:189C  58F1       MOV [--R15], R1
  30:189E  58F0       MOV [--R15], R0
  30:18A0  081B       MOV R1, R11
  30:18A2  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:18A6  4800       MOV R0, #0x0
  30:18A8  58F1       MOV [--R15], R1
  30:18AA  58F0       MOV [--R15], R0
> 30:18AC  BD03 407C  SCALL 03:407C
  30:18B0  50F8       ADD R15, #0x8
  30:18B2  AC00 18DE  AJMP ALWAYS, 30:18DE
  30:18B6  780B FFDE  MOV R0, [R11+0xFFDE]
  30:18BA  5600       CMP R0, #0x0
  30:18BC  AC02 18DE  AJMP NZ/NE, 30:18DE
  30:18C0  68F1 DBD8  MOV REG[0xF1], #0xDBD8
  30:18C4  68F0 0031  MOV REG[0xF0], #0x0031
  30:18C8  58F1       MOV [--R15], R1
  30:18CA  58F0       MOV [--R15], R0
  30:18CC  081B       MOV R1, R11
  30:18CE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:18D2  4800       MOV R0, #0x0
```

### `30:18D8` in `sub_30_15FC`

```text
  30:18BC  AC02 18DE  AJMP NZ/NE, 30:18DE
  30:18C0  68F1 DBD8  MOV REG[0xF1], #0xDBD8
  30:18C4  68F0 0031  MOV REG[0xF0], #0x0031
  30:18C8  58F1       MOV [--R15], R1
  30:18CA  58F0       MOV [--R15], R0
  30:18CC  081B       MOV R1, R11
  30:18CE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:18D2  4800       MOV R0, #0x0
  30:18D4  58F1       MOV [--R15], R1
  30:18D6  58F0       MOV [--R15], R0
> 30:18D8  BD03 407C  SCALL 03:407C
  30:18DC  50F8       ADD R15, #0x8
  30:18DE  780B FFF8  MOV R0, [R11+0xFFF8]
  30:18E2  58F0       MOV [--R15], R0
  30:18E4  68F1 DC00  MOV REG[0xF1], #0xDC00
  30:18E8  68F0 0031  MOV REG[0xF0], #0x0031
  30:18EC  58F1       MOV [--R15], R1
  30:18EE  58F0       MOV [--R15], R0
  30:18F0  081B       MOV R1, R11
  30:18F2  70F1 FFD0  ADD REG[0xF1], #0xFFD0
  30:18F6  4800       MOV R0, #0x0
  30:18F8  58F1       MOV [--R15], R1
  30:18FA  58F0       MOV [--R15], R0
```

### `30:1946` in `sub_30_15FC`

```text
  30:192A  AC0D 1950  AJMP SLE, 30:1950
  30:192E  68F1 DBD4  MOV REG[0xF1], #0xDBD4
  30:1932  68F0 0031  MOV REG[0xF0], #0x0031
  30:1936  58F1       MOV [--R15], R1
  30:1938  58F0       MOV [--R15], R0
  30:193A  081B       MOV R1, R11
  30:193C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1940  4800       MOV R0, #0x0
  30:1942  58F1       MOV [--R15], R1
  30:1944  58F0       MOV [--R15], R0
> 30:1946  BD03 407C  SCALL 03:407C
  30:194A  50F8       ADD R15, #0x8
  30:194C  AC00 2522  AJMP ALWAYS, 30:2522
  30:1950  6810 00A4  MOV REG[0x10], #0x00A4
  30:1954  88F0 792A  MOV REG[0xF0], [0x792A]
  30:1958  5600       CMP R0, #0x0
  30:195A  AC0D 2522  AJMP SLE, 30:2522
  30:195E  68F1 DBD0  MOV REG[0xF1], #0xDBD0
  30:1962  68F0 0031  MOV REG[0xF0], #0x0031
  30:1966  58F1       MOV [--R15], R1
  30:1968  58F0       MOV [--R15], R0
  30:196A  081B       MOV R1, R11
  30:196C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
```

### `30:1976` in `sub_30_15FC`

```text
  30:195A  AC0D 2522  AJMP SLE, 30:2522
  30:195E  68F1 DBD0  MOV REG[0xF1], #0xDBD0
  30:1962  68F0 0031  MOV REG[0xF0], #0x0031
  30:1966  58F1       MOV [--R15], R1
  30:1968  58F0       MOV [--R15], R0
  30:196A  081B       MOV R1, R11
  30:196C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1970  4800       MOV R0, #0x0
  30:1972  58F1       MOV [--R15], R1
  30:1974  58F0       MOV [--R15], R0
> 30:1976  BD03 407C  SCALL 03:407C
  30:197A  50F8       ADD R15, #0x8
  30:197C  AC00 2522  AJMP ALWAYS, 30:2522
  30:1980  780B FFFE  MOV R0, [R11+0xFFFE]
  30:1984  5602       CMP R0, #0x2
  30:1986  AC02 24F0  AJMP NZ/NE, 30:24F0
  30:198A  6810 00A4  MOV REG[0x10], #0x00A4
  30:198E  99F0 7ACC  MOVZE REG[0xF0], [0x7ACC]
  30:1992  5600       CMP R0, #0x0
  30:1994  AC0D 1FDE  AJMP SLE, 30:1FDE
  30:1998  6810 00A4  MOV REG[0x10], #0x00A4
  30:199C  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  30:19A0  1601       CMP R0, R1
```

### `30:1BDC` in `sub_30_1A54`

```text
  30:1BC0  AC0D 1BE6  AJMP SLE, 30:1BE6
  30:1BC4  68F1 DBCA  MOV REG[0xF1], #0xDBCA
  30:1BC8  68F0 0031  MOV REG[0xF0], #0x0031
  30:1BCC  58F1       MOV [--R15], R1
  30:1BCE  58F0       MOV [--R15], R0
  30:1BD0  081B       MOV R1, R11
  30:1BD2  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1BD6  4800       MOV R0, #0x0
  30:1BD8  58F1       MOV [--R15], R1
  30:1BDA  58F0       MOV [--R15], R0
> 30:1BDC  BD03 407C  SCALL 03:407C
  30:1BE0  50F8       ADD R15, #0x8
  30:1BE2  AC00 2522  AJMP ALWAYS, 30:2522
  30:1BE6  780B FFF0  MOV R0, [R11+0xFFF0]
  30:1BEA  5600       CMP R0, #0x0
  30:1BEC  AC0D 1C12  AJMP SLE, 30:1C12
  30:1BF0  68F1 DBC4  MOV REG[0xF1], #0xDBC4
  30:1BF4  68F0 0031  MOV REG[0xF0], #0x0031
  30:1BF8  58F1       MOV [--R15], R1
  30:1BFA  58F0       MOV [--R15], R0
  30:1BFC  081B       MOV R1, R11
  30:1BFE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1C02  4800       MOV R0, #0x0
```

### `30:1C08` in `sub_30_1A54`

```text
  30:1BEC  AC0D 1C12  AJMP SLE, 30:1C12
  30:1BF0  68F1 DBC4  MOV REG[0xF1], #0xDBC4
  30:1BF4  68F0 0031  MOV REG[0xF0], #0x0031
  30:1BF8  58F1       MOV [--R15], R1
  30:1BFA  58F0       MOV [--R15], R0
  30:1BFC  081B       MOV R1, R11
  30:1BFE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1C02  4800       MOV R0, #0x0
  30:1C04  58F1       MOV [--R15], R1
  30:1C06  58F0       MOV [--R15], R0
> 30:1C08  BD03 407C  SCALL 03:407C
  30:1C0C  50F8       ADD R15, #0x8
  30:1C0E  AC00 2522  AJMP ALWAYS, 30:2522
  30:1C12  780B FFF0  MOV R0, [R11+0xFFF0]
  30:1C16  5600       CMP R0, #0x0
  30:1C18  AC0E 1CE4  AJMP SGE, 30:1CE4
  30:1C1C  68F1 0094  MOV REG[0xF1], #0x0094
  30:1C20  4800       MOV R0, #0x0
  30:1C22  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1C26  5630       CMP R3, #0x0
  30:1C28  DE03       RJMP SGE, 30:1C30 ; rel +3
  30:1C2A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1C2E  D001       RJMP ALWAYS, 30:1C32 ; rel +1
```

### `30:1C76` in `sub_30_1A54`

```text
  30:1C5A  AC09 1C80  AJMP SL, 30:1C80
  30:1C5E  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:1C62  68F0 0031  MOV REG[0xF0], #0x0031
  30:1C66  58F1       MOV [--R15], R1
  30:1C68  58F0       MOV [--R15], R0
  30:1C6A  081B       MOV R1, R11
  30:1C6C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1C70  4800       MOV R0, #0x0
  30:1C72  58F1       MOV [--R15], R1
  30:1C74  58F0       MOV [--R15], R0
> 30:1C76  BD03 407C  SCALL 03:407C
  30:1C7A  50F8       ADD R15, #0x8
  30:1C7C  AC00 2522  AJMP ALWAYS, 30:2522
  30:1C80  68F1 0094  MOV REG[0xF1], #0x0094
  30:1C84  4800       MOV R0, #0x0
  30:1C86  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1C8A  5630       CMP R3, #0x0
  30:1C8C  DE03       RJMP SGE, 30:1C94 ; rel +3
  30:1C8E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1C92  D001       RJMP ALWAYS, 30:1C96 ; rel +1
  30:1C94  4820       MOV R2, #0x0
  30:1C96  58F3       MOV [--R15], R3
  30:1C98  58F2       MOV [--R15], R2
```

### `30:1CDA` in `sub_30_1A54`

```text
  30:1CBE  AC0E 2522  AJMP SGE, 30:2522
  30:1CC2  68F1 DBBA  MOV REG[0xF1], #0xDBBA
  30:1CC6  68F0 0031  MOV REG[0xF0], #0x0031
  30:1CCA  58F1       MOV [--R15], R1
  30:1CCC  58F0       MOV [--R15], R0
  30:1CCE  081B       MOV R1, R11
  30:1CD0  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1CD4  4800       MOV R0, #0x0
  30:1CD6  58F1       MOV [--R15], R1
  30:1CD8  58F0       MOV [--R15], R0
> 30:1CDA  BD03 407C  SCALL 03:407C
  30:1CDE  50F8       ADD R15, #0x8
  30:1CE0  AC00 2522  AJMP ALWAYS, 30:2522
  30:1CE4  780B FFF2  MOV R0, [R11+0xFFF2]
  30:1CE8  5600       CMP R0, #0x0
  30:1CEA  AC0D 1D10  AJMP SLE, 30:1D10
  30:1CEE  68F1 DBB4  MOV REG[0xF1], #0xDBB4
  30:1CF2  68F0 0031  MOV REG[0xF0], #0x0031
  30:1CF6  58F1       MOV [--R15], R1
  30:1CF8  58F0       MOV [--R15], R0
  30:1CFA  081B       MOV R1, R11
  30:1CFC  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1D00  4800       MOV R0, #0x0
```

### `30:1D06` in `sub_30_1A54`

```text
  30:1CEA  AC0D 1D10  AJMP SLE, 30:1D10
  30:1CEE  68F1 DBB4  MOV REG[0xF1], #0xDBB4
  30:1CF2  68F0 0031  MOV REG[0xF0], #0x0031
  30:1CF6  58F1       MOV [--R15], R1
  30:1CF8  58F0       MOV [--R15], R0
  30:1CFA  081B       MOV R1, R11
  30:1CFC  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1D00  4800       MOV R0, #0x0
  30:1D02  58F1       MOV [--R15], R1
  30:1D04  58F0       MOV [--R15], R0
> 30:1D06  BD03 407C  SCALL 03:407C
  30:1D0A  50F8       ADD R15, #0x8
  30:1D0C  AC00 2522  AJMP ALWAYS, 30:2522
  30:1D10  780B FFF2  MOV R0, [R11+0xFFF2]
  30:1D14  5600       CMP R0, #0x0
  30:1D16  AC0E 1DE2  AJMP SGE, 30:1DE2
  30:1D1A  68F1 0094  MOV REG[0xF1], #0x0094
  30:1D1E  4800       MOV R0, #0x0
  30:1D20  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1D24  5630       CMP R3, #0x0
  30:1D26  DE03       RJMP SGE, 30:1D2E ; rel +3
  30:1D28  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1D2C  D001       RJMP ALWAYS, 30:1D30 ; rel +1
```

### `30:1D74` in `sub_30_1A54`

```text
  30:1D58  AC09 1D7E  AJMP SL, 30:1D7E
  30:1D5C  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:1D60  68F0 0031  MOV REG[0xF0], #0x0031
  30:1D64  58F1       MOV [--R15], R1
  30:1D66  58F0       MOV [--R15], R0
  30:1D68  081B       MOV R1, R11
  30:1D6A  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1D6E  4800       MOV R0, #0x0
  30:1D70  58F1       MOV [--R15], R1
  30:1D72  58F0       MOV [--R15], R0
> 30:1D74  BD03 407C  SCALL 03:407C
  30:1D78  50F8       ADD R15, #0x8
  30:1D7A  AC00 2522  AJMP ALWAYS, 30:2522
  30:1D7E  68F1 0094  MOV REG[0xF1], #0x0094
  30:1D82  4800       MOV R0, #0x0
  30:1D84  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1D88  5630       CMP R3, #0x0
  30:1D8A  DE03       RJMP SGE, 30:1D92 ; rel +3
  30:1D8C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1D90  D001       RJMP ALWAYS, 30:1D94 ; rel +1
  30:1D92  4820       MOV R2, #0x0
  30:1D94  58F3       MOV [--R15], R3
  30:1D96  58F2       MOV [--R15], R2
```

### `30:1DD8` in `sub_30_1A54`

```text
  30:1DBC  AC0E 2522  AJMP SGE, 30:2522
  30:1DC0  68F1 DBB0  MOV REG[0xF1], #0xDBB0
  30:1DC4  68F0 0031  MOV REG[0xF0], #0x0031
  30:1DC8  58F1       MOV [--R15], R1
  30:1DCA  58F0       MOV [--R15], R0
  30:1DCC  081B       MOV R1, R11
  30:1DCE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1DD2  4800       MOV R0, #0x0
  30:1DD4  58F1       MOV [--R15], R1
  30:1DD6  58F0       MOV [--R15], R0
> 30:1DD8  BD03 407C  SCALL 03:407C
  30:1DDC  50F8       ADD R15, #0x8
  30:1DDE  AC00 2522  AJMP ALWAYS, 30:2522
  30:1DE2  780B FFF4  MOV R0, [R11+0xFFF4]
  30:1DE6  5600       CMP R0, #0x0
  30:1DE8  AC0D 1E0E  AJMP SLE, 30:1E0E
  30:1DEC  68F1 DBAA  MOV REG[0xF1], #0xDBAA
  30:1DF0  68F0 0031  MOV REG[0xF0], #0x0031
  30:1DF4  58F1       MOV [--R15], R1
  30:1DF6  58F0       MOV [--R15], R0
  30:1DF8  081B       MOV R1, R11
  30:1DFA  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1DFE  4800       MOV R0, #0x0
```

### `30:1E04` in `sub_30_1A54`

```text
  30:1DE8  AC0D 1E0E  AJMP SLE, 30:1E0E
  30:1DEC  68F1 DBAA  MOV REG[0xF1], #0xDBAA
  30:1DF0  68F0 0031  MOV REG[0xF0], #0x0031
  30:1DF4  58F1       MOV [--R15], R1
  30:1DF6  58F0       MOV [--R15], R0
  30:1DF8  081B       MOV R1, R11
  30:1DFA  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1DFE  4800       MOV R0, #0x0
  30:1E00  58F1       MOV [--R15], R1
  30:1E02  58F0       MOV [--R15], R0
> 30:1E04  BD03 407C  SCALL 03:407C
  30:1E08  50F8       ADD R15, #0x8
  30:1E0A  AC00 2522  AJMP ALWAYS, 30:2522
  30:1E0E  780B FFF4  MOV R0, [R11+0xFFF4]
  30:1E12  5600       CMP R0, #0x0
  30:1E14  AC0E 1EE0  AJMP SGE, 30:1EE0
  30:1E18  68F1 0094  MOV REG[0xF1], #0x0094
  30:1E1C  4800       MOV R0, #0x0
  30:1E1E  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1E22  5630       CMP R3, #0x0
  30:1E24  DE03       RJMP SGE, 30:1E2C ; rel +3
  30:1E26  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1E2A  D001       RJMP ALWAYS, 30:1E2E ; rel +1
```

### `30:1E72` in `sub_30_1A54`

```text
  30:1E56  AC09 1E7C  AJMP SL, 30:1E7C
  30:1E5A  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:1E5E  68F0 0031  MOV REG[0xF0], #0x0031
  30:1E62  58F1       MOV [--R15], R1
  30:1E64  58F0       MOV [--R15], R0
  30:1E66  081B       MOV R1, R11
  30:1E68  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1E6C  4800       MOV R0, #0x0
  30:1E6E  58F1       MOV [--R15], R1
  30:1E70  58F0       MOV [--R15], R0
> 30:1E72  BD03 407C  SCALL 03:407C
  30:1E76  50F8       ADD R15, #0x8
  30:1E78  AC00 2522  AJMP ALWAYS, 30:2522
  30:1E7C  68F1 0094  MOV REG[0xF1], #0x0094
  30:1E80  4800       MOV R0, #0x0
  30:1E82  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1E86  5630       CMP R3, #0x0
  30:1E88  DE03       RJMP SGE, 30:1E90 ; rel +3
  30:1E8A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1E8E  D001       RJMP ALWAYS, 30:1E92 ; rel +1
  30:1E90  4820       MOV R2, #0x0
  30:1E92  58F3       MOV [--R15], R3
  30:1E94  58F2       MOV [--R15], R2
```

### `30:1ED6` in `sub_30_1EAA`

```text
  30:1EBA  AC0E 2522  AJMP SGE, 30:2522
  30:1EBE  68F1 DBA6  MOV REG[0xF1], #0xDBA6
  30:1EC2  68F0 0031  MOV REG[0xF0], #0x0031
  30:1EC6  58F1       MOV [--R15], R1
  30:1EC8  58F0       MOV [--R15], R0
  30:1ECA  081B       MOV R1, R11
  30:1ECC  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1ED0  4800       MOV R0, #0x0
  30:1ED2  58F1       MOV [--R15], R1
  30:1ED4  58F0       MOV [--R15], R0
> 30:1ED6  BD03 407C  SCALL 03:407C
  30:1EDA  50F8       ADD R15, #0x8
  30:1EDC  AC00 2522  AJMP ALWAYS, 30:2522
  30:1EE0  780B FFF6  MOV R0, [R11+0xFFF6]
  30:1EE4  5600       CMP R0, #0x0
  30:1EE6  AC0D 1F0C  AJMP SLE, 30:1F0C
  30:1EEA  68F1 DBA0  MOV REG[0xF1], #0xDBA0
  30:1EEE  68F0 0031  MOV REG[0xF0], #0x0031
  30:1EF2  58F1       MOV [--R15], R1
  30:1EF4  58F0       MOV [--R15], R0
  30:1EF6  081B       MOV R1, R11
  30:1EF8  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1EFC  4800       MOV R0, #0x0
```

### `30:1F02` in `sub_30_1EAA`

```text
  30:1EE6  AC0D 1F0C  AJMP SLE, 30:1F0C
  30:1EEA  68F1 DBA0  MOV REG[0xF1], #0xDBA0
  30:1EEE  68F0 0031  MOV REG[0xF0], #0x0031
  30:1EF2  58F1       MOV [--R15], R1
  30:1EF4  58F0       MOV [--R15], R0
  30:1EF6  081B       MOV R1, R11
  30:1EF8  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1EFC  4800       MOV R0, #0x0
  30:1EFE  58F1       MOV [--R15], R1
  30:1F00  58F0       MOV [--R15], R0
> 30:1F02  BD03 407C  SCALL 03:407C
  30:1F06  50F8       ADD R15, #0x8
  30:1F08  AC00 2522  AJMP ALWAYS, 30:2522
  30:1F0C  780B FFF6  MOV R0, [R11+0xFFF6]
  30:1F10  5600       CMP R0, #0x0
  30:1F12  AC0E 2522  AJMP SGE, 30:2522
  30:1F16  68F1 0094  MOV REG[0xF1], #0x0094
  30:1F1A  4800       MOV R0, #0x0
  30:1F1C  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1F20  5630       CMP R3, #0x0
  30:1F22  DE03       RJMP SGE, 30:1F2A ; rel +3
  30:1F24  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1F28  D001       RJMP ALWAYS, 30:1F2C ; rel +1
```

### `30:1F70` in `sub_30_1EAA`

```text
  30:1F54  AC09 1F7A  AJMP SL, 30:1F7A
  30:1F58  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:1F5C  68F0 0031  MOV REG[0xF0], #0x0031
  30:1F60  58F1       MOV [--R15], R1
  30:1F62  58F0       MOV [--R15], R0
  30:1F64  081B       MOV R1, R11
  30:1F66  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1F6A  4800       MOV R0, #0x0
  30:1F6C  58F1       MOV [--R15], R1
  30:1F6E  58F0       MOV [--R15], R0
> 30:1F70  BD03 407C  SCALL 03:407C
  30:1F74  50F8       ADD R15, #0x8
  30:1F76  AC00 2522  AJMP ALWAYS, 30:2522
  30:1F7A  68F1 0094  MOV REG[0xF1], #0x0094
  30:1F7E  4800       MOV R0, #0x0
  30:1F80  783B FFEE  MOV R3, [R11+0xFFEE]
  30:1F84  5630       CMP R3, #0x0
  30:1F86  DE03       RJMP SGE, 30:1F8E ; rel +3
  30:1F88  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:1F8C  D001       RJMP ALWAYS, 30:1F90 ; rel +1
  30:1F8E  4820       MOV R2, #0x0
  30:1F90  58F3       MOV [--R15], R3
  30:1F92  58F2       MOV [--R15], R2
```

### `30:1FD4` in `sub_30_1EAA`

```text
  30:1FB8  AC0E 2522  AJMP SGE, 30:2522
  30:1FBC  68F1 DB9C  MOV REG[0xF1], #0xDB9C
  30:1FC0  68F0 0031  MOV REG[0xF0], #0x0031
  30:1FC4  58F1       MOV [--R15], R1
  30:1FC6  58F0       MOV [--R15], R0
  30:1FC8  081B       MOV R1, R11
  30:1FCA  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1FCE  4800       MOV R0, #0x0
  30:1FD0  58F1       MOV [--R15], R1
  30:1FD2  58F0       MOV [--R15], R0
> 30:1FD4  BD03 407C  SCALL 03:407C
  30:1FD8  50F8       ADD R15, #0x8
  30:1FDA  AC00 2522  AJMP ALWAYS, 30:2522
  30:1FDE  6810 00A4  MOV REG[0x10], #0x00A4
  30:1FE2  99F0 7ACC  MOVZE REG[0xF0], [0x7ACC]
  30:1FE6  6810 00A4  MOV REG[0x10], #0x00A4
  30:1FEA  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  30:1FEE  1601       CMP R0, R1
  30:1FF0  AC0D 2522  AJMP SLE, 30:2522
  30:1FF4  6810 00A4  MOV REG[0x10], #0x00A4
  30:1FF8  99F3 7AF0  MOVZE REG[0xF3], [0x7AF0]
  30:1FFC  1031       ADD R3, R1
  30:1FFE  1603       CMP R0, R3
```

### `30:20F2` in `sub_30_1EAA`

```text
  30:20D6  AC0D 20F8  AJMP SLE, 30:20F8
  30:20DA  68F1 DBCA  MOV REG[0xF1], #0xDBCA
  30:20DE  68F0 0031  MOV REG[0xF0], #0x0031
  30:20E2  58F1       MOV [--R15], R1
  30:20E4  58F0       MOV [--R15], R0
  30:20E6  081B       MOV R1, R11
  30:20E8  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:20EC  4800       MOV R0, #0x0
  30:20EE  58F1       MOV [--R15], R1
  30:20F0  58F0       MOV [--R15], R0
> 30:20F2  BD03 407C  SCALL 03:407C
  30:20F6  50F8       ADD R15, #0x8
  30:20F8  780B FFF0  MOV R0, [R11+0xFFF0]
  30:20FC  5600       CMP R0, #0x0
  30:20FE  AC0D 2124  AJMP SLE, 30:2124
  30:2102  68F1 DBC4  MOV REG[0xF1], #0xDBC4
  30:2106  68F0 0031  MOV REG[0xF0], #0x0031
  30:210A  58F1       MOV [--R15], R1
  30:210C  58F0       MOV [--R15], R0
  30:210E  081B       MOV R1, R11
  30:2110  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2114  4800       MOV R0, #0x0
  30:2116  58F1       MOV [--R15], R1
```

### `30:211A` in `sub_30_1EAA`

```text
  30:20FE  AC0D 2124  AJMP SLE, 30:2124
  30:2102  68F1 DBC4  MOV REG[0xF1], #0xDBC4
  30:2106  68F0 0031  MOV REG[0xF0], #0x0031
  30:210A  58F1       MOV [--R15], R1
  30:210C  58F0       MOV [--R15], R0
  30:210E  081B       MOV R1, R11
  30:2110  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2114  4800       MOV R0, #0x0
  30:2116  58F1       MOV [--R15], R1
  30:2118  58F0       MOV [--R15], R0
> 30:211A  BD03 407C  SCALL 03:407C
  30:211E  50F8       ADD R15, #0x8
  30:2120  AC00 2522  AJMP ALWAYS, 30:2522
  30:2124  780B FFF0  MOV R0, [R11+0xFFF0]
  30:2128  5600       CMP R0, #0x0
  30:212A  AC0E 21F6  AJMP SGE, 30:21F6
  30:212E  68F1 0094  MOV REG[0xF1], #0x0094
  30:2132  4800       MOV R0, #0x0
  30:2134  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2138  5630       CMP R3, #0x0
  30:213A  DE03       RJMP SGE, 30:2142 ; rel +3
  30:213C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:2140  D001       RJMP ALWAYS, 30:2144 ; rel +1
```

### `30:2188` in `sub_30_1EAA`

```text
  30:216C  AC09 2192  AJMP SL, 30:2192
  30:2170  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:2174  68F0 0031  MOV REG[0xF0], #0x0031
  30:2178  58F1       MOV [--R15], R1
  30:217A  58F0       MOV [--R15], R0
  30:217C  081B       MOV R1, R11
  30:217E  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2182  4800       MOV R0, #0x0
  30:2184  58F1       MOV [--R15], R1
  30:2186  58F0       MOV [--R15], R0
> 30:2188  BD03 407C  SCALL 03:407C
  30:218C  50F8       ADD R15, #0x8
  30:218E  AC00 2522  AJMP ALWAYS, 30:2522
  30:2192  68F1 0094  MOV REG[0xF1], #0x0094
  30:2196  4800       MOV R0, #0x0
  30:2198  783B FFEE  MOV R3, [R11+0xFFEE]
  30:219C  5630       CMP R3, #0x0
  30:219E  DE03       RJMP SGE, 30:21A6 ; rel +3
  30:21A0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:21A4  D001       RJMP ALWAYS, 30:21A8 ; rel +1
  30:21A6  4820       MOV R2, #0x0
  30:21A8  58F3       MOV [--R15], R3
  30:21AA  58F2       MOV [--R15], R2
```

### `30:21EC` in `sub_30_1EAA`

```text
  30:21D0  AC0E 2522  AJMP SGE, 30:2522
  30:21D4  68F1 DBBA  MOV REG[0xF1], #0xDBBA
  30:21D8  68F0 0031  MOV REG[0xF0], #0x0031
  30:21DC  58F1       MOV [--R15], R1
  30:21DE  58F0       MOV [--R15], R0
  30:21E0  081B       MOV R1, R11
  30:21E2  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:21E6  4800       MOV R0, #0x0
  30:21E8  58F1       MOV [--R15], R1
  30:21EA  58F0       MOV [--R15], R0
> 30:21EC  BD03 407C  SCALL 03:407C
  30:21F0  50F8       ADD R15, #0x8
  30:21F2  AC00 2522  AJMP ALWAYS, 30:2522
  30:21F6  780B FFF2  MOV R0, [R11+0xFFF2]
  30:21FA  5600       CMP R0, #0x0
  30:21FC  AC0D 2222  AJMP SLE, 30:2222
  30:2200  68F1 DBB4  MOV REG[0xF1], #0xDBB4
  30:2204  68F0 0031  MOV REG[0xF0], #0x0031
  30:2208  58F1       MOV [--R15], R1
  30:220A  58F0       MOV [--R15], R0
  30:220C  081B       MOV R1, R11
  30:220E  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2212  4800       MOV R0, #0x0
```

### `30:2218` in `sub_30_1EAA`

```text
  30:21FC  AC0D 2222  AJMP SLE, 30:2222
  30:2200  68F1 DBB4  MOV REG[0xF1], #0xDBB4
  30:2204  68F0 0031  MOV REG[0xF0], #0x0031
  30:2208  58F1       MOV [--R15], R1
  30:220A  58F0       MOV [--R15], R0
  30:220C  081B       MOV R1, R11
  30:220E  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2212  4800       MOV R0, #0x0
  30:2214  58F1       MOV [--R15], R1
  30:2216  58F0       MOV [--R15], R0
> 30:2218  BD03 407C  SCALL 03:407C
  30:221C  50F8       ADD R15, #0x8
  30:221E  AC00 2522  AJMP ALWAYS, 30:2522
  30:2222  780B FFF2  MOV R0, [R11+0xFFF2]
  30:2226  5600       CMP R0, #0x0
  30:2228  AC0E 22F4  AJMP SGE, 30:22F4
  30:222C  68F1 0094  MOV REG[0xF1], #0x0094
  30:2230  4800       MOV R0, #0x0
  30:2232  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2236  5630       CMP R3, #0x0
  30:2238  DE03       RJMP SGE, 30:2240 ; rel +3
  30:223A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:223E  D001       RJMP ALWAYS, 30:2242 ; rel +1
```

### `30:2286` in `sub_30_1EAA`

```text
  30:226A  AC09 2290  AJMP SL, 30:2290
  30:226E  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:2272  68F0 0031  MOV REG[0xF0], #0x0031
  30:2276  58F1       MOV [--R15], R1
  30:2278  58F0       MOV [--R15], R0
  30:227A  081B       MOV R1, R11
  30:227C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2280  4800       MOV R0, #0x0
  30:2282  58F1       MOV [--R15], R1
  30:2284  58F0       MOV [--R15], R0
> 30:2286  BD03 407C  SCALL 03:407C
  30:228A  50F8       ADD R15, #0x8
  30:228C  AC00 2522  AJMP ALWAYS, 30:2522
  30:2290  68F1 0094  MOV REG[0xF1], #0x0094
  30:2294  4800       MOV R0, #0x0
  30:2296  783B FFEE  MOV R3, [R11+0xFFEE]
  30:229A  5630       CMP R3, #0x0
  30:229C  DE03       RJMP SGE, 30:22A4 ; rel +3
  30:229E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:22A2  D001       RJMP ALWAYS, 30:22A6 ; rel +1
  30:22A4  4820       MOV R2, #0x0
  30:22A6  58F3       MOV [--R15], R3
  30:22A8  58F2       MOV [--R15], R2
```

### `30:22EA` in `sub_30_1EAA`

```text
  30:22CE  AC0E 2522  AJMP SGE, 30:2522
  30:22D2  68F1 DBB0  MOV REG[0xF1], #0xDBB0
  30:22D6  68F0 0031  MOV REG[0xF0], #0x0031
  30:22DA  58F1       MOV [--R15], R1
  30:22DC  58F0       MOV [--R15], R0
  30:22DE  081B       MOV R1, R11
  30:22E0  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:22E4  4800       MOV R0, #0x0
  30:22E6  58F1       MOV [--R15], R1
  30:22E8  58F0       MOV [--R15], R0
> 30:22EA  BD03 407C  SCALL 03:407C
  30:22EE  50F8       ADD R15, #0x8
  30:22F0  AC00 2522  AJMP ALWAYS, 30:2522
  30:22F4  780B FFF4  MOV R0, [R11+0xFFF4]
  30:22F8  5600       CMP R0, #0x0
  30:22FA  AC0D 2320  AJMP SLE, 30:2320
  30:22FE  68F1 DBAA  MOV REG[0xF1], #0xDBAA
  30:2302  68F0 0031  MOV REG[0xF0], #0x0031
  30:2306  58F1       MOV [--R15], R1
  30:2308  58F0       MOV [--R15], R0
  30:230A  081B       MOV R1, R11
  30:230C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2310  4800       MOV R0, #0x0
```

### `30:2316` in `sub_30_1EAA`

```text
  30:22FA  AC0D 2320  AJMP SLE, 30:2320
  30:22FE  68F1 DBAA  MOV REG[0xF1], #0xDBAA
  30:2302  68F0 0031  MOV REG[0xF0], #0x0031
  30:2306  58F1       MOV [--R15], R1
  30:2308  58F0       MOV [--R15], R0
  30:230A  081B       MOV R1, R11
  30:230C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2310  4800       MOV R0, #0x0
  30:2312  58F1       MOV [--R15], R1
  30:2314  58F0       MOV [--R15], R0
> 30:2316  BD03 407C  SCALL 03:407C
  30:231A  50F8       ADD R15, #0x8
  30:231C  AC00 2522  AJMP ALWAYS, 30:2522
  30:2320  780B FFF4  MOV R0, [R11+0xFFF4]
  30:2324  5600       CMP R0, #0x0
  30:2326  AC0E 23F2  AJMP SGE, 30:23F2
  30:232A  68F1 0094  MOV REG[0xF1], #0x0094
  30:232E  4800       MOV R0, #0x0
  30:2330  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2334  5630       CMP R3, #0x0
  30:2336  DE03       RJMP SGE, 30:233E ; rel +3
  30:2338  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:233C  D001       RJMP ALWAYS, 30:2340 ; rel +1
```

### `30:2384` in `sub_30_1EAA`

```text
  30:2368  AC09 238E  AJMP SL, 30:238E
  30:236C  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:2370  68F0 0031  MOV REG[0xF0], #0x0031
  30:2374  58F1       MOV [--R15], R1
  30:2376  58F0       MOV [--R15], R0
  30:2378  081B       MOV R1, R11
  30:237A  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:237E  4800       MOV R0, #0x0
  30:2380  58F1       MOV [--R15], R1
  30:2382  58F0       MOV [--R15], R0
> 30:2384  BD03 407C  SCALL 03:407C
  30:2388  50F8       ADD R15, #0x8
  30:238A  AC00 2522  AJMP ALWAYS, 30:2522
  30:238E  68F1 0094  MOV REG[0xF1], #0x0094
  30:2392  4800       MOV R0, #0x0
  30:2394  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2398  5630       CMP R3, #0x0
  30:239A  DE03       RJMP SGE, 30:23A2 ; rel +3
  30:239C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:23A0  D001       RJMP ALWAYS, 30:23A4 ; rel +1
  30:23A2  4820       MOV R2, #0x0
  30:23A4  58F3       MOV [--R15], R3
  30:23A6  58F2       MOV [--R15], R2
```

### `30:23E8` in `sub_30_1EAA`

```text
  30:23CC  AC0E 2522  AJMP SGE, 30:2522
  30:23D0  68F1 DBA6  MOV REG[0xF1], #0xDBA6
  30:23D4  68F0 0031  MOV REG[0xF0], #0x0031
  30:23D8  58F1       MOV [--R15], R1
  30:23DA  58F0       MOV [--R15], R0
  30:23DC  081B       MOV R1, R11
  30:23DE  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:23E2  4800       MOV R0, #0x0
  30:23E4  58F1       MOV [--R15], R1
  30:23E6  58F0       MOV [--R15], R0
> 30:23E8  BD03 407C  SCALL 03:407C
  30:23EC  50F8       ADD R15, #0x8
  30:23EE  AC00 2522  AJMP ALWAYS, 30:2522
  30:23F2  780B FFF6  MOV R0, [R11+0xFFF6]
  30:23F6  5600       CMP R0, #0x0
  30:23F8  AC0D 241E  AJMP SLE, 30:241E
  30:23FC  68F1 DBA0  MOV REG[0xF1], #0xDBA0
  30:2400  68F0 0031  MOV REG[0xF0], #0x0031
  30:2404  58F1       MOV [--R15], R1
  30:2406  58F0       MOV [--R15], R0
  30:2408  081B       MOV R1, R11
  30:240A  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:240E  4800       MOV R0, #0x0
```

### `30:2414` in `sub_30_1EAA`

```text
  30:23F8  AC0D 241E  AJMP SLE, 30:241E
  30:23FC  68F1 DBA0  MOV REG[0xF1], #0xDBA0
  30:2400  68F0 0031  MOV REG[0xF0], #0x0031
  30:2404  58F1       MOV [--R15], R1
  30:2406  58F0       MOV [--R15], R0
  30:2408  081B       MOV R1, R11
  30:240A  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:240E  4800       MOV R0, #0x0
  30:2410  58F1       MOV [--R15], R1
  30:2412  58F0       MOV [--R15], R0
> 30:2414  BD03 407C  SCALL 03:407C
  30:2418  50F8       ADD R15, #0x8
  30:241A  AC00 2522  AJMP ALWAYS, 30:2522
  30:241E  780B FFF6  MOV R0, [R11+0xFFF6]
  30:2422  5600       CMP R0, #0x0
  30:2424  AC0E 2522  AJMP SGE, 30:2522
  30:2428  68F1 0094  MOV REG[0xF1], #0x0094
  30:242C  4800       MOV R0, #0x0
  30:242E  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2432  5630       CMP R3, #0x0
  30:2434  DE03       RJMP SGE, 30:243C ; rel +3
  30:2436  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:243A  D001       RJMP ALWAYS, 30:243E ; rel +1
```

### `30:2482` in `sub_30_1EAA`

```text
  30:2466  AC09 248C  AJMP SL, 30:248C
  30:246A  68F1 DBBE  MOV REG[0xF1], #0xDBBE
  30:246E  68F0 0031  MOV REG[0xF0], #0x0031
  30:2472  58F1       MOV [--R15], R1
  30:2474  58F0       MOV [--R15], R0
  30:2476  081B       MOV R1, R11
  30:2478  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:247C  4800       MOV R0, #0x0
  30:247E  58F1       MOV [--R15], R1
  30:2480  58F0       MOV [--R15], R0
> 30:2482  BD03 407C  SCALL 03:407C
  30:2486  50F8       ADD R15, #0x8
  30:2488  AC00 2522  AJMP ALWAYS, 30:2522
  30:248C  68F1 0094  MOV REG[0xF1], #0x0094
  30:2490  4800       MOV R0, #0x0
  30:2492  783B FFEE  MOV R3, [R11+0xFFEE]
  30:2496  5630       CMP R3, #0x0
  30:2498  DE03       RJMP SGE, 30:24A0 ; rel +3
  30:249A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  30:249E  D001       RJMP ALWAYS, 30:24A2 ; rel +1
  30:24A0  4820       MOV R2, #0x0
  30:24A2  58F3       MOV [--R15], R3
  30:24A4  58F2       MOV [--R15], R2
```

### `30:24E6` in `sub_30_1EAA`

```text
  30:24CA  AC0E 2522  AJMP SGE, 30:2522
  30:24CE  68F1 DB9C  MOV REG[0xF1], #0xDB9C
  30:24D2  68F0 0031  MOV REG[0xF0], #0x0031
  30:24D6  58F1       MOV [--R15], R1
  30:24D8  58F0       MOV [--R15], R0
  30:24DA  081B       MOV R1, R11
  30:24DC  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:24E0  4800       MOV R0, #0x0
  30:24E2  58F1       MOV [--R15], R1
  30:24E4  58F0       MOV [--R15], R0
> 30:24E6  BD03 407C  SCALL 03:407C
  30:24EA  50F8       ADD R15, #0x8
  30:24EC  AC00 2522  AJMP ALWAYS, 30:2522
  30:24F0  780B FFFE  MOV R0, [R11+0xFFFE]
  30:24F4  76F0 0010  CMP REG[0xF0], #0x0010
  30:24F8  AC09 2522  AJMP SL, 30:2522
  30:24FC  76F0 0013  CMP REG[0xF0], #0x0013
  30:2500  AC0B 2522  AJMP SG, 30:2522
  30:2504  68F1 DB96  MOV REG[0xF1], #0xDB96
  30:2508  68F0 0031  MOV REG[0xF0], #0x0031
  30:250C  58F1       MOV [--R15], R1
  30:250E  58F0       MOV [--R15], R0
  30:2510  081B       MOV R1, R11
```

### `30:251C` in `sub_30_1EAA`

```text
  30:2500  AC0B 2522  AJMP SG, 30:2522
  30:2504  68F1 DB96  MOV REG[0xF1], #0xDB96
  30:2508  68F0 0031  MOV REG[0xF0], #0x0031
  30:250C  58F1       MOV [--R15], R1
  30:250E  58F0       MOV [--R15], R0
  30:2510  081B       MOV R1, R11
  30:2512  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2516  4800       MOV R0, #0x0
  30:2518  58F1       MOV [--R15], R1
  30:251A  58F0       MOV [--R15], R0
> 30:251C  BD03 407C  SCALL 03:407C
  30:2520  50F8       ADD R15, #0x8
  30:2522  780B FFF8  MOV R0, [R11+0xFFF8]
  30:2526  5600       CMP R0, #0x0
  30:2528  AC0D 2554  AJMP SLE, 30:2554
  30:252C  081B       MOV R1, R11
  30:252E  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:2532  4800       MOV R0, #0x0
  30:2534  58F1       MOV [--R15], R1
  30:2536  58F0       MOV [--R15], R0
  30:2538  780B FFDA  MOV R0, [R11+0xFFDA]
  30:253C  4817       MOV R1, #0x7
  30:253E  783B FFCE  MOV R3, [R11+0xFFCE]
```

## `03:4080`

Call sites: `2F:5BA0`, `2F:5BBE`, `2F:5CC6`, `2F:5CE4`, `2F:5DEC`, `2F:5E0A`, `2F:A9D8`, `2F:A9F6`, `2F:AC56`, `2F:AC74`, `2F:AD74`, `2F:AD92`, `2F:AFF2`, `2F:B010`, `30:191A`

### `2F:5BA0` in `sub_2F_5A54`

```text
  2F:5B86  50FA       ADD R15, #0xA
  2F:5B88  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5B8C  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5B90  58F1       MOV [--R15], R1
  2F:5B92  58F0       MOV [--R15], R0
  2F:5B94  081B       MOV R1, R11
  2F:5B96  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5B9A  4800       MOV R0, #0x0
  2F:5B9C  58F1       MOV [--R15], R1
  2F:5B9E  58F0       MOV [--R15], R0
> 2F:5BA0  BD03 4080  SCALL 03:4080
  2F:5BA4  50F8       ADD R15, #0x8
  2F:5BA6  081B       MOV R1, R11
  2F:5BA8  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5BAC  4800       MOV R0, #0x0
  2F:5BAE  58F1       MOV [--R15], R1
  2F:5BB0  58F0       MOV [--R15], R0
  2F:5BB2  081B       MOV R1, R11
  2F:5BB4  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5BB8  4800       MOV R0, #0x0
  2F:5BBA  58F1       MOV [--R15], R1
  2F:5BBC  58F0       MOV [--R15], R0
  2F:5BBE  BD03 4080  SCALL 03:4080
```

### `2F:5BBE` in `sub_2F_5A54`

```text
  2F:5BA6  081B       MOV R1, R11
  2F:5BA8  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5BAC  4800       MOV R0, #0x0
  2F:5BAE  58F1       MOV [--R15], R1
  2F:5BB0  58F0       MOV [--R15], R0
  2F:5BB2  081B       MOV R1, R11
  2F:5BB4  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5BB8  4800       MOV R0, #0x0
  2F:5BBA  58F1       MOV [--R15], R1
  2F:5BBC  58F0       MOV [--R15], R0
> 2F:5BBE  BD03 4080  SCALL 03:4080
  2F:5BC2  50F8       ADD R15, #0x8
  2F:5BC4  480B       MOV R0, #0xB
  2F:5BC6  58F0       MOV [--R15], R0
  2F:5BC8  081B       MOV R1, R11
  2F:5BCA  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5BCE  4800       MOV R0, #0x0
  2F:5BD0  58F1       MOV [--R15], R1
  2F:5BD2  58F0       MOV [--R15], R0
  2F:5BD4  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5BD8  58F0       MOV [--R15], R0
  2F:5BDA  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5BDE  58F0       MOV [--R15], R0
```

### `2F:5CC6` in `sub_2F_5A54`

```text
  2F:5CAC  50FA       ADD R15, #0xA
  2F:5CAE  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5CB2  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5CB6  58F1       MOV [--R15], R1
  2F:5CB8  58F0       MOV [--R15], R0
  2F:5CBA  081B       MOV R1, R11
  2F:5CBC  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5CC0  4800       MOV R0, #0x0
  2F:5CC2  58F1       MOV [--R15], R1
  2F:5CC4  58F0       MOV [--R15], R0
> 2F:5CC6  BD03 4080  SCALL 03:4080
  2F:5CCA  50F8       ADD R15, #0x8
  2F:5CCC  081B       MOV R1, R11
  2F:5CCE  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5CD2  4800       MOV R0, #0x0
  2F:5CD4  58F1       MOV [--R15], R1
  2F:5CD6  58F0       MOV [--R15], R0
  2F:5CD8  081B       MOV R1, R11
  2F:5CDA  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5CDE  4800       MOV R0, #0x0
  2F:5CE0  58F1       MOV [--R15], R1
  2F:5CE2  58F0       MOV [--R15], R0
  2F:5CE4  BD03 4080  SCALL 03:4080
```

### `2F:5CE4` in `sub_2F_5A54`

```text
  2F:5CCC  081B       MOV R1, R11
  2F:5CCE  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5CD2  4800       MOV R0, #0x0
  2F:5CD4  58F1       MOV [--R15], R1
  2F:5CD6  58F0       MOV [--R15], R0
  2F:5CD8  081B       MOV R1, R11
  2F:5CDA  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5CDE  4800       MOV R0, #0x0
  2F:5CE0  58F1       MOV [--R15], R1
  2F:5CE2  58F0       MOV [--R15], R0
> 2F:5CE4  BD03 4080  SCALL 03:4080
  2F:5CE8  50F8       ADD R15, #0x8
  2F:5CEA  4809       MOV R0, #0x9
  2F:5CEC  58F0       MOV [--R15], R0
  2F:5CEE  081B       MOV R1, R11
  2F:5CF0  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5CF4  4800       MOV R0, #0x0
  2F:5CF6  58F1       MOV [--R15], R1
  2F:5CF8  58F0       MOV [--R15], R0
  2F:5CFA  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5CFE  58F0       MOV [--R15], R0
  2F:5D00  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5D04  58F0       MOV [--R15], R0
```

### `2F:5DEC` in `sub_2F_5A54`

```text
  2F:5DD2  50FA       ADD R15, #0xA
  2F:5DD4  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5DD8  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5DDC  58F1       MOV [--R15], R1
  2F:5DDE  58F0       MOV [--R15], R0
  2F:5DE0  081B       MOV R1, R11
  2F:5DE2  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5DE6  4800       MOV R0, #0x0
  2F:5DE8  58F1       MOV [--R15], R1
  2F:5DEA  58F0       MOV [--R15], R0
> 2F:5DEC  BD03 4080  SCALL 03:4080
  2F:5DF0  50F8       ADD R15, #0x8
  2F:5DF2  081B       MOV R1, R11
  2F:5DF4  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5DF8  4800       MOV R0, #0x0
  2F:5DFA  58F1       MOV [--R15], R1
  2F:5DFC  58F0       MOV [--R15], R0
  2F:5DFE  081B       MOV R1, R11
  2F:5E00  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5E04  4800       MOV R0, #0x0
  2F:5E06  58F1       MOV [--R15], R1
  2F:5E08  58F0       MOV [--R15], R0
  2F:5E0A  BD03 4080  SCALL 03:4080
```

### `2F:5E0A` in `sub_2F_5A54`

```text
  2F:5DF2  081B       MOV R1, R11
  2F:5DF4  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5DF8  4800       MOV R0, #0x0
  2F:5DFA  58F1       MOV [--R15], R1
  2F:5DFC  58F0       MOV [--R15], R0
  2F:5DFE  081B       MOV R1, R11
  2F:5E00  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5E04  4800       MOV R0, #0x0
  2F:5E06  58F1       MOV [--R15], R1
  2F:5E08  58F0       MOV [--R15], R0
> 2F:5E0A  BD03 4080  SCALL 03:4080
  2F:5E0E  50F8       ADD R15, #0x8
  2F:5E10  4809       MOV R0, #0x9
  2F:5E12  58F0       MOV [--R15], R0
  2F:5E14  081B       MOV R1, R11
  2F:5E16  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5E1A  4800       MOV R0, #0x0
  2F:5E1C  58F1       MOV [--R15], R1
  2F:5E1E  58F0       MOV [--R15], R0
  2F:5E20  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5E24  58F0       MOV [--R15], R0
  2F:5E26  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5E2A  58F0       MOV [--R15], R0
```

### `2F:A9D8` in `sub_2F_A0B6`

```text
  2F:A9BE  50FA       ADD R15, #0xA
  2F:A9C0  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:A9C4  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A9C8  58F1       MOV [--R15], R1
  2F:A9CA  58F0       MOV [--R15], R0
  2F:A9CC  081B       MOV R1, R11
  2F:A9CE  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A9D2  4800       MOV R0, #0x0
  2F:A9D4  58F1       MOV [--R15], R1
  2F:A9D6  58F0       MOV [--R15], R0
> 2F:A9D8  BD03 4080  SCALL 03:4080
  2F:A9DC  50F8       ADD R15, #0x8
  2F:A9DE  081B       MOV R1, R11
  2F:A9E0  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:A9E4  4800       MOV R0, #0x0
  2F:A9E6  58F1       MOV [--R15], R1
  2F:A9E8  58F0       MOV [--R15], R0
  2F:A9EA  081B       MOV R1, R11
  2F:A9EC  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A9F0  4800       MOV R0, #0x0
  2F:A9F2  58F1       MOV [--R15], R1
  2F:A9F4  58F0       MOV [--R15], R0
  2F:A9F6  BD03 4080  SCALL 03:4080
```

### `2F:A9F6` in `sub_2F_A0B6`

```text
  2F:A9DE  081B       MOV R1, R11
  2F:A9E0  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:A9E4  4800       MOV R0, #0x0
  2F:A9E6  58F1       MOV [--R15], R1
  2F:A9E8  58F0       MOV [--R15], R0
  2F:A9EA  081B       MOV R1, R11
  2F:A9EC  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A9F0  4800       MOV R0, #0x0
  2F:A9F2  58F1       MOV [--R15], R1
  2F:A9F4  58F0       MOV [--R15], R0
> 2F:A9F6  BD03 4080  SCALL 03:4080
  2F:A9FA  50F8       ADD R15, #0x8
  2F:A9FC  081B       MOV R1, R11
  2F:A9FE  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AA02  4800       MOV R0, #0x0
  2F:AA04  58F1       MOV [--R15], R1
  2F:AA06  58F0       MOV [--R15], R0
  2F:AA08  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:AA0C  70F0 0024  ADD REG[0xF0], #0x0024
  2F:AA10  58F0       MOV [--R15], R0
  2F:AA12  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:AA16  70F0 0020  ADD REG[0xF0], #0x0020
  2F:AA1A  58F0       MOV [--R15], R0
```

### `2F:AC56` in `sub_2F_A0B6`

```text
  2F:AC3C  50FA       ADD R15, #0xA
  2F:AC3E  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AC42  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AC46  58F1       MOV [--R15], R1
  2F:AC48  58F0       MOV [--R15], R0
  2F:AC4A  081B       MOV R1, R11
  2F:AC4C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC50  4800       MOV R0, #0x0
  2F:AC52  58F1       MOV [--R15], R1
  2F:AC54  58F0       MOV [--R15], R0
> 2F:AC56  BD03 4080  SCALL 03:4080
  2F:AC5A  50F8       ADD R15, #0x8
  2F:AC5C  081B       MOV R1, R11
  2F:AC5E  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AC62  4800       MOV R0, #0x0
  2F:AC64  58F1       MOV [--R15], R1
  2F:AC66  58F0       MOV [--R15], R0
  2F:AC68  081B       MOV R1, R11
  2F:AC6A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC6E  4800       MOV R0, #0x0
  2F:AC70  58F1       MOV [--R15], R1
  2F:AC72  58F0       MOV [--R15], R0
  2F:AC74  BD03 4080  SCALL 03:4080
```

### `2F:AC74` in `sub_2F_A0B6`

```text
  2F:AC5C  081B       MOV R1, R11
  2F:AC5E  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AC62  4800       MOV R0, #0x0
  2F:AC64  58F1       MOV [--R15], R1
  2F:AC66  58F0       MOV [--R15], R0
  2F:AC68  081B       MOV R1, R11
  2F:AC6A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC6E  4800       MOV R0, #0x0
  2F:AC70  58F1       MOV [--R15], R1
  2F:AC72  58F0       MOV [--R15], R0
> 2F:AC74  BD03 4080  SCALL 03:4080
  2F:AC78  50F8       ADD R15, #0x8
  2F:AC7A  081B       MOV R1, R11
  2F:AC7C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC80  4800       MOV R0, #0x0
  2F:AC82  58F1       MOV [--R15], R1
  2F:AC84  58F0       MOV [--R15], R0
  2F:AC86  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:AC8A  70F0 0024  ADD REG[0xF0], #0x0024
  2F:AC8E  58F0       MOV [--R15], R0
  2F:AC90  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:AC94  70F0 005A  ADD REG[0xF0], #0x005A
  2F:AC98  58F0       MOV [--R15], R0
```

### `2F:AD74` in `sub_2F_A0B6`

```text
  2F:AD5A  50FA       ADD R15, #0xA
  2F:AD5C  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AD60  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AD64  58F1       MOV [--R15], R1
  2F:AD66  58F0       MOV [--R15], R0
  2F:AD68  081B       MOV R1, R11
  2F:AD6A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD6E  4800       MOV R0, #0x0
  2F:AD70  58F1       MOV [--R15], R1
  2F:AD72  58F0       MOV [--R15], R0
> 2F:AD74  BD03 4080  SCALL 03:4080
  2F:AD78  50F8       ADD R15, #0x8
  2F:AD7A  081B       MOV R1, R11
  2F:AD7C  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AD80  4800       MOV R0, #0x0
  2F:AD82  58F1       MOV [--R15], R1
  2F:AD84  58F0       MOV [--R15], R0
  2F:AD86  081B       MOV R1, R11
  2F:AD88  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD8C  4800       MOV R0, #0x0
  2F:AD8E  58F1       MOV [--R15], R1
  2F:AD90  58F0       MOV [--R15], R0
  2F:AD92  BD03 4080  SCALL 03:4080
```

### `2F:AD92` in `sub_2F_A0B6`

```text
  2F:AD7A  081B       MOV R1, R11
  2F:AD7C  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AD80  4800       MOV R0, #0x0
  2F:AD82  58F1       MOV [--R15], R1
  2F:AD84  58F0       MOV [--R15], R0
  2F:AD86  081B       MOV R1, R11
  2F:AD88  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD8C  4800       MOV R0, #0x0
  2F:AD8E  58F1       MOV [--R15], R1
  2F:AD90  58F0       MOV [--R15], R0
> 2F:AD92  BD03 4080  SCALL 03:4080
  2F:AD96  50F8       ADD R15, #0x8
  2F:AD98  081B       MOV R1, R11
  2F:AD9A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD9E  4800       MOV R0, #0x0
  2F:ADA0  58F1       MOV [--R15], R1
  2F:ADA2  58F0       MOV [--R15], R0
  2F:ADA4  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:ADA8  70F0 0031  ADD REG[0xF0], #0x0031
  2F:ADAC  58F0       MOV [--R15], R0
  2F:ADAE  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:ADB2  70F0 0020  ADD REG[0xF0], #0x0020
  2F:ADB6  58F0       MOV [--R15], R0
```

### `2F:AFF2` in `sub_2F_A0B6`

```text
  2F:AFD8  50FA       ADD R15, #0xA
  2F:AFDA  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AFDE  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AFE2  58F1       MOV [--R15], R1
  2F:AFE4  58F0       MOV [--R15], R0
  2F:AFE6  081B       MOV R1, R11
  2F:AFE8  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AFEC  4800       MOV R0, #0x0
  2F:AFEE  58F1       MOV [--R15], R1
  2F:AFF0  58F0       MOV [--R15], R0
> 2F:AFF2  BD03 4080  SCALL 03:4080
  2F:AFF6  50F8       ADD R15, #0x8
  2F:AFF8  081B       MOV R1, R11
  2F:AFFA  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AFFE  4800       MOV R0, #0x0
  2F:B000  58F1       MOV [--R15], R1
  2F:B002  58F0       MOV [--R15], R0
  2F:B004  081B       MOV R1, R11
  2F:B006  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B00A  4800       MOV R0, #0x0
  2F:B00C  58F1       MOV [--R15], R1
  2F:B00E  58F0       MOV [--R15], R0
  2F:B010  BD03 4080  SCALL 03:4080
```

### `2F:B010` in `sub_2F_A0B6`

```text
  2F:AFF8  081B       MOV R1, R11
  2F:AFFA  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AFFE  4800       MOV R0, #0x0
  2F:B000  58F1       MOV [--R15], R1
  2F:B002  58F0       MOV [--R15], R0
  2F:B004  081B       MOV R1, R11
  2F:B006  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B00A  4800       MOV R0, #0x0
  2F:B00C  58F1       MOV [--R15], R1
  2F:B00E  58F0       MOV [--R15], R0
> 2F:B010  BD03 4080  SCALL 03:4080
  2F:B014  50F8       ADD R15, #0x8
  2F:B016  081B       MOV R1, R11
  2F:B018  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B01C  4800       MOV R0, #0x0
  2F:B01E  58F1       MOV [--R15], R1
  2F:B020  58F0       MOV [--R15], R0
  2F:B022  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B026  70F0 0031  ADD REG[0xF0], #0x0031
  2F:B02A  58F0       MOV [--R15], R0
  2F:B02C  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B030  70F0 005A  ADD REG[0xF0], #0x005A
  2F:B034  58F0       MOV [--R15], R0
```

### `30:191A` in `sub_30_15FC`

```text
  30:1902  081B       MOV R1, R11
  30:1904  70F1 FFD0  ADD REG[0xF1], #0xFFD0
  30:1908  4800       MOV R0, #0x0
  30:190A  58F1       MOV [--R15], R1
  30:190C  58F0       MOV [--R15], R0
  30:190E  081B       MOV R1, R11
  30:1910  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1914  4800       MOV R0, #0x0
  30:1916  58F1       MOV [--R15], R1
  30:1918  58F0       MOV [--R15], R0
> 30:191A  BD03 4080  SCALL 03:4080
  30:191E  50F8       ADD R15, #0x8
  30:1920  6810 00A4  MOV REG[0x10], #0x00A4
  30:1924  88F0 792C  MOV REG[0xF0], [0x792C]
  30:1928  5600       CMP R0, #0x0
  30:192A  AC0D 1950  AJMP SLE, 30:1950
  30:192E  68F1 DBD4  MOV REG[0xF1], #0xDBD4
  30:1932  68F0 0031  MOV REG[0xF0], #0x0031
  30:1936  58F1       MOV [--R15], R1
  30:1938  58F0       MOV [--R15], R0
  30:193A  081B       MOV R1, R11
  30:193C  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1940  4800       MOV R0, #0x0
```

## `03:40B4`

Call sites: `2F:5A98`, `2F:5B22`, `2F:5B82`, `2F:5C48`, `2F:5CA8`, `2F:5D6E`, `2F:5DCE`, `2F:5E94`, `2F:5F1E`, `2F:60C4`, `2F:614E`, `2F:61D8`, `2F:A71E`, `2F:A80E`, `2F:A95C`, `2F:A9BA`, `2F:ABDA`, `2F:AC38`, `2F:ACF8`, `2F:AD56`, `2F:AF76`, `2F:AFD4`, `2F:B094`, `2F:B21E`, `2F:B2A2`, `2F:B73E`, `30:18FC`

### `2F:5A98` in `sub_2F_5A54`

```text
  2F:5A7E  58F0       MOV [--R15], R0
  2F:5A80  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5A84  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5A88  58F1       MOV [--R15], R1
  2F:5A8A  58F0       MOV [--R15], R0
  2F:5A8C  081B       MOV R1, R11
  2F:5A8E  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5A92  4800       MOV R0, #0x0
  2F:5A94  58F1       MOV [--R15], R1
  2F:5A96  58F0       MOV [--R15], R0
> 2F:5A98  BD03 40B4  SCALL 03:40B4
  2F:5A9C  50FA       ADD R15, #0xA
  2F:5A9E  4809       MOV R0, #0x9
  2F:5AA0  58F0       MOV [--R15], R0
  2F:5AA2  081B       MOV R1, R11
  2F:5AA4  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5AA8  4800       MOV R0, #0x0
  2F:5AAA  58F1       MOV [--R15], R1
  2F:5AAC  58F0       MOV [--R15], R0
  2F:5AAE  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5AB2  58F0       MOV [--R15], R0
  2F:5AB4  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5AB8  58F0       MOV [--R15], R0
```

### `2F:5B22` in `sub_2F_5A54`

```text
  2F:5B08  58F0       MOV [--R15], R0
  2F:5B0A  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5B0E  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5B12  58F1       MOV [--R15], R1
  2F:5B14  58F0       MOV [--R15], R0
  2F:5B16  081B       MOV R1, R11
  2F:5B18  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5B1C  4800       MOV R0, #0x0
  2F:5B1E  58F1       MOV [--R15], R1
  2F:5B20  58F0       MOV [--R15], R0
> 2F:5B22  BD03 40B4  SCALL 03:40B4
  2F:5B26  50FA       ADD R15, #0xA
  2F:5B28  68F1 0094  MOV REG[0xF1], #0x0094
  2F:5B2C  4800       MOV R0, #0x0
  2F:5B2E  6810 00A4  MOV REG[0x10], #0x00A4
  2F:5B32  99F3 7A44  MOVZE REG[0xF3], [0x7A44]
  2F:5B36  5630       CMP R3, #0x0
  2F:5B38  DE03       RJMP SGE, 2F:5B40 ; rel +3
  2F:5B3A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:5B3E  D001       RJMP ALWAYS, 2F:5B42 ; rel +1
  2F:5B40  4820       MOV R2, #0x0
  2F:5B42  58F3       MOV [--R15], R3
  2F:5B44  58F2       MOV [--R15], R2
```

### `2F:5B82` in `sub_2F_5A54`

```text
  2F:5B68  58F0       MOV [--R15], R0
  2F:5B6A  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5B6E  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5B72  58F1       MOV [--R15], R1
  2F:5B74  58F0       MOV [--R15], R0
  2F:5B76  081B       MOV R1, R11
  2F:5B78  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5B7C  4800       MOV R0, #0x0
  2F:5B7E  58F1       MOV [--R15], R1
  2F:5B80  58F0       MOV [--R15], R0
> 2F:5B82  BD03 40B4  SCALL 03:40B4
  2F:5B86  50FA       ADD R15, #0xA
  2F:5B88  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5B8C  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5B90  58F1       MOV [--R15], R1
  2F:5B92  58F0       MOV [--R15], R0
  2F:5B94  081B       MOV R1, R11
  2F:5B96  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5B9A  4800       MOV R0, #0x0
  2F:5B9C  58F1       MOV [--R15], R1
  2F:5B9E  58F0       MOV [--R15], R0
  2F:5BA0  BD03 4080  SCALL 03:4080
  2F:5BA4  50F8       ADD R15, #0x8
```

### `2F:5C48` in `sub_2F_5A54`

```text
  2F:5C2E  58F0       MOV [--R15], R0
  2F:5C30  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5C34  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5C38  58F1       MOV [--R15], R1
  2F:5C3A  58F0       MOV [--R15], R0
  2F:5C3C  081B       MOV R1, R11
  2F:5C3E  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5C42  4800       MOV R0, #0x0
  2F:5C44  58F1       MOV [--R15], R1
  2F:5C46  58F0       MOV [--R15], R0
> 2F:5C48  BD03 40B4  SCALL 03:40B4
  2F:5C4C  50FA       ADD R15, #0xA
  2F:5C4E  68F1 0094  MOV REG[0xF1], #0x0094
  2F:5C52  4800       MOV R0, #0x0
  2F:5C54  6810 00A4  MOV REG[0x10], #0x00A4
  2F:5C58  99F3 7A44  MOVZE REG[0xF3], [0x7A44]
  2F:5C5C  5630       CMP R3, #0x0
  2F:5C5E  DE03       RJMP SGE, 2F:5C66 ; rel +3
  2F:5C60  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:5C64  D001       RJMP ALWAYS, 2F:5C68 ; rel +1
  2F:5C66  4820       MOV R2, #0x0
  2F:5C68  58F3       MOV [--R15], R3
  2F:5C6A  58F2       MOV [--R15], R2
```

### `2F:5CA8` in `sub_2F_5A54`

```text
  2F:5C8E  58F0       MOV [--R15], R0
  2F:5C90  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5C94  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5C98  58F1       MOV [--R15], R1
  2F:5C9A  58F0       MOV [--R15], R0
  2F:5C9C  081B       MOV R1, R11
  2F:5C9E  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5CA2  4800       MOV R0, #0x0
  2F:5CA4  58F1       MOV [--R15], R1
  2F:5CA6  58F0       MOV [--R15], R0
> 2F:5CA8  BD03 40B4  SCALL 03:40B4
  2F:5CAC  50FA       ADD R15, #0xA
  2F:5CAE  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5CB2  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5CB6  58F1       MOV [--R15], R1
  2F:5CB8  58F0       MOV [--R15], R0
  2F:5CBA  081B       MOV R1, R11
  2F:5CBC  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5CC0  4800       MOV R0, #0x0
  2F:5CC2  58F1       MOV [--R15], R1
  2F:5CC4  58F0       MOV [--R15], R0
  2F:5CC6  BD03 4080  SCALL 03:4080
  2F:5CCA  50F8       ADD R15, #0x8
```

### `2F:5D6E` in `sub_2F_5A54`

```text
  2F:5D54  58F0       MOV [--R15], R0
  2F:5D56  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5D5A  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5D5E  58F1       MOV [--R15], R1
  2F:5D60  58F0       MOV [--R15], R0
  2F:5D62  081B       MOV R1, R11
  2F:5D64  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5D68  4800       MOV R0, #0x0
  2F:5D6A  58F1       MOV [--R15], R1
  2F:5D6C  58F0       MOV [--R15], R0
> 2F:5D6E  BD03 40B4  SCALL 03:40B4
  2F:5D72  50FA       ADD R15, #0xA
  2F:5D74  68F1 0094  MOV REG[0xF1], #0x0094
  2F:5D78  4800       MOV R0, #0x0
  2F:5D7A  6810 00A4  MOV REG[0x10], #0x00A4
  2F:5D7E  99F3 7A44  MOVZE REG[0xF3], [0x7A44]
  2F:5D82  5630       CMP R3, #0x0
  2F:5D84  DE03       RJMP SGE, 2F:5D8C ; rel +3
  2F:5D86  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:5D8A  D001       RJMP ALWAYS, 2F:5D8E ; rel +1
  2F:5D8C  4820       MOV R2, #0x0
  2F:5D8E  58F3       MOV [--R15], R3
  2F:5D90  58F2       MOV [--R15], R2
```

### `2F:5DCE` in `sub_2F_5A54`

```text
  2F:5DB4  58F0       MOV [--R15], R0
  2F:5DB6  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5DBA  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5DBE  58F1       MOV [--R15], R1
  2F:5DC0  58F0       MOV [--R15], R0
  2F:5DC2  081B       MOV R1, R11
  2F:5DC4  70F1 FFE6  ADD REG[0xF1], #0xFFE6
  2F:5DC8  4800       MOV R0, #0x0
  2F:5DCA  58F1       MOV [--R15], R1
  2F:5DCC  58F0       MOV [--R15], R0
> 2F:5DCE  BD03 40B4  SCALL 03:40B4
  2F:5DD2  50FA       ADD R15, #0xA
  2F:5DD4  68F1 58D0  MOV REG[0xF1], #0x58D0
  2F:5DD8  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5DDC  58F1       MOV [--R15], R1
  2F:5DDE  58F0       MOV [--R15], R0
  2F:5DE0  081B       MOV R1, R11
  2F:5DE2  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5DE6  4800       MOV R0, #0x0
  2F:5DE8  58F1       MOV [--R15], R1
  2F:5DEA  58F0       MOV [--R15], R0
  2F:5DEC  BD03 4080  SCALL 03:4080
  2F:5DF0  50F8       ADD R15, #0x8
```

### `2F:5E94` in `sub_2F_5A54`

```text
  2F:5E7A  58F0       MOV [--R15], R0
  2F:5E7C  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5E80  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5E84  58F1       MOV [--R15], R1
  2F:5E86  58F0       MOV [--R15], R0
  2F:5E88  081B       MOV R1, R11
  2F:5E8A  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5E8E  4800       MOV R0, #0x0
  2F:5E90  58F1       MOV [--R15], R1
  2F:5E92  58F0       MOV [--R15], R0
> 2F:5E94  BD03 40B4  SCALL 03:40B4
  2F:5E98  50FA       ADD R15, #0xA
  2F:5E9A  4809       MOV R0, #0x9
  2F:5E9C  58F0       MOV [--R15], R0
  2F:5E9E  081B       MOV R1, R11
  2F:5EA0  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5EA4  4800       MOV R0, #0x0
  2F:5EA6  58F1       MOV [--R15], R1
  2F:5EA8  58F0       MOV [--R15], R0
  2F:5EAA  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5EAE  58F0       MOV [--R15], R0
  2F:5EB0  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5EB4  58F0       MOV [--R15], R0
```

### `2F:5F1E` in `sub_2F_5A54`

```text
  2F:5F04  58F0       MOV [--R15], R0
  2F:5F06  68F1 5962  MOV REG[0xF1], #0x5962
  2F:5F0A  68F0 0030  MOV REG[0xF0], #0x0030
  2F:5F0E  58F1       MOV [--R15], R1
  2F:5F10  58F0       MOV [--R15], R0
  2F:5F12  081B       MOV R1, R11
  2F:5F14  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5F18  4800       MOV R0, #0x0
  2F:5F1A  58F1       MOV [--R15], R1
  2F:5F1C  58F0       MOV [--R15], R0
> 2F:5F1E  BD03 40B4  SCALL 03:40B4
  2F:5F22  50FA       ADD R15, #0xA
  2F:5F24  4809       MOV R0, #0x9
  2F:5F26  58F0       MOV [--R15], R0
  2F:5F28  081B       MOV R1, R11
  2F:5F2A  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:5F2E  4800       MOV R0, #0x0
  2F:5F30  58F1       MOV [--R15], R1
  2F:5F32  58F0       MOV [--R15], R0
  2F:5F34  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:5F38  58F0       MOV [--R15], R0
  2F:5F3A  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:5F3E  58F0       MOV [--R15], R0
```

### `2F:60C4` in `sub_2F_5A54`

```text
  2F:60AA  58F0       MOV [--R15], R0
  2F:60AC  68F1 5962  MOV REG[0xF1], #0x5962
  2F:60B0  68F0 0030  MOV REG[0xF0], #0x0030
  2F:60B4  58F1       MOV [--R15], R1
  2F:60B6  58F0       MOV [--R15], R0
  2F:60B8  081B       MOV R1, R11
  2F:60BA  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:60BE  4800       MOV R0, #0x0
  2F:60C0  58F1       MOV [--R15], R1
  2F:60C2  58F0       MOV [--R15], R0
> 2F:60C4  BD03 40B4  SCALL 03:40B4
  2F:60C8  50FA       ADD R15, #0xA
  2F:60CA  4808       MOV R0, #0x8
  2F:60CC  58F0       MOV [--R15], R0
  2F:60CE  081B       MOV R1, R11
  2F:60D0  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:60D4  4800       MOV R0, #0x0
  2F:60D6  58F1       MOV [--R15], R1
  2F:60D8  58F0       MOV [--R15], R0
  2F:60DA  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:60DE  58F0       MOV [--R15], R0
  2F:60E0  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:60E4  58F0       MOV [--R15], R0
```

### `2F:614E` in `sub_2F_5A54`

```text
  2F:6134  58F0       MOV [--R15], R0
  2F:6136  68F1 5962  MOV REG[0xF1], #0x5962
  2F:613A  68F0 0030  MOV REG[0xF0], #0x0030
  2F:613E  58F1       MOV [--R15], R1
  2F:6140  58F0       MOV [--R15], R0
  2F:6142  081B       MOV R1, R11
  2F:6144  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:6148  4800       MOV R0, #0x0
  2F:614A  58F1       MOV [--R15], R1
  2F:614C  58F0       MOV [--R15], R0
> 2F:614E  BD03 40B4  SCALL 03:40B4
  2F:6152  50FA       ADD R15, #0xA
  2F:6154  4808       MOV R0, #0x8
  2F:6156  58F0       MOV [--R15], R0
  2F:6158  081B       MOV R1, R11
  2F:615A  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:615E  4800       MOV R0, #0x0
  2F:6160  58F1       MOV [--R15], R1
  2F:6162  58F0       MOV [--R15], R0
  2F:6164  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:6168  58F0       MOV [--R15], R0
  2F:616A  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:616E  58F0       MOV [--R15], R0
```

### `2F:61D8` in `sub_2F_5A54`

```text
  2F:61BE  58F0       MOV [--R15], R0
  2F:61C0  68F1 5962  MOV REG[0xF1], #0x5962
  2F:61C4  68F0 0030  MOV REG[0xF0], #0x0030
  2F:61C8  58F1       MOV [--R15], R1
  2F:61CA  58F0       MOV [--R15], R0
  2F:61CC  081B       MOV R1, R11
  2F:61CE  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:61D2  4800       MOV R0, #0x0
  2F:61D4  58F1       MOV [--R15], R1
  2F:61D6  58F0       MOV [--R15], R0
> 2F:61D8  BD03 40B4  SCALL 03:40B4
  2F:61DC  50FA       ADD R15, #0xA
  2F:61DE  4808       MOV R0, #0x8
  2F:61E0  58F0       MOV [--R15], R0
  2F:61E2  081B       MOV R1, R11
  2F:61E4  70F1 FFEE  ADD REG[0xF1], #0xFFEE
  2F:61E8  4800       MOV R0, #0x0
  2F:61EA  58F1       MOV [--R15], R1
  2F:61EC  58F0       MOV [--R15], R0
  2F:61EE  780B FFFE  MOV R0, [R11+0xFFFE]
  2F:61F2  58F0       MOV [--R15], R0
  2F:61F4  780B FFFC  MOV R0, [R11+0xFFFC]
  2F:61F8  58F0       MOV [--R15], R0
```

### `2F:A71E` in `sub_2F_A0B6`

```text
  2F:A704  58F0       MOV [--R15], R0
  2F:A706  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:A70A  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A70E  58F1       MOV [--R15], R1
  2F:A710  58F0       MOV [--R15], R0
  2F:A712  081B       MOV R1, R11
  2F:A714  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A718  4800       MOV R0, #0x0
  2F:A71A  58F1       MOV [--R15], R1
  2F:A71C  58F0       MOV [--R15], R0
> 2F:A71E  BD03 40B4  SCALL 03:40B4
  2F:A722  50FA       ADD R15, #0xA
  2F:A724  081B       MOV R1, R11
  2F:A726  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A72A  4800       MOV R0, #0x0
  2F:A72C  58F1       MOV [--R15], R1
  2F:A72E  58F0       MOV [--R15], R0
  2F:A730  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:A734  70F0 0017  ADD REG[0xF0], #0x0017
  2F:A738  58F0       MOV [--R15], R0
  2F:A73A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:A73E  70F0 002D  ADD REG[0xF0], #0x002D
  2F:A742  58F0       MOV [--R15], R0
```

### `2F:A80E` in `sub_2F_A0B6`

```text
  2F:A7F4  58F0       MOV [--R15], R0
  2F:A7F6  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:A7FA  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A7FE  58F1       MOV [--R15], R1
  2F:A800  58F0       MOV [--R15], R0
  2F:A802  081B       MOV R1, R11
  2F:A804  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A808  4800       MOV R0, #0x0
  2F:A80A  58F1       MOV [--R15], R1
  2F:A80C  58F0       MOV [--R15], R0
> 2F:A80E  BD03 40B4  SCALL 03:40B4
  2F:A812  50FA       ADD R15, #0xA
  2F:A814  081B       MOV R1, R11
  2F:A816  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A81A  4800       MOV R0, #0x0
  2F:A81C  58F1       MOV [--R15], R1
  2F:A81E  58F0       MOV [--R15], R0
  2F:A820  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:A824  70F0 0017  ADD REG[0xF0], #0x0017
  2F:A828  58F0       MOV [--R15], R0
  2F:A82A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:A82E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:A832  58F0       MOV [--R15], R0
```

### `2F:A95C` in `sub_2F_A0B6`

```text
  2F:A942  58F0       MOV [--R15], R0
  2F:A944  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:A948  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A94C  58F1       MOV [--R15], R1
  2F:A94E  58F0       MOV [--R15], R0
  2F:A950  081B       MOV R1, R11
  2F:A952  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A956  4800       MOV R0, #0x0
  2F:A958  58F1       MOV [--R15], R1
  2F:A95A  58F0       MOV [--R15], R0
> 2F:A95C  BD03 40B4  SCALL 03:40B4
  2F:A960  50FA       ADD R15, #0xA
  2F:A962  68F1 0094  MOV REG[0xF1], #0x0094
  2F:A966  4800       MOV R0, #0x0
  2F:A968  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:A96C  1937       MOVZE R3, RB7
  2F:A96E  5630       CMP R3, #0x0
  2F:A970  DE03       RJMP SGE, 2F:A978 ; rel +3
  2F:A972  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:A976  D001       RJMP ALWAYS, 2F:A97A ; rel +1
  2F:A978  4820       MOV R2, #0x0
  2F:A97A  58F3       MOV [--R15], R3
  2F:A97C  58F2       MOV [--R15], R2
```

### `2F:A9BA` in `sub_2F_A0B6`

```text
  2F:A9A0  58F0       MOV [--R15], R0
  2F:A9A2  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:A9A6  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A9AA  58F1       MOV [--R15], R1
  2F:A9AC  58F0       MOV [--R15], R0
  2F:A9AE  081B       MOV R1, R11
  2F:A9B0  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:A9B4  4800       MOV R0, #0x0
  2F:A9B6  58F1       MOV [--R15], R1
  2F:A9B8  58F0       MOV [--R15], R0
> 2F:A9BA  BD03 40B4  SCALL 03:40B4
  2F:A9BE  50FA       ADD R15, #0xA
  2F:A9C0  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:A9C4  68F0 0031  MOV REG[0xF0], #0x0031
  2F:A9C8  58F1       MOV [--R15], R1
  2F:A9CA  58F0       MOV [--R15], R0
  2F:A9CC  081B       MOV R1, R11
  2F:A9CE  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A9D2  4800       MOV R0, #0x0
  2F:A9D4  58F1       MOV [--R15], R1
  2F:A9D6  58F0       MOV [--R15], R0
  2F:A9D8  BD03 4080  SCALL 03:4080
  2F:A9DC  50F8       ADD R15, #0x8
```

### `2F:ABDA` in `sub_2F_A0B6`

```text
  2F:ABC0  58F0       MOV [--R15], R0
  2F:ABC2  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:ABC6  68F0 0031  MOV REG[0xF0], #0x0031
  2F:ABCA  58F1       MOV [--R15], R1
  2F:ABCC  58F0       MOV [--R15], R0
  2F:ABCE  081B       MOV R1, R11
  2F:ABD0  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:ABD4  4800       MOV R0, #0x0
  2F:ABD6  58F1       MOV [--R15], R1
  2F:ABD8  58F0       MOV [--R15], R0
> 2F:ABDA  BD03 40B4  SCALL 03:40B4
  2F:ABDE  50FA       ADD R15, #0xA
  2F:ABE0  68F1 0094  MOV REG[0xF1], #0x0094
  2F:ABE4  4800       MOV R0, #0x0
  2F:ABE6  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:ABEA  1937       MOVZE R3, RB7
  2F:ABEC  5630       CMP R3, #0x0
  2F:ABEE  DE03       RJMP SGE, 2F:ABF6 ; rel +3
  2F:ABF0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:ABF4  D001       RJMP ALWAYS, 2F:ABF8 ; rel +1
  2F:ABF6  4820       MOV R2, #0x0
  2F:ABF8  58F3       MOV [--R15], R3
  2F:ABFA  58F2       MOV [--R15], R2
```

### `2F:AC38` in `sub_2F_A0B6`

```text
  2F:AC1E  58F0       MOV [--R15], R0
  2F:AC20  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:AC24  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AC28  58F1       MOV [--R15], R1
  2F:AC2A  58F0       MOV [--R15], R0
  2F:AC2C  081B       MOV R1, R11
  2F:AC2E  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AC32  4800       MOV R0, #0x0
  2F:AC34  58F1       MOV [--R15], R1
  2F:AC36  58F0       MOV [--R15], R0
> 2F:AC38  BD03 40B4  SCALL 03:40B4
  2F:AC3C  50FA       ADD R15, #0xA
  2F:AC3E  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AC42  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AC46  58F1       MOV [--R15], R1
  2F:AC48  58F0       MOV [--R15], R0
  2F:AC4A  081B       MOV R1, R11
  2F:AC4C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC50  4800       MOV R0, #0x0
  2F:AC52  58F1       MOV [--R15], R1
  2F:AC54  58F0       MOV [--R15], R0
  2F:AC56  BD03 4080  SCALL 03:4080
  2F:AC5A  50F8       ADD R15, #0x8
```

### `2F:ACF8` in `sub_2F_A0B6`

```text
  2F:ACDE  58F0       MOV [--R15], R0
  2F:ACE0  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:ACE4  68F0 0031  MOV REG[0xF0], #0x0031
  2F:ACE8  58F1       MOV [--R15], R1
  2F:ACEA  58F0       MOV [--R15], R0
  2F:ACEC  081B       MOV R1, R11
  2F:ACEE  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:ACF2  4800       MOV R0, #0x0
  2F:ACF4  58F1       MOV [--R15], R1
  2F:ACF6  58F0       MOV [--R15], R0
> 2F:ACF8  BD03 40B4  SCALL 03:40B4
  2F:ACFC  50FA       ADD R15, #0xA
  2F:ACFE  68F1 0094  MOV REG[0xF1], #0x0094
  2F:AD02  4800       MOV R0, #0x0
  2F:AD04  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:AD08  1937       MOVZE R3, RB7
  2F:AD0A  5630       CMP R3, #0x0
  2F:AD0C  DE03       RJMP SGE, 2F:AD14 ; rel +3
  2F:AD0E  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:AD12  D001       RJMP ALWAYS, 2F:AD16 ; rel +1
  2F:AD14  4820       MOV R2, #0x0
  2F:AD16  58F3       MOV [--R15], R3
  2F:AD18  58F2       MOV [--R15], R2
```

### `2F:AD56` in `sub_2F_A0B6`

```text
  2F:AD3C  58F0       MOV [--R15], R0
  2F:AD3E  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:AD42  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AD46  58F1       MOV [--R15], R1
  2F:AD48  58F0       MOV [--R15], R0
  2F:AD4A  081B       MOV R1, R11
  2F:AD4C  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AD50  4800       MOV R0, #0x0
  2F:AD52  58F1       MOV [--R15], R1
  2F:AD54  58F0       MOV [--R15], R0
> 2F:AD56  BD03 40B4  SCALL 03:40B4
  2F:AD5A  50FA       ADD R15, #0xA
  2F:AD5C  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AD60  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AD64  58F1       MOV [--R15], R1
  2F:AD66  58F0       MOV [--R15], R0
  2F:AD68  081B       MOV R1, R11
  2F:AD6A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD6E  4800       MOV R0, #0x0
  2F:AD70  58F1       MOV [--R15], R1
  2F:AD72  58F0       MOV [--R15], R0
  2F:AD74  BD03 4080  SCALL 03:4080
  2F:AD78  50F8       ADD R15, #0x8
```

### `2F:AF76` in `sub_2F_A0B6`

```text
  2F:AF5C  58F0       MOV [--R15], R0
  2F:AF5E  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:AF62  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AF66  58F1       MOV [--R15], R1
  2F:AF68  58F0       MOV [--R15], R0
  2F:AF6A  081B       MOV R1, R11
  2F:AF6C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AF70  4800       MOV R0, #0x0
  2F:AF72  58F1       MOV [--R15], R1
  2F:AF74  58F0       MOV [--R15], R0
> 2F:AF76  BD03 40B4  SCALL 03:40B4
  2F:AF7A  50FA       ADD R15, #0xA
  2F:AF7C  68F1 0094  MOV REG[0xF1], #0x0094
  2F:AF80  4800       MOV R0, #0x0
  2F:AF82  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:AF86  1937       MOVZE R3, RB7
  2F:AF88  5630       CMP R3, #0x0
  2F:AF8A  DE03       RJMP SGE, 2F:AF92 ; rel +3
  2F:AF8C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:AF90  D001       RJMP ALWAYS, 2F:AF94 ; rel +1
  2F:AF92  4820       MOV R2, #0x0
  2F:AF94  58F3       MOV [--R15], R3
  2F:AF96  58F2       MOV [--R15], R2
```

### `2F:AFD4` in `sub_2F_A0B6`

```text
  2F:AFBA  58F0       MOV [--R15], R0
  2F:AFBC  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:AFC0  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AFC4  58F1       MOV [--R15], R1
  2F:AFC6  58F0       MOV [--R15], R0
  2F:AFC8  081B       MOV R1, R11
  2F:AFCA  70F1 FFDC  ADD REG[0xF1], #0xFFDC
  2F:AFCE  4800       MOV R0, #0x0
  2F:AFD0  58F1       MOV [--R15], R1
  2F:AFD2  58F0       MOV [--R15], R0
> 2F:AFD4  BD03 40B4  SCALL 03:40B4
  2F:AFD8  50FA       ADD R15, #0xA
  2F:AFDA  68F1 DBFE  MOV REG[0xF1], #0xDBFE
  2F:AFDE  68F0 0031  MOV REG[0xF0], #0x0031
  2F:AFE2  58F1       MOV [--R15], R1
  2F:AFE4  58F0       MOV [--R15], R0
  2F:AFE6  081B       MOV R1, R11
  2F:AFE8  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AFEC  4800       MOV R0, #0x0
  2F:AFEE  58F1       MOV [--R15], R1
  2F:AFF0  58F0       MOV [--R15], R0
  2F:AFF2  BD03 4080  SCALL 03:4080
  2F:AFF6  50F8       ADD R15, #0x8
```

### `2F:B094` in `sub_2F_A0B6`

```text
  2F:B07A  58F0       MOV [--R15], R0
  2F:B07C  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:B080  68F0 0031  MOV REG[0xF0], #0x0031
  2F:B084  58F1       MOV [--R15], R1
  2F:B086  58F0       MOV [--R15], R0
  2F:B088  081B       MOV R1, R11
  2F:B08A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B08E  4800       MOV R0, #0x0
  2F:B090  58F1       MOV [--R15], R1
  2F:B092  58F0       MOV [--R15], R0
> 2F:B094  BD03 40B4  SCALL 03:40B4
  2F:B098  50FA       ADD R15, #0xA
  2F:B09A  081B       MOV R1, R11
  2F:B09C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B0A0  4800       MOV R0, #0x0
  2F:B0A2  58F1       MOV [--R15], R1
  2F:B0A4  58F0       MOV [--R15], R0
  2F:B0A6  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B0AA  70F0 003E  ADD REG[0xF0], #0x003E
  2F:B0AE  58F0       MOV [--R15], R0
  2F:B0B0  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B0B4  70F0 002D  ADD REG[0xF0], #0x002D
  2F:B0B8  58F0       MOV [--R15], R0
```

### `2F:B21E` in `sub_2F_A0B6`

```text
  2F:B204  58F0       MOV [--R15], R0
  2F:B206  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:B20A  68F0 0031  MOV REG[0xF0], #0x0031
  2F:B20E  58F1       MOV [--R15], R1
  2F:B210  58F0       MOV [--R15], R0
  2F:B212  081B       MOV R1, R11
  2F:B214  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B218  4800       MOV R0, #0x0
  2F:B21A  58F1       MOV [--R15], R1
  2F:B21C  58F0       MOV [--R15], R0
> 2F:B21E  BD03 40B4  SCALL 03:40B4
  2F:B222  50FA       ADD R15, #0xA
  2F:B224  081B       MOV R1, R11
  2F:B226  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B22A  4800       MOV R0, #0x0
  2F:B22C  58F1       MOV [--R15], R1
  2F:B22E  58F0       MOV [--R15], R0
  2F:B230  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B234  70F0 003E  ADD REG[0xF0], #0x003E
  2F:B238  58F0       MOV [--R15], R0
  2F:B23A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B23E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:B242  58F0       MOV [--R15], R0
```

### `2F:B2A2` in `sub_2F_A0B6`

```text
  2F:B288  58F0       MOV [--R15], R0
  2F:B28A  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:B28E  68F0 0031  MOV REG[0xF0], #0x0031
  2F:B292  58F1       MOV [--R15], R1
  2F:B294  58F0       MOV [--R15], R0
  2F:B296  081B       MOV R1, R11
  2F:B298  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B29C  4800       MOV R0, #0x0
  2F:B29E  58F1       MOV [--R15], R1
  2F:B2A0  58F0       MOV [--R15], R0
> 2F:B2A2  BD03 40B4  SCALL 03:40B4
  2F:B2A6  50FA       ADD R15, #0xA
  2F:B2A8  081B       MOV R1, R11
  2F:B2AA  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B2AE  4800       MOV R0, #0x0
  2F:B2B0  58F1       MOV [--R15], R1
  2F:B2B2  58F0       MOV [--R15], R0
  2F:B2B4  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B2B8  70F0 004B  ADD REG[0xF0], #0x004B
  2F:B2BC  58F0       MOV [--R15], R0
  2F:B2BE  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B2C2  70F0 002D  ADD REG[0xF0], #0x002D
  2F:B2C6  58F0       MOV [--R15], R0
```

### `2F:B73E` in `sub_2F_B514`

```text
  2F:B724  58F0       MOV [--R15], R0
  2F:B726  68F1 DC00  MOV REG[0xF1], #0xDC00
  2F:B72A  68F0 0031  MOV REG[0xF0], #0x0031
  2F:B72E  58F1       MOV [--R15], R1
  2F:B730  58F0       MOV [--R15], R0
  2F:B732  081B       MOV R1, R11
  2F:B734  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B738  4800       MOV R0, #0x0
  2F:B73A  58F1       MOV [--R15], R1
  2F:B73C  58F0       MOV [--R15], R0
> 2F:B73E  BD03 40B4  SCALL 03:40B4
  2F:B742  50FA       ADD R15, #0xA
  2F:B744  081B       MOV R1, R11
  2F:B746  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B74A  4800       MOV R0, #0x0
  2F:B74C  58F1       MOV [--R15], R1
  2F:B74E  58F0       MOV [--R15], R0
  2F:B750  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B754  70F0 004B  ADD REG[0xF0], #0x004B
  2F:B758  58F0       MOV [--R15], R0
  2F:B75A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B75E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:B762  58F0       MOV [--R15], R0
```

### `30:18FC` in `sub_30_15FC`

```text
  30:18E2  58F0       MOV [--R15], R0
  30:18E4  68F1 DC00  MOV REG[0xF1], #0xDC00
  30:18E8  68F0 0031  MOV REG[0xF0], #0x0031
  30:18EC  58F1       MOV [--R15], R1
  30:18EE  58F0       MOV [--R15], R0
  30:18F0  081B       MOV R1, R11
  30:18F2  70F1 FFD0  ADD REG[0xF1], #0xFFD0
  30:18F6  4800       MOV R0, #0x0
  30:18F8  58F1       MOV [--R15], R1
  30:18FA  58F0       MOV [--R15], R0
> 30:18FC  BD03 40B4  SCALL 03:40B4
  30:1900  50FA       ADD R15, #0xA
  30:1902  081B       MOV R1, R11
  30:1904  70F1 FFD0  ADD REG[0xF1], #0xFFD0
  30:1908  4800       MOV R0, #0x0
  30:190A  58F1       MOV [--R15], R1
  30:190C  58F0       MOV [--R15], R0
  30:190E  081B       MOV R1, R11
  30:1910  70F1 FFE4  ADD REG[0xF1], #0xFFE4
  30:1914  4800       MOV R0, #0x0
  30:1916  58F1       MOV [--R15], R1
  30:1918  58F0       MOV [--R15], R0
  30:191A  BD03 4080  SCALL 03:4080
```

## `03:4120`

Call sites: `2F:B774`, `2F:BD58`, `2F:C042`, `2F:C290`, `30:2596`, `30:25A6`

### `2F:B774` in `sub_2F_B514`

```text
  2F:B754  70F0 004B  ADD REG[0xF0], #0x004B
  2F:B758  58F0       MOV [--R15], R0
  2F:B75A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B75E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:B762  58F0       MOV [--R15], R0
  2F:B764  BD03 41A8  SCALL 03:41A8
  2F:B768  50F8       ADD R15, #0x8
  2F:B76A  BD33 2FF2  SCALL 33:2FF2
  2F:B76E  68F0 0050  MOV REG[0xF0], #0x0050
  2F:B772  58F0       MOV [--R15], R0
> 2F:B774  BD03 4120  SCALL 03:4120
  2F:B778  50F2       ADD R15, #0x2
  2F:B77A  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2F:B77E  1901       MOVZE R0, RB1
  2F:B780  58F0       MOV [--R15], R0
  2F:B782  BD26 C174  SCALL 26:C174
  2F:B786  50F2       ADD R15, #0x2
  2F:B788  68F1 0094  MOV REG[0xF1], #0x0094
  2F:B78C  4800       MOV R0, #0x0
  2F:B78E  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:B792  1937       MOVZE R3, RB7
  2F:B794  5630       CMP R3, #0x0
  2F:B796  DE03       RJMP SGE, 2F:B79E ; rel +3
```

### `2F:BD58` in `sub_2F_B8A4`

```text
  2F:BD40  58F1       MOV [--R15], R1
  2F:BD42  58F0       MOV [--R15], R0
  2F:BD44  480A       MOV R0, #0xA
  2F:BD46  58F0       MOV [--R15], R0
  2F:BD48  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD4C  58F0       MOV [--R15], R0
  2F:BD4E  BD03 41A8  SCALL 03:41A8
  2F:BD52  50F8       ADD R15, #0x8
  2F:BD54  480A       MOV R0, #0xA
  2F:BD56  58F0       MOV [--R15], R0
> 2F:BD58  BD03 4120  SCALL 03:4120
  2F:BD5C  50F2       ADD R15, #0x2
  2F:BD5E  4800       MOV R0, #0x0
  2F:BD60  58F0       MOV [--R15], R0
  2F:BD62  4801       MOV R0, #0x1
  2F:BD64  58F0       MOV [--R15], R0
  2F:BD66  BD03 41C8  SCALL 03:41C8
  2F:BD6A  50F4       ADD R15, #0x4
  2F:BD6C  68F0 0017  MOV REG[0xF0], #0x0017
  2F:BD70  58F0       MOV [--R15], R0
  2F:BD72  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:BD76  58F0       MOV [--R15], R0
  2F:BD78  480A       MOV R0, #0xA
```

### `2F:C042` in `sub_2F_BFBC`

```text
  2F:C02A  58F0       MOV [--R15], R0
  2F:C02C  1F90       POP REG[0x10]
  2F:C02E  4D11       SR R1, #0x1
  2F:C030  2911       MOVB RB1, [R1]
  2F:C032  1901       MOVZE R0, RB1
  2F:C034  58F0       MOV [--R15], R0
  2F:C036  BD31 467C  SCALL 31:467C
  2F:C03A  50FE       ADD R15, #0xE
  2F:C03C  68F0 0096  MOV REG[0xF0], #0x0096
  2F:C040  58F0       MOV [--R15], R0
> 2F:C042  BD03 4120  SCALL 03:4120
  2F:C046  50F2       ADD R15, #0x2
  2F:C048  791B FFFD  MOVB RB1, [R11+0xFFFD]
  2F:C04C  1901       MOVZE R0, RB1
  2F:C04E  5001       ADD R0, #0x1
  2F:C050  6B1B FFFD  MOVB [R11+0xFFFD], RB1
  2F:C054  791B FFFD  MOVB RB1, [R11+0xFFFD]
  2F:C058  1901       MOVZE R0, RB1
  2F:C05A  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C05E  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  2F:C062  1601       CMP R0, R1
  2F:C064  AC09 BDB4  AJMP SL, 2F:BDB4
  2F:C068  4930       MOVB RB3, #0x0
```

### `2F:C290` in `sub_2F_C216`

```text
  2F:C276  58F1       MOV [--R15], R1
  2F:C278  58F0       MOV [--R15], R0
  2F:C27A  480A       MOV R0, #0xA
  2F:C27C  58F0       MOV [--R15], R0
  2F:C27E  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C282  58F0       MOV [--R15], R0
  2F:C284  BD03 41A8  SCALL 03:41A8
  2F:C288  50F8       ADD R15, #0x8
  2F:C28A  68F0 0064  MOV REG[0xF0], #0x0064
  2F:C28E  58F0       MOV [--R15], R0
> 2F:C290  BD03 4120  SCALL 03:4120
  2F:C294  50F2       ADD R15, #0x2
  2F:C296  4800       MOV R0, #0x0
  2F:C298  58F0       MOV [--R15], R0
  2F:C29A  4801       MOV R0, #0x1
  2F:C29C  58F0       MOV [--R15], R0
  2F:C29E  BD03 41C8  SCALL 03:41C8
  2F:C2A2  50F4       ADD R15, #0x4
  2F:C2A4  68F0 0017  MOV REG[0xF0], #0x0017
  2F:C2A8  58F0       MOV [--R15], R0
  2F:C2AA  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:C2AE  58F0       MOV [--R15], R0
  2F:C2B0  480A       MOV R0, #0xA
```

### `30:2596` in `sub_30_1EAA`

```text
  30:257A  BD33 2FF2  SCALL 33:2FF2
  30:257E  4811       MOV R1, #0x1
  30:2580  58F1       MOV [--R15], R1
  30:2582  BD03 4224  SCALL 03:4224
  30:2586  50F2       ADD R15, #0x2
  30:2588  781B FFCE  MOV R1, [R11+0xFFCE]
  30:258C  5610       CMP R1, #0x0
  30:258E  AC02 25A0  AJMP NZ/NE, 30:25A0
  30:2592  4815       MOV R1, #0x5
  30:2594  58F1       MOV [--R15], R1
> 30:2596  BD03 4120  SCALL 03:4120
  30:259A  50F2       ADD R15, #0x2
  30:259C  AC00 25AC  AJMP ALWAYS, 30:25AC
  30:25A0  68F0 001E  MOV REG[0xF0], #0x001E
  30:25A4  58F0       MOV [--R15], R0
  30:25A6  BD03 4120  SCALL 03:4120
  30:25AA  50F2       ADD R15, #0x2
  30:25AC  BD03 422C  SCALL 03:422C
  30:25B0  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25B4  5001       ADD R0, #0x1
  30:25B6  6A0B FFCE  MOV [R11+0xFFCE], R0
  30:25BA  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25BE  5603       CMP R0, #0x3
```

### `30:25A6` in `sub_30_1EAA`

```text
  30:2588  781B FFCE  MOV R1, [R11+0xFFCE]
  30:258C  5610       CMP R1, #0x0
  30:258E  AC02 25A0  AJMP NZ/NE, 30:25A0
  30:2592  4815       MOV R1, #0x5
  30:2594  58F1       MOV [--R15], R1
  30:2596  BD03 4120  SCALL 03:4120
  30:259A  50F2       ADD R15, #0x2
  30:259C  AC00 25AC  AJMP ALWAYS, 30:25AC
  30:25A0  68F0 001E  MOV REG[0xF0], #0x001E
  30:25A4  58F0       MOV [--R15], R0
> 30:25A6  BD03 4120  SCALL 03:4120
  30:25AA  50F2       ADD R15, #0x2
  30:25AC  BD03 422C  SCALL 03:422C
  30:25B0  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25B4  5001       ADD R0, #0x1
  30:25B6  6A0B FFCE  MOV [R11+0xFFCE], R0
  30:25BA  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25BE  5603       CMP R0, #0x3
  30:25C0  AC09 138C  AJMP SL, 30:138C
  30:25C4  387F       MOV R7, [R15++]
  30:25C6  386F       MOV R6, [R15++]
  30:25C8  385F       MOV R5, [R15++]
  30:25CA  384F       MOV R4, [R15++]
```

## `03:4124`

Call sites: `2F:B9E4`, `32:D610`, `32:D8CE`, `32:E09A`, `32:E194`, `33:6EFE`

### `2F:B9E4` in `sub_2F_B8A4`

```text
  2F:B9C8  1F90       POP REG[0x10]
  2F:B9CA  4D11       SR R1, #0x1
  2F:B9CC  2911       MOVB RB1, [R1]
  2F:B9CE  1901       MOVZE R0, RB1
  2F:B9D0  5606       CMP R0, #0x6
  2F:B9D2  AC02 C664  AJMP NZ/NE, 2F:C664
  2F:B9D6  6810 00A4  MOV REG[0x10], #0x00A4
  2F:B9DA  99F0 7A9A  MOVZE REG[0xF0], [0x7A9A]
  2F:B9DE  5600       CMP R0, #0x0
  2F:B9E0  AC02 C256  AJMP NZ/NE, 2F:C256
> 2F:B9E4  BD03 4124  SCALL 03:4124
  2F:B9E8  0870       MOV R7, R0
  2F:B9EA  68F0 0064  MOV REG[0xF0], #0x0064
  2F:B9EE  C300       UDIV R0
  2F:B9F0  6A6B FFFE  MOV [R11+0xFFFE], R6
  2F:B9F4  786B FFFE  MOV R6, [R11+0xFFFE]
  2F:B9F8  566A       CMP R6, #0xA
  2F:B9FA  AC0E BD9A  AJMP SGE, 2F:BD9A
  2F:B9FE  4860       MOV R6, #0x0
  2F:BA00  6A6B FFFE  MOV [R11+0xFFFE], R6
  2F:BA04  AC00 BD16  AJMP ALWAYS, 2F:BD16
  2F:BA08  68F1 0094  MOV REG[0xF1], #0x0094
  2F:BA0C  4800       MOV R0, #0x0
```

### `32:D610` in `sub_32_D530`

```text
  32:D5EC  AC02 D610  AJMP NZ/NE, 32:D610
  32:D5F0  6810 00A4  MOV REG[0x10], #0x00A4
  32:D5F4  99F0 7ACC  MOVZE REG[0xF0], [0x7ACC]
  32:D5F8  6810 00A4  MOV REG[0x10], #0x00A4
  32:D5FC  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  32:D600  5012       ADD R1, #0x2
  32:D602  1601       CMP R0, R1
  32:D604  AC02 D610  AJMP NZ/NE, 32:D610
  32:D608  68F1 0050  MOV REG[0xF1], #0x0050
  32:D60C  6A1B FFF8  MOV [R11+0xFFF8], R1
> 32:D610  BD03 4124  SCALL 03:4124
  32:D614  0870       MOV R7, R0
  32:D616  68F0 0064  MOV REG[0xF0], #0x0064
  32:D61A  C300       UDIV R0
  32:D61C  6A6B FFF6  MOV [R11+0xFFF6], R6
  32:D620  786B FFF6  MOV R6, [R11+0xFFF6]
  32:D624  781B FFF8  MOV R1, [R11+0xFFF8]
  32:D628  1661       CMP R6, R1
  32:D62A  AC09 D694  AJMP SL, 32:D694
  32:D62E  68F1 0094  MOV REG[0xF1], #0x0094
  32:D632  4800       MOV R0, #0x0
  32:D634  797B FFFB  MOVB RB7, [R11+0xFFFB]
  32:D638  1937       MOVZE R3, RB7
```

### `32:D8CE` in `sub_32_D530`

```text
  32:D8BA  59F5       MOVB [--R15], RB5
  32:D8BC  52F1       SUB R15, #0x1
  32:D8BE  4C11       SL R1, #0x1
  32:D8C0  5C01       SLOSB R0, #0x1
  32:D8C2  4D11       SR R1, #0x1
  32:D8C4  58F0       MOV [--R15], R0
  32:D8C6  1F90       POP REG[0x10]
  32:D8C8  3F01       CRIT #1
  32:D8CA  50F1       ADD R15, #0x1
  32:D8CC  3B1F       MOVB [R1], [R15++]
> 32:D8CE  BD03 4124  SCALL 03:4124
  32:D8D2  0870       MOV R7, R0
  32:D8D4  68F0 0064  MOV REG[0xF0], #0x0064
  32:D8D8  C300       UDIV R0
  32:D8DA  6A6B FFF8  MOV [R11+0xFFF8], R6
  32:D8DE  786B FFF8  MOV R6, [R11+0xFFF8]
  32:D8E2  76F6 0032  CMP REG[0xF6], #0x0032
  32:D8E6  AC0E D8F4  AJMP SGE, 32:D8F4
  32:D8EA  49D0       MOVB RB13, #0x0
  32:D8EC  6BDB FFFF  MOVB [R11+0xFFFF], RB13
  32:D8F0  AC00 D920  AJMP ALWAYS, 32:D920
  32:D8F4  786B FFF8  MOV R6, [R11+0xFFF8]
  32:D8F8  76F6 004B  CMP REG[0xF6], #0x004B
```

### `32:E09A` in `sub_32_DB08`

```text
  32:E084  1102       ADDC R0, R2
  32:E086  4C11       SL R1, #0x1
  32:E088  5C01       SLOSB R0, #0x1
  32:E08A  58F0       MOV [--R15], R0
  32:E08C  1F90       POP REG[0x10]
  32:E08E  4D11       SR R1, #0x1
  32:E090  2911       MOVB RB1, [R1]
  32:E092  1901       MOVZE R0, RB1
  32:E094  5600       CMP R0, #0x0
  32:E096  AC02 E194  AJMP NZ/NE, 32:E194
> 32:E09A  BD03 4124  SCALL 03:4124
  32:E09E  0870       MOV R7, R0
  32:E0A0  68F0 0064  MOV REG[0xF0], #0x0064
  32:E0A4  C300       UDIV R0
  32:E0A6  0876       MOV R7, R6
  32:E0A8  6810 00A4  MOV REG[0x10], #0x00A4
  32:E0AC  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  32:E0B0  C301       UDIV R1
  32:E0B2  5061       ADD R6, #0x1
  32:E0B4  6810 00A4  MOV REG[0x10], #0x00A4
  32:E0B8  C700       NOP
  32:E0BA  A9FD 7AC0  MOVB [0x7AC0], REG[0xFD]
  32:E0BE  AC00 E0F8  AJMP ALWAYS, 32:E0F8
```

### `32:E194` in `sub_32_E0F4`

```text
  32:E17E  52F1       SUB R15, #0x1
  32:E180  4C11       SL R1, #0x1
  32:E182  5C01       SLOSB R0, #0x1
  32:E184  4D11       SR R1, #0x1
  32:E186  58F0       MOV [--R15], R0
  32:E188  1F90       POP REG[0x10]
  32:E18A  3F01       CRIT #1
  32:E18C  50F1       ADD R15, #0x1
  32:E18E  3B1F       MOVB [R1], [R15++]
  32:E190  AC00 E2AA  AJMP ALWAYS, 32:E2AA
> 32:E194  BD03 4124  SCALL 03:4124
  32:E198  0870       MOV R7, R0
  32:E19A  68F0 0064  MOV REG[0xF0], #0x0064
  32:E19E  C300       UDIV R0
  32:E1A0  0876       MOV R7, R6
  32:E1A2  6810 00A4  MOV REG[0x10], #0x00A4
  32:E1A6  99F1 7AF0  MOVZE REG[0xF1], [0x7AF0]
  32:E1AA  C301       UDIV R1
  32:E1AC  5061       ADD R6, #0x1
  32:E1AE  6810 00A4  MOV REG[0x10], #0x00A4
  32:E1B2  99F7 7AFA  MOVZE REG[0xF7], [0x7AFA]
  32:E1B6  1067       ADD R6, R7
  32:E1B8  6810 00A4  MOV REG[0x10], #0x00A4
```

### `33:6EFE` in `sub_33_6EFA`

```text
  33:6EFA  6A0B FFF6  MOV [R11+0xFFF6], R0
> 33:6EFE  BD03 4124  SCALL 03:4124
  33:6F02  0870       MOV R7, R0
  33:6F04  68F0 0064  MOV REG[0xF0], #0x0064
  33:6F08  C300       UDIV R0
  33:6F0A  6A6B FFFA  MOV [R11+0xFFFA], R6
  33:6F0E  786B FFF8  MOV R6, [R11+0xFFF8]
  33:6F12  6A6B FFEA  MOV [R11+0xFFEA], R6
  33:6F16  781B FFFA  MOV R1, [R11+0xFFFA]
  33:6F1A  0876       MOV R7, R6
  33:6F1C  780B FFF6  MOV R0, [R11+0xFFF6]
  33:6F20  783B FFEA  MOV R3, [R11+0xFFEA]
  33:6F24  1030       ADD R3, R0
  33:6F26  C203       DIV R3
```

## `03:4154`

Call sites: `2C:C8F4`

### `2C:C8F4` in `sub_2C_C07E`

```text
  2C:C8D4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8D8  C700       NOP
  2C:C8DA  A8F0 7AB4  MOV [0x7AB4], REG[0xF0]
  2C:C8DE  4910       MOVB RB1, #0x0
  2C:C8E0  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8E4  C700       NOP
  2C:C8E6  A9F1 7A32  MOVB [0x7A32], REG[0xF1]
  2C:C8EA  BD33 2FF2  SCALL 33:2FF2
  2C:C8EE  68F0 0FA0  MOV REG[0xF0], #0x0FA0
  2C:C8F2  58F0       MOV [--R15], R0
> 2C:C8F4  BD03 4154  SCALL 03:4154
  2C:C8F8  50F2       ADD R15, #0x2
  2C:C8FA  AC00 D5B8  AJMP ALWAYS, 2C:D5B8
  2C:D5B8  387F       MOV R7, [R15++]
  2C:D5BA  386F       MOV R6, [R15++]
  2C:D5BC  383F       MOV R3, [R15++]
  2C:D5BE  382F       MOV R2, [R15++]
  2C:D5C0  381F       MOV R1, [R15++]
  2C:D5C2  380F       MOV R0, [R15++]
  2C:D5C4  2F00       UNLINK
  2C:D5C6  C620       RETS
```

## `03:4184`

Call sites: `2F:C116`

### `2F:C116` in `sub_2F_BFBC`

```text
  2F:C0FC  4930       MOVB RB3, #0x0
  2F:C0FE  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C102  C700       NOP
  2F:C104  A9F3 7AA4  MOVB [0x7AA4], REG[0xF3]
  2F:C108  4810       MOV R1, #0x0
  2F:C10A  58F1       MOV [--R15], R1
  2F:C10C  BD03 4224  SCALL 03:4224
  2F:C110  50F2       ADD R15, #0x2
  2F:C112  4811       MOV R1, #0x1
  2F:C114  58F1       MOV [--R15], R1
> 2F:C116  BD03 4184  SCALL 03:4184
  2F:C11A  50F2       ADD R15, #0x2
  2F:C11C  BD27 6ADC  SCALL 27:6ADC
  2F:C120  BD33 2FF2  SCALL 33:2FF2
  2F:C124  4801       MOV R0, #0x1
  2F:C126  58F0       MOV [--R15], R0
  2F:C128  BD03 4224  SCALL 03:4224
  2F:C12C  50F2       ADD R15, #0x2
  2F:C12E  BD03 4398  SCALL 03:4398
  2F:C132  BD03 41F8  SCALL 03:41F8
  2F:C136  4910       MOVB RB1, #0x0
  2F:C138  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C13C  C700       NOP
```

## `03:41A8`

Call sites: `2F:A6BE`, `2F:A744`, `2F:A834`, `2F:AA1C`, `2F:AC9A`, `2F:ADB8`, `2F:B036`, `2F:B0BA`, `2F:B244`, `2F:B2C8`, `2F:B764`, `2F:BD4E`, `2F:C284`, `30:254E`

### `2F:A6BE` in `sub_2F_A0B6`

```text
  2F:A6A4  1013       ADD R1, R3
  2F:A6A6  1102       ADDC R0, R2
  2F:A6A8  58F1       MOV [--R15], R1
  2F:A6AA  58F0       MOV [--R15], R0
  2F:A6AC  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:A6B0  5008       ADD R0, #0x8
  2F:A6B2  58F0       MOV [--R15], R0
  2F:A6B4  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:A6B8  70F0 0014  ADD REG[0xF0], #0x0014
  2F:A6BC  58F0       MOV [--R15], R0
> 2F:A6BE  BD03 41A8  SCALL 03:41A8
  2F:A6C2  50F8       ADD R15, #0x8
  2F:A6C4  68F1 0094  MOV REG[0xF1], #0x0094
  2F:A6C8  4800       MOV R0, #0x0
  2F:A6CA  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:A6CE  1937       MOVZE R3, RB7
  2F:A6D0  5630       CMP R3, #0x0
  2F:A6D2  DE03       RJMP SGE, 2F:A6DA ; rel +3
  2F:A6D4  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:A6D8  D001       RJMP ALWAYS, 2F:A6DC ; rel +1
  2F:A6DA  4820       MOV R2, #0x0
  2F:A6DC  58F3       MOV [--R15], R3
  2F:A6DE  58F2       MOV [--R15], R2
```

### `2F:A744` in `sub_2F_A0B6`

```text
  2F:A726  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A72A  4800       MOV R0, #0x0
  2F:A72C  58F1       MOV [--R15], R1
  2F:A72E  58F0       MOV [--R15], R0
  2F:A730  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:A734  70F0 0017  ADD REG[0xF0], #0x0017
  2F:A738  58F0       MOV [--R15], R0
  2F:A73A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:A73E  70F0 002D  ADD REG[0xF0], #0x002D
  2F:A742  58F0       MOV [--R15], R0
> 2F:A744  BD03 41A8  SCALL 03:41A8
  2F:A748  50F8       ADD R15, #0x8
  2F:A74A  68F1 0094  MOV REG[0xF1], #0x0094
  2F:A74E  4800       MOV R0, #0x0
  2F:A750  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:A754  1937       MOVZE R3, RB7
  2F:A756  5630       CMP R3, #0x0
  2F:A758  DE03       RJMP SGE, 2F:A760 ; rel +3
  2F:A75A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:A75E  D001       RJMP ALWAYS, 2F:A762 ; rel +1
  2F:A760  4820       MOV R2, #0x0
  2F:A762  58F3       MOV [--R15], R3
  2F:A764  58F2       MOV [--R15], R2
```

### `2F:A834` in `sub_2F_A0B6`

```text
  2F:A816  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:A81A  4800       MOV R0, #0x0
  2F:A81C  58F1       MOV [--R15], R1
  2F:A81E  58F0       MOV [--R15], R0
  2F:A820  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:A824  70F0 0017  ADD REG[0xF0], #0x0017
  2F:A828  58F0       MOV [--R15], R0
  2F:A82A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:A82E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:A832  58F0       MOV [--R15], R0
> 2F:A834  BD03 41A8  SCALL 03:41A8
  2F:A838  50F8       ADD R15, #0x8
  2F:A83A  68F1 0094  MOV REG[0xF1], #0x0094
  2F:A83E  4800       MOV R0, #0x0
  2F:A840  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:A844  1937       MOVZE R3, RB7
  2F:A846  5630       CMP R3, #0x0
  2F:A848  DE03       RJMP SGE, 2F:A850 ; rel +3
  2F:A84A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:A84E  D001       RJMP ALWAYS, 2F:A852 ; rel +1
  2F:A850  4820       MOV R2, #0x0
  2F:A852  58F3       MOV [--R15], R3
  2F:A854  58F2       MOV [--R15], R2
```

### `2F:AA1C` in `sub_2F_A0B6`

```text
  2F:A9FE  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AA02  4800       MOV R0, #0x0
  2F:AA04  58F1       MOV [--R15], R1
  2F:AA06  58F0       MOV [--R15], R0
  2F:AA08  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:AA0C  70F0 0024  ADD REG[0xF0], #0x0024
  2F:AA10  58F0       MOV [--R15], R0
  2F:AA12  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:AA16  70F0 0020  ADD REG[0xF0], #0x0020
  2F:AA1A  58F0       MOV [--R15], R0
> 2F:AA1C  BD03 41A8  SCALL 03:41A8
  2F:AA20  50F8       ADD R15, #0x8
  2F:AA22  68F1 0094  MOV REG[0xF1], #0x0094
  2F:AA26  4800       MOV R0, #0x0
  2F:AA28  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:AA2C  1937       MOVZE R3, RB7
  2F:AA2E  5630       CMP R3, #0x0
  2F:AA30  DE03       RJMP SGE, 2F:AA38 ; rel +3
  2F:AA32  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:AA36  D001       RJMP ALWAYS, 2F:AA3A ; rel +1
  2F:AA38  4820       MOV R2, #0x0
  2F:AA3A  58F3       MOV [--R15], R3
  2F:AA3C  58F2       MOV [--R15], R2
```

### `2F:AC9A` in `sub_2F_A0B6`

```text
  2F:AC7C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AC80  4800       MOV R0, #0x0
  2F:AC82  58F1       MOV [--R15], R1
  2F:AC84  58F0       MOV [--R15], R0
  2F:AC86  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:AC8A  70F0 0024  ADD REG[0xF0], #0x0024
  2F:AC8E  58F0       MOV [--R15], R0
  2F:AC90  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:AC94  70F0 005A  ADD REG[0xF0], #0x005A
  2F:AC98  58F0       MOV [--R15], R0
> 2F:AC9A  BD03 41A8  SCALL 03:41A8
  2F:AC9E  50F8       ADD R15, #0x8
  2F:ACA0  68F1 0094  MOV REG[0xF1], #0x0094
  2F:ACA4  4800       MOV R0, #0x0
  2F:ACA6  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:ACAA  1937       MOVZE R3, RB7
  2F:ACAC  5630       CMP R3, #0x0
  2F:ACAE  DE03       RJMP SGE, 2F:ACB6 ; rel +3
  2F:ACB0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:ACB4  D001       RJMP ALWAYS, 2F:ACB8 ; rel +1
  2F:ACB6  4820       MOV R2, #0x0
  2F:ACB8  58F3       MOV [--R15], R3
  2F:ACBA  58F2       MOV [--R15], R2
```

### `2F:ADB8` in `sub_2F_A0B6`

```text
  2F:AD9A  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:AD9E  4800       MOV R0, #0x0
  2F:ADA0  58F1       MOV [--R15], R1
  2F:ADA2  58F0       MOV [--R15], R0
  2F:ADA4  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:ADA8  70F0 0031  ADD REG[0xF0], #0x0031
  2F:ADAC  58F0       MOV [--R15], R0
  2F:ADAE  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:ADB2  70F0 0020  ADD REG[0xF0], #0x0020
  2F:ADB6  58F0       MOV [--R15], R0
> 2F:ADB8  BD03 41A8  SCALL 03:41A8
  2F:ADBC  50F8       ADD R15, #0x8
  2F:ADBE  68F1 0094  MOV REG[0xF1], #0x0094
  2F:ADC2  4800       MOV R0, #0x0
  2F:ADC4  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:ADC8  1937       MOVZE R3, RB7
  2F:ADCA  5630       CMP R3, #0x0
  2F:ADCC  DE03       RJMP SGE, 2F:ADD4 ; rel +3
  2F:ADCE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:ADD2  D001       RJMP ALWAYS, 2F:ADD6 ; rel +1
  2F:ADD4  4820       MOV R2, #0x0
  2F:ADD6  58F3       MOV [--R15], R3
  2F:ADD8  58F2       MOV [--R15], R2
```

### `2F:B036` in `sub_2F_A0B6`

```text
  2F:B018  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B01C  4800       MOV R0, #0x0
  2F:B01E  58F1       MOV [--R15], R1
  2F:B020  58F0       MOV [--R15], R0
  2F:B022  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B026  70F0 0031  ADD REG[0xF0], #0x0031
  2F:B02A  58F0       MOV [--R15], R0
  2F:B02C  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B030  70F0 005A  ADD REG[0xF0], #0x005A
  2F:B034  58F0       MOV [--R15], R0
> 2F:B036  BD03 41A8  SCALL 03:41A8
  2F:B03A  50F8       ADD R15, #0x8
  2F:B03C  68F1 0094  MOV REG[0xF1], #0x0094
  2F:B040  4800       MOV R0, #0x0
  2F:B042  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:B046  1937       MOVZE R3, RB7
  2F:B048  5630       CMP R3, #0x0
  2F:B04A  DE03       RJMP SGE, 2F:B052 ; rel +3
  2F:B04C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:B050  D001       RJMP ALWAYS, 2F:B054 ; rel +1
  2F:B052  4820       MOV R2, #0x0
  2F:B054  58F3       MOV [--R15], R3
  2F:B056  58F2       MOV [--R15], R2
```

### `2F:B0BA` in `sub_2F_A0B6`

```text
  2F:B09C  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B0A0  4800       MOV R0, #0x0
  2F:B0A2  58F1       MOV [--R15], R1
  2F:B0A4  58F0       MOV [--R15], R0
  2F:B0A6  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B0AA  70F0 003E  ADD REG[0xF0], #0x003E
  2F:B0AE  58F0       MOV [--R15], R0
  2F:B0B0  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B0B4  70F0 002D  ADD REG[0xF0], #0x002D
  2F:B0B8  58F0       MOV [--R15], R0
> 2F:B0BA  BD03 41A8  SCALL 03:41A8
  2F:B0BE  50F8       ADD R15, #0x8
  2F:B0C0  68F1 0094  MOV REG[0xF1], #0x0094
  2F:B0C4  4800       MOV R0, #0x0
  2F:B0C6  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:B0CA  1937       MOVZE R3, RB7
  2F:B0CC  5630       CMP R3, #0x0
  2F:B0CE  DE03       RJMP SGE, 2F:B0D6 ; rel +3
  2F:B0D0  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:B0D4  D001       RJMP ALWAYS, 2F:B0D8 ; rel +1
  2F:B0D6  4820       MOV R2, #0x0
  2F:B0D8  58F3       MOV [--R15], R3
  2F:B0DA  58F2       MOV [--R15], R2
```

### `2F:B244` in `sub_2F_A0B6`

```text
  2F:B226  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B22A  4800       MOV R0, #0x0
  2F:B22C  58F1       MOV [--R15], R1
  2F:B22E  58F0       MOV [--R15], R0
  2F:B230  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B234  70F0 003E  ADD REG[0xF0], #0x003E
  2F:B238  58F0       MOV [--R15], R0
  2F:B23A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B23E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:B242  58F0       MOV [--R15], R0
> 2F:B244  BD03 41A8  SCALL 03:41A8
  2F:B248  50F8       ADD R15, #0x8
  2F:B24A  68F1 0094  MOV REG[0xF1], #0x0094
  2F:B24E  4800       MOV R0, #0x0
  2F:B250  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:B254  1937       MOVZE R3, RB7
  2F:B256  5630       CMP R3, #0x0
  2F:B258  DE03       RJMP SGE, 2F:B260 ; rel +3
  2F:B25A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:B25E  D001       RJMP ALWAYS, 2F:B262 ; rel +1
  2F:B260  4820       MOV R2, #0x0
  2F:B262  58F3       MOV [--R15], R3
  2F:B264  58F2       MOV [--R15], R2
```

### `2F:B2C8` in `sub_2F_A0B6`

```text
  2F:B2AA  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B2AE  4800       MOV R0, #0x0
  2F:B2B0  58F1       MOV [--R15], R1
  2F:B2B2  58F0       MOV [--R15], R0
  2F:B2B4  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B2B8  70F0 004B  ADD REG[0xF0], #0x004B
  2F:B2BC  58F0       MOV [--R15], R0
  2F:B2BE  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B2C2  70F0 002D  ADD REG[0xF0], #0x002D
  2F:B2C6  58F0       MOV [--R15], R0
> 2F:B2C8  BD03 41A8  SCALL 03:41A8
  2F:B2CC  50F8       ADD R15, #0x8
  2F:B2CE  68F1 0094  MOV REG[0xF1], #0x0094
  2F:B2D2  4800       MOV R0, #0x0
  2F:B2D4  797B FFFF  MOVB RB7, [R11+0xFFFF]
  2F:B2D8  1937       MOVZE R3, RB7
  2F:B2DA  5630       CMP R3, #0x0
  2F:B2DC  DE03       RJMP SGE, 2F:B2E4 ; rel +3
  2F:B2DE  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:B2E2  D001       RJMP ALWAYS, 2F:B2E6 ; rel +1
  2F:B2E4  4820       MOV R2, #0x0
  2F:B2E6  58F3       MOV [--R15], R3
  2F:B2E8  58F2       MOV [--R15], R2
```

### `2F:B764` in `sub_2F_B514`

```text
  2F:B746  70F1 FFF0  ADD REG[0xF1], #0xFFF0
  2F:B74A  4800       MOV R0, #0x0
  2F:B74C  58F1       MOV [--R15], R1
  2F:B74E  58F0       MOV [--R15], R0
  2F:B750  780B FFEC  MOV R0, [R11+0xFFEC]
  2F:B754  70F0 004B  ADD REG[0xF0], #0x004B
  2F:B758  58F0       MOV [--R15], R0
  2F:B75A  780B FFEE  MOV R0, [R11+0xFFEE]
  2F:B75E  70F0 006A  ADD REG[0xF0], #0x006A
  2F:B762  58F0       MOV [--R15], R0
> 2F:B764  BD03 41A8  SCALL 03:41A8
  2F:B768  50F8       ADD R15, #0x8
  2F:B76A  BD33 2FF2  SCALL 33:2FF2
  2F:B76E  68F0 0050  MOV REG[0xF0], #0x0050
  2F:B772  58F0       MOV [--R15], R0
  2F:B774  BD03 4120  SCALL 03:4120
  2F:B778  50F2       ADD R15, #0x2
  2F:B77A  791B FFFF  MOVB RB1, [R11+0xFFFF]
  2F:B77E  1901       MOVZE R0, RB1
  2F:B780  58F0       MOV [--R15], R0
  2F:B782  BD26 C174  SCALL 26:C174
  2F:B786  50F2       ADD R15, #0x2
  2F:B788  68F1 0094  MOV REG[0xF1], #0x0094
```

### `2F:BD4E` in `sub_2F_B8A4`

```text
  2F:BD32  BD03 4224  SCALL 03:4224
  2F:BD36  50F2       ADD R15, #0x2
  2F:BD38  68F1 DB7C  MOV REG[0xF1], #0xDB7C
  2F:BD3C  68F0 0031  MOV REG[0xF0], #0x0031
  2F:BD40  58F1       MOV [--R15], R1
  2F:BD42  58F0       MOV [--R15], R0
  2F:BD44  480A       MOV R0, #0xA
  2F:BD46  58F0       MOV [--R15], R0
  2F:BD48  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD4C  58F0       MOV [--R15], R0
> 2F:BD4E  BD03 41A8  SCALL 03:41A8
  2F:BD52  50F8       ADD R15, #0x8
  2F:BD54  480A       MOV R0, #0xA
  2F:BD56  58F0       MOV [--R15], R0
  2F:BD58  BD03 4120  SCALL 03:4120
  2F:BD5C  50F2       ADD R15, #0x2
  2F:BD5E  4800       MOV R0, #0x0
  2F:BD60  58F0       MOV [--R15], R0
  2F:BD62  4801       MOV R0, #0x1
  2F:BD64  58F0       MOV [--R15], R0
  2F:BD66  BD03 41C8  SCALL 03:41C8
  2F:BD6A  50F4       ADD R15, #0x4
  2F:BD6C  68F0 0017  MOV REG[0xF0], #0x0017
```

### `2F:C284` in `sub_2F_C216`

```text
  2F:C268  BD03 4224  SCALL 03:4224
  2F:C26C  50F2       ADD R15, #0x2
  2F:C26E  68F1 DB72  MOV REG[0xF1], #0xDB72
  2F:C272  68F0 0031  MOV REG[0xF0], #0x0031
  2F:C276  58F1       MOV [--R15], R1
  2F:C278  58F0       MOV [--R15], R0
  2F:C27A  480A       MOV R0, #0xA
  2F:C27C  58F0       MOV [--R15], R0
  2F:C27E  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C282  58F0       MOV [--R15], R0
> 2F:C284  BD03 41A8  SCALL 03:41A8
  2F:C288  50F8       ADD R15, #0x8
  2F:C28A  68F0 0064  MOV REG[0xF0], #0x0064
  2F:C28E  58F0       MOV [--R15], R0
  2F:C290  BD03 4120  SCALL 03:4120
  2F:C294  50F2       ADD R15, #0x2
  2F:C296  4800       MOV R0, #0x0
  2F:C298  58F0       MOV [--R15], R0
  2F:C29A  4801       MOV R0, #0x1
  2F:C29C  58F0       MOV [--R15], R0
  2F:C29E  BD03 41C8  SCALL 03:41C8
  2F:C2A2  50F4       ADD R15, #0x4
  2F:C2A4  68F0 0017  MOV REG[0xF0], #0x0017
```

### `30:254E` in `sub_30_1EAA`

```text
  30:2534  58F1       MOV [--R15], R1
  30:2536  58F0       MOV [--R15], R0
  30:2538  780B FFDA  MOV R0, [R11+0xFFDA]
  30:253C  4817       MOV R1, #0x7
  30:253E  783B FFCE  MOV R3, [R11+0xFFCE]
  30:2542  C013       MUL R1, R3
  30:2544  1207       SUB R0, R7
  30:2546  58F0       MOV [--R15], R0
  30:2548  780B FFDC  MOV R0, [R11+0xFFDC]
  30:254C  58F0       MOV [--R15], R0
> 30:254E  BD03 41A8  SCALL 03:41A8
  30:2552  50F8       ADD R15, #0x8
  30:2554  780B FFFC  MOV R0, [R11+0xFFFC]
  30:2558  5001       ADD R0, #0x1
  30:255A  6A0B FFFC  MOV [R11+0xFFFC], R0
  30:255E  780B FFFC  MOV R0, [R11+0xFFFC]
  30:2562  6810 00A4  MOV REG[0x10], #0x00A4
  30:2566  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  30:256A  6810 00A4  MOV REG[0x10], #0x00A4
  30:256E  99F3 7AF0  MOVZE REG[0xF3], [0x7AF0]
  30:2572  1013       ADD R1, R3
  30:2574  1601       CMP R0, R1
  30:2576  AC09 13FE  AJMP SL, 30:13FE
```

## `03:41AC`

Call sites: `2C:C6E2`, `2C:C706`, `2C:C728`, `2C:C74C`

### `2C:C6E2` in `sub_2C_C07E`

```text
  2C:C6C6  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C6CA  58F0       MOV [--R15], R0
  2C:C6CC  780B FFDE  MOV R0, [R11+0xFFDE]
  2C:C6D0  781B FFE0  MOV R1, [R11+0xFFE0]
  2C:C6D4  58F1       MOV [--R15], R1
  2C:C6D6  58F0       MOV [--R15], R0
  2C:C6D8  68F0 0054  MOV REG[0xF0], #0x0054
  2C:C6DC  58F0       MOV [--R15], R0
  2C:C6DE  4800       MOV R0, #0x0
  2C:C6E0  58F0       MOV [--R15], R0
> 2C:C6E2  BD03 41AC  SCALL 03:41AC
  2C:C6E6  50FA       ADD R15, #0xA
  2C:C6E8  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C6EC  58F0       MOV [--R15], R0
  2C:C6EE  780B FFDA  MOV R0, [R11+0xFFDA]
  2C:C6F2  781B FFDC  MOV R1, [R11+0xFFDC]
  2C:C6F6  58F1       MOV [--R15], R1
  2C:C6F8  58F0       MOV [--R15], R0
  2C:C6FA  68F0 0054  MOV REG[0xF0], #0x0054
  2C:C6FE  58F0       MOV [--R15], R0
  2C:C700  68F0 0078  MOV REG[0xF0], #0x0078
  2C:C704  58F0       MOV [--R15], R0
  2C:C706  BD03 41AC  SCALL 03:41AC
```

### `2C:C706` in `sub_2C_C07E`

```text
  2C:C6E8  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C6EC  58F0       MOV [--R15], R0
  2C:C6EE  780B FFDA  MOV R0, [R11+0xFFDA]
  2C:C6F2  781B FFDC  MOV R1, [R11+0xFFDC]
  2C:C6F6  58F1       MOV [--R15], R1
  2C:C6F8  58F0       MOV [--R15], R0
  2C:C6FA  68F0 0054  MOV REG[0xF0], #0x0054
  2C:C6FE  58F0       MOV [--R15], R0
  2C:C700  68F0 0078  MOV REG[0xF0], #0x0078
  2C:C704  58F0       MOV [--R15], R0
> 2C:C706  BD03 41AC  SCALL 03:41AC
  2C:C70A  50FA       ADD R15, #0xA
  2C:C70C  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C710  58F0       MOV [--R15], R0
  2C:C712  780B FFD6  MOV R0, [R11+0xFFD6]
  2C:C716  781B FFD8  MOV R1, [R11+0xFFD8]
  2C:C71A  58F1       MOV [--R15], R1
  2C:C71C  58F0       MOV [--R15], R0
  2C:C71E  68F0 0060  MOV REG[0xF0], #0x0060
  2C:C722  58F0       MOV [--R15], R0
  2C:C724  4800       MOV R0, #0x0
  2C:C726  58F0       MOV [--R15], R0
  2C:C728  BD03 41AC  SCALL 03:41AC
```

### `2C:C728` in `sub_2C_C07E`

```text
  2C:C70C  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C710  58F0       MOV [--R15], R0
  2C:C712  780B FFD6  MOV R0, [R11+0xFFD6]
  2C:C716  781B FFD8  MOV R1, [R11+0xFFD8]
  2C:C71A  58F1       MOV [--R15], R1
  2C:C71C  58F0       MOV [--R15], R0
  2C:C71E  68F0 0060  MOV REG[0xF0], #0x0060
  2C:C722  58F0       MOV [--R15], R0
  2C:C724  4800       MOV R0, #0x0
  2C:C726  58F0       MOV [--R15], R0
> 2C:C728  BD03 41AC  SCALL 03:41AC
  2C:C72C  50FA       ADD R15, #0xA
  2C:C72E  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C732  58F0       MOV [--R15], R0
  2C:C734  780B FFD2  MOV R0, [R11+0xFFD2]
  2C:C738  781B FFD4  MOV R1, [R11+0xFFD4]
  2C:C73C  58F1       MOV [--R15], R1
  2C:C73E  58F0       MOV [--R15], R0
  2C:C740  68F0 0060  MOV REG[0xF0], #0x0060
  2C:C744  58F0       MOV [--R15], R0
  2C:C746  68F0 0078  MOV REG[0xF0], #0x0078
  2C:C74A  58F0       MOV [--R15], R0
  2C:C74C  BD03 41AC  SCALL 03:41AC
```

### `2C:C74C` in `sub_2C_C07E`

```text
  2C:C72E  68F0 0014  MOV REG[0xF0], #0x0014
  2C:C732  58F0       MOV [--R15], R0
  2C:C734  780B FFD2  MOV R0, [R11+0xFFD2]
  2C:C738  781B FFD4  MOV R1, [R11+0xFFD4]
  2C:C73C  58F1       MOV [--R15], R1
  2C:C73E  58F0       MOV [--R15], R0
  2C:C740  68F0 0060  MOV REG[0xF0], #0x0060
  2C:C744  58F0       MOV [--R15], R0
  2C:C746  68F0 0078  MOV REG[0xF0], #0x0078
  2C:C74A  58F0       MOV [--R15], R0
> 2C:C74C  BD03 41AC  SCALL 03:41AC
  2C:C750  50FA       ADD R15, #0xA
  2C:C752  68F0 0060  MOV REG[0xF0], #0x0060
  2C:C756  58F0       MOV [--R15], R0
  2C:C758  4806       MOV R0, #0x6
  2C:C75A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C75E  99F1 7AD8  MOVZE REG[0xF1], [0x7AD8]
  2C:C762  C001       MUL R0, R1
  2C:C764  58F7       MOV [--R15], R7
  2C:C766  68F6 0054  MOV REG[0xF6], #0x0054
  2C:C76A  58F6       MOV [--R15], R6
  2C:C76C  4860       MOV R6, #0x0
  2C:C76E  58F6       MOV [--R15], R6
```

## `03:41C8`

Call sites: `2C:C84E`, `2F:BD66`, `2F:C29E`, `31:7A2C`, `31:7FC0`, `31:8116`, `32:E6A4`, `32:E968`, `32:ECAE`, `32:EE7A`

### `2C:C84E` in `sub_2C_C07E`

```text
  2C:C836  68F0 0056  MOV REG[0xF0], #0x0056
  2C:C83A  58F0       MOV [--R15], R0
  2C:C83C  4800       MOV R0, #0x0
  2C:C83E  58F0       MOV [--R15], R0
  2C:C840  BD2F A0B6  SCALL 2F:A0B6
  2C:C844  50FA       ADD R15, #0xA
  2C:C846  4800       MOV R0, #0x0
  2C:C848  58F0       MOV [--R15], R0
  2C:C84A  4801       MOV R0, #0x1
  2C:C84C  58F0       MOV [--R15], R0
> 2C:C84E  BD03 41C8  SCALL 03:41C8
  2C:C852  50F4       ADD R15, #0x4
  2C:C854  68F0 0063  MOV REG[0xF0], #0x0063
  2C:C858  58F0       MOV [--R15], R0
  2C:C85A  68F0 00E4  MOV REG[0xF0], #0x00E4
  2C:C85E  58F0       MOV [--R15], R0
  2C:C860  68F0 0057  MOV REG[0xF0], #0x0057
  2C:C864  58F0       MOV [--R15], R0
  2C:C866  68F0 0024  MOV REG[0xF0], #0x0024
  2C:C86A  58F0       MOV [--R15], R0
  2C:C86C  BD03 4214  SCALL 03:4214
  2C:C870  50F8       ADD R15, #0x8
  2C:C872  780B FFCE  MOV R0, [R11+0xFFCE]
```

### `2F:BD66` in `sub_2F_B8A4`

```text
  2F:BD4E  BD03 41A8  SCALL 03:41A8
  2F:BD52  50F8       ADD R15, #0x8
  2F:BD54  480A       MOV R0, #0xA
  2F:BD56  58F0       MOV [--R15], R0
  2F:BD58  BD03 4120  SCALL 03:4120
  2F:BD5C  50F2       ADD R15, #0x2
  2F:BD5E  4800       MOV R0, #0x0
  2F:BD60  58F0       MOV [--R15], R0
  2F:BD62  4801       MOV R0, #0x1
  2F:BD64  58F0       MOV [--R15], R0
> 2F:BD66  BD03 41C8  SCALL 03:41C8
  2F:BD6A  50F4       ADD R15, #0x4
  2F:BD6C  68F0 0017  MOV REG[0xF0], #0x0017
  2F:BD70  58F0       MOV [--R15], R0
  2F:BD72  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:BD76  58F0       MOV [--R15], R0
  2F:BD78  480A       MOV R0, #0xA
  2F:BD7A  58F0       MOV [--R15], R0
  2F:BD7C  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD80  58F0       MOV [--R15], R0
  2F:BD82  BD03 4214  SCALL 03:4214
  2F:BD86  50F8       ADD R15, #0x8
  2F:BD88  BD33 2FF2  SCALL 33:2FF2
```

### `2F:C29E` in `sub_2F_C216`

```text
  2F:C284  BD03 41A8  SCALL 03:41A8
  2F:C288  50F8       ADD R15, #0x8
  2F:C28A  68F0 0064  MOV REG[0xF0], #0x0064
  2F:C28E  58F0       MOV [--R15], R0
  2F:C290  BD03 4120  SCALL 03:4120
  2F:C294  50F2       ADD R15, #0x2
  2F:C296  4800       MOV R0, #0x0
  2F:C298  58F0       MOV [--R15], R0
  2F:C29A  4801       MOV R0, #0x1
  2F:C29C  58F0       MOV [--R15], R0
> 2F:C29E  BD03 41C8  SCALL 03:41C8
  2F:C2A2  50F4       ADD R15, #0x4
  2F:C2A4  68F0 0017  MOV REG[0xF0], #0x0017
  2F:C2A8  58F0       MOV [--R15], R0
  2F:C2AA  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:C2AE  58F0       MOV [--R15], R0
  2F:C2B0  480A       MOV R0, #0xA
  2F:C2B2  58F0       MOV [--R15], R0
  2F:C2B4  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C2B8  58F0       MOV [--R15], R0
  2F:C2BA  BD03 4214  SCALL 03:4214
  2F:C2BE  50F8       ADD R15, #0x8
  2F:C2C0  BD33 2FF2  SCALL 33:2FF2
```

### `31:7A2C` in `sub_31_7772`

```text
  31:7A16  1F90       POP REG[0x10]
  31:7A18  4D11       SR R1, #0x1
  31:7A1A  2911       MOVB RB1, [R1]
  31:7A1C  1901       MOVZE R0, RB1
  31:7A1E  5600       CMP R0, #0x0
  31:7A20  AC02 7BC4  AJMP NZ/NE, 31:7BC4
  31:7A24  4800       MOV R0, #0x0
  31:7A26  58F0       MOV [--R15], R0
  31:7A28  4801       MOV R0, #0x1
  31:7A2A  58F0       MOV [--R15], R0
> 31:7A2C  BD03 41C8  SCALL 03:41C8
  31:7A30  50F4       ADD R15, #0x4
  31:7A32  780B FFFA  MOV R0, [R11+0xFFFA]
  31:7A36  0810       MOV R1, R0
  31:7A38  70F1 0032  ADD REG[0xF1], #0x0032
  31:7A3C  58F1       MOV [--R15], R1
  31:7A3E  781B FFFC  MOV R1, [R11+0xFFFC]
  31:7A42  0831       MOV R3, R1
  31:7A44  70F3 0028  ADD REG[0xF3], #0x0028
  31:7A48  58F3       MOV [--R15], R3
  31:7A4A  58F0       MOV [--R15], R0
  31:7A4C  58F1       MOV [--R15], R1
  31:7A4E  BD03 4214  SCALL 03:4214
```

### `31:7FC0` in `sub_31_7D02`

```text
  31:7FA4  C010       MUL R1, R0
  31:7FA6  0867       MOV R6, R7
  31:7FA8  70F6 008E  ADD REG[0xF6], #0x008E
  31:7FAC  6A6B FFFC  MOV [R11+0xFFFC], R6
  31:7FB0  68F6 003B  MOV REG[0xF6], #0x003B
  31:7FB4  6A6B FFFA  MOV [R11+0xFFFA], R6
  31:7FB8  4860       MOV R6, #0x0
  31:7FBA  58F6       MOV [--R15], R6
  31:7FBC  4861       MOV R6, #0x1
  31:7FBE  58F6       MOV [--R15], R6
> 31:7FC0  BD03 41C8  SCALL 03:41C8
  31:7FC4  50F4       ADD R15, #0x4
  31:7FC6  780B FFFA  MOV R0, [R11+0xFFFA]
  31:7FCA  0810       MOV R1, R0
  31:7FCC  70F1 0028  ADD REG[0xF1], #0x0028
  31:7FD0  58F1       MOV [--R15], R1
  31:7FD2  781B FFFC  MOV R1, [R11+0xFFFC]
  31:7FD6  0831       MOV R3, R1
  31:7FD8  70F3 0020  ADD REG[0xF3], #0x0020
  31:7FDC  58F3       MOV [--R15], R3
  31:7FDE  58F0       MOV [--R15], R0
  31:7FE0  58F1       MOV [--R15], R1
  31:7FE2  BD03 4214  SCALL 03:4214
```

### `31:8116` in `sub_31_7D02`

```text
  31:80FC  1612       CMP R1, R2
  31:80FE  AC01 810E  AJMP Z/EQ, 31:810E
  31:8102  793B 000A  MOVB RB3, [R11+0x000A]
  31:8106  1913       MOVZE R1, RB3
  31:8108  1612       CMP R1, R2
  31:810A  AC02 828C  AJMP NZ/NE, 31:828C
  31:810E  4820       MOV R2, #0x0
  31:8110  58F2       MOV [--R15], R2
  31:8112  4821       MOV R2, #0x1
  31:8114  58F2       MOV [--R15], R2
> 31:8116  BD03 41C8  SCALL 03:41C8
  31:811A  50F4       ADD R15, #0x4
  31:811C  780B FFFA  MOV R0, [R11+0xFFFA]
  31:8120  0810       MOV R1, R0
  31:8122  70F1 0028  ADD REG[0xF1], #0x0028
  31:8126  58F1       MOV [--R15], R1
  31:8128  781B FFFC  MOV R1, [R11+0xFFFC]
  31:812C  0831       MOV R3, R1
  31:812E  70F3 0020  ADD REG[0xF3], #0x0020
  31:8132  58F3       MOV [--R15], R3
  31:8134  58F0       MOV [--R15], R0
  31:8136  58F1       MOV [--R15], R1
  31:8138  BD03 4214  SCALL 03:4214
```

### `32:E6A4` in `sub_32_E1C0`

```text
  32:E68E  1F90       POP REG[0x10]
  32:E690  4D11       SR R1, #0x1
  32:E692  2911       MOVB RB1, [R1]
  32:E694  1901       MOVZE R0, RB1
  32:E696  5600       CMP R0, #0x0
  32:E698  AC02 E7C0  AJMP NZ/NE, 32:E7C0
  32:E69C  4800       MOV R0, #0x0
  32:E69E  58F0       MOV [--R15], R0
  32:E6A0  4801       MOV R0, #0x1
  32:E6A2  58F0       MOV [--R15], R0
> 32:E6A4  BD03 41C8  SCALL 03:41C8
  32:E6A8  50F4       ADD R15, #0x4
  32:E6AA  68F1 0094  MOV REG[0xF1], #0x0094
  32:E6AE  4800       MOV R0, #0x0
  32:E6B0  783B FFFE  MOV R3, [R11+0xFFFE]
  32:E6B4  5630       CMP R3, #0x0
  32:E6B6  DE03       RJMP SGE, 32:E6BE ; rel +3
  32:E6B8  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:E6BC  D001       RJMP ALWAYS, 32:E6C0 ; rel +1
  32:E6BE  4820       MOV R2, #0x0
  32:E6C0  58F3       MOV [--R15], R3
  32:E6C2  58F2       MOV [--R15], R2
  32:E6C4  58F1       MOV [--R15], R1
```

### `32:E968` in `sub_32_E8EE`

```text
  32:E94E  793B 000A  MOVB RB3, [R11+0x000A]
  32:E952  1913       MOVZE R1, RB3
  32:E954  780B FFFE  MOV R0, [R11+0xFFFE]
  32:E958  5001       ADD R0, #0x1
  32:E95A  1610       CMP R1, R0
  32:E95C  AC02 F0C6  AJMP NZ/NE, 32:F0C6
  32:E960  4800       MOV R0, #0x0
  32:E962  58F0       MOV [--R15], R0
  32:E964  4801       MOV R0, #0x1
  32:E966  58F0       MOV [--R15], R0
> 32:E968  BD03 41C8  SCALL 03:41C8
  32:E96C  50F4       ADD R15, #0x4
  32:E96E  780B FFFA  MOV R0, [R11+0xFFFA]
  32:E972  0810       MOV R1, R0
  32:E974  70F1 0028  ADD REG[0xF1], #0x0028
  32:E978  58F1       MOV [--R15], R1
  32:E97A  781B FFFC  MOV R1, [R11+0xFFFC]
  32:E97E  0831       MOV R3, R1
  32:E980  70F3 0020  ADD REG[0xF3], #0x0020
  32:E984  58F3       MOV [--R15], R3
  32:E986  58F0       MOV [--R15], R0
  32:E988  58F1       MOV [--R15], R1
  32:E98A  BD03 4214  SCALL 03:4214
```

### `32:ECAE` in `sub_32_EC6E`

```text
  32:EC92  C010       MUL R1, R0
  32:EC94  0867       MOV R6, R7
  32:EC96  70F6 008E  ADD REG[0xF6], #0x008E
  32:EC9A  6A6B FFFC  MOV [R11+0xFFFC], R6
  32:EC9E  68F6 003B  MOV REG[0xF6], #0x003B
  32:ECA2  6A6B FFFA  MOV [R11+0xFFFA], R6
  32:ECA6  4860       MOV R6, #0x0
  32:ECA8  58F6       MOV [--R15], R6
  32:ECAA  4861       MOV R6, #0x1
  32:ECAC  58F6       MOV [--R15], R6
> 32:ECAE  BD03 41C8  SCALL 03:41C8
  32:ECB2  50F4       ADD R15, #0x4
  32:ECB4  68F1 0094  MOV REG[0xF1], #0x0094
  32:ECB8  4800       MOV R0, #0x0
  32:ECBA  783B FFFE  MOV R3, [R11+0xFFFE]
  32:ECBE  5630       CMP R3, #0x0
  32:ECC0  DE03       RJMP SGE, 32:ECC8 ; rel +3
  32:ECC2  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:ECC6  D001       RJMP ALWAYS, 32:ECCA ; rel +1
  32:ECC8  4820       MOV R2, #0x0
  32:ECCA  58F3       MOV [--R15], R3
  32:ECCC  58F2       MOV [--R15], R2
  32:ECCE  58F1       MOV [--R15], R1
```

### `32:EE7A` in `sub_32_EC6E`

```text
  32:EE62  4D11       SR R1, #0x1
  32:EE64  2911       MOVB RB1, [R1]
  32:EE66  1901       MOVZE R0, RB1
  32:EE68  5601       CMP R0, #0x1
  32:EE6A  AC02 EE72  AJMP NZ/NE, 32:EE72
  32:EE6E  AC00 F0C6  AJMP ALWAYS, 32:F0C6
  32:EE72  4800       MOV R0, #0x0
  32:EE74  58F0       MOV [--R15], R0
  32:EE76  4801       MOV R0, #0x1
  32:EE78  58F0       MOV [--R15], R0
> 32:EE7A  BD03 41C8  SCALL 03:41C8
  32:EE7E  50F4       ADD R15, #0x4
  32:EE80  791B 0008  MOVB RB1, [R11+0x0008]
  32:EE84  1901       MOVZE R0, RB1
  32:EE86  5601       CMP R0, #0x1
  32:EE88  AC02 F008  AJMP NZ/NE, 32:F008
  32:EE8C  68F1 0094  MOV REG[0xF1], #0x0094
  32:EE90  4800       MOV R0, #0x0
  32:EE92  783B FFFE  MOV R3, [R11+0xFFFE]
  32:EE96  5630       CMP R3, #0x0
  32:EE98  DE03       RJMP SGE, 32:EEA0 ; rel +3
  32:EE9A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:EE9E  D001       RJMP ALWAYS, 32:EEA2 ; rel +1
```

## `03:41F8`

Call sites: `2F:C132`

### `2F:C132` in `sub_2F_BFBC`

```text
  2F:C114  58F1       MOV [--R15], R1
  2F:C116  BD03 4184  SCALL 03:4184
  2F:C11A  50F2       ADD R15, #0x2
  2F:C11C  BD27 6ADC  SCALL 27:6ADC
  2F:C120  BD33 2FF2  SCALL 33:2FF2
  2F:C124  4801       MOV R0, #0x1
  2F:C126  58F0       MOV [--R15], R0
  2F:C128  BD03 4224  SCALL 03:4224
  2F:C12C  50F2       ADD R15, #0x2
  2F:C12E  BD03 4398  SCALL 03:4398
> 2F:C132  BD03 41F8  SCALL 03:41F8
  2F:C136  4910       MOVB RB1, #0x0
  2F:C138  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C13C  C700       NOP
  2F:C13E  A9F1 7AA8  MOVB [0x7AA8], REG[0xF1]
  2F:C142  4801       MOV R0, #0x1
  2F:C144  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C148  C700       NOP
  2F:C14A  A8F0 7934  MOV [0x7934], REG[0xF0]
  2F:C14E  4801       MOV R0, #0x1
  2F:C150  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C154  C700       NOP
  2F:C156  A8F0 7AB4  MOV [0x7AB4], REG[0xF0]
```

## `03:420C`

Call sites: `2C:C81E`

### `2C:C81E` in `sub_2C_C07E`

```text
  2C:C804  58F0       MOV [--R15], R0
  2C:C806  BD03 407C  SCALL 03:407C
  2C:C80A  50F8       ADD R15, #0x8
  2C:C80C  68F0 0054  MOV REG[0xF0], #0x0054
  2C:C810  58F0       MOV [--R15], R0
  2C:C812  68F1 00F0  MOV REG[0xF1], #0x00F0
  2C:C816  58F1       MOV [--R15], R1
  2C:C818  58F0       MOV [--R15], R0
  2C:C81A  4800       MOV R0, #0x0
  2C:C81C  58F0       MOV [--R15], R0
> 2C:C81E  BD03 420C  SCALL 03:420C
  2C:C822  50F8       ADD R15, #0x8
  2C:C824  68F0 0028  MOV REG[0xF0], #0x0028
  2C:C828  58F0       MOV [--R15], R0
  2C:C82A  68F1 3588  MOV REG[0xF1], #0x3588
  2C:C82E  68F0 0032  MOV REG[0xF0], #0x0032
  2C:C832  58F1       MOV [--R15], R1
  2C:C834  58F0       MOV [--R15], R0
  2C:C836  68F0 0056  MOV REG[0xF0], #0x0056
  2C:C83A  58F0       MOV [--R15], R0
  2C:C83C  4800       MOV R0, #0x0
  2C:C83E  58F0       MOV [--R15], R0
  2C:C840  BD2F A0B6  SCALL 2F:A0B6
```

## `03:4214`

Call sites: `2C:C86C`, `2F:BD82`, `2F:C2BA`, `31:7A4E`, `31:7FE2`, `31:8138`, `32:E752`, `32:E98A`, `32:ED5C`, `32:EF34`, `32:F030`

### `2C:C86C` in `sub_2C_C07E`

```text
  2C:C84E  BD03 41C8  SCALL 03:41C8
  2C:C852  50F4       ADD R15, #0x4
  2C:C854  68F0 0063  MOV REG[0xF0], #0x0063
  2C:C858  58F0       MOV [--R15], R0
  2C:C85A  68F0 00E4  MOV REG[0xF0], #0x00E4
  2C:C85E  58F0       MOV [--R15], R0
  2C:C860  68F0 0057  MOV REG[0xF0], #0x0057
  2C:C864  58F0       MOV [--R15], R0
  2C:C866  68F0 0024  MOV REG[0xF0], #0x0024
  2C:C86A  58F0       MOV [--R15], R0
> 2C:C86C  BD03 4214  SCALL 03:4214
  2C:C870  50F8       ADD R15, #0x8
  2C:C872  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C876  58F0       MOV [--R15], R0
  2C:C878  BD03 4324  SCALL 03:4324
  2C:C87C  50F2       ADD R15, #0x2
  2C:C87E  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C882  58F0       MOV [--R15], R0
  2C:C884  BD03 4328  SCALL 03:4328
  2C:C888  50F2       ADD R15, #0x2
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
  2C:C890  BD03 4324  SCALL 03:4324
```

### `2F:BD82` in `sub_2F_B8A4`

```text
  2F:BD66  BD03 41C8  SCALL 03:41C8
  2F:BD6A  50F4       ADD R15, #0x4
  2F:BD6C  68F0 0017  MOV REG[0xF0], #0x0017
  2F:BD70  58F0       MOV [--R15], R0
  2F:BD72  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:BD76  58F0       MOV [--R15], R0
  2F:BD78  480A       MOV R0, #0xA
  2F:BD7A  58F0       MOV [--R15], R0
  2F:BD7C  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD80  58F0       MOV [--R15], R0
> 2F:BD82  BD03 4214  SCALL 03:4214
  2F:BD86  50F8       ADD R15, #0x8
  2F:BD88  BD33 2FF2  SCALL 33:2FF2
  2F:BD8C  4801       MOV R0, #0x1
  2F:BD8E  58F0       MOV [--R15], R0
  2F:BD90  BD03 4224  SCALL 03:4224
  2F:BD94  50F2       ADD R15, #0x2
  2F:BD96  AC00 C914  AJMP ALWAYS, 2F:C914
  2F:BD9A  BD12 CBB0  SCALL 12:CBB0
  2F:BD9E  4911       MOVB RB1, #0x1
  2F:BDA0  6810 00A4  MOV REG[0x10], #0x00A4
  2F:BDA4  C700       NOP
  2F:BDA6  A9F1 7AA8  MOVB [0x7AA8], REG[0xF1]
```

### `2F:C2BA` in `sub_2F_C216`

```text
  2F:C29E  BD03 41C8  SCALL 03:41C8
  2F:C2A2  50F4       ADD R15, #0x4
  2F:C2A4  68F0 0017  MOV REG[0xF0], #0x0017
  2F:C2A8  58F0       MOV [--R15], R0
  2F:C2AA  68F0 00A8  MOV REG[0xF0], #0x00A8
  2F:C2AE  58F0       MOV [--R15], R0
  2F:C2B0  480A       MOV R0, #0xA
  2F:C2B2  58F0       MOV [--R15], R0
  2F:C2B4  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C2B8  58F0       MOV [--R15], R0
> 2F:C2BA  BD03 4214  SCALL 03:4214
  2F:C2BE  50F8       ADD R15, #0x8
  2F:C2C0  BD33 2FF2  SCALL 33:2FF2
  2F:C2C4  4801       MOV R0, #0x1
  2F:C2C6  58F0       MOV [--R15], R0
  2F:C2C8  BD03 4224  SCALL 03:4224
  2F:C2CC  50F2       ADD R15, #0x2
  2F:C2CE  4910       MOVB RB1, #0x0
  2F:C2D0  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C2D4  C700       NOP
  2F:C2D6  A9F1 7AAE  MOVB [0x7AAE], REG[0xF1]
  2F:C2DA  4800       MOV R0, #0x0
  2F:C2DC  6A0B FFFE  MOV [R11+0xFFFE], R0
```

### `31:7A4E` in `sub_31_7772`

```text
  31:7A32  780B FFFA  MOV R0, [R11+0xFFFA]
  31:7A36  0810       MOV R1, R0
  31:7A38  70F1 0032  ADD REG[0xF1], #0x0032
  31:7A3C  58F1       MOV [--R15], R1
  31:7A3E  781B FFFC  MOV R1, [R11+0xFFFC]
  31:7A42  0831       MOV R3, R1
  31:7A44  70F3 0028  ADD REG[0xF3], #0x0028
  31:7A48  58F3       MOV [--R15], R3
  31:7A4A  58F0       MOV [--R15], R0
  31:7A4C  58F1       MOV [--R15], R1
> 31:7A4E  BD03 4214  SCALL 03:4214
  31:7A52  50F8       ADD R15, #0x8
  31:7A54  68F1 0094  MOV REG[0xF1], #0x0094
  31:7A58  4800       MOV R0, #0x0
  31:7A5A  783B FFFE  MOV R3, [R11+0xFFFE]
  31:7A5E  5630       CMP R3, #0x0
  31:7A60  DE03       RJMP SGE, 31:7A68 ; rel +3
  31:7A62  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:7A66  D001       RJMP ALWAYS, 31:7A6A ; rel +1
  31:7A68  4820       MOV R2, #0x0
  31:7A6A  58F3       MOV [--R15], R3
  31:7A6C  58F2       MOV [--R15], R2
  31:7A6E  58F1       MOV [--R15], R1
```

### `31:7FE2` in `sub_31_7D02`

```text
  31:7FC6  780B FFFA  MOV R0, [R11+0xFFFA]
  31:7FCA  0810       MOV R1, R0
  31:7FCC  70F1 0028  ADD REG[0xF1], #0x0028
  31:7FD0  58F1       MOV [--R15], R1
  31:7FD2  781B FFFC  MOV R1, [R11+0xFFFC]
  31:7FD6  0831       MOV R3, R1
  31:7FD8  70F3 0020  ADD REG[0xF3], #0x0020
  31:7FDC  58F3       MOV [--R15], R3
  31:7FDE  58F0       MOV [--R15], R0
  31:7FE0  58F1       MOV [--R15], R1
> 31:7FE2  BD03 4214  SCALL 03:4214
  31:7FE6  50F8       ADD R15, #0x8
  31:7FE8  68F1 0094  MOV REG[0xF1], #0x0094
  31:7FEC  4800       MOV R0, #0x0
  31:7FEE  783B FFFE  MOV R3, [R11+0xFFFE]
  31:7FF2  5630       CMP R3, #0x0
  31:7FF4  DE03       RJMP SGE, 31:7FFC ; rel +3
  31:7FF6  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:7FFA  D001       RJMP ALWAYS, 31:7FFE ; rel +1
  31:7FFC  4820       MOV R2, #0x0
  31:7FFE  58F3       MOV [--R15], R3
  31:8000  58F2       MOV [--R15], R2
  31:8002  58F1       MOV [--R15], R1
```

### `31:8138` in `sub_31_7D02`

```text
  31:811C  780B FFFA  MOV R0, [R11+0xFFFA]
  31:8120  0810       MOV R1, R0
  31:8122  70F1 0028  ADD REG[0xF1], #0x0028
  31:8126  58F1       MOV [--R15], R1
  31:8128  781B FFFC  MOV R1, [R11+0xFFFC]
  31:812C  0831       MOV R3, R1
  31:812E  70F3 0020  ADD REG[0xF3], #0x0020
  31:8132  58F3       MOV [--R15], R3
  31:8134  58F0       MOV [--R15], R0
  31:8136  58F1       MOV [--R15], R1
> 31:8138  BD03 4214  SCALL 03:4214
  31:813C  50F8       ADD R15, #0x8
  31:813E  68F1 0094  MOV REG[0xF1], #0x0094
  31:8142  4800       MOV R0, #0x0
  31:8144  783B FFFE  MOV R3, [R11+0xFFFE]
  31:8148  5630       CMP R3, #0x0
  31:814A  DE03       RJMP SGE, 31:8152 ; rel +3
  31:814C  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  31:8150  D001       RJMP ALWAYS, 31:8154 ; rel +1
  31:8152  4820       MOV R2, #0x0
  31:8154  58F3       MOV [--R15], R3
  31:8156  58F2       MOV [--R15], R2
  31:8158  58F1       MOV [--R15], R1
```

### `32:E752` in `sub_32_E72E`

```text
  32:E73E  1013       ADD R1, R3
  32:E740  1102       ADDC R0, R2
  32:E742  4C11       SL R1, #0x1
  32:E744  5C01       SLOSB R0, #0x1
  32:E746  58F0       MOV [--R15], R0
  32:E748  1F90       POP REG[0x10]
  32:E74A  4D11       SR R1, #0x1
  32:E74C  2911       MOVB RB1, [R1]
  32:E74E  1901       MOVZE R0, RB1
  32:E750  58F0       MOV [--R15], R0
> 32:E752  BD03 4214  SCALL 03:4214
  32:E756  50F8       ADD R15, #0x8
  32:E758  4801       MOV R0, #0x1
  32:E75A  58F0       MOV [--R15], R0
  32:E75C  780B FFFA  MOV R0, [R11+0xFFFA]
  32:E760  58F0       MOV [--R15], R0
  32:E762  780B FFFC  MOV R0, [R11+0xFFFC]
  32:E766  58F0       MOV [--R15], R0
  32:E768  6810 00A4  MOV REG[0x10], #0x00A4
  32:E76C  88F0 7AF2  MOV REG[0xF0], [0x7AF2]
  32:E770  6A0B FFF0  MOV [R11+0xFFF0], R0
  32:E774  68F3 0094  MOV REG[0xF3], #0x0094
  32:E778  4820       MOV R2, #0x0
```

### `32:E98A` in `sub_32_E8EE`

```text
  32:E96E  780B FFFA  MOV R0, [R11+0xFFFA]
  32:E972  0810       MOV R1, R0
  32:E974  70F1 0028  ADD REG[0xF1], #0x0028
  32:E978  58F1       MOV [--R15], R1
  32:E97A  781B FFFC  MOV R1, [R11+0xFFFC]
  32:E97E  0831       MOV R3, R1
  32:E980  70F3 0020  ADD REG[0xF3], #0x0020
  32:E984  58F3       MOV [--R15], R3
  32:E986  58F0       MOV [--R15], R0
  32:E988  58F1       MOV [--R15], R1
> 32:E98A  BD03 4214  SCALL 03:4214
  32:E98E  50F8       ADD R15, #0x8
  32:E990  4810       MOV R1, #0x0
  32:E992  58F1       MOV [--R15], R1
  32:E994  793B FFF9  MOVB RB3, [R11+0xFFF9]
  32:E998  1913       MOVZE R1, RB3
  32:E99A  5610       CMP R1, #0x0
  32:E99C  DE03       RJMP SGE, 32:E9A4 ; rel +3
  32:E99E  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  32:E9A2  D001       RJMP ALWAYS, 32:E9A6 ; rel +1
  32:E9A4  4800       MOV R0, #0x0
  32:E9A6  4C11       SL R1, #0x1
  32:E9A8  5C01       SLOSB R0, #0x1
```

### `32:ED5C` in `sub_32_EC6E`

```text
  32:ED48  1013       ADD R1, R3
  32:ED4A  1102       ADDC R0, R2
  32:ED4C  4C11       SL R1, #0x1
  32:ED4E  5C01       SLOSB R0, #0x1
  32:ED50  58F0       MOV [--R15], R0
  32:ED52  1F90       POP REG[0x10]
  32:ED54  4D11       SR R1, #0x1
  32:ED56  2911       MOVB RB1, [R1]
  32:ED58  1901       MOVZE R0, RB1
  32:ED5A  58F0       MOV [--R15], R0
> 32:ED5C  BD03 4214  SCALL 03:4214
  32:ED60  50F8       ADD R15, #0x8
  32:ED62  4800       MOV R0, #0x0
  32:ED64  58F0       MOV [--R15], R0
  32:ED66  791B FFF9  MOVB RB1, [R11+0xFFF9]
  32:ED6A  1901       MOVZE R0, RB1
  32:ED6C  0810       MOV R1, R0
  32:ED6E  5610       CMP R1, #0x0
  32:ED70  DE03       RJMP SGE, 32:ED78 ; rel +3
  32:ED72  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  32:ED76  D001       RJMP ALWAYS, 32:ED7A ; rel +1
  32:ED78  4800       MOV R0, #0x0
  32:ED7A  4C11       SL R1, #0x1
```

### `32:EF34` in `sub_32_EC6E`

```text
  32:EF20  1013       ADD R1, R3
  32:EF22  1102       ADDC R0, R2
  32:EF24  4C11       SL R1, #0x1
  32:EF26  5C01       SLOSB R0, #0x1
  32:EF28  58F0       MOV [--R15], R0
  32:EF2A  1F90       POP REG[0x10]
  32:EF2C  4D11       SR R1, #0x1
  32:EF2E  2911       MOVB RB1, [R1]
  32:EF30  1901       MOVZE R0, RB1
  32:EF32  58F0       MOV [--R15], R0
> 32:EF34  BD03 4214  SCALL 03:4214
  32:EF38  50F8       ADD R15, #0x8
  32:EF3A  68F1 0094  MOV REG[0xF1], #0x0094
  32:EF3E  4800       MOV R0, #0x0
  32:EF40  783B FFFE  MOV R3, [R11+0xFFFE]
  32:EF44  5630       CMP R3, #0x0
  32:EF46  DE03       RJMP SGE, 32:EF4E ; rel +3
  32:EF48  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  32:EF4C  D001       RJMP ALWAYS, 32:EF50 ; rel +1
  32:EF4E  4820       MOV R2, #0x0
  32:EF50  58F3       MOV [--R15], R3
  32:EF52  58F2       MOV [--R15], R2
  32:EF54  58F1       MOV [--R15], R1
```

### `32:F030` in `sub_32_EC6E`

```text
  32:F014  782B FFFA  MOV R2, [R11+0xFFFA]
  32:F018  0812       MOV R1, R2
  32:F01A  70F1 0028  ADD REG[0xF1], #0x0028
  32:F01E  58F1       MOV [--R15], R1
  32:F020  781B FFFC  MOV R1, [R11+0xFFFC]
  32:F024  0801       MOV R0, R1
  32:F026  70F0 0020  ADD REG[0xF0], #0x0020
  32:F02A  58F0       MOV [--R15], R0
  32:F02C  58F2       MOV [--R15], R2
  32:F02E  58F1       MOV [--R15], R1
> 32:F030  BD03 4214  SCALL 03:4214
  32:F034  50F8       ADD R15, #0x8
  32:F036  781B FFFC  MOV R1, [R11+0xFFFC]
  32:F03A  72F1 0010  SUB REG[0xF1], #0x0010
  32:F03E  6A1B FFFC  MOV [R11+0xFFFC], R1
  32:F042  4936       MOVB RB3, #0x6
  32:F044  6B3B FFF9  MOVB [R11+0xFFF9], RB3
  32:F048  4812       MOV R1, #0x2
  32:F04A  58F1       MOV [--R15], R1
  32:F04C  793B FFF9  MOVB RB3, [R11+0xFFF9]
  32:F050  1913       MOVZE R1, RB3
  32:F052  5610       CMP R1, #0x0
  32:F054  DE03       RJMP SGE, 32:F05C ; rel +3
```

## `03:4218`

Call sites: `2C:C770`

### `2C:C770` in `sub_2C_C07E`

```text
  2C:C756  58F0       MOV [--R15], R0
  2C:C758  4806       MOV R0, #0x6
  2C:C75A  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C75E  99F1 7AD8  MOVZE REG[0xF1], [0x7AD8]
  2C:C762  C001       MUL R0, R1
  2C:C764  58F7       MOV [--R15], R7
  2C:C766  68F6 0054  MOV REG[0xF6], #0x0054
  2C:C76A  58F6       MOV [--R15], R6
  2C:C76C  4860       MOV R6, #0x0
  2C:C76E  58F6       MOV [--R15], R6
> 2C:C770  BD03 4218  SCALL 03:4218
  2C:C774  50F8       ADD R15, #0x8
  2C:C776  4860       MOV R6, #0x0
  2C:C778  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C77C  C700       NOP
  2C:C77E  A8F6 7938  MOV [0x7938], REG[0xF6]
  2C:C782  AC00 C872  AJMP ALWAYS, 2C:C872
  2C:C786  4863       MOV R6, #0x3
  2C:C788  58F6       MOV [--R15], R6
  2C:C78A  4860       MOV R6, #0x0
  2C:C78C  58F6       MOV [--R15], R6
  2C:C78E  BD29 91FA  SCALL 29:91FA
  2C:C792  50F4       ADD R15, #0x4
```

## `03:4224`

Call sites: `2F:BD32`, `2F:BD90`, `2F:C10C`, `2F:C128`, `2F:C268`, `2F:C2C8`, `30:13EE`, `30:2582`

### `2F:BD32` in `sub_2F_B8A4`

```text
  2F:BD12  6A2B FFFE  MOV [R11+0xFFFE], R2
  2F:BD16  782B FFFE  MOV R2, [R11+0xFFFE]
  2F:BD1A  6810 00A4  MOV REG[0x10], #0x00A4
  2F:BD1E  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  2F:BD22  1621       CMP R2, R1
  2F:BD24  AC09 BA08  AJMP SL, 2F:BA08
  2F:BD28  4811       MOV R1, #0x1
  2F:BD2A  6A1B FFFA  MOV [R11+0xFFFA], R1
  2F:BD2E  4810       MOV R1, #0x0
  2F:BD30  58F1       MOV [--R15], R1
> 2F:BD32  BD03 4224  SCALL 03:4224
  2F:BD36  50F2       ADD R15, #0x2
  2F:BD38  68F1 DB7C  MOV REG[0xF1], #0xDB7C
  2F:BD3C  68F0 0031  MOV REG[0xF0], #0x0031
  2F:BD40  58F1       MOV [--R15], R1
  2F:BD42  58F0       MOV [--R15], R0
  2F:BD44  480A       MOV R0, #0xA
  2F:BD46  58F0       MOV [--R15], R0
  2F:BD48  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD4C  58F0       MOV [--R15], R0
  2F:BD4E  BD03 41A8  SCALL 03:41A8
  2F:BD52  50F8       ADD R15, #0x8
  2F:BD54  480A       MOV R0, #0xA
```

### `2F:BD90` in `sub_2F_B8A4`

```text
  2F:BD76  58F0       MOV [--R15], R0
  2F:BD78  480A       MOV R0, #0xA
  2F:BD7A  58F0       MOV [--R15], R0
  2F:BD7C  68F0 0078  MOV REG[0xF0], #0x0078
  2F:BD80  58F0       MOV [--R15], R0
  2F:BD82  BD03 4214  SCALL 03:4214
  2F:BD86  50F8       ADD R15, #0x8
  2F:BD88  BD33 2FF2  SCALL 33:2FF2
  2F:BD8C  4801       MOV R0, #0x1
  2F:BD8E  58F0       MOV [--R15], R0
> 2F:BD90  BD03 4224  SCALL 03:4224
  2F:BD94  50F2       ADD R15, #0x2
  2F:BD96  AC00 C914  AJMP ALWAYS, 2F:C914
  2F:BD9A  BD12 CBB0  SCALL 12:CBB0
  2F:BD9E  4911       MOVB RB1, #0x1
  2F:BDA0  6810 00A4  MOV REG[0x10], #0x00A4
  2F:BDA4  C700       NOP
  2F:BDA6  A9F1 7AA8  MOVB [0x7AA8], REG[0xF1]
  2F:BDAA  4910       MOVB RB1, #0x0
  2F:BDAC  6B1B FFFD  MOVB [R11+0xFFFD], RB1
  2F:BDB0  AC00 C054  AJMP ALWAYS, 2F:C054
  2F:BDB4  68F1 0094  MOV REG[0xF1], #0x0094
  2F:BDB8  4800       MOV R0, #0x0
```

### `2F:C10C` in `sub_2F_BFBC`

```text
  2F:C0F0  88F1 7A88  MOV REG[0xF1], [0x7A88]
  2F:C0F4  58F1       MOV [--R15], R1
  2F:C0F6  BD03 4328  SCALL 03:4328
  2F:C0FA  50F2       ADD R15, #0x2
  2F:C0FC  4930       MOVB RB3, #0x0
  2F:C0FE  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C102  C700       NOP
  2F:C104  A9F3 7AA4  MOVB [0x7AA4], REG[0xF3]
  2F:C108  4810       MOV R1, #0x0
  2F:C10A  58F1       MOV [--R15], R1
> 2F:C10C  BD03 4224  SCALL 03:4224
  2F:C110  50F2       ADD R15, #0x2
  2F:C112  4811       MOV R1, #0x1
  2F:C114  58F1       MOV [--R15], R1
  2F:C116  BD03 4184  SCALL 03:4184
  2F:C11A  50F2       ADD R15, #0x2
  2F:C11C  BD27 6ADC  SCALL 27:6ADC
  2F:C120  BD33 2FF2  SCALL 33:2FF2
  2F:C124  4801       MOV R0, #0x1
  2F:C126  58F0       MOV [--R15], R0
  2F:C128  BD03 4224  SCALL 03:4224
  2F:C12C  50F2       ADD R15, #0x2
  2F:C12E  BD03 4398  SCALL 03:4398
```

### `2F:C128` in `sub_2F_BFBC`

```text
  2F:C10C  BD03 4224  SCALL 03:4224
  2F:C110  50F2       ADD R15, #0x2
  2F:C112  4811       MOV R1, #0x1
  2F:C114  58F1       MOV [--R15], R1
  2F:C116  BD03 4184  SCALL 03:4184
  2F:C11A  50F2       ADD R15, #0x2
  2F:C11C  BD27 6ADC  SCALL 27:6ADC
  2F:C120  BD33 2FF2  SCALL 33:2FF2
  2F:C124  4801       MOV R0, #0x1
  2F:C126  58F0       MOV [--R15], R0
> 2F:C128  BD03 4224  SCALL 03:4224
  2F:C12C  50F2       ADD R15, #0x2
  2F:C12E  BD03 4398  SCALL 03:4398
  2F:C132  BD03 41F8  SCALL 03:41F8
  2F:C136  4910       MOVB RB1, #0x0
  2F:C138  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C13C  C700       NOP
  2F:C13E  A9F1 7AA8  MOVB [0x7AA8], REG[0xF1]
  2F:C142  4801       MOV R0, #0x1
  2F:C144  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C148  C700       NOP
  2F:C14A  A8F0 7934  MOV [0x7934], REG[0xF0]
  2F:C14E  4801       MOV R0, #0x1
```

### `2F:C268` in `sub_2F_C216`

```text
  2F:C248  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  2F:C24C  1601       CMP R0, R1
  2F:C24E  AC09 C1E2  AJMP SL, 2F:C1E2
  2F:C252  AC00 C914  AJMP ALWAYS, 2F:C914
  2F:C256  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C25A  99F1 7A9A  MOVZE REG[0xF1], [0x7A9A]
  2F:C25E  5611       CMP R1, #0x1
  2F:C260  AC02 C914  AJMP NZ/NE, 2F:C914
  2F:C264  4810       MOV R1, #0x0
  2F:C266  58F1       MOV [--R15], R1
> 2F:C268  BD03 4224  SCALL 03:4224
  2F:C26C  50F2       ADD R15, #0x2
  2F:C26E  68F1 DB72  MOV REG[0xF1], #0xDB72
  2F:C272  68F0 0031  MOV REG[0xF0], #0x0031
  2F:C276  58F1       MOV [--R15], R1
  2F:C278  58F0       MOV [--R15], R0
  2F:C27A  480A       MOV R0, #0xA
  2F:C27C  58F0       MOV [--R15], R0
  2F:C27E  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C282  58F0       MOV [--R15], R0
  2F:C284  BD03 41A8  SCALL 03:41A8
  2F:C288  50F8       ADD R15, #0x8
  2F:C28A  68F0 0064  MOV REG[0xF0], #0x0064
```

### `2F:C2C8` in `sub_2F_C216`

```text
  2F:C2AE  58F0       MOV [--R15], R0
  2F:C2B0  480A       MOV R0, #0xA
  2F:C2B2  58F0       MOV [--R15], R0
  2F:C2B4  68F0 0078  MOV REG[0xF0], #0x0078
  2F:C2B8  58F0       MOV [--R15], R0
  2F:C2BA  BD03 4214  SCALL 03:4214
  2F:C2BE  50F8       ADD R15, #0x8
  2F:C2C0  BD33 2FF2  SCALL 33:2FF2
  2F:C2C4  4801       MOV R0, #0x1
  2F:C2C6  58F0       MOV [--R15], R0
> 2F:C2C8  BD03 4224  SCALL 03:4224
  2F:C2CC  50F2       ADD R15, #0x2
  2F:C2CE  4910       MOVB RB1, #0x0
  2F:C2D0  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C2D4  C700       NOP
  2F:C2D6  A9F1 7AAE  MOVB [0x7AAE], REG[0xF1]
  2F:C2DA  4800       MOV R0, #0x0
  2F:C2DC  6A0B FFFE  MOV [R11+0xFFFE], R0
  2F:C2E0  AC00 C5F0  AJMP ALWAYS, 2F:C5F0
  2F:C2E4  68F1 0094  MOV REG[0xF1], #0x0094
  2F:C2E8  4800       MOV R0, #0x0
  2F:C2EA  783B FFFE  MOV R3, [R11+0xFFFE]
  2F:C2EE  5630       CMP R3, #0x0
```

### `30:13EE` in `sub_30_1084`

```text
  30:13D6  58F0       MOV [--R15], R0
  30:13D8  1F90       POP REG[0x10]
  30:13DA  4D11       SR R1, #0x1
  30:13DC  2911       MOVB RB1, [R1]
  30:13DE  1901       MOVZE R0, RB1
  30:13E0  5605       CMP R0, #0x5
  30:13E2  AC02 13EA  AJMP NZ/NE, 30:13EA
  30:13E6  AC00 25B0  AJMP ALWAYS, 30:25B0
  30:13EA  4800       MOV R0, #0x0
  30:13EC  58F0       MOV [--R15], R0
> 30:13EE  BD03 4224  SCALL 03:4224
  30:13F2  50F2       ADD R15, #0x2
  30:13F4  4800       MOV R0, #0x0
  30:13F6  6A0B FFFC  MOV [R11+0xFFFC], R0
  30:13FA  AC00 255E  AJMP ALWAYS, 30:255E
  30:13FE  780B FFFC  MOV R0, [R11+0xFFFC]
  30:1402  0810       MOV R1, R0
  30:1404  5610       CMP R1, #0x0
  30:1406  DE03       RJMP SGE, 30:140E ; rel +3
  30:1408  68F0 FFFF  MOV REG[0xF0], #0xFFFF
  30:140C  D001       RJMP ALWAYS, 30:1410 ; rel +1
  30:140E  4800       MOV R0, #0x0
  30:1410  4C11       SL R1, #0x1
```

### `30:2582` in `sub_30_1EAA`

```text
  30:2562  6810 00A4  MOV REG[0x10], #0x00A4
  30:2566  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  30:256A  6810 00A4  MOV REG[0x10], #0x00A4
  30:256E  99F3 7AF0  MOVZE REG[0xF3], [0x7AF0]
  30:2572  1013       ADD R1, R3
  30:2574  1601       CMP R0, R1
  30:2576  AC09 13FE  AJMP SL, 30:13FE
  30:257A  BD33 2FF2  SCALL 33:2FF2
  30:257E  4811       MOV R1, #0x1
  30:2580  58F1       MOV [--R15], R1
> 30:2582  BD03 4224  SCALL 03:4224
  30:2586  50F2       ADD R15, #0x2
  30:2588  781B FFCE  MOV R1, [R11+0xFFCE]
  30:258C  5610       CMP R1, #0x0
  30:258E  AC02 25A0  AJMP NZ/NE, 30:25A0
  30:2592  4815       MOV R1, #0x5
  30:2594  58F1       MOV [--R15], R1
  30:2596  BD03 4120  SCALL 03:4120
  30:259A  50F2       ADD R15, #0x2
  30:259C  AC00 25AC  AJMP ALWAYS, 30:25AC
  30:25A0  68F0 001E  MOV REG[0xF0], #0x001E
  30:25A4  58F0       MOV [--R15], R0
  30:25A6  BD03 4120  SCALL 03:4120
```

## `03:422C`

Call sites: `2F:BE54`, `30:25AC`

### `2F:BE54` in `sub_2F_B8A4`

```text
  2F:BE3E  1F90       POP REG[0x10]
  2F:BE40  3F01       CRIT #1
  2F:BE42  50F1       ADD R15, #0x1
  2F:BE44  3B1F       MOVB [R1], [R15++]
  2F:BE46  4820       MOV R2, #0x0
  2F:BE48  58F2       MOV [--R15], R2
  2F:BE4A  58F2       MOV [--R15], R2
  2F:BE4C  58F2       MOV [--R15], R2
  2F:BE4E  BD1A 8C6E  SCALL 1A:8C6E
  2F:BE52  50F6       ADD R15, #0x6
> 2F:BE54  BD03 422C  SCALL 03:422C
  2F:BE58  68F1 0094  MOV REG[0xF1], #0x0094
  2F:BE5C  4800       MOV R0, #0x0
  2F:BE5E  795B FFFD  MOVB RB5, [R11+0xFFFD]
  2F:BE62  1925       MOVZE R2, RB5
  2F:BE64  0832       MOV R3, R2
  2F:BE66  5630       CMP R3, #0x0
  2F:BE68  DE03       RJMP SGE, 2F:BE70 ; rel +3
  2F:BE6A  68F2 FFFF  MOV REG[0xF2], #0xFFFF
  2F:BE6E  D001       RJMP ALWAYS, 2F:BE72 ; rel +1
  2F:BE70  4820       MOV R2, #0x0
  2F:BE72  58F3       MOV [--R15], R3
  2F:BE74  58F2       MOV [--R15], R2
```

### `30:25AC` in `sub_30_1EAA`

```text
  30:258E  AC02 25A0  AJMP NZ/NE, 30:25A0
  30:2592  4815       MOV R1, #0x5
  30:2594  58F1       MOV [--R15], R1
  30:2596  BD03 4120  SCALL 03:4120
  30:259A  50F2       ADD R15, #0x2
  30:259C  AC00 25AC  AJMP ALWAYS, 30:25AC
  30:25A0  68F0 001E  MOV REG[0xF0], #0x001E
  30:25A4  58F0       MOV [--R15], R0
  30:25A6  BD03 4120  SCALL 03:4120
  30:25AA  50F2       ADD R15, #0x2
> 30:25AC  BD03 422C  SCALL 03:422C
  30:25B0  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25B4  5001       ADD R0, #0x1
  30:25B6  6A0B FFCE  MOV [R11+0xFFCE], R0
  30:25BA  780B FFCE  MOV R0, [R11+0xFFCE]
  30:25BE  5603       CMP R0, #0x3
  30:25C0  AC09 138C  AJMP SL, 30:138C
  30:25C4  387F       MOV R7, [R15++]
  30:25C6  386F       MOV R6, [R15++]
  30:25C8  385F       MOV R5, [R15++]
  30:25CA  384F       MOV R4, [R15++]
  30:25CC  383F       MOV R3, [R15++]
  30:25CE  382F       MOV R2, [R15++]
```

## `03:431C`

Call sites: `2C:C14A`, `2C:C26E`, `2C:C392`, `2C:C4B6`

### `2C:C14A` in `sub_2C_C07E`

```text
  2C:C12C  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C130  58F0       MOV [--R15], R0
  2C:C132  BD03 4324  SCALL 03:4324
  2C:C136  50F2       ADD R15, #0x2
  2C:C138  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C13C  58F0       MOV [--R15], R0
  2C:C13E  BD03 4328  SCALL 03:4328
  2C:C142  50F2       ADD R15, #0x2
  2C:C144  68F0 0029  MOV REG[0xF0], #0x0029
  2C:C148  58F0       MOV [--R15], R0
> 2C:C14A  BD03 431C  SCALL 03:431C
  2C:C14E  50F2       ADD R15, #0x2
  2C:C150  6A0B FFCE  MOV [R11+0xFFCE], R0
  2C:C154  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C158  58F0       MOV [--R15], R0
  2C:C15A  BD03 4320  SCALL 03:4320
  2C:C15E  50F2       ADD R15, #0x2
  2C:C160  6A0B FFDE  MOV [R11+0xFFDE], R0
  2C:C164  6A1B FFE0  MOV [R11+0xFFE0], R1
  2C:C168  4801       MOV R0, #0x1
  2C:C16A  58F0       MOV [--R15], R0
  2C:C16C  081B       MOV R1, R11
  2C:C16E  70F1 FFFF  ADD REG[0xF1], #0xFFFF
```

### `2C:C26E` in `sub_2C_C07E`

```text
  2C:C258  4C11       SL R1, #0x1
  2C:C25A  5C01       SLOSB R0, #0x1
  2C:C25C  4D11       SR R1, #0x1
  2C:C25E  58F0       MOV [--R15], R0
  2C:C260  1F90       POP REG[0x10]
  2C:C262  3F01       CRIT #1
  2C:C264  50F1       ADD R15, #0x1
  2C:C266  3B1F       MOVB [R1], [R15++]
  2C:C268  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C26C  58F2       MOV [--R15], R2
> 2C:C26E  BD03 431C  SCALL 03:431C
  2C:C272  50F2       ADD R15, #0x2
  2C:C274  6A0B FFCC  MOV [R11+0xFFCC], R0
  2C:C278  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C27C  58F0       MOV [--R15], R0
  2C:C27E  BD03 4320  SCALL 03:4320
  2C:C282  50F2       ADD R15, #0x2
  2C:C284  6A0B FFDA  MOV [R11+0xFFDA], R0
  2C:C288  6A1B FFDC  MOV [R11+0xFFDC], R1
  2C:C28C  4801       MOV R0, #0x1
  2C:C28E  58F0       MOV [--R15], R0
  2C:C290  081B       MOV R1, R11
  2C:C292  70F1 FFFF  ADD REG[0xF1], #0xFFFF
```

### `2C:C392` in `sub_2C_C07E`

```text
  2C:C37C  4C11       SL R1, #0x1
  2C:C37E  5C01       SLOSB R0, #0x1
  2C:C380  4D11       SR R1, #0x1
  2C:C382  58F0       MOV [--R15], R0
  2C:C384  1F90       POP REG[0x10]
  2C:C386  3F01       CRIT #1
  2C:C388  50F1       ADD R15, #0x1
  2C:C38A  3B1F       MOVB [R1], [R15++]
  2C:C38C  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C390  58F2       MOV [--R15], R2
> 2C:C392  BD03 431C  SCALL 03:431C
  2C:C396  50F2       ADD R15, #0x2
  2C:C398  6A0B FFCA  MOV [R11+0xFFCA], R0
  2C:C39C  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C3A0  58F0       MOV [--R15], R0
  2C:C3A2  BD03 4320  SCALL 03:4320
  2C:C3A6  50F2       ADD R15, #0x2
  2C:C3A8  6A0B FFD6  MOV [R11+0xFFD6], R0
  2C:C3AC  6A1B FFD8  MOV [R11+0xFFD8], R1
  2C:C3B0  4801       MOV R0, #0x1
  2C:C3B2  58F0       MOV [--R15], R0
  2C:C3B4  081B       MOV R1, R11
  2C:C3B6  70F1 FFFF  ADD REG[0xF1], #0xFFFF
```

### `2C:C4B6` in `sub_2C_C07E`

```text
  2C:C4A0  4C11       SL R1, #0x1
  2C:C4A2  5C01       SLOSB R0, #0x1
  2C:C4A4  4D11       SR R1, #0x1
  2C:C4A6  58F0       MOV [--R15], R0
  2C:C4A8  1F90       POP REG[0x10]
  2C:C4AA  3F01       CRIT #1
  2C:C4AC  50F1       ADD R15, #0x1
  2C:C4AE  3B1F       MOVB [R1], [R15++]
  2C:C4B0  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C4B4  58F2       MOV [--R15], R2
> 2C:C4B6  BD03 431C  SCALL 03:431C
  2C:C4BA  50F2       ADD R15, #0x2
  2C:C4BC  6A0B FFC8  MOV [R11+0xFFC8], R0
  2C:C4C0  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C4C4  58F0       MOV [--R15], R0
  2C:C4C6  BD03 4320  SCALL 03:4320
  2C:C4CA  50F2       ADD R15, #0x2
  2C:C4CC  6A0B FFD2  MOV [R11+0xFFD2], R0
  2C:C4D0  6A1B FFD4  MOV [R11+0xFFD4], R1
  2C:C4D4  4801       MOV R0, #0x1
  2C:C4D6  58F0       MOV [--R15], R0
  2C:C4D8  081B       MOV R1, R11
  2C:C4DA  70F1 FFFF  ADD REG[0xF1], #0xFFFF
```

## `03:4320`

Call sites: `2C:C15A`, `2C:C27E`, `2C:C3A2`, `2C:C4C6`

### `2C:C15A` in `sub_2C_C07E`

```text
  2C:C13C  58F0       MOV [--R15], R0
  2C:C13E  BD03 4328  SCALL 03:4328
  2C:C142  50F2       ADD R15, #0x2
  2C:C144  68F0 0029  MOV REG[0xF0], #0x0029
  2C:C148  58F0       MOV [--R15], R0
  2C:C14A  BD03 431C  SCALL 03:431C
  2C:C14E  50F2       ADD R15, #0x2
  2C:C150  6A0B FFCE  MOV [R11+0xFFCE], R0
  2C:C154  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C158  58F0       MOV [--R15], R0
> 2C:C15A  BD03 4320  SCALL 03:4320
  2C:C15E  50F2       ADD R15, #0x2
  2C:C160  6A0B FFDE  MOV [R11+0xFFDE], R0
  2C:C164  6A1B FFE0  MOV [R11+0xFFE0], R1
  2C:C168  4801       MOV R0, #0x1
  2C:C16A  58F0       MOV [--R15], R0
  2C:C16C  081B       MOV R1, R11
  2C:C16E  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C172  4800       MOV R0, #0x0
  2C:C174  58F1       MOV [--R15], R1
  2C:C176  58F0       MOV [--R15], R0
  2C:C178  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C17C  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `2C:C27E` in `sub_2C_C07E`

```text
  2C:C262  3F01       CRIT #1
  2C:C264  50F1       ADD R15, #0x1
  2C:C266  3B1F       MOVB [R1], [R15++]
  2C:C268  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C26C  58F2       MOV [--R15], R2
  2C:C26E  BD03 431C  SCALL 03:431C
  2C:C272  50F2       ADD R15, #0x2
  2C:C274  6A0B FFCC  MOV [R11+0xFFCC], R0
  2C:C278  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C27C  58F0       MOV [--R15], R0
> 2C:C27E  BD03 4320  SCALL 03:4320
  2C:C282  50F2       ADD R15, #0x2
  2C:C284  6A0B FFDA  MOV [R11+0xFFDA], R0
  2C:C288  6A1B FFDC  MOV [R11+0xFFDC], R1
  2C:C28C  4801       MOV R0, #0x1
  2C:C28E  58F0       MOV [--R15], R0
  2C:C290  081B       MOV R1, R11
  2C:C292  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C296  4800       MOV R0, #0x0
  2C:C298  58F1       MOV [--R15], R1
  2C:C29A  58F0       MOV [--R15], R0
  2C:C29C  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C2A0  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `2C:C3A2` in `sub_2C_C07E`

```text
  2C:C386  3F01       CRIT #1
  2C:C388  50F1       ADD R15, #0x1
  2C:C38A  3B1F       MOVB [R1], [R15++]
  2C:C38C  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C390  58F2       MOV [--R15], R2
  2C:C392  BD03 431C  SCALL 03:431C
  2C:C396  50F2       ADD R15, #0x2
  2C:C398  6A0B FFCA  MOV [R11+0xFFCA], R0
  2C:C39C  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C3A0  58F0       MOV [--R15], R0
> 2C:C3A2  BD03 4320  SCALL 03:4320
  2C:C3A6  50F2       ADD R15, #0x2
  2C:C3A8  6A0B FFD6  MOV [R11+0xFFD6], R0
  2C:C3AC  6A1B FFD8  MOV [R11+0xFFD8], R1
  2C:C3B0  4801       MOV R0, #0x1
  2C:C3B2  58F0       MOV [--R15], R0
  2C:C3B4  081B       MOV R1, R11
  2C:C3B6  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C3BA  4800       MOV R0, #0x0
  2C:C3BC  58F1       MOV [--R15], R1
  2C:C3BE  58F0       MOV [--R15], R0
  2C:C3C0  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C3C4  88F0 7992  MOV REG[0xF0], [0x7992]
```

### `2C:C4C6` in `sub_2C_C07E`

```text
  2C:C4AA  3F01       CRIT #1
  2C:C4AC  50F1       ADD R15, #0x1
  2C:C4AE  3B1F       MOVB [R1], [R15++]
  2C:C4B0  68F2 0029  MOV REG[0xF2], #0x0029
  2C:C4B4  58F2       MOV [--R15], R2
  2C:C4B6  BD03 431C  SCALL 03:431C
  2C:C4BA  50F2       ADD R15, #0x2
  2C:C4BC  6A0B FFC8  MOV [R11+0xFFC8], R0
  2C:C4C0  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C4C4  58F0       MOV [--R15], R0
> 2C:C4C6  BD03 4320  SCALL 03:4320
  2C:C4CA  50F2       ADD R15, #0x2
  2C:C4CC  6A0B FFD2  MOV [R11+0xFFD2], R0
  2C:C4D0  6A1B FFD4  MOV [R11+0xFFD4], R1
  2C:C4D4  4801       MOV R0, #0x1
  2C:C4D6  58F0       MOV [--R15], R0
  2C:C4D8  081B       MOV R1, R11
  2C:C4DA  70F1 FFFF  ADD REG[0xF1], #0xFFFF
  2C:C4DE  4800       MOV R0, #0x0
  2C:C4E0  58F1       MOV [--R15], R1
  2C:C4E2  58F0       MOV [--R15], R0
  2C:C4E4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C4E8  88F0 7992  MOV REG[0xF0], [0x7992]
```

## `03:4324`

Call sites: `2C:C132`, `2C:C878`, `2C:C890`, `2C:C8A8`, `2C:C8C0`, `2F:C0E6`

### `2C:C132` in `sub_2C_C07E`

```text
  2C:C11A  3F10       IGNDS #0
  2C:C11C  1A0E       MOV [R0++], R14
  2C:C11E  380F       MOV R0, [R15++]
  2C:C120  38EF       MOV R14, [R15++]
  2C:C122  4D01       SR R0, #0x1
  2C:C124  5D10       SROSB R1, #0x0
  2C:C126  BD29 E552  SCALL 29:E552
  2C:C12A  50FC       ADD R15, #0xC
  2C:C12C  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C130  58F0       MOV [--R15], R0
> 2C:C132  BD03 4324  SCALL 03:4324
  2C:C136  50F2       ADD R15, #0x2
  2C:C138  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C13C  58F0       MOV [--R15], R0
  2C:C13E  BD03 4328  SCALL 03:4328
  2C:C142  50F2       ADD R15, #0x2
  2C:C144  68F0 0029  MOV REG[0xF0], #0x0029
  2C:C148  58F0       MOV [--R15], R0
  2C:C14A  BD03 431C  SCALL 03:431C
  2C:C14E  50F2       ADD R15, #0x2
  2C:C150  6A0B FFCE  MOV [R11+0xFFCE], R0
  2C:C154  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C158  58F0       MOV [--R15], R0
```

### `2C:C878` in `sub_2C_C07E`

```text
  2C:C85A  68F0 00E4  MOV REG[0xF0], #0x00E4
  2C:C85E  58F0       MOV [--R15], R0
  2C:C860  68F0 0057  MOV REG[0xF0], #0x0057
  2C:C864  58F0       MOV [--R15], R0
  2C:C866  68F0 0024  MOV REG[0xF0], #0x0024
  2C:C86A  58F0       MOV [--R15], R0
  2C:C86C  BD03 4214  SCALL 03:4214
  2C:C870  50F8       ADD R15, #0x8
  2C:C872  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C876  58F0       MOV [--R15], R0
> 2C:C878  BD03 4324  SCALL 03:4324
  2C:C87C  50F2       ADD R15, #0x2
  2C:C87E  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C882  58F0       MOV [--R15], R0
  2C:C884  BD03 4328  SCALL 03:4328
  2C:C888  50F2       ADD R15, #0x2
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
  2C:C890  BD03 4324  SCALL 03:4324
  2C:C894  50F2       ADD R15, #0x2
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
  2C:C89C  BD03 4328  SCALL 03:4328
```

### `2C:C890` in `sub_2C_C07E`

```text
  2C:C872  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C876  58F0       MOV [--R15], R0
  2C:C878  BD03 4324  SCALL 03:4324
  2C:C87C  50F2       ADD R15, #0x2
  2C:C87E  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C882  58F0       MOV [--R15], R0
  2C:C884  BD03 4328  SCALL 03:4328
  2C:C888  50F2       ADD R15, #0x2
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
> 2C:C890  BD03 4324  SCALL 03:4324
  2C:C894  50F2       ADD R15, #0x2
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
  2C:C89C  BD03 4328  SCALL 03:4328
  2C:C8A0  50F2       ADD R15, #0x2
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
  2C:C8A8  BD03 4324  SCALL 03:4324
  2C:C8AC  50F2       ADD R15, #0x2
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
  2C:C8B4  BD03 4328  SCALL 03:4328
```

### `2C:C8A8` in `sub_2C_C07E`

```text
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
  2C:C890  BD03 4324  SCALL 03:4324
  2C:C894  50F2       ADD R15, #0x2
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
  2C:C89C  BD03 4328  SCALL 03:4328
  2C:C8A0  50F2       ADD R15, #0x2
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
> 2C:C8A8  BD03 4324  SCALL 03:4324
  2C:C8AC  50F2       ADD R15, #0x2
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
  2C:C8B4  BD03 4328  SCALL 03:4328
  2C:C8B8  50F2       ADD R15, #0x2
  2C:C8BA  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8BE  58F0       MOV [--R15], R0
  2C:C8C0  BD03 4324  SCALL 03:4324
  2C:C8C4  50F2       ADD R15, #0x2
  2C:C8C6  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8CA  58F0       MOV [--R15], R0
  2C:C8CC  BD03 4328  SCALL 03:4328
```

### `2C:C8C0` in `sub_2C_C07E`

```text
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
  2C:C8A8  BD03 4324  SCALL 03:4324
  2C:C8AC  50F2       ADD R15, #0x2
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
  2C:C8B4  BD03 4328  SCALL 03:4328
  2C:C8B8  50F2       ADD R15, #0x2
  2C:C8BA  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8BE  58F0       MOV [--R15], R0
> 2C:C8C0  BD03 4324  SCALL 03:4324
  2C:C8C4  50F2       ADD R15, #0x2
  2C:C8C6  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8CA  58F0       MOV [--R15], R0
  2C:C8CC  BD03 4328  SCALL 03:4328
  2C:C8D0  50F2       ADD R15, #0x2
  2C:C8D2  4800       MOV R0, #0x0
  2C:C8D4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8D8  C700       NOP
  2C:C8DA  A8F0 7AB4  MOV [0x7AB4], REG[0xF0]
  2C:C8DE  4910       MOVB RB1, #0x0
  2C:C8E0  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8E4  C700       NOP
```

### `2F:C0E6` in `sub_2F_BFBC`

```text
  2F:C0C4  6B5B FFFD  MOVB [R11+0xFFFD], RB5
  2F:C0C8  795B FFFD  MOVB RB5, [R11+0xFFFD]
  2F:C0CC  1925       MOVZE R2, RB5
  2F:C0CE  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C0D2  99F1 7AFA  MOVZE REG[0xF1], [0x7AFA]
  2F:C0D6  1621       CMP R2, R1
  2F:C0D8  AC09 C072  AJMP SL, 2F:C072
  2F:C0DC  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C0E0  88F1 7A88  MOV REG[0xF1], [0x7A88]
  2F:C0E4  58F1       MOV [--R15], R1
> 2F:C0E6  BD03 4324  SCALL 03:4324
  2F:C0EA  50F2       ADD R15, #0x2
  2F:C0EC  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C0F0  88F1 7A88  MOV REG[0xF1], [0x7A88]
  2F:C0F4  58F1       MOV [--R15], R1
  2F:C0F6  BD03 4328  SCALL 03:4328
  2F:C0FA  50F2       ADD R15, #0x2
  2F:C0FC  4930       MOVB RB3, #0x0
  2F:C0FE  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C102  C700       NOP
  2F:C104  A9F3 7AA4  MOVB [0x7AA4], REG[0xF3]
  2F:C108  4810       MOV R1, #0x0
  2F:C10A  58F1       MOV [--R15], R1
```

## `03:4328`

Call sites: `2C:C13E`, `2C:C884`, `2C:C89C`, `2C:C8B4`, `2C:C8CC`, `2F:C0F6`

### `2C:C13E` in `sub_2C_C07E`

```text
  2C:C122  4D01       SR R0, #0x1
  2C:C124  5D10       SROSB R1, #0x0
  2C:C126  BD29 E552  SCALL 29:E552
  2C:C12A  50FC       ADD R15, #0xC
  2C:C12C  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C130  58F0       MOV [--R15], R0
  2C:C132  BD03 4324  SCALL 03:4324
  2C:C136  50F2       ADD R15, #0x2
  2C:C138  780B FFD0  MOV R0, [R11+0xFFD0]
  2C:C13C  58F0       MOV [--R15], R0
> 2C:C13E  BD03 4328  SCALL 03:4328
  2C:C142  50F2       ADD R15, #0x2
  2C:C144  68F0 0029  MOV REG[0xF0], #0x0029
  2C:C148  58F0       MOV [--R15], R0
  2C:C14A  BD03 431C  SCALL 03:431C
  2C:C14E  50F2       ADD R15, #0x2
  2C:C150  6A0B FFCE  MOV [R11+0xFFCE], R0
  2C:C154  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C158  58F0       MOV [--R15], R0
  2C:C15A  BD03 4320  SCALL 03:4320
  2C:C15E  50F2       ADD R15, #0x2
  2C:C160  6A0B FFDE  MOV [R11+0xFFDE], R0
  2C:C164  6A1B FFE0  MOV [R11+0xFFE0], R1
```

### `2C:C884` in `sub_2C_C07E`

```text
  2C:C866  68F0 0024  MOV REG[0xF0], #0x0024
  2C:C86A  58F0       MOV [--R15], R0
  2C:C86C  BD03 4214  SCALL 03:4214
  2C:C870  50F8       ADD R15, #0x8
  2C:C872  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C876  58F0       MOV [--R15], R0
  2C:C878  BD03 4324  SCALL 03:4324
  2C:C87C  50F2       ADD R15, #0x2
  2C:C87E  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C882  58F0       MOV [--R15], R0
> 2C:C884  BD03 4328  SCALL 03:4328
  2C:C888  50F2       ADD R15, #0x2
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
  2C:C890  BD03 4324  SCALL 03:4324
  2C:C894  50F2       ADD R15, #0x2
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
  2C:C89C  BD03 4328  SCALL 03:4328
  2C:C8A0  50F2       ADD R15, #0x2
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
  2C:C8A8  BD03 4324  SCALL 03:4324
```

### `2C:C89C` in `sub_2C_C07E`

```text
  2C:C87E  780B FFCE  MOV R0, [R11+0xFFCE]
  2C:C882  58F0       MOV [--R15], R0
  2C:C884  BD03 4328  SCALL 03:4328
  2C:C888  50F2       ADD R15, #0x2
  2C:C88A  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C88E  58F0       MOV [--R15], R0
  2C:C890  BD03 4324  SCALL 03:4324
  2C:C894  50F2       ADD R15, #0x2
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
> 2C:C89C  BD03 4328  SCALL 03:4328
  2C:C8A0  50F2       ADD R15, #0x2
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
  2C:C8A8  BD03 4324  SCALL 03:4324
  2C:C8AC  50F2       ADD R15, #0x2
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
  2C:C8B4  BD03 4328  SCALL 03:4328
  2C:C8B8  50F2       ADD R15, #0x2
  2C:C8BA  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8BE  58F0       MOV [--R15], R0
  2C:C8C0  BD03 4324  SCALL 03:4324
```

### `2C:C8B4` in `sub_2C_C07E`

```text
  2C:C896  780B FFCC  MOV R0, [R11+0xFFCC]
  2C:C89A  58F0       MOV [--R15], R0
  2C:C89C  BD03 4328  SCALL 03:4328
  2C:C8A0  50F2       ADD R15, #0x2
  2C:C8A2  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8A6  58F0       MOV [--R15], R0
  2C:C8A8  BD03 4324  SCALL 03:4324
  2C:C8AC  50F2       ADD R15, #0x2
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
> 2C:C8B4  BD03 4328  SCALL 03:4328
  2C:C8B8  50F2       ADD R15, #0x2
  2C:C8BA  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8BE  58F0       MOV [--R15], R0
  2C:C8C0  BD03 4324  SCALL 03:4324
  2C:C8C4  50F2       ADD R15, #0x2
  2C:C8C6  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8CA  58F0       MOV [--R15], R0
  2C:C8CC  BD03 4328  SCALL 03:4328
  2C:C8D0  50F2       ADD R15, #0x2
  2C:C8D2  4800       MOV R0, #0x0
  2C:C8D4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8D8  C700       NOP
```

### `2C:C8CC` in `sub_2C_C07E`

```text
  2C:C8AE  780B FFCA  MOV R0, [R11+0xFFCA]
  2C:C8B2  58F0       MOV [--R15], R0
  2C:C8B4  BD03 4328  SCALL 03:4328
  2C:C8B8  50F2       ADD R15, #0x2
  2C:C8BA  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8BE  58F0       MOV [--R15], R0
  2C:C8C0  BD03 4324  SCALL 03:4324
  2C:C8C4  50F2       ADD R15, #0x2
  2C:C8C6  780B FFC8  MOV R0, [R11+0xFFC8]
  2C:C8CA  58F0       MOV [--R15], R0
> 2C:C8CC  BD03 4328  SCALL 03:4328
  2C:C8D0  50F2       ADD R15, #0x2
  2C:C8D2  4800       MOV R0, #0x0
  2C:C8D4  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8D8  C700       NOP
  2C:C8DA  A8F0 7AB4  MOV [0x7AB4], REG[0xF0]
  2C:C8DE  4910       MOVB RB1, #0x0
  2C:C8E0  6810 00A4  MOV REG[0x10], #0x00A4
  2C:C8E4  C700       NOP
  2C:C8E6  A9F1 7A32  MOVB [0x7A32], REG[0xF1]
  2C:C8EA  BD33 2FF2  SCALL 33:2FF2
  2C:C8EE  68F0 0FA0  MOV REG[0xF0], #0x0FA0
  2C:C8F2  58F0       MOV [--R15], R0
```

### `2F:C0F6` in `sub_2F_BFBC`

```text
  2F:C0D6  1621       CMP R2, R1
  2F:C0D8  AC09 C072  AJMP SL, 2F:C072
  2F:C0DC  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C0E0  88F1 7A88  MOV REG[0xF1], [0x7A88]
  2F:C0E4  58F1       MOV [--R15], R1
  2F:C0E6  BD03 4324  SCALL 03:4324
  2F:C0EA  50F2       ADD R15, #0x2
  2F:C0EC  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C0F0  88F1 7A88  MOV REG[0xF1], [0x7A88]
  2F:C0F4  58F1       MOV [--R15], R1
> 2F:C0F6  BD03 4328  SCALL 03:4328
  2F:C0FA  50F2       ADD R15, #0x2
  2F:C0FC  4930       MOVB RB3, #0x0
  2F:C0FE  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C102  C700       NOP
  2F:C104  A9F3 7AA4  MOVB [0x7AA4], REG[0xF3]
  2F:C108  4810       MOV R1, #0x0
  2F:C10A  58F1       MOV [--R15], R1
  2F:C10C  BD03 4224  SCALL 03:4224
  2F:C110  50F2       ADD R15, #0x2
  2F:C112  4811       MOV R1, #0x1
  2F:C114  58F1       MOV [--R15], R1
  2F:C116  BD03 4184  SCALL 03:4184
```

## `03:4398`

Call sites: `2F:C12E`

### `2F:C12E` in `sub_2F_BFBC`

```text
  2F:C112  4811       MOV R1, #0x1
  2F:C114  58F1       MOV [--R15], R1
  2F:C116  BD03 4184  SCALL 03:4184
  2F:C11A  50F2       ADD R15, #0x2
  2F:C11C  BD27 6ADC  SCALL 27:6ADC
  2F:C120  BD33 2FF2  SCALL 33:2FF2
  2F:C124  4801       MOV R0, #0x1
  2F:C126  58F0       MOV [--R15], R0
  2F:C128  BD03 4224  SCALL 03:4224
  2F:C12C  50F2       ADD R15, #0x2
> 2F:C12E  BD03 4398  SCALL 03:4398
  2F:C132  BD03 41F8  SCALL 03:41F8
  2F:C136  4910       MOVB RB1, #0x0
  2F:C138  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C13C  C700       NOP
  2F:C13E  A9F1 7AA8  MOVB [0x7AA8], REG[0xF1]
  2F:C142  4801       MOV R0, #0x1
  2F:C144  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C148  C700       NOP
  2F:C14A  A8F0 7934  MOV [0x7934], REG[0xF0]
  2F:C14E  4801       MOV R0, #0x1
  2F:C150  6810 00A4  MOV REG[0x10], #0x00A4
  2F:C154  C700       NOP
```

## `03:B548`

Call sites: `20:D11C`, `22:3CEE`

### `20:D11C` in `sub_20_C376`

```text
  20:D104  4802       MOV R0, #0x2
  20:D106  58F0       MOV [--R15], R0
  20:D108  4810       MOV R1, #0x0
  20:D10A  4800       MOV R0, #0x0
  20:D10C  58F1       MOV [--R15], R1
  20:D10E  58F0       MOV [--R15], R0
  20:D110  780B FFF6  MOV R0, [R11+0xFFF6]
  20:D114  781B FFF8  MOV R1, [R11+0xFFF8]
  20:D118  58F1       MOV [--R15], R1
  20:D11A  58F0       MOV [--R15], R0
> 20:D11C  BD03 B548  SCALL 03:B548
  20:D120  50FC       ADD R15, #0xC
  20:D122  783B FFF0  MOV R3, [R11+0xFFF0]
  20:D126  4C32       SL R3, #0x2
  20:D128  082B       MOV R2, R11
  20:D12A  70F2 FFB2  ADD REG[0xF2], #0xFFB2
  20:D12E  1032       ADD R3, R2
  20:D130  3F11       IGNDS #1
  20:D132  0A30       MOV [R3], R0
  20:D134  6A13 0002  MOV [R3+0x0002], R1
  20:D138  5210       SUB R1, #0x0
  20:D13A  5300       SUBC R0, #0x0
  20:D13C  AC01 D274  AJMP Z/EQ, 20:D274
```

### `22:3CEE` in `sub_22_23C4`

```text
  22:3CD6  780B FFE2  MOV R0, [R11+0xFFE2]
  22:3CDA  781B FFE4  MOV R1, [R11+0xFFE4]
  22:3CDE  5012       ADD R1, #0x2
  22:3CE0  5100       ADDC R0, #0x0
  22:3CE2  58F1       MOV [--R15], R1
  22:3CE4  58F0       MOV [--R15], R0
  22:3CE6  4810       MOV R1, #0x0
  22:3CE8  4800       MOV R0, #0x0
  22:3CEA  58F1       MOV [--R15], R1
  22:3CEC  58F0       MOV [--R15], R0
> 22:3CEE  BD03 B548  SCALL 03:B548
  22:3CF2  50FC       ADD R15, #0xC
  22:3CF4  6A0B FFFC  MOV [R11+0xFFFC], R0
  22:3CF8  6A1B FFFE  MOV [R11+0xFFFE], R1
  22:3CFC  5210       SUB R1, #0x0
  22:3CFE  5300       SUBC R0, #0x0
  22:3D00  AC01 3EAC  AJMP Z/EQ, 22:3EAC
  22:3D04  780B FFFC  MOV R0, [R11+0xFFFC]
  22:3D08  781B FFFE  MOV R1, [R11+0xFFFE]
  22:3D0C  6810 00A5  MOV REG[0x10], #0x00A5
  22:3D10  C700       NOP
  22:3D12  A8F0 75FC  MOV [0x75FC], REG[0xF0]
  22:3D16  A8F1 75FE  MOV [0x75FE], REG[0xF1]
```

## `03:E126`

Call sites: `20:9C40`, `20:A128`, `20:B0E6`, `20:B2CC`, `20:B462`

### `20:9C40` in `sub_20_97F4`

```text
  20:9C22  58F0       MOV [--R15], R0
  20:9C24  6810 00A6  MOV REG[0x10], #0x00A6
  20:9C28  88F0 2296  MOV REG[0xF0], [0x2296]
  20:9C2C  88F1 2298  MOV REG[0xF1], [0x2298]
  20:9C30  70F1 0042  ADD REG[0xF1], #0x0042
  20:9C34  5100       ADDC R0, #0x0
  20:9C36  58F1       MOV [--R15], R1
  20:9C38  58F0       MOV [--R15], R0
  20:9C3A  BD2E 4572  SCALL 2E:4572
  20:9C3E  50FC       ADD R15, #0xC
> 20:9C40  BD03 E126  SCALL 03:E126
  20:9C44  4801       MOV R0, #0x1
  20:9C46  AC00 B53A  AJMP ALWAYS, 20:B53A
  20:9C4A  6810 00A6  MOV REG[0x10], #0x00A6
  20:9C4E  99F0 1D9C  MOVZE REG[0xF0], [0x1D9C]
  20:9C52  76F0 0027  CMP REG[0xF0], #0x0027
  20:9C56  AC02 9C68  AJMP NZ/NE, 20:9C68
  20:9C5A  6810 00A6  MOV REG[0x10], #0x00A6
  20:9C5E  88F0 2318  MOV REG[0xF0], [0x2318]
  20:9C62  5600       CMP R0, #0x0
  20:9C64  AC01 9CC6  AJMP Z/EQ, 20:9CC6
  20:9C68  6810 00A6  MOV REG[0x10], #0x00A6
  20:9C6C  99F0 1D9C  MOVZE REG[0xF0], [0x1D9C]
```

### `20:A128` in `sub_20_97F4`

```text
  20:A106  5600       CMP R0, #0x0
  20:A108  AC01 A132  AJMP Z/EQ, 20:A132
  20:A10C  BD06 61CE  SCALL 06:61CE
  20:A110  6810 00A6  MOV REG[0x10], #0x00A6
  20:A114  88F0 2372  MOV REG[0xF0], [0x2372]
  20:A118  5600       CMP R0, #0x0
  20:A11A  AC02 A124  AJMP NZ/NE, 20:A124
  20:A11E  4800       MOV R0, #0x0
  20:A120  AC00 B53A  AJMP ALWAYS, 20:B53A
  20:A124  BD07 6E62  SCALL 07:6E62
> 20:A128  BD03 E126  SCALL 03:E126
  20:A12C  4801       MOV R0, #0x1
  20:A12E  AC00 B53A  AJMP ALWAYS, 20:B53A
  20:A132  6810 00A6  MOV REG[0x10], #0x00A6
  20:A136  88F0 2334  MOV REG[0xF0], [0x2334]
  20:A13A  5601       CMP R0, #0x1
  20:A13C  AC0D A21E  AJMP SLE, 20:A21E
  20:A140  4812       MOV R1, #0x2
  20:A142  4800       MOV R0, #0x0
  20:A144  58F1       MOV [--R15], R1
  20:A146  58F0       MOV [--R15], R0
  20:A148  68F1 70C6  MOV REG[0xF1], #0x70C6
  20:A14C  68F0 0006  MOV REG[0xF0], #0x0006
```

### `20:B0E6` in `sub_20_A856`

```text
  20:B0C4  5620       CMP R2, #0x0
  20:B0C6  AC0D B1BC  AJMP SLE, 20:B1BC
  20:B0CA  BD06 61CE  SCALL 06:61CE
  20:B0CE  6810 00A6  MOV REG[0x10], #0x00A6
  20:B0D2  88F2 2372  MOV REG[0xF2], [0x2372]
  20:B0D6  5620       CMP R2, #0x0
  20:B0D8  AC02 B0E2  AJMP NZ/NE, 20:B0E2
  20:B0DC  4800       MOV R0, #0x0
  20:B0DE  AC00 B53A  AJMP ALWAYS, 20:B53A
  20:B0E2  BD07 6E62  SCALL 07:6E62
> 20:B0E6  BD03 E126  SCALL 03:E126
  20:B0EA  6810 00A6  MOV REG[0x10], #0x00A6
  20:B0EE  88F0 2362  MOV REG[0xF0], [0x2362]
  20:B0F2  5601       CMP R0, #0x1
  20:B0F4  AC02 B1BC  AJMP NZ/NE, 20:B1BC
  20:B0F8  68F1 0018  MOV REG[0xF1], #0x0018
  20:B0FC  4800       MOV R0, #0x0
  20:B0FE  58F1       MOV [--R15], R1
  20:B100  58F0       MOV [--R15], R0
  20:B102  68F0 0020  MOV REG[0xF0], #0x0020
  20:B106  58F0       MOV [--R15], R0
  20:B108  6810 00A6  MOV REG[0x10], #0x00A6
  20:B10C  88F0 2296  MOV REG[0xF0], [0x2296]
```

### `20:B2CC` in `sub_20_A856`

```text
  20:B2AE  58F0       MOV [--R15], R0
  20:B2B0  6810 00A6  MOV REG[0x10], #0x00A6
  20:B2B4  88F0 2296  MOV REG[0xF0], [0x2296]
  20:B2B8  88F1 2298  MOV REG[0xF1], [0x2298]
  20:B2BC  70F1 0016  ADD REG[0xF1], #0x0016
  20:B2C0  5100       ADDC R0, #0x0
  20:B2C2  58F1       MOV [--R15], R1
  20:B2C4  58F0       MOV [--R15], R0
  20:B2C6  BD2E 4572  SCALL 2E:4572
  20:B2CA  50FC       ADD R15, #0xC
> 20:B2CC  BD03 E126  SCALL 03:E126
  20:B2D0  4800       MOV R0, #0x0
  20:B2D2  6810 00A6  MOV REG[0x10], #0x00A6
  20:B2D6  C700       NOP
  20:B2D8  A8F0 2334  MOV [0x2334], REG[0xF0]
  20:B2DC  6810 00A6  MOV REG[0x10], #0x00A6
  20:B2E0  88F0 22C2  MOV REG[0xF0], [0x22C2]
  20:B2E4  88F1 22C4  MOV REG[0xF1], [0x22C4]
  20:B2E8  0801       MOV R0, R1
  20:B2EA  58F0       MOV [--R15], R0
  20:B2EC  BD06 3C02  SCALL 06:3C02
  20:B2F0  50F2       ADD R15, #0x2
  20:B2F2  5600       CMP R0, #0x0
```

### `20:B462` in `sub_20_A856`

```text
  20:B440  50FC       ADD R15, #0xC
  20:B442  AC00 B462  AJMP ALWAYS, 20:B462
  20:B446  BD06 61CE  SCALL 06:61CE
  20:B44A  6810 00A6  MOV REG[0x10], #0x00A6
  20:B44E  88F0 2372  MOV REG[0xF0], [0x2372]
  20:B452  5600       CMP R0, #0x0
  20:B454  AC02 B45E  AJMP NZ/NE, 20:B45E
  20:B458  4800       MOV R0, #0x0
  20:B45A  AC00 B53A  AJMP ALWAYS, 20:B53A
  20:B45E  BD07 6E62  SCALL 07:6E62
> 20:B462  BD03 E126  SCALL 03:E126
  20:B466  6810 00A6  MOV REG[0x10], #0x00A6
  20:B46A  88F0 2362  MOV REG[0xF0], [0x2362]
  20:B46E  5601       CMP R0, #0x1
  20:B470  AC02 B538  AJMP NZ/NE, 20:B538
  20:B474  68F1 0018  MOV REG[0xF1], #0x0018
  20:B478  4800       MOV R0, #0x0
  20:B47A  58F1       MOV [--R15], R1
  20:B47C  58F0       MOV [--R15], R0
  20:B47E  68F0 0020  MOV REG[0xF0], #0x0020
  20:B482  58F0       MOV [--R15], R0
  20:B484  6810 00A6  MOV REG[0x10], #0x00A6
  20:B488  88F0 2296  MOV REG[0xF0], [0x2296]
```
