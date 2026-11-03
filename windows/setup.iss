; OpenPLC Runtime - Inno Setup Script
; This script creates a Windows installer that bundles MSYS2 with all dependencies

#define MyAppName "OpenPLC Runtime"
#define MyAppVersion "4.0"
#define MyAppPublisher "Autonomy Logic"
#define MyAppURL "https://autonomylogic.com"
#define MyAppExeName "StartOpenPLC.bat"

[Setup]
; Application information
AppId={{A1B2C3D4-E5F6-7890-ABCD-EF1234567890}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} {#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}
AppUpdatesURL={#MyAppURL}

; Installation settings
DefaultDirName={localappdata}\OpenPLC Runtime
DefaultGroupName={#MyAppName}
DisableProgramGroupPage=yes

; Per-user installation (no admin required)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog

; Output settings
OutputDir=output
OutputBaseFilename=OpenPLC_Runtime_Setup
SetupIconFile=openplc.ico
UninstallDisplayIcon={app}\openplc.ico

; Compression settings (LZMA2 for best compression of large files)
Compression=lzma2/ultra64
SolidCompression=yes
LZMAUseSeparateProcess=yes
LZMANumBlockThreads=4

; UI settings
WizardStyle=modern
WizardSizePercent=120

; Disk spanning for large installers (optional)
; DiskSpanning=yes

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
; Bundle the entire MSYS2 installation
Source: "payload\msys64\*"; DestDir: "{app}\msys64"; Flags: ignoreversion recursesubdirs createallsubdirs

; Bundle the OpenPLC Runtime
Source: "payload\openplc-runtime\*"; DestDir: "{app}\openplc-runtime"; Flags: ignoreversion recursesubdirs createallsubdirs

; Launcher and support files
Source: "StartOpenPLC.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "openplc.ico"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
; Start Menu shortcuts (per-user, no admin needed)
Name: "{userprograms}\{#MyAppName}\Start OpenPLC Runtime"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\openplc.ico"
Name: "{userprograms}\{#MyAppName}\MSYS2 Terminal"; Filename: "{app}\msys64\msys2.exe"; WorkingDir: "{app}\msys64"
Name: "{userprograms}\{#MyAppName}\Uninstall {#MyAppName}"; Filename: "{uninstallexe}"

; Desktop shortcut (optional)
Name: "{autodesktop}\{#MyAppName}"; Filename: "{app}\{#MyAppExeName}"; WorkingDir: "{app}"; IconFilename: "{app}\openplc.ico"; Tasks: desktopicon

[Run]
; Option to start OpenPLC after installation
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#StringChange(MyAppName, '&', '&&')}}"; Flags: nowait postinstall skipifsilent shellexec

[UninstallDelete]
; Clean up runtime directories on uninstall
Type: filesandordirs; Name: "{app}\msys64\run\runtime"
Type: filesandordirs; Name: "{app}\openplc-runtime\build"
Type: filesandordirs; Name: "{app}\openplc-runtime\venvs"
Type: filesandordirs; Name: "{app}\openplc-runtime\*.pyc"
Type: filesandordirs; Name: "{app}\openplc-runtime\__pycache__"

[Code]
// Custom code for installation

function InitializeSetup(): Boolean;
begin
  Result := True;
  // Add any pre-installation checks here
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  RuntimeDir: String;
begin
  if CurStep = ssPostInstall then
  begin
    // Create runtime directory after installation
    RuntimeDir := ExpandConstant('{app}\msys64\run\runtime');
    if not DirExists(RuntimeDir) then
      CreateDir(RuntimeDir);
  end;
end;
