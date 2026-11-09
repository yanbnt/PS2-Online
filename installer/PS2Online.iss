; Instalador do PS2 Online (Inno Setup 6)
; Compilar:  ISCC.exe /DAppDir="<pasta do app gerada pelo PyInstaller>" /DOutDir="<saída>" PS2Online.iss
; (o build.ps1 faz isso automaticamente)

#define AppName "PS2 Online"
#define AppVersion "1.3.1"
#define AppExe "PS2 Online.exe"
#ifndef AppDir
  #define AppDir "..\dist\PS2 Online"
#endif
#ifndef OutDir
  #define OutDir "..\out"
#endif

[Setup]
AppId={{7DE85483-F52A-4210-A060-D2946BE35793}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher=yanbnt
AppPublisherURL=https://github.com/yanbnt/PS2-Online
AppSupportURL=https://github.com/yanbnt/PS2-Online
VersionInfoVersion={#AppVersion}.0
VersionInfoDescription=Instalador do PS2 Online
VersionInfoProductName={#AppName}
; instala só para o usuário atual: não pede administrador (só o driver pede, se marcado)
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\{#AppName}
DisableProgramGroupPage=yes
DisableDirPage=auto
OutputDir={#OutDir}
OutputBaseFilename=Instalar-PS2-Online
SetupIconFile=..\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
CloseApplications=yes
RestartApplications=no
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible

[Languages]
Name: "ptbr"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"
Name: "vigem"; Description: "Instalar o driver de controle virtual (ViGEmBus) — necessário para HOSPEDAR partidas. O Windows vai pedir permissão de administrador."; GroupDescription: "Driver:"; Check: not ViGEmInstalled

[InstallDelete]
; atualização limpa (inclui sobras do instalador antigo)
Type: filesandordirs; Name: "{app}\_internal"
Type: files; Name: "{app}\Desinstalar.cmd"

[Files]
Source: "{#AppDir}\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs

[Registry]
; remove a entrada de "Aplicativos instalados" do instalador antigo (v1.0–1.2 sem Inno)
Root: HKCU; Subkey: "Software\Microsoft\Windows\CurrentVersion\Uninstall\PS2Online"; Flags: deletekey dontcreatekey

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "msiexec.exe"; Parameters: "/i ""{app}\_internal\vgamepad\win\vigem\install\x64\ViGEmBusSetup_x64.msi"" /passive /norestart"; Verb: "runas"; Flags: shellexec waituntilterminated; StatusMsg: "Instalando o driver ViGEmBus… (aceite o pedido de administrador)"; Tasks: vigem
Filename: "{app}\{#AppExe}"; Description: "Abrir o PS2 Online agora"; Flags: nowait postinstall skipifsilent

[Code]
function ViGEmInstalled(): Boolean;
begin
  Result := RegKeyExists(HKLM, 'SYSTEM\CurrentControlSet\Services\ViGEmBus');
end;
