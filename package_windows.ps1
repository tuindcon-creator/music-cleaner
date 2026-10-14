$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$destination = Join-Path $PSScriptRoot "dist"
$package = Join-Path $destination "MusicCleaner"
New-Item -ItemType Directory -Force $package | Out-Null
$compiler = Join-Path $env:WINDIR "Microsoft.NET\Framework64\v4.0.30319\csc.exe"
if (-not (Test-Path $compiler)) { throw "The Windows .NET Framework compiler is unavailable." }
& $compiler /nologo /target:winexe /optimize+ /platform:anycpu /reference:System.Windows.Forms.dll /out:"$package\MusicCleaner.exe" build_launcher.cs
if ($LASTEXITCODE -ne 0) { throw "Launcher compilation failed." }
Get-ChildItem -File -Filter "*.py" | Copy-Item -Destination $package
foreach ($file in @("run_windows.bat", "install_windows.bat", "setup_windows.ps1",
                    "requirements.txt", "README.md", "VALIDATION.md")) {
    Copy-Item $file $package
}
Compress-Archive -Path $package -DestinationPath "$destination\MusicCleaner-Windows.zip" -Force
Get-FileHash "$destination\MusicCleaner-Windows.zip" -Algorithm SHA256 | Format-List
