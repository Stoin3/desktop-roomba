# Bouwt dist\Roomba\Roomba.exe (PyInstaller, map met alles erin).
$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $PSScriptRoot
Push-Location $Root
py -3 -m venv .build-venv
& .build-venv\Scripts\python.exe -m pip install --quiet --upgrade pip
& .build-venv\Scripts\python.exe -m pip install --quiet -r requirements-windows.txt pyinstaller
& .build-venv\Scripts\python.exe -m kde_roomba.make_icon windows\roomba.ico
& .build-venv\Scripts\pyinstaller.exe --noconfirm --windowed --name Roomba --icon windows\roomba.ico `
    --paths . --collect-submodules comtypes --hidden-import kde_roomba.windows_shell `
    --hidden-import kde_roomba.windows_integration --hidden-import kde_roomba.windows_com windows\run_roomba.py
Pop-Location
Write-Host "Klaar: dist\Roomba\Roomba.exe"
