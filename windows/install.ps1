# Roomba voor Windows – installatie. Geen administrator nodig (en liever niet:
# als administrator kan de roomba je Verkenner-vensters niet zien).
$ErrorActionPreference = "Stop"
$Src   = Split-Path -Parent $PSScriptRoot
$Base  = Join-Path $env:LOCALAPPDATA "kde-roomba"
$App   = Join-Path $Base "app"
$Venv  = Join-Path $Base "venv"
$Model = if ($env:ROOMBA_MODEL) { $env:ROOMBA_MODEL } else { "qwen2.5:1.5b" }

function Say($m)  { Write-Host "==> $m" -ForegroundColor Green }
function Warn($m) { Write-Host "!!  $m" -ForegroundColor Yellow }
function Ask($q)  { $a = Read-Host "$q [J/n]"; return ($a -eq "" -or $a -match "^[JjYy]") }
function Refresh-Path { $env:Path = [Environment]::GetEnvironmentVariable("Path","Machine") + ";" + [Environment]::GetEnvironmentVariable("Path","User") }

# 1. Python ------------------------------------------------------------------
$py = Get-Command py -ErrorAction SilentlyContinue
if (-not $py) {
    Say "Python installeren (winget)…"
    winget install -e --id Python.Python.3.12 --scope user --accept-source-agreements --accept-package-agreements
    Refresh-Path
}
if (-not (Test-Path "$Venv\Scripts\python.exe")) {
    Say "Eigen Python-omgeving maken in $Venv"
    & py -3 -m venv $Venv
}
$Python  = "$Venv\Scripts\python.exe"
$PythonW = "$Venv\Scripts\pythonw.exe"
Say "PyQt6 en comtypes installeren…"
& $Python -m pip install --quiet --upgrade pip
& $Python -m pip install --quiet -r "$Src\requirements-windows.txt"

# 2. Oude roomba stoppen, programma kopiëren ----------------------------------
if (Test-Path "$App\kde_roomba") { & $Python -m kde_roomba --quit 2>$null | Out-Null }
Say "Programma installeren in $App"
New-Item -ItemType Directory -Force $App | Out-Null
Remove-Item -Recurse -Force "$App\kde_roomba" -ErrorAction SilentlyContinue
Copy-Item -Recurse "$Src\kde_roomba" $App
Push-Location $App
& $Python -m kde_roomba.make_icon "$App\roomba.ico" | Out-Null
Pop-Location

# 3. Snelkoppelingen ------------------------------------------------------------
function New-Shortcut($Path, $Arguments, $Description) {
    $ws = New-Object -ComObject WScript.Shell
    $s = $ws.CreateShortcut($Path)
    $s.TargetPath = $PythonW
    $s.Arguments = ("-m kde_roomba " + $Arguments).Trim()
    $s.WorkingDirectory = $App
    $s.Description = $Description
    $s.IconLocation = "$App\roomba.ico"
    $s.Save()
}
$Menu = Join-Path ([Environment]::GetFolderPath("Programs")) "Roomba"
New-Item -ItemType Directory -Force $Menu | Out-Null
New-Shortcut "$Menu\Roomba.lnk" "" "Bureaublad-stofzuiger met lokale AI"
New-Shortcut "$Menu\Roomba herstarten.lnk" "--restart" "Roomba herstarten"
New-Shortcut "$Menu\Roomba afsluiten.lnk" "--quit" "Roomba afsluiten"
if (Ask "Automatisch starten bij aanmelden?") {
    New-Shortcut (Join-Path ([Environment]::GetFolderPath("Startup")) "Roomba.lnk") "" "Roomba"
}

# 4. Lokale AI (Ollama) -------------------------------------------------------
if (Ask "Lokaal AI-model installeren via Ollama (model: $Model, ±1 GB)?") {
    if (-not (Get-Command ollama -ErrorAction SilentlyContinue)) {
        Say "Ollama installeren (winget)…"
        winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
        Refresh-Path
    }
    try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null }
    catch { Start-Process ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
    Say "Model $Model downloaden…"
    & ollama pull $Model
} else {
    Warn "Geen AI: de roomba gebruikt dan zijn ingebouwde regels."
}

# 5. Starten -------------------------------------------------------------------
Say "Roomba starten…"
Start-Process $PythonW -ArgumentList "-m kde_roomba" -WorkingDirectory $App
Start-Sleep 4
$Log = Join-Path $Base "roomba.log"
if ((Test-Path $Log) -and (Select-String -Path $Log -Pattern "Venster getoond" -Quiet)) {
    Say "De roomba staat rechtsonder op je bureaublad. Dubbelklik erop!"
} else {
    Warn "De roomba lijkt niet gestart. Kijk in $Log"
}
Say "Startmenu: 'Roomba', 'Roomba herstarten', 'Roomba afsluiten'. Of rechtsklik op het icoon in het systeemvak."
