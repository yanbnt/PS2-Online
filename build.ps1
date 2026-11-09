# Gera o app (pasta "PS2 Online") e o instalador ("Instalar PS2 Online.exe").
# Uso:  powershell -ExecutionPolicy Bypass -File build.ps1
# Saída: .\out\Instalar PS2 Online.exe
$ErrorActionPreference = "Stop"
$proj = $PSScriptRoot
$work = Join-Path $env:LOCALAPPDATA "PS2Online-build"   # caminho curto (evita limite de 260 caracteres)
$venv = Join-Path $work "venv"
$py = Join-Path $venv "Scripts\python.exe"
$pi = Join-Path $venv "Scripts\pyinstaller.exe"

if (-not (Test-Path $py)) { python -m venv $venv }
$env:VGAMEPAD_SKIP_VIGEMBUS_INSTALL = "true"
& $py -m pip install -q --upgrade pip
& $py -m pip install -q -r (Join-Path $proj "requirements.txt") pyinstaller pillow

foreach ($d in "dist", "build", "ibuild", "idist", "payload") { Remove-Item -Recurse -Force (Join-Path $work $d) -ErrorAction SilentlyContinue }

# 1) App
& $pi --noconfirm --windowed --name "PS2 Online" --icon "$proj\icon.ico" --add-data "$proj\icon.png;." `
    --collect-all vgamepad --collect-binaries pyaudiowpatch --hidden-import host --hidden-import guest `
    --exclude-module tkinter --exclude-module PySide6.QtQuick --exclude-module PySide6.QtQml `
    --exclude-module PySide6.QtPdf --exclude-module PySide6.QtNetwork --exclude-module PySide6.QtOpenGL `
    --paths $proj --workpath "$work\build" --distpath "$work\dist" --specpath "$work\build" --log-level ERROR "$proj\app.py"

# Remove partes do Qt que o app não usa (~40 MB)
$qt = "$work\dist\PS2 Online\_internal\PySide6"
"opengl32sw.dll", "Qt6Pdf.dll", "Qt6Qml.dll", "Qt6QmlMeta.dll", "Qt6QmlModels.dll", "Qt6QmlWorkerScript.dll",
"Qt6Quick.dll", "Qt6VirtualKeyboard.dll" | ForEach-Object { Remove-Item "$qt\$_" -ErrorAction SilentlyContinue }
Get-ChildItem "$qt\plugins" -Recurse -File | Where-Object { $_.Name -match 'qpdf|virtualkeyboard' } | Remove-Item
Copy-Item "$proj\LEIAME.md" "$work\dist\PS2 Online\LEIAME.md"

# 2) Instalador com Inno Setup (https://jrsoftware.org/isinfo.php — winget install JRSoftware.InnoSetup)
#    Um instalador "PyInstaller --onefile" é marcado como Trojan:Win32/Wacatac.B!ml pelo Defender (falso positivo);
#    o Inno Setup não tem esse problema.
$iscc = @("$env:LOCALAPPDATA\Programs\Inno Setup 6\ISCC.exe", "${env:ProgramFiles(x86)}\Inno Setup 6\ISCC.exe",
          "$env:ProgramFiles\Inno Setup 6\ISCC.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $iscc) { throw "Inno Setup 6 não encontrado. Instale com: winget install JRSoftware.InnoSetup" }
New-Item -ItemType Directory -Force "$proj\out" | Out-Null
& $iscc /Q "/DAppDir=$work\dist\PS2 Online" "/DOutDir=$proj\out" "$proj\installer\PS2Online.iss"
if ($LASTEXITCODE -ne 0) { throw "ISCC falhou ($LASTEXITCODE)" }
Write-Host "Pronto: $proj\out\Instalar-PS2-Online.exe"
