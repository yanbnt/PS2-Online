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

# 2) Instalador (app compactado dentro de um .exe único)
New-Item -ItemType Directory -Force "$work\payload" | Out-Null
Compress-Archive -Path "$work\dist\PS2 Online" -DestinationPath "$work\payload\payload.zip" -CompressionLevel Optimal
& $pi --noconfirm --onefile --windowed --name "Instalar PS2 Online" --icon "$proj\icon.ico" `
    --add-data "$work\payload\payload.zip;." --add-data "$proj\icon.ico;." --exclude-module numpy --exclude-module PySide6 `
    --workpath "$work\ibuild" --distpath "$work\idist" --specpath "$work\ibuild" --log-level ERROR "$proj\installer\installer.py"

New-Item -ItemType Directory -Force "$proj\out" | Out-Null
Copy-Item "$work\idist\Instalar PS2 Online.exe" "$proj\out\" -Force
Write-Host "Pronto: $proj\out\Instalar PS2 Online.exe"
