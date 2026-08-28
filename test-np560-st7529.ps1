[CmdletBinding()]
param([int]$Port = 8768)

$ErrorActionPreference = 'Stop'
$temporaryRoot = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
$firmware = Join-Path $temporaryRoot (
    'np560-st7529-test-{0}.bin' -f [guid]::NewGuid().ToString('N')
)
$words = [Collections.Generic.List[uint16]]::new()

function Add-Word([uint16]$Value) { $words.Add($Value) }
function Add-Move([uint16]$Register, [uint16]$Value) {
    Add-Word ([uint16](0x68F0 -bor $Register))
    Add-Word $Value
}
function Add-ByteWrite([bool]$Data, [byte]$Value) {
    Add-Word 0x69F4                 # MOVB RB4, #Value
    Add-Word ([uint16]$Value)
    Add-Word ([uint16]$(if ($Data) { 0x0B14 } else { 0x0B04 }))
}
function Add-Command([byte]$Command, [byte[]]$Parameters = @()) {
    Add-ByteWrite $false $Command
    foreach ($parameter in $Parameters) { Add-ByteWrite $true $parameter }
}

Add-Word 0x3F10                     # IGNDS: next DS write is unbanked
Add-Word 0x6811                     # MOV DS1, #0x01E0
Add-Word 0x01E0
Add-Move 0 0x8001                   # command port -> 0xF00001
Add-Move 1 0x8003                   # data port -> 0xF00003
Add-Command 0x30
Add-Command 0x94
Add-Command 0xBC ([byte[]](0x00, 0x00, 0x02))
Add-Command 0xBB ([byte[]](0x01))       # NP560 V3.80 COMSCN setting
Add-Command 0x15 ([byte[]](0x00, 0x00))
Add-Command 0x75 ([byte[]](0x14, 0x14)) # GRAM20 -> physical panel row 119
Add-Command 0x5C
foreach ($pixel in [byte[]](0x20, 0x20, 0x20)) {
    Add-ByteWrite $true $pixel
}
Add-Command 0x75 ([byte[]](0x4F, 0x4F)) # GRAM79 -> physical panel row 60
Add-Command 0x5C
foreach ($pixel in [byte[]](0x60, 0x60, 0x60)) {
    Add-ByteWrite $true $pixel
}
Add-Command 0x75 ([byte[]](0x50, 0x50)) # GRAM80 -> physical panel row 59
Add-Command 0x5C
foreach ($pixel in [byte[]](0xA0, 0xA0, 0xA0)) {
    Add-ByteWrite $true $pixel
}
Add-Command 0x75 ([byte[]](0x8B, 0x8B)) # GRAM139 -> physical panel row 0
Add-Command 0x5C
foreach ($pixel in [byte[]](0xE0, 0xE0, 0xE0)) {
    Add-ByteWrite $true $pixel
}
Add-Command 0xAF
Add-Word 0xD0FF                     # RJMP ALWAYS, self

$image = [byte[]]::new(0x400000)
for ($index = 0; $index -lt $words.Count; $index++) {
    $image[$index * 2] = $words[$index] -band 0xFF
    $image[$index * 2 + 1] = ($words[$index] -shr 8) -band 0xFF
}
[IO.File]::WriteAllBytes($firmware, $image)

try {
    & (Join-Path $PSScriptRoot 'test-np560-web.ps1') `
        -Firmware $firmware -Port $Port -FrameSource lcd `
        -ExpectNonzero -InitialDelayMs 100 `
        -ExpectedPixel '0,0,28','0,59,20','0,60,12','0,119,4' `
        -RegisterPattern 'ST7529=on.*COM=1.*WINDOW=C0-0,L139-139.*FRAMES=4'
} finally {
    $resolved = [IO.Path]::GetFullPath($firmware)
    if ($resolved.StartsWith($temporaryRoot, [StringComparison]::OrdinalIgnoreCase) -and
        (Test-Path -LiteralPath $resolved -PathType Leaf)) {
        Remove-Item -LiteralPath $resolved -Force
    }
}
