; Roomba voor Windows – installatiewizard + uninstaller (Inno Setup 6)
;
; Bouwen (na PyInstaller, map dist\Roomba):
;   ISCC.exe /DMyAppVersion=2.3.0 installer\roomba.iss
; Resultaat: dist-installer\Roomba-Setup-<versie>.exe
;
; Geen administrator nodig: installeert in %LOCALAPPDATA%\Programs\Roomba.

#ifndef MyAppVersion
  #define MyAppVersion "0.0.0"
#endif
#define MyAppName "Roomba"
#define MyAppExe "Roomba.exe"

[Setup]
AppId={{7D937103-B8DF-448E-9A50-A882609C61ED}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher=KDE Roomba
AppPublisherURL=https://github.com/Stoin3/desktop-roomba
AppSupportURL=https://github.com/Stoin3/desktop-roomba/issues
AppUpdatesURL=https://github.com/Stoin3/desktop-roomba/releases
DefaultDirName={localappdata}\Programs\{#MyAppName}
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes
PrivilegesRequired=lowest
OutputDir=..\dist-installer
OutputBaseFilename=Roomba-Setup-{#MyAppVersion}
SetupIconFile=..\windows\roomba.ico
UninstallDisplayIcon={app}\{#MyAppExe}
UninstallDisplayName={#MyAppName} – bureaublad-stofzuiger
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=no
VersionInfoVersion={#MyAppVersion}
VersionInfoDescription=Roomba installatie

[Languages]
Name: "dutch"; MessagesFile: "compiler:Languages\Dutch.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[CustomMessages]
dutch.DesktopIcon=Snelkoppeling op het bureaublad
dutch.AutoStart=Roomba automatisch starten bij aanmelden
dutch.Ollama=Lokaal AI-model installeren (Ollama + qwen2.5:1.5b, ±1 GB downloaden)
dutch.Extra=Extra:
dutch.RunNow=Roomba nu starten
dutch.Restart=Roomba herstarten
dutch.Quit=Roomba afsluiten
dutch.InstallingAI=Lokaal AI-model installeren (dit kan even duren)…
dutch.RemoveData=Wil je ook je Roomba-instellingen en het logboek verwijderen?
english.DesktopIcon=Desktop shortcut
english.AutoStart=Start Roomba when I sign in
english.Ollama=Install local AI model (Ollama + qwen2.5:1.5b, ~1 GB download)
english.Extra=Extra:
english.RunNow=Start Roomba now
english.Restart=Restart Roomba
english.Quit=Quit Roomba
english.InstallingAI=Installing local AI model (this may take a while)…
english.RemoveData=Also remove your Roomba settings and log?

[Tasks]
Name: "desktopicon"; Description: "{cm:DesktopIcon}"; GroupDescription: "{cm:Extra}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:Extra}"
Name: "ollama"; Description: "{cm:Ollama}"; GroupDescription: "{cm:Extra}"; Flags: unchecked

[Files]
Source: "..\dist\Roomba\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\windows\install-ai.ps1"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{autoprograms}\{#MyAppName}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"
Name: "{autoprograms}\{#MyAppName}\{cm:Restart}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--restart"
Name: "{autoprograms}\{#MyAppName}\{cm:Quit}"; Filename: "{app}\{#MyAppExe}"; Parameters: "--quit"
Name: "{autoprograms}\{#MyAppName}\{cm:UninstallProgram,{#MyAppName}}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon
Name: "{userstartup}\{#MyAppName}"; Filename: "{app}\{#MyAppExe}"; Tasks: autostart

[Run]
; Ollama + het model ophalen (eigen venster, zodat je de voortgang ziet)
Filename: "powershell.exe"; Parameters: "-NoProfile -ExecutionPolicy Bypass -File ""{app}\install-ai.ps1"""; StatusMsg: "{cm:InstallingAI}"; Tasks: ollama; Flags: waituntilterminated
Filename: "{app}\{#MyAppExe}"; Description: "{cm:RunNow}"; Flags: nowait postinstall skipifsilent

[UninstallRun]
; eerst de draaiende roomba netjes afsluiten, anders zijn de bestanden in gebruik
Filename: "{app}\{#MyAppExe}"; Parameters: "--quit"; Flags: runhidden waituntilterminated; RunOnceId: "QuitRoomba"

[Code]
procedure QuitRunningRoomba();
var
  Rc: Integer;
  Exe: String;
begin
  Exe := ExpandConstant('{app}\{#MyAppExe}');
  if FileExists(Exe) then
    Exec(Exe, '--quit', '', SW_HIDE, ewWaitUntilTerminated, Rc);
end;

function PrepareToInstall(var NeedsRestart: Boolean): String;
begin
  { bij een update: de oude roomba afsluiten zodat zijn bestanden vervangen kunnen worden }
  QuitRunningRoomba();
  Result := '';
end;

procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
  begin
    { standaard (ook bij stil verwijderen): instellingen bewaren }
    if SuppressibleMsgBox(CustomMessage('RemoveData'), mbConfirmation, MB_YESNO or MB_DEFBUTTON2, IDNO) = IDYES then
    begin
      DelTree(ExpandConstant('{userappdata}\kde-roomba'), True, True, True);
      DelTree(ExpandConstant('{localappdata}\kde-roomba'), True, True, True);
    end;
  end;
end;
