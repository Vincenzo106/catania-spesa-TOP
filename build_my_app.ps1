$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

$projectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$backendDir = Join-Path $projectRoot "backend"
$frontendDir = Join-Path $projectRoot "frontend"
$envFile = Join-Path $backendDir ".env"
$envExampleFile = Join-Path $backendDir ".env.example"
$popplerPath = 'C:\Users\vgchi\Downloads\Release-26.02.0-0\poppler-26.02.0\Library\bin'

function Stop-WithPause {
    param(
        [string]$Message,
        [System.Exception]$Exception = $null
    )

    Write-Host ""
    Write-Host "Build script failed." -ForegroundColor Red
    Write-Host $Message -ForegroundColor Yellow

    if ($null -ne $Exception) {
        Write-Host $Exception.Message -ForegroundColor DarkYellow
    }

    Read-Host "Press Enter to close this window"
    exit 1
}

function Invoke-Step {
    param(
        [string]$Name,
        [scriptblock]$Action
    )

    Write-Host ""
    Write-Host "==> $Name" -ForegroundColor Cyan

    try {
        & $Action
        Write-Host "Completed: $Name" -ForegroundColor Green
    }
    catch {
        Stop-WithPause -Message "Step failed: $Name" -Exception $_.Exception
    }
}

function Update-OrAppend-EnvValue {
    param(
        [string]$FilePath,
        [string]$Key,
        [string]$Value
    )

    if (-not (Test-Path -LiteralPath $FilePath)) {
        if (Test-Path -LiteralPath $envExampleFile) {
            Copy-Item -LiteralPath $envExampleFile -Destination $FilePath -Force
        }
        else {
            New-Item -ItemType File -Path $FilePath -Force | Out-Null
        }
    }

    $content = Get-Content -LiteralPath $FilePath -Raw -ErrorAction SilentlyContinue
    if ($null -eq $content) {
        $content = ""
    }

    $escapedKey = [regex]::Escape($Key)
    $newLine = $Key + '="' + $Value + '"'

    if ($content -match "(?m)^$escapedKey=") {
        $updated = [regex]::Replace($content, "(?m)^$escapedKey=.*$", $newLine)
    }
    else {
        $trimmed = $content.TrimEnd("`r", "`n")
        if ([string]::IsNullOrWhiteSpace($trimmed)) {
            $updated = $newLine
        }
        else {
            $updated = $trimmed + "`r`n" + $newLine
        }
    }

    [System.IO.File]::WriteAllText($FilePath, $updated + "`r`n", [System.Text.UTF8Encoding]::new($false))
}

function Ensure-CommandExists {
    param([string]$CommandName)

    $command = Get-Command $CommandName -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        throw "Required command '$CommandName' was not found in PATH."
    }
}

try {
    if (-not (Test-Path -LiteralPath $backendDir)) {
        throw "Backend directory not found: $backendDir"
    }

    if (-not (Test-Path -LiteralPath $frontendDir)) {
        throw "Frontend directory not found: $frontendDir"
    }

    Invoke-Step -Name "Checking required tools" -Action {
        Ensure-CommandExists -CommandName "npm"
    }

    Invoke-Step -Name "Configuring backend POPPLER_PATH in backend/.env" -Action {
        Update-OrAppend-EnvValue -FilePath $envFile -Key "POPPLER_PATH" -Value $popplerPath
        Write-Host "POPPLER_PATH set to: $popplerPath"
    }

    Invoke-Step -Name "Installing global Expo build tool (eas-cli)" -Action {
        & npm install -g eas-cli
        if ($LASTEXITCODE -ne 0) {
            throw "npm install -g eas-cli exited with code $LASTEXITCODE."
        }
    }

    Invoke-Step -Name "Logging into Expo with EAS" -Action {
        Push-Location $frontendDir
        try {
            Write-Host ""
            Write-Host "If you are not already authenticated, complete the Expo login flow now." -ForegroundColor Yellow
            & eas login
            if ($LASTEXITCODE -ne 0) {
                throw "eas login exited with code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    Invoke-Step -Name "Triggering Android APK build with EAS" -Action {
        Push-Location $frontendDir
        try {
            & eas build --platform android --profile preview
            if ($LASTEXITCODE -ne 0) {
                throw "eas build exited with code $LASTEXITCODE."
            }
        }
        finally {
            Pop-Location
        }
    }

    Write-Host ""
    Write-Host "All steps completed. Your Android preview APK build has been triggered." -ForegroundColor Green
    Read-Host "Press Enter to close this window"
}
catch {
    Stop-WithPause -Message "Unexpected error while preparing the build." -Exception $_.Exception
}
