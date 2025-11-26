; Script Inno Setup para SOFIA
[Setup]
AppName=SOFIA OCR Edition
AppVersion=1.0
DefaultDirName={pf}\SOFIA
DefaultGroupName=SOFIA
Compression=lzma
SolidCompression=yes
OutputDir=Output
OutputBaseFilename=Setup_SO F IA
CloseApplicationsTimeout=5000
PrivilegesRequired=admin
LicenseFile=

[Files]
; El exe debe haberse generado/colocado en installer\build\SOFIA.exe antes de compilar
Source: "..\installer\build\SOFIA.exe"; DestDir: "{app}"; Flags: ignoreversion

[Icons]
Name: "{group}\SOFIA"; Filename: "{app}\SOFIA.exe"; WorkingDir: "{app}"
Name: "{userdesktop}\SOFIA"; Filename: "{app}\SOFIA.exe"; Tasks: desktopicon

[Tasks]
Name: "desktopicon"; Description: "Crear acceso directo en el Escritorio"; GroupDescription: "Tareas opcionales:"; Flags: unchecked
Name: "startup_shortcut"; Description: "Crear acceso en carpeta Inicio (ejecutar al iniciar sesión)"; Flags: unchecked
Name: "create_schtask"; Description: "Crear tarea programada para iniciar SOFIA al iniciar sesión (requiere privilegios)"; Flags: unchecked

[Run]
; Opción para lanzar la aplicación después de instalar si el usuario lo desea
Filename: "{app}\SOFIA.exe"; Description: "Iniciar SOFIA ahora"; Flags: nowait postinstall skipifsilent; Tasks: startup_shortcut

[UninstallRun]
; eliminar tarea programada si existía
Filename: "schtasks.exe"; Parameters: "/Delete /F /TN ""SOFIA"""; Flags: runhidden

[Code]
var
  PinPage: TInputQueryWizardPage;
  ParentalPIN: string;

procedure InitializeWizard();
begin
  // Página para establecer PIN parental (aparece antes de seleccionar carpeta)
  PinPage := CreateInputQueryPage(wpSelectDir,
    'Configuración parental',
    'Establece un PIN para la configuración parental',
    'Introduce un PIN que sólo el tutor conocerá. Será almacenado como hash SHA‑256 en el directorio de instalación.');
  PinPage.Add('PIN (4-8 dígitos):', False);
  PinPage.Add('Confirmar PIN:', False);
end;

function NextButtonClick(CurPageID: Integer): Boolean;
var
  pin1, pin2: string;
begin
  Result := True;
  if CurPageID = PinPage.ID then
  begin
    pin1 := Trim(PinPage.Values[0]);
    pin2 := Trim(PinPage.Values[1]);
    if (pin1 = '') or (pin1 <> pin2) then
    begin
      MsgBox('Los PIN no coinciden o están vacíos. Por favor, verifica.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    if (Length(pin1) < 4) or (Length(pin1) > 8) then
    begin
      MsgBox('El PIN debe tener entre 4 y 8 caracteres.', mbError, MB_OK);
      Result := False;
      exit;
    end;
    ParentalPIN := pin1;
  end;
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ScriptPath, ScriptText, AppPath: string;
  ResultCode: Integer;
begin
  if CurStep = ssPostInstall then
  begin
    if ParentalPIN <> '' then
    begin
      AppPath := ExpandConstant('{app}');
      // Generar un script PowerShell temporal que calcule SHA256 y escriba JSON con el hash
      ScriptPath := ExpandConstant('{tmp}\sofia_write_pin.ps1');
      ScriptText :=
        '$p = "' + ParentalPIN + '";' +
        '$h = [System.BitConverter]::ToString((New-Object Security.Cryptography.SHA256Managed).ComputeHash([System.Text.Encoding]::UTF8.GetBytes($p))).Replace("-","").ToLower();' +
        '$o = @{parental_pin_hash=$h} | ConvertTo-Json -Compress;' +
        'Set-Content -Path "' + AppPath + '\parental_config.json" -Value $o -Encoding UTF8;';
      // Escribir el script en %TEMP%
      SaveStringToFile(ScriptPath, ScriptText, False);
      // Ejecutar PowerShell para crear el archivo (sin ventana)
      Exec(ExpandConstant('{sys}\WindowsPowerShell\v1.0\powershell.exe'),
           '-NoProfile -ExecutionPolicy Bypass -File "' + ScriptPath + '"',
           '', SW_HIDE, ewWaitUntilTerminated, ResultCode);
      // intentar eliminar el script temporal (silencioso)
      DeleteFile(ScriptPath);
    end;
  end;
end;
