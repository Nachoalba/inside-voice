; Inno Setup script for Inside Voice (English + Spanish installer).
; Build:  ISCC.exe installer\inside-voice.iss      (run after PyInstaller)

#define MyAppName "Inside Voice"
#define MyAppExe "InsideVoice.exe"
#define MyAppVersion GetEnv("IV_VERSION")
#if MyAppVersion == ""
  #undef MyAppVersion
  #define MyAppVersion "0.1.2"
#endif

[Setup]
AppId={{8F3D2A17-5C4B-4E0E-9A57-1B6C2D9E7F40}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppPublisher=Nachoalba
DefaultDirName={autopf}\Inside Voice
DefaultGroupName=Inside Voice
DisableProgramGroupPage=yes
OutputDir=..\dist-installer
OutputBaseFilename=InsideVoice-Setup-{#MyAppVersion}
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#MyAppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
CloseApplications=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[CustomMessages]
english.AutoStart=Start Inside Voice with Windows (in the tray)
spanish.AutoStart=Iniciar Inside Voice con Windows (en la bandeja)
english.Coffee=Buy me a coffee (opens Ko-fi in your browser)
spanish.Coffee=Invítame a un café (abre Ko-fi en el navegador)

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked
Name: "autostart"; Description: "{cm:AutoStart}"; GroupDescription: "{cm:AdditionalIcons}"

[Files]
Source: "..\dist\InsideVoice\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Icons]
Name: "{autoprograms}\Inside Voice"; Filename: "{app}\{#MyAppExe}"
Name: "{autodesktop}\Inside Voice"; Filename: "{app}\{#MyAppExe}"; Tasks: desktopicon

[Registry]
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Run"; ValueType: string; ValueName: "InsideVoice"; ValueData: """{app}\{#MyAppExe}"" --minimized"; Tasks: autostart

[Run]
Filename: "{app}\{#MyAppExe}"; Description: "{cm:LaunchProgram,{#MyAppName}}"; Flags: nowait postinstall skipifsilent

Filename: "https://ko-fi.com/nachoalba"; Description: "{cm:Coffee}"; Flags: shellexec postinstall skipifsilent unchecked

[UninstallRun]
Filename: "{sys}\taskkill.exe"; Parameters: "/F /IM {#MyAppExe}"; Flags: runhidden; RunOnceId: "StopInsideVoice"

[Code]
// The app can also enable "start with Windows" by itself; remove that entry on uninstall.
procedure CurUninstallStepChanged(CurUninstallStep: TUninstallStep);
begin
  if CurUninstallStep = usPostUninstall then
    RegDeleteValue(HKCU, 'Software\Microsoft\Windows\CurrentVersion\Run', 'InsideVoice');
end;
