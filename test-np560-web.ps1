[CmdletBinding()]
param(
    [string]$Firmware = (Join-Path (Split-Path $PSScriptRoot -Parent) 'NP560+V3.80版系统升级程序\NP560.PRG'),
    [string]$SocRom,
    [switch]$SocRomSkeleton,
    [string]$DriverCode,
    [string]$BurnCode,
    [string]$NandImage,
    [string]$NandCheckpoint,
    [string]$NandSaveOnExit,
    [ValidateSet('firmware', 'usb', 'burn', 'driver')]
    [string]$BootMode = 'firmware',
    [int]$Port = 8766,
    [ValidateRange(30, 1800)]
    [int]$ServerTimeoutSeconds = 180,
    [ValidateRange(-1, 20)]
    [int]$IcountShift = -1,
    [switch]$ExpectNonzero,
    [switch]$ExpectHle,
    [switch]$RomHle,
    [switch]$HleUi,
    [switch]$ExpectNative,
    [switch]$ExpectModalPolling,
    [uint32]$StartupContext = 0,
    [int]$InitialDelayMs = 0,
    [int]$MinimumLcdCalls = 0,
    [string]$RegisterPattern,
    [string[]]$ExpectedPixel,
    [ValidateSet('memory', 'data', 'lcd')]
    [string]$FrameSource = 'memory',
    [uint32]$MemoryBase = 0xEF0000
)

$ErrorActionPreference = 'Stop'
$distro = 'Ubuntu2'
$qemu = '/mnt/e/qemu-dmcu-build/qemu-system-dmcu'
$scriptWindows = Join-Path $PSScriptRoot 'web\np560_web.py'
$shutdownToken = [guid]::NewGuid().ToString('N')

$firmwareWindows = (Resolve-Path -LiteralPath $Firmware).Path -replace '\\', '/'
$scriptWindows = (Resolve-Path -LiteralPath $scriptWindows).Path -replace '\\', '/'
$wslFirmware = (& wsl.exe -d $distro -- wslpath -a -- $firmwareWindows).Trim()
$wslScript = (& wsl.exe -d $distro -- wslpath -a -- $scriptWindows).Trim()
if ($LASTEXITCODE -ne 0 -or -not $wslFirmware -or -not $wslScript) {
    throw 'Unable to translate test paths into WSL.'
}

