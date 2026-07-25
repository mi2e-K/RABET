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
;   "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" /DAppVersion=1.4.2 packaging\RABET.iss
; Produces: dist\RABET-Setup-<AppVersion>.exe
;
; AppVersion / SourceDir may be overridden with /D defines; the defaults suit a
; local build from the repo root.

#ifndef AppVersion
  #define AppVersion "1.4.2"
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
; Branded wizard artwork, kept under packaging/ rather than resources/ so it
; is not mistaken for an application asset -- the app bundles resources/ by
; name and these are installer-only. Inno 6 takes BMP only and picks the entry closest to
; the active display scaling, so each size is rendered rather than upscaled
; (100/125/150/175/200%). Base sizes match the images Inno itself ships:
; 164x314 for the side panel and 55x55 for the header mark.
WizardImageFile=wizard\WizardImage-164x314.bmp,wizard\WizardImage-205x393.bmp,wizard\WizardImage-246x471.bmp,wizard\WizardImage-287x550.bmp,wizard\WizardImage-328x628.bmp
WizardSmallImageFile=wizard\WizardSmallImage-55x55.bmp,wizard\WizardSmallImage-69x69.bmp,wizard\WizardSmallImage-83x83.bmp,wizard\WizardSmallImage-96x96.bmp,wizard\WizardSmallImage-110x110.bmp
; The side panel only appears on the Welcome and Finished pages, and modern
; style hides Welcome by default -- so it would otherwise show up just once,
; on the way out.
DisableWelcomePage=no
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

[Messages]
; Inno's stock WelcomeLabel2 advises closing all other applications. That
; dates from installers replacing shared system DLLs; RABET installs per-user
; into %LocalAppData%, ships self-contained, and registers nothing, so no
; other application can conflict with it. The one real case is upgrading while
; RABET itself is running, which locks its own executable -- so that is all
; the message says now.
;
; NOTE: this file must stay UTF-8 with BOM for the Japanese text below.
english.WelcomeLabel2=This will install [name/ver] on your computer.%n%nIf RABET is already running, close it before continuing.
japanese.WelcomeLabel2=このプログラムはご使用のコンピューターへ [name/ver] をインストールします。%n%nRABET が起動している場合は、続行する前に終了してください。

[Tasks]
Name: "desktopicon"; Description: "{cm:CreateDesktopIcon}"; GroupDescription: "{cm:AdditionalIcons}"; Flags: unchecked

[Files]
Source: "{#SourceDir}\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExeName}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExeName}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExeName}"; Description: "{cm:LaunchProgram,{#AppName}}"; Flags: nowait postinstall skipifsilent
