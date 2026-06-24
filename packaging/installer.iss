; Inno Setup script for the Windows installer.
; Build the app first (pyinstaller packaging/windows.spec), then compile this
; with Inno Setup 6:  iscc packaging\installer.iss
;
; Output: installer-output\VideoEnhancer-Setup.exe

#define AppName "Video Enhancer"
#define AppVersion "1.0.0"
#define AppPublisher "Filip Nieslanik"
#define AppExe "VideoEnhancer.exe"

[Setup]
AppId={{8F3C2A11-6B4D-4E2A-9C77-VIDEOENHANCER}}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher={#AppPublisher}
DefaultDirName={autopf}\{#AppName}
DefaultGroupName={#AppName}
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
OutputDir=..\installer-output
OutputBaseFilename=VideoEnhancer-Setup
; Per-user install needs no admin rights, which also avoids one UAC prompt.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "desktopicon"; Description: "Create a desktop shortcut"; GroupDescription: "Shortcuts:"

[Files]
; the entire PyInstaller one-dir output
Source: "..\dist\VideoEnhancer\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Uninstall {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Launch {#AppName}"; Flags: nowait postinstall skipifsilent
