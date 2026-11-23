# Test van de installatiewizard en uninstaller (stil), voor GitHub Actions.
param([string]$Setup)
$ErrorActionPreference = "Stop"
$App   = Join-Path $env:LOCALAPPDATA "Programs\Roomba"
$Menu  = Join-Path ([Environment]::GetFolderPath("Programs")) "Roomba"
$Start = Join-Path ([Environment]::GetFolderPath("Startup")) "Roomba.lnk"
$Log   = Join-Path $env:LOCALAPPDATA "kde-roomba\roomba.log"
function Check($ok, $what) { if ($ok) { Write-Host "  OK  $what" } else { Write-Host "  FOUT $what" -ForegroundColor Red; exit 1 } }

Write-Host "== Installeren (stil): $Setup"
$p = Start-Process $Setup -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/TASKS=autostart","/LOG=e2e-out\setup.log" -Wait -PassThru
Check ($p.ExitCode -eq 0) "setup klaar (code $($p.ExitCode))"
Check (Test-Path "$App\Roomba.exe") "Roomba.exe geïnstalleerd in $App"
Check (Test-Path "$App\install-ai.ps1") "AI-installatiescript meegeleverd"
Check (Test-Path "$App\unins000.exe") "uninstaller aanwezig"
Check (Test-Path "$Menu\Roomba.lnk") "Startmenu: Roomba"
Check (Test-Path "$Menu\Roomba afsluiten.lnk") "Startmenu: Roomba afsluiten"
Check (Test-Path $Start) "autostart-snelkoppeling"
$reg = Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall | Get-ItemProperty | Where-Object { $_.DisplayName -like "Roomba*" }
Check ($null -ne $reg) "staat in Instellingen → Apps ($($reg.DisplayName) $($reg.DisplayVersion))"

Write-Host "== Geïnstalleerde Roomba starten"
if (Test-Path $Log) { Remove-Item $Log }
Start-Process "$App\Roomba.exe"
$ok = $false
for ($i = 0; $i -lt 40; $i++) { Start-Sleep 0.5; if ((Test-Path $Log) -and (Select-String -Path $Log -Pattern "Venster getoond" -Quiet)) { $ok = $true; break } }
Check $ok "Roomba.exe start en toont zijn venster"
Check ((Get-Process Roomba -ErrorAction SilentlyContinue) -ne $null) "proces draait"

Write-Host "== Opnieuw installeren over de draaiende versie heen (update)"
$p = Start-Process $Setup -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART","/TASKS=autostart" -Wait -PassThru
Check ($p.ExitCode -eq 0) "update geslaagd terwijl de roomba draaide (code $($p.ExitCode))"

Write-Host "== Verwijderen (stil)"
Start-Process "$App\Roomba.exe"; Start-Sleep 6
$p = Start-Process "$App\unins000.exe" -ArgumentList "/VERYSILENT","/SUPPRESSMSGBOXES","/NORESTART" -Wait -PassThru
Start-Sleep 3
Check (-not (Test-Path "$App\Roomba.exe")) "programmabestanden verwijderd"
Check (-not (Test-Path "$Menu\Roomba.lnk")) "Startmenu opgeruimd"
Check (-not (Test-Path $Start)) "autostart opgeruimd"
Check ((Get-Process Roomba -ErrorAction SilentlyContinue) -eq $null) "roomba is afgesloten"
$reg = Get-ChildItem HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall | Get-ItemProperty | Where-Object { $_.DisplayName -like "Roomba*" }
Check ($null -eq $reg) "niet meer in Instellingen → Apps"
Write-Host "INSTALLER-TEST OK" -ForegroundColor Green
