$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Find-Python {
    $candidates = @()
    if (Get-Command py -ErrorAction SilentlyContinue) {
        $candidates += ,@("py", "-3.11")
    }
    $localPython = Join-Path $env:LOCALAPPDATA "Programs\Python\Python311\python.exe"
    if (Test-Path $localPython) { $candidates += ,@($localPython) }
    if (Get-Command python -ErrorAction SilentlyContinue) { $candidates += ,@("python") }
    foreach ($candidate in $candidates) {
        $exe = $candidate[0]
        $prefix = @($candidate | Select-Object -Skip 1)
        try {
            $path = & $exe @prefix -c "import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8; print(sys.executable)" 2>$null
            if ($LASTEXITCODE -eq 0 -and $path) { return "$path".Trim() }
        } catch {}
    }
    return $null
}

try {
    $architecture = [System.Runtime.InteropServices.RuntimeInformation]::OSArchitecture.ToString()
    if ($architecture -ne "X64") { throw "This Windows installer requires x64. ARM and 32-bit Windows are not supported." }
    if ([Environment]::OSVersion.Version.Build -lt 10240) { throw "Windows 10 or 11 is required." }
    $pythonPath = Find-Python
    if (-not $pythonPath) {
        Write-Host "Python 3.11 x64 missing. Installing per-user with winget..."
        if (-not (Get-Command winget -ErrorAction SilentlyContinue)) {
            throw "winget is unavailable. Install Python 3.11 x64 from python.org, then run setup again."
        }
        & winget install --id Python.Python.3.11 --exact --source winget --scope user --silent --accept-package-agreements --accept-source-agreements
        $pythonPath = Find-Python
        if (-not $pythonPath) { throw "Python installation did not complete. Install Python 3.11 x64 manually and retry." }
    }
    $venvPython = Join-Path $PSScriptRoot ".venv\Scripts\python.exe"
    $usable = $false
    if (Test-Path $venvPython) {
        try {
            & $venvPython -c "import sys,struct; assert sys.version_info[:2]==(3,11) and struct.calcsize('P')==8"
            $usable = $LASTEXITCODE -eq 0
        } catch {}
    }
    if (-not $usable) {
        if (Test-Path ".venv") {
            $backupName = ".venv-backup-" + [Guid]::NewGuid().ToString("N")
            Move-Item ".venv" $backupName
        }
        & $pythonPath -m venv .venv
        if ($LASTEXITCODE -ne 0) { throw "Could not create .venv; move the app to a writable folder." }
    }
    & $venvPython setup_runtime.py
    if ($LASTEXITCODE -ne 0) { throw "Dependency setup failed. See the error above and retry." }
    exit 0
} catch {
    Write-Host $_.Exception.Message -ForegroundColor Red
    exit 1
}

