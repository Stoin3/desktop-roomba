# Lokaal AI-model voor de Roomba installeren: Ollama (via winget) + qwen2.5:1.5b.
# Wordt door de installatiewizard gestart als je die optie aanvinkt; kan ook los.
$ErrorActionPreference = "Continue"
$Model = "qwen2.5:1.5b"
Write-Host "== Lokaal AI-model voor de Roomba ==" -ForegroundColor Green
$ollama = (Get-Command ollama -ErrorAction SilentlyContinue).Source
if (-not $ollama) { $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe" }
if (-not (Test-Path $ollama)) {
    Write-Host "Ollama installeren (winget)…"
    winget install -e --id Ollama.Ollama --accept-source-agreements --accept-package-agreements
    $ollama = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
}
if (-not (Test-Path $ollama)) {
    Write-Host "Ollama kon niet geïnstalleerd worden. De Roomba gebruikt dan zijn ingebouwde regels." -ForegroundColor Yellow
    Start-Sleep 5; exit 0
}
try { Invoke-WebRequest -UseBasicParsing http://127.0.0.1:11434/api/tags -TimeoutSec 2 | Out-Null }
catch { Start-Process $ollama -ArgumentList "serve" -WindowStyle Hidden; Start-Sleep 3 }
Write-Host "Model $Model downloaden (±1 GB)…"
& $ollama pull $Model
Write-Host "Klaar." -ForegroundColor Green
Start-Sleep 2
