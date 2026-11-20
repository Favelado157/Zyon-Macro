[Setup]
AppId={{F9BC7E0A-73F2-48F1-AF61-1E7B9C12FBB1}
AppName=GhosttzzKBot
AppVersion=1.2.0
DefaultDirName={localappdata}\Programs\GhosttzzKBot
DefaultGroupName=GhosttzzKBot
PrivilegesRequired=lowest
UsePreviousAppDir=yes
OutputDir=installer
OutputBaseFilename=GhosttzzKBot-Setup
SetupIconFile=assets\GhosttzzKBot.ico
UninstallDisplayIcon={app}\GhosttzzKBot.exe
WizardStyle=modern
CloseApplications=yes

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Files]
Source: "dist\GhosttzzKBot\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion
Source: "assets\*"; DestDir: "{app}\assets"; Flags: ignoreversion
Source: "config\settings.json"; DestDir: "{localappdata}\GhosttzzKBot\config"; Flags: onlyifdoesntexist uninsneveruninstall

[Icons]
Name: "{group}\GhosttzzKBot"; Filename: "{app}\GhosttzzKBot.exe"
Name: "{autodesktop}\GhosttzzKBot"; Filename: "{app}\GhosttzzKBot.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; Flags: unchecked

[Run]
Filename: "{app}\GhosttzzKBot.exe"; Description: "Abrir GhosttzzKBot"; Flags: postinstall nowait skipifsilent
