; RABET installer script (Inno Setup 6).
;
; Wraps the PyInstaller *onedir* output (dist\RABET) into a single Setup.exe:
;   - one-file download for users
;   - fast launch with NO per-launch extraction (unlike the onefile build)
;   - Start-Menu (and optional desktop) shortcut
;   - _internal stays under the install dir, out of the user's way
;   - clean uninstaller
;
; Build (from the repo root) AFTER building the onedir dist:
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /DAppVersion=1.3.5 packaging\RABET.iss
; Produces: dist\RABET-Setup-<AppVersion>.exe
;
; AppVersion / SourceDir may be overridden with /D defines; the defaults suit a
; local build from the repo root.

#ifndef AppVersion
  #define AppVersion "1.3.5"
#endif
#ifndef SourceDir
  #define SourceDir "..\dist\RABET"
#endif

#define AppName "RABET"
#define AppExeName "RABET.exe"
#define AppPublisher "RABET project"
#define AppURL "https://github.com/mi2e-K/RABET"

[Setup]
; Stable AppId so future versions upgrade the same installation. DO NOT change.
AppId={{8F2A6B1C-3D4E-4F5A-9B6C-7D8E9F0A1B2C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppPublisher}
AppPublisherURL={#AppURL}
AppSupportURL={#AppURL}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppName}
DisableProgramGroupPage=yes
UninstallDisplayIcon={app}\{#AppExeName}
UninstallDisplayName={#AppName} {#AppVersion}
OutputDir=..\dist
OutputBaseFilename=RABET-Setup-{#AppVersion}
SetupIconFile=..\resources\RABET.ico
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
; Auto-detect the OS UI language and switch the wizard between Japanese and
; English with no prompt (falls back to English -- the first [Languages]
; entry -- for any other system language). NOTE: this localizes the installer
; wizard only; the RABET application UI itself stays English.
ShowLanguageDialog=no
LanguageDetectionMethod=uilanguage
; Per-user install: no UAC prompt; lands in %LocalAppData%\Programs\RABET.
PrivilegesRequired=lowest
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
; English first so it is the fallback for any non-Japanese system language.
Name: "english"; MessagesFile: "compiler:Default.isl"
Name: "japanese"; MessagesFile: "compiler:Languages\Japanese.isl"

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
