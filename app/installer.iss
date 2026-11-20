[Setup]
AppId={{F9BC7E0A-73F2-48F1-AF61-1E7B9C12FBB1}
AppName=Zyon Macro
AppPublisher=Zyon Nexus
AppVersion=1.4.1
DefaultDirName={localappdata}\Programs\Zyon Macro
DefaultGroupName=Zyon Macro
UsePreviousGroup=no
PrivilegesRequired=lowest
UsePreviousAppDir=yes
OutputDir=installer
OutputBaseFilename=Zyon-Macro-Setup
SetupIconFile=assets\GhosttzzKBot.ico
UninstallDisplayIcon={app}\ZyonMacro.exe
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\ZyonMacro\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "config\settings.json"; DestDir: "{localappdata}\GhosttzzKBot\config"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\Zyon Macro"; Filename: "{app}\ZyonMacro.exe"
Name: "{autodesktop}\Zyon Macro"; Filename: "{app}\ZyonMacro.exe"; Tasks: desktopicon

[InstallDelete]
Type: files; Name: "{app}\GhosttzzKBot.exe"
Type: files; Name: "{autoprograms}\GhosttzzKBot\GhosttzzKBot.lnk"
Type: files; Name: "{autodesktop}\GhosttzzKBot.lnk"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Run]
Filename: "{app}\ZyonMacro.exe"; Description: "Abrir Zyon Macro"; Flags: postinstall nowait skipifsilent

Filename: "{app}\ZyonMacro.exe"; Flags: nowait skipifnotsilent; Check: IsGhostUpdate

[Code]
function IsGhostUpdate: Boolean;
var
  I: Integer;
begin
  Result := False;
  for I := 1 to ParamCount do
    if CompareText(ParamStr(I), '/GHOST_UPDATE') = 0 then
    begin
      Result := True;
      Exit;
    end;
end;
