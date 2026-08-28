[CmdletBinding()]
param([int]$Port = 8767)

$ErrorActionPreference = 'Stop'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$firmware = Join-Path $temporaryRoot (
    'np560-lcd-test-{0}.bin' -f [guid]::NewGuid().ToString('N')
)

$words = [Collections.Generic.List[uint16]]::new()
function Add-Word([uint16]$Value) {
    $words.Add($Value)
}
function Add-ImmediatePush([uint16]$Value) {
    Add-Word 0x68F0                 # MOV R0, #Value
    Add-Word $Value
    Add-Word 0x58F0                 # MOV [--SP], R0
}
function Add-RomCall([uint16]$Address) {
    Add-Word 0xBD03                 # SCALL 03:Address
    Add-Word $Address
}
function Add-PointerPush([uint32]$Address) {
    Add-ImmediatePush ([uint16]($Address -band 0xFFFF))
    Add-ImmediatePush ([uint16](($Address -shr 16) -band 0xFF))
}

# foreground=1, background=0
Add-ImmediatePush 0
Add-ImmediatePush 1
Add-RomCall 0x41C8
Add-Word 0x50F4                     # ADD SP, #4

# Filled rectangle (20,15)-(219,104); arguments are pushed right-to-left.
Add-ImmediatePush 104
Add-ImmediatePush 219
Add-ImmediatePush 15
Add-ImmediatePush 20
Add-RomCall 0x4218
Add-Word 0x50F8                     # ADD SP, #8

# Exercise the native ROM string ABI: strcpy + strcat into program RAM.
$source1 = 0x201000
$source2 = 0x201020
$destination = 0x201100
Add-PointerPush $source1            # rightmost argument: source
Add-PointerPush $destination        # leftmost argument: destination
Add-RomCall 0x407C
Add-Word 0x50F8                     # ADD SP, #8
Add-PointerPush $source2
Add-PointerPush $destination
Add-RomCall 0x4080
Add-Word 0x50F8

# Draw the assembled string as white pixels inside the filled rectangle.
Add-ImmediatePush 1                 # background
Add-ImmediatePush 0                 # foreground
Add-RomCall 0x41C8
Add-Word 0x50F4
Add-PointerPush $destination
Add-ImmediatePush 45                # y
Add-ImmediatePush 35                # x
Add-RomCall 0x41A8
Add-Word 0x50F8

# Fixed-length text has the ABI (x, y, pointer, byte_count).
Add-ImmediatePush 3
Add-PointerPush $source1
Add-ImmediatePush 62
Add-ImmediatePush 35
Add-RomCall 0x41AC
Add-Word 0x50FA

# Present one completed LCD frame, then idle in place.
Add-ImmediatePush 1
Add-RomCall 0x4224
Add-Word 0x50F2                     # ADD SP, #2
Add-Word 0xD0FF                     # RJMP ALWAYS, self

$image = [byte[]]::new(0x400000)
for ($index = 0; $index -lt $words.Count; $index++) {
    $image[$index * 2] = $words[$index] -band 0xFF
    $image[$index * 2 + 1] = ($words[$index] -shr 8) -band 0xFF
}
$ascii = [Text.Encoding]::ASCII
[Buffer]::BlockCopy($ascii.GetBytes('NP560'), 0, $image, 0x1000, 5)
[Buffer]::BlockCopy($ascii.GetBytes(' QEMU'), 0, $image, 0x1020, 5)
[IO.File]::WriteAllBytes($firmware, $image)

try {
    & (Join-Path $PSScriptRoot 'test-np560-web.ps1') `
        -Firmware $firmware -Port $Port -RomHle `
        -ExpectNonzero -MinimumLcdCalls 6
} finally {
    $resolved = [IO.Path]::GetFullPath($firmware)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Remove-Item -LiteralPath $resolved -Force
    }
}