$arguments = @(
    '-d', $distro, '--', 'timeout', "${ServerTimeoutSeconds}s", 'python3', $wslScript,
    '--qemu', $qemu, '--firmware', $wslFirmware, '--port', [string]$Port,
    '--startup-context', [string]$StartupContext, '--boot-mode', $BootMode,
    '--shutdown-token', $shutdownToken
)
if ($IcountShift -ge 0) {
    $arguments += @('--icount-shift', [string]$IcountShift)
}
$enableHleUi = $HleUi -or $ExpectHle
$enableRomHle = $RomHle -or $enableHleUi
if ($enableRomHle) {
    $arguments += '--rom-hle'
}
if ($enableHleUi) {
    $arguments += '--hle-ui'
}
if ($SocRom) {
    $socRomWindows = (Resolve-Path -LiteralPath $SocRom).Path -replace '\\', '/'
    $wslSocRom = (& wsl.exe -d $distro -- wslpath -a -- $socRomWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslSocRom) {
        throw 'Unable to translate the SoC ROM test path into WSL.'
    }
    $arguments += @('--soc-rom', $wslSocRom)
    if ($SocRomSkeleton) {
        $arguments += '--soc-rom-skeleton'
    }
} elseif ($SocRomSkeleton) {
    throw 'SocRomSkeleton requires -SocRom.'
}
if ($DriverCode) {
    $driverWindows = (Resolve-Path -LiteralPath $DriverCode).Path -replace '\\', '/'
    $wslDriver = (& wsl.exe -d $distro -- wslpath -a -- $driverWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslDriver) {
        throw 'Unable to translate the update driver path into WSL.'
    }
    $arguments += @('--driver-code', $wslDriver)
}
if ($BurnCode) {
    $burnWindows = (Resolve-Path -LiteralPath $BurnCode).Path -replace '\\', '/'
    $wslBurn = (& wsl.exe -d $distro -- wslpath -a -- $burnWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslBurn) {
        throw 'Unable to translate the burner-code test path into WSL.'
    }
    $arguments += @('--burn-code', $wslBurn)
}
if ($NandImage) {
    $nandWindows = (Resolve-Path -LiteralPath $NandImage).Path -replace '\\', '/'
    $wslNand = (& wsl.exe -d $distro -- wslpath -a -- $nandWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslNand) {
        throw 'Unable to translate the NAND-image test path into WSL.'
    }
    $arguments += @('--nand-image', $wslNand)
}
if ($NandCheckpoint) {
    if ($NandImage) {
        throw 'NandImage and NandCheckpoint are mutually exclusive.'
    }
    $checkpointWindows = (Resolve-Path -LiteralPath $NandCheckpoint).Path -replace '\\', '/'
    $wslCheckpoint = (& wsl.exe -d $distro -- wslpath -a -- $checkpointWindows).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslCheckpoint) {
        throw 'Unable to translate the NAND-checkpoint path into WSL.'
    }
    $arguments += @('--nand-checkpoint', $wslCheckpoint)
}
if ($NandSaveOnExit) {
    $saveWindows = [IO.Path]::GetFullPath($NandSaveOnExit)
    $saveParent = Split-Path -Parent $saveWindows
    if ($saveParent -and -not (Test-Path -LiteralPath $saveParent)) {
        [IO.Directory]::CreateDirectory($saveParent) | Out-Null
    }
    $saveWslInput = $saveWindows -replace '\\', '/'
    $wslSave = (& wsl.exe -d $distro -- wslpath -a -- $saveWslInput).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $wslSave) {
        throw 'Unable to translate the NAND save test path into WSL.'
    }
    $arguments += @('--nand-save-on-exit', $wslSave)
}
if ($BootMode -eq 'driver' -and -not $DriverCode) {
    throw 'BootMode driver requires -DriverCode.'
}
$serverProcess = Start-Process -FilePath 'wsl.exe' -ArgumentList $arguments `
    -PassThru -WindowStyle Hidden
$stateUri = if ($FrameSource -eq 'lcd') {
    "http://127.0.0.1:$Port/api/state"
} else {
    "http://127.0.0.1:$Port/api/state?source=$FrameSource&base=0x$($MemoryBase.ToString('X6'))&size=3600"
}

try {
    if ($InitialDelayMs -gt 0) {
        Start-Sleep -Milliseconds $InitialDelayMs
    }
    $state = $null
    $lastStateError = $null
    for ($attempt = 0; $attempt -lt 60 -and $null -eq $state; $attempt++) {
        try {
            $state = Invoke-RestMethod -Uri $stateUri -TimeoutSec 1
        } catch {
            $lastStateError = $_.Exception.Message
            Start-Sleep -Milliseconds 100
        }
    }
    if ($null -eq $state) {
        $serverProcess.Refresh()
        throw "Web API did not become ready (process exit=$($serverProcess.ExitCode)): $lastStateError"
    }

    if ($ExpectNative) {
        $nativeReady = $false
        for ($attempt = 0; $attempt -lt 240; $attempt++) {
            $state = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $residentWitness = (
                $state.registers -match
                    'CONTROL_TRACE=[^\r\n]*3b:f7c6/bd33>33:2562' -or
                $state.registers -match '\bF010_READS=([5-9]|[1-9]\d+)' -or
                ($state.registers -match
                    '(?:APPLICATION_TRACE=|,)MODALHEAD:([1-9]\d*)@' -and
                 $state.registers -match '\bMATRIX_READS[:=]([1-9]\d*)')
            )
            $nativeReady = (
                $state.registers -match 'ROM_HLE=off' -and
                $state.registers -match 'ROM_MISSING=none' -and
                $state.registers -match 'INVALID_CONTROL=none' -and
                $state.registers -match 'UNSUPPORTED=none' -and
                $state.registers -match 'FIRST_LOW_FP=none' -and
                $state.registers -match 'FIRST_LOW_SP=none' -and
                $state.registers -match 'NAND=EC:DC:10:95' -and
                $state.registers -match 'ERROR=0' -and
                $residentWitness -and
                $state.lcd_state -match '\bFRAMES=([1-9]\d*)'
            )
            if ($nativeReady) { break }
            $serverProcess.Refresh()
            if ($serverProcess.HasExited) {
                throw "Native Web guest exited with $($serverProcess.ExitCode).`n$($state.registers)"
            }
            Start-Sleep -Milliseconds 50
        }
        if (-not $nativeReady) {
            throw "Native firmware did not reach the resident event loop.`n$($state.registers)"
        }
    }

    $frame = [Convert]::FromBase64String($state.frame)
    $expectedFrameLength = if ($FrameSource -eq 'lcd') { 240 * 120 } else { 3600 }
    if ($frame.Length -ne $expectedFrameLength) {
        throw "Expected a $expectedFrameLength-byte frame, received $($frame.Length)."
    }
    if ($FrameSource -eq 'lcd') {
        if ($state.format -ne 'gray5' -or
            $state.lcd_state -notmatch '^ST7529 ') {
            throw 'QEMU does not expose the ST7529 hardware framebuffer.'
        }
    } elseif ($FrameSource -eq 'memory' -and
              ($state.registers -notmatch 'HLE_FB=ef0000' -or
               $state.registers -notmatch 'HLE_LCD_CALLS=')) {
        throw 'QEMU CPU state does not expose the diagnostic HLE framebuffer.'
    } elseif ($FrameSource -eq 'data' -and
              $state.lcd_state -ne 'Raw NP560 data-RAM diagnostic view') {
        throw 'Web API did not return the raw NP560 data-RAM backend.'
    }
    if ($NandSaveOnExit) {
        if (-not $state.nand_save_enabled) {
            throw 'Web state did not enable configured NAND persistence.'
        }
        $savedNand = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/nand/save" `
            -ContentType 'application/json' -Body '{}'
        $expectedCheckpointSize = 64L + 0x20000000L + 0x01000000L
        if (-not $savedNand.ok -or
            -not (Test-Path -LiteralPath $saveWindows -PathType Leaf) -or
            (Get-Item -LiteralPath $saveWindows).Length -ne
                $expectedCheckpointSize) {
            throw 'Web NAND save endpoint did not write a complete checkpoint.'
        }
    } elseif ($state.nand_save_enabled) {
        throw 'Web state enabled NAND persistence without an output path.'
    }
    if ($RegisterPattern -and $state.registers -notmatch $RegisterPattern) {
        throw "CPU state does not match expected pattern: $RegisterPattern`n$($state.registers)"
    }
    foreach ($pixelExpectation in $ExpectedPixel) {
        $parts = $pixelExpectation -split ','
        if ($parts.Count -ne 3) {
            throw "ExpectedPixel uses X,Y,LEVEL: $pixelExpectation"
        }
        $pixelX = [int]$parts[0]
        $pixelY = [int]$parts[1]
        $pixelLevel = [int]$parts[2]
        if ($FrameSource -ne 'lcd' -or $pixelX -lt 0 -or $pixelX -ge 240 -or
            $pixelY -lt 0 -or $pixelY -ge 120 -or
            $pixelLevel -lt 0 -or $pixelLevel -gt 31) {
            throw "Invalid LCD ExpectedPixel: $pixelExpectation"
        }
        $actualLevel = $frame[$pixelY * 240 + $pixelX]
        if ($actualLevel -ne $pixelLevel) {
            throw "LCD pixel ($pixelX,$pixelY) expected $pixelLevel, received $actualLevel."
        }
    }
    if ($ExpectHle -and $state.registers -notmatch 'HLE_UI=active\s+PAGE=0\s+SEL=0') {
        throw 'The ROM-less QEMU menu did not become active.'
    }
    if ($enableRomHle -and $state.registers -notmatch 'ROM_HLE=on') {
        throw 'The explicitly requested ROM HLE mode is not active.'
    }
    if (-not $enableRomHle -and $state.registers -notmatch 'ROM_HLE=off') {
        throw 'Strict hardware mode unexpectedly enabled ROM HLE.'
    }
    $nativeEventsBefore = 0
    if ($ExpectNative) {
        $nativeFrame = [Convert]::FromBase64String($state.frame)
        if (@($nativeFrame | Select-Object -Unique).Count -lt 2) {
            # FRAMES>0 also includes the controller's initial blank transfer.
            # Wait for the first completed visible frame instead of treating
            # that valid boot phase as an LCD failure.
            for ($attempt = 0; $attempt -lt 6000; $attempt++) {
                $state = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
                $nativeFrame = [Convert]::FromBase64String($state.frame)
                if (@($nativeFrame | Select-Object -Unique).Count -ge 2) {
                    break
                }
                Start-Sleep -Milliseconds 250
            }
            if (@($nativeFrame | Select-Object -Unique).Count -lt 2) {
                throw 'Native firmware produced only uniform ST7529 frames.'
            }
        }
        $matrixConsumerReady = $false
        $matrixConsumerAttempts = if ($ExpectModalPolling) { 6000 } else { 100 }
        for ($attempt = 0; $attempt -lt $matrixConsumerAttempts; $attempt++) {
            $state = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            if ($ExpectModalPolling) {
                $matrixConsumerReady = (
                    $state.registers -match
                        '(?:APPLICATION_TRACE=|,)MODALHEAD:([1-9]\d*)@' -and
                    $state.registers -match '\bMATRIX_READS[:=]([1-9]\d*)'
                )
            } else {
                $matrixConsumerReady =
                    $state.registers -match 'ROM_CALL=06:b126'
            }
            if ($matrixConsumerReady) { break }
            # cpu-state is deliberately very detailed; sparse polling leaves
            # the emulated CPU enough host time to finish the NAND/OOB scan.
            Start-Sleep -Milliseconds $(if ($ExpectModalPolling) { 250 } else { 10 })
        }
        if (-not $matrixConsumerReady) {
            throw "Native application did not reach the F160/F164 matrix reader.`n$($state.registers)"
        }
        # Verify that the diagnostic view really returns the backing data RAM,
        # rather than a physical-bus alias.  The exact resource/storage graph
        # copies 30:524C..525D to executable RAM at 33:524C during boot.
        # Unlike the live key words, this range is immutable after bootstrap,
        # so two separately requested Web snapshots cannot race the 64-Hz
        # keyboard scanner.
        $dataState = Invoke-RestMethod -Uri (
            "http://127.0.0.1:$Port/api/state?source=data&base=0x33524c&size=18"
        ) -TimeoutSec 2
        $dataBytes = [Convert]::FromBase64String($dataState.frame)
        $firmwareBytes = [IO.File]::ReadAllBytes(
            (Resolve-Path -LiteralPath $Firmware).Path
        )
        $expectedDataBytes = [byte[]]$firmwareBytes[0x30524c..0x30525d]
        if ($dataState.lcd_state -ne 'Raw NP560 data-RAM diagnostic view' -or
            $dataBytes.Length -ne 18 -or
            [BitConverter]::ToString($dataBytes) -ne
                [BitConverter]::ToString($expectedDataBytes)) {
            throw 'Raw data-RAM diagnostic view disagrees with overlay 33:524C.'
        }
        if ($ExpectModalPolling) {
            # The complete storage context enters the exact modal loop at
            # 31:F2AE.  Its timer scanner debounces the physical key while it
            # is held, then exact guest code at 28:F6DE commits event 0x0085
            # after release.  Synchronise on those two guest-owned boundaries
            # instead of the earlier bootstrap menu's blocking 06:B126 call.
            $activeMatch = [regex]::Match(
                $state.registers, '\bACTIVE:(\d+)'
            )
            $matrixReadMatch = [regex]::Match(
                $state.registers, '\bMATRIX_READS[:=](\d+)'
            )
            $matrixMapMatch = [regex]::Match(
                $state.registers, '\bMATRIX_EVENT_MAPS=(\d+)'
            )
            if (-not $activeMatch.Success -or
                -not $matrixReadMatch.Success -or
                -not $matrixMapMatch.Success) {
                throw "Modal keyboard diagnostics are incomplete.`n$($state.registers)"
            }
            $activeBefore = [int]$activeMatch.Groups[1].Value
            $matrixReadsBefore = [int]$matrixReadMatch.Groups[1].Value
            $matrixMapsBefore = [int]$matrixMapMatch.Groups[1].Value
            $keyDown = Invoke-RestMethod -Method Post `
                -Uri "http://127.0.0.1:$Port/api/key" `
                -ContentType 'application/json' `
                -Body '{"state":16,"code":260,"matrix_low":1048576,"matrix_high":0}'
            $afterNativeKey = $null
            $keyDebounced = $false
            for ($attempt = 0; $attempt -lt 500; $attempt++) {
                $afterNativeKey = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
                $activeMatch = [regex]::Match(
                    $afterNativeKey.registers, '\bACTIVE:(\d+)'
                )
                if ($activeMatch.Success -and
                    [int]$activeMatch.Groups[1].Value -ge $activeBefore + 16) {
                    $keyDebounced = $true
                    break
                }
                Start-Sleep -Milliseconds 10
            }
            $keyUp = Invoke-RestMethod -Method Post `
                -Uri "http://127.0.0.1:$Port/api/key" `
                -ContentType 'application/json' `
                -Body '{"state":0,"code":0,"matrix_low":0,"matrix_high":0}'
            if (-not $keyDown.ok -or -not $keyUp.ok -or -not $keyDebounced) {
                throw "Web Enter did not reach the modal matrix scanner.`n$($afterNativeKey.registers)"
            }
            $modalKeyMapped = $false
            for ($attempt = 0; $attempt -lt 6000; $attempt++) {
                $afterNativeKey = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
                $matrixReadMatch = [regex]::Match(
                    $afterNativeKey.registers, '\bMATRIX_READS[:=](\d+)'
                )
                $matrixMapMatch = [regex]::Match(
                    $afterNativeKey.registers,
                    '\bMATRIX_EVENT_MAPS=(\d+)\s+LAST=0085@28:f6de'
                )
                if ($matrixReadMatch.Success -and
                    [int]$matrixReadMatch.Groups[1].Value -gt
                        $matrixReadsBefore -and
                    $matrixMapMatch.Success -and
                    [int]$matrixMapMatch.Groups[1].Value -gt
                        $matrixMapsBefore -and
                    $afterNativeKey.registers -match '\bF160:00ff') {
                    $modalKeyMapped = $true
                    break
                }
                Start-Sleep -Milliseconds 10
            }
            if (-not $modalKeyMapped -or
                $afterNativeKey.registers -notmatch '\bKEY_CODE=00000000' -or
                $afterNativeKey.registers -notmatch '\bF340_READS=0' -or
                $afterNativeKey.registers -notmatch 'FIRST_LOW_FP=none' -or
                $afterNativeKey.registers -notmatch 'FIRST_LOW_SP=none' -or
                $afterNativeKey.registers -notmatch 'ROM_MISSING=none' -or
                $afterNativeKey.registers -notmatch 'INVALID_CONTROL=none' -or
                $afterNativeKey.registers -notmatch 'UNSUPPORTED=none') {
                throw "Modal Web Enter was not committed as exact event 0085.`n$($afterNativeKey.registers)"
            }
        } else {
        $mainRetBefore = 0
        $mainRetMatch = [regex]::Match($state.registers, '(?:^|,)MAINRET:(\d+)@')
        if ($mainRetMatch.Success) {
            $mainRetBefore = [int]$mainRetMatch.Groups[1].Value
        }
        $activeBefore = [int]([regex]::Match(
            $state.registers, '\bACTIVE:(\d+)'
        ).Groups[1].Value)
        $keyDown = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":16,"code":260,"matrix_low":1048576,"matrix_high":0}'
        $afterNativeKey = $null
        $nativeKeyProcessed = $false
        for ($attempt = 0; $attempt -lt 100; $attempt++) {
            $afterNativeKey = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $mainRetMatch = [regex]::Match(
                $afterNativeKey.registers,
                '(?:^|,)MAINRET:(\d+)@[^,\r\n]*/r0085:'
            )
            $activeMatch = [regex]::Match(
                $afterNativeKey.registers, '\bACTIVE:(\d+)'
            )
            if ($mainRetMatch.Success -and $activeMatch.Success -and
                [int]$mainRetMatch.Groups[1].Value -gt $mainRetBefore -and
                [int]$activeMatch.Groups[1].Value -gt $activeBefore) {
                $nativeKeyProcessed = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        $releaseCallMatch = [regex]::Match(
            $afterNativeKey.registers,
            '\bROM_CALL=[^\r\n]*\bCALLS=(\d+)'
        )
        $releaseCallCount = if ($releaseCallMatch.Success) {
            [int]$releaseCallMatch.Groups[1].Value
        } else { 0 }
        $keyUp = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":0,"code":0,"matrix_low":0,"matrix_high":0}'
        if (-not $nativeKeyProcessed) {
            throw "Native firmware did not return Enter through F160/F164 as event 0085.`n$($afterNativeKey.registers)"
        }
        Start-Sleep -Milliseconds 50
        $afterRelease = $null
        $releaseReady = $false
        # A full post-upgrade checkpoint can spend several seconds rebuilding
        # NAND-backed application state after TOP:2 before it returns to the
        # blocking matrix reader.  Wait for the evidenced guest boundary;
        # the former ~2 s polling window incorrectly treated that valid work
        # as a resident relaunch failure.
        for ($attempt = 0; $attempt -lt 3000; $attempt++) {
            $afterRelease = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $newCallMatch = [regex]::Match(
                $afterRelease.registers,
                '\bROM_CALL=[^\r\n]*\bCALLS=(\d+)'
            )
            if ($afterRelease.registers -match 'APPLICATION_TRACE=TOP:2@' -and
                $afterRelease.registers -match 'ROM_CALL=06:b126' -and
                $newCallMatch.Success -and
                [int]$newCallMatch.Groups[1].Value -gt $releaseCallCount) {
                $releaseReady = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        if (-not $releaseReady) {
            throw "Resident continuation did not relaunch the native application.`n$($afterRelease.registers)"
        }
        if ($afterRelease.registers -notmatch 'KEY_CODE=00000000' -or
            $afterRelease.registers -notmatch 'F340_READS=0') {
            throw "Strict Web input touched the legacy F340 latch.`n$($afterRelease.registers)"
        }
        if ($afterRelease.registers -notmatch 'FIRST_LOW_FP=none' -or
            $afterRelease.registers -notmatch 'FIRST_LOW_SP=none' -or
            $afterRelease.registers -notmatch
                'BENIGN_SP_WRAP=COUNT:([1-9]\d*) LAST:33:52a4/380f') {
            throw "Application handoff corrupted the stack.`n$($afterRelease.registers)"
        }

        # The first Enter completes the bootstrap-owned application.  Only
        # the following lifecycle was entered by the reconstructed resident
        # scheduler, so exercise Enter once more and require the complete
        # 20:026A epilogue to return through 20:0326 -> 03:0084.  This catches
        # regressions which merely relaunch at 2D:7DD2 and never prove its
        # parent compiler frame can unwind.
        $schedulerReturnBefore = 0
        $schedulerReturnMatch = [regex]::Match(
            $afterRelease.registers,
            '(?:APPLICATION_TRACE=|,)SCHEDRET:(\d+)@20:0326'
        )
        if ($schedulerReturnMatch.Success) {
            $schedulerReturnBefore =
                [int]$schedulerReturnMatch.Groups[1].Value
        }
        $secondMainRetBefore = 0
        $secondMainRetMatch = [regex]::Match(
            $afterRelease.registers, '(?:^|,)MAINRET:(\d+)@'
        )
        if ($secondMainRetMatch.Success) {
            $secondMainRetBefore = [int]$secondMainRetMatch.Groups[1].Value
        }
        $secondKeyDown = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":16,"code":260,"matrix_low":1048576,"matrix_high":0}'
        $afterSecondKey = $null
        $secondKeyProcessed = $false
        for ($attempt = 0; $attempt -lt 200; $attempt++) {
            $afterSecondKey = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $secondMainRetMatch = [regex]::Match(
                $afterSecondKey.registers,
                '(?:^|,)MAINRET:(\d+)@[^,\r\n]*/r0085:'
            )
            if ($secondMainRetMatch.Success -and
                [int]$secondMainRetMatch.Groups[1].Value -gt
                    $secondMainRetBefore) {
                $secondKeyProcessed = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        $secondKeyUp = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":0,"code":0,"matrix_low":0,"matrix_high":0}'
        if (-not $secondKeyDown.ok -or -not $secondKeyUp.ok -or
            -not $secondKeyProcessed) {
            throw "Scheduler-owned application did not consume Enter as event 0085.`n$($afterSecondKey.registers)"
        }
        $afterSchedulerReturn = $null
        $schedulerReturned = $false
        for ($attempt = 0; $attempt -lt 4000; $attempt++) {
            $afterSchedulerReturn = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $schedulerReturnMatch = [regex]::Match(
                $afterSchedulerReturn.registers,
                '(?:APPLICATION_TRACE=|,)SCHEDRET:(\d+)@20:0326'
            )
            $topMatch = [regex]::Match(
                $afterSchedulerReturn.registers,
                'APPLICATION_TRACE=TOP:(\d+)@20:031c'
            )
            if ($schedulerReturnMatch.Success -and $topMatch.Success -and
                [int]$schedulerReturnMatch.Groups[1].Value -gt
                    $schedulerReturnBefore -and
                [int]$topMatch.Groups[1].Value -ge 3) {
                $schedulerReturned = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        if (-not $schedulerReturned -or
            $afterSchedulerReturn.registers -notmatch
                '(?:APPLICATION_TRACE=|,)SCHEDRET:\d+@20:0326/sp[0-9a-f]{4}/r0000:0080:0085/a' -or
            $afterSchedulerReturn.registers -notmatch 'FIRST_LOW_FP=none' -or
            $afterSchedulerReturn.registers -notmatch 'FIRST_LOW_SP=none') {
            throw "Complete system main did not return event 0085 in R2 to the resident scheduler.`n$($afterSchedulerReturn.registers)"
        }
        $afterRelease = $afterSchedulerReturn

        # Exercise the Web API's explicit 64-bit physical matrix fields
        # independently of the legacy navigation aliases.  Index 10 is the
        # recovered QWERTY A position and exact 28:F4A4 maps it to 0x0061.
        $keyMapBefore = 0
        $keyMapMatch = [regex]::Match(
            $afterRelease.registers, '(?:APPLICATION_TRACE=|,)KEYMAPRET:(\d+)@'
        )
        if ($keyMapMatch.Success) {
            $keyMapBefore = [int]$keyMapMatch.Groups[1].Value
        }
        $matrixMainBefore = 0
        $matrixMainMatch = [regex]::Match(
            $afterRelease.registers, '(?:^|,)MAINRET:(\d+)@'
        )
        if ($matrixMainMatch.Success) {
            $matrixMainBefore = [int]$matrixMainMatch.Groups[1].Value
        }
        $romAppBefore = 0
        $romAppMatch = [regex]::Match(
            $afterRelease.registers, '(?:APPLICATION_TRACE=|,)ROMAPP:(\d+)@'
        )
        if ($romAppMatch.Success) {
            $romAppBefore = [int]$romAppMatch.Groups[1].Value
        }
        $activeBefore = [int]([regex]::Match(
            $afterRelease.registers, '\bACTIVE:(\d+)'
        ).Groups[1].Value)
        $matrixA = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":0,"code":0,"matrix_low":1024,"matrix_high":0}'
        $afterMatrixA = $null
        $matrixAProcessed = $false
        for ($attempt = 0; $attempt -lt 100; $attempt++) {
            $afterMatrixA = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $keyMapMatch = [regex]::Match(
                $afterMatrixA.registers,
                '(?:APPLICATION_TRACE=|,)KEYMAPRET:(\d+)@[^,\r\n]*/r0061:'
            )
            $activeMatch = [regex]::Match(
                $afterMatrixA.registers, '\bACTIVE:(\d+)'
            )
            $matrixMainMatch = [regex]::Match(
                $afterMatrixA.registers,
                '(?:^|,)MAINRET:(\d+)@[^,\r\n]*/r0061:'
            )
            $romAppMatch = [regex]::Match(
                $afterMatrixA.registers,
                '(?:APPLICATION_TRACE=|,)ROMAPP:(\d+)@[^,\r\n]*/r0061:'
            )
            $mappedByGuest = (
                $keyMapMatch.Success -and
                [int]$keyMapMatch.Groups[1].Value -gt $keyMapBefore
            )
            $returnedByMain = (
                $matrixMainMatch.Success -and
                [int]$matrixMainMatch.Groups[1].Value -gt $matrixMainBefore
            )
            $dispatchedByResident = (
                $romAppMatch.Success -and
                [int]$romAppMatch.Groups[1].Value -gt $romAppBefore
            )
            if ($activeMatch.Success -and
                [int]$activeMatch.Groups[1].Value -gt $activeBefore -and
                ($mappedByGuest -or $returnedByMain -or
                 $dispatchedByResident)) {
                $matrixAProcessed = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        $matrixAReleaseMatch = [regex]::Match(
            $afterMatrixA.registers,
            '\bROM_CALL=[^\r\n]*\bCALLS=(\d+)'
        )
        $matrixAReleaseCalls = if ($matrixAReleaseMatch.Success) {
            [int]$matrixAReleaseMatch.Groups[1].Value
        } else { 0 }
        $matrixAUp = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' `
            -Body '{"state":0,"code":0,"matrix_low":0,"matrix_high":0}'
        if (-not $matrixA.ok -or -not $matrixAUp.ok -or
            -not $matrixAProcessed) {
            throw "Web matrix index 10 did not map to event 0061.`n$($afterMatrixA.registers)"
        }
        $matrixAReady = $false
        for ($attempt = 0; $attempt -lt 200; $attempt++) {
            $afterMatrixARelease = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            $newCallMatch = [regex]::Match(
                $afterMatrixARelease.registers,
                '\bROM_CALL=[^\r\n]*\bCALLS=(\d+)'
            )
            if ($afterMatrixARelease.registers -match 'ROM_CALL=06:b126' -and
                $newCallMatch.Success -and
                [int]$newCallMatch.Groups[1].Value -gt $matrixAReleaseCalls) {
                $matrixAReady = $true
                break
            }
            Start-Sleep -Milliseconds 10
        }
        if (-not $matrixAReady) {
            throw "Native application did not observe Web matrix A release.`n$($afterMatrixARelease.registers)"
        }
        }
    } else {
        $keyDown = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":2,"code":257}'
        $keyUp = Invoke-RestMethod -Method Post `
            -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":0,"code":0}'
    }

    if ($ExpectHle) {
        $afterKey = $null
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            $afterKey = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            if ($afterKey.registers -match 'HLE_UI=active\s+PAGE=0\s+SEL=1') {
                break
            }
            Start-Sleep -Milliseconds 50
        }
        if ($afterKey.registers -notmatch 'HLE_UI=active\s+PAGE=0\s+SEL=1') {
            throw 'The QEMU menu did not process the Down key.'
        }
        if ($afterKey.frame -eq $state.frame) {
            throw 'The LCD framebuffer did not change after menu navigation.'
        }

        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":16,"code":260}' | Out-Null
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":0,"code":0}' | Out-Null
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            $detail = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            if ($detail.registers -match 'HLE_UI=active\s+PAGE=2\s+SEL=1') {
                break
            }
            Start-Sleep -Milliseconds 50
        }
        if ($detail.registers -notmatch 'HLE_UI=active\s+PAGE=2\s+SEL=1' -or
            $detail.frame -eq $afterKey.frame) {
            throw 'The QEMU menu did not open the selected page.'
        }

        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":32,"code":261}' | Out-Null
        Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:$Port/api/key" `
            -ContentType 'application/json' -Body '{"state":0,"code":0}' | Out-Null
        for ($attempt = 0; $attempt -lt 20; $attempt++) {
            $back = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
            if ($back.registers -match 'HLE_UI=active\s+PAGE=0\s+SEL=1') {
                break
            }
            Start-Sleep -Milliseconds 50
        }
        if ($back.registers -notmatch 'HLE_UI=active\s+PAGE=0\s+SEL=1') {
            throw 'The QEMU menu did not process the Escape key.'
        }
    }

    $pause = Invoke-RestMethod -Method Post `
        -Uri "http://127.0.0.1:$Port/api/control" `
        -ContentType 'application/json' -Body '{"action":"pause"}'
    $paused = Invoke-RestMethod -Uri $stateUri -TimeoutSec 2
    $resume = Invoke-RestMethod -Method Post `
        -Uri "http://127.0.0.1:$Port/api/control" `
        -ContentType 'application/json' -Body '{"action":"resume"}'

    if (-not $keyDown.ok -or -not $keyUp.ok -or
        -not $pause.ok -or -not $resume.ok -or
        $paused.status -ne 'paused') {
        throw 'Web input or run-control API check failed.'
    }

    $nonzero = @($frame | Where-Object { $_ -ne 0 }).Count
    if ($ExpectNonzero -and $nonzero -eq 0) {
        throw 'LCD test firmware produced an empty frame.'
    }
    if ($FrameSource -eq 'memory') {
        if ($state.registers -notmatch 'HLE_LCD_CALLS=(\d+)') {
            throw 'HLE LCD call counter is missing from QEMU CPU state.'
        }
        if ([int]$Matches[1] -lt $MinimumLcdCalls) {
            throw "Expected at least $MinimumLcdCalls LCD calls, got $($Matches[1])."
        }
    }
    Write-Host "NP560+ Web test passed: $expectedFrameLength-byte $FrameSource frame, $nonzero nonzero bytes."
    Write-Host $state.registers
    if ($ExpectNative) {
        Write-Host $afterNativeKey.registers
    }
} finally {
    $serverProcess.Refresh()
    if (-not $serverProcess.HasExited) {
        try {
            Invoke-RestMethod -Method Post `
                -Uri "http://127.0.0.1:$Port/api/control" `
                -ContentType 'application/json' `
                -Body (ConvertTo-Json @{
                    action = 'shutdown'
                    token = $shutdownToken
                } -Compress) -TimeoutSec 2 | Out-Null
        } catch {
            # The process may already be exiting after an earlier test error.
        }
    }
    $shutdownTimeout = if ($NandSaveOnExit) { 30 } else { 5 }
    Wait-Process -Id $serverProcess.Id -Timeout $shutdownTimeout `
        -ErrorAction SilentlyContinue
    $serverProcess.Refresh()
    if (-not $serverProcess.HasExited) {
        Stop-Process -Id $serverProcess.Id -Force -ErrorAction SilentlyContinue
    }
}
