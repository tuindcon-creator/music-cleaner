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
& ".venv\Scripts\python.exe" -c "import pathlib,zipfile; p=pathlib.Path('dist/MusicCleaner'); z=zipfile.ZipFile('dist/MusicCleaner-Windows.zip','w',zipfile.ZIP_DEFLATED); [z.write(f,f.relative_to(p.parent).as_posix()) for f in sorted(p.rglob('*')) if f.is_file()]; z.close()"
if ($LASTEXITCODE -ne 0) { throw "ZIP packaging failed." }
Get-FileHash "$destination\MusicCleaner-Windows.zip" -Algorithm SHA256 | Format-List
