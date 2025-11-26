```powershell
Param(
    [string]$ProjectDir = "c:\Users\ariel\Desktop\SOFIA",
    [string]$MainPy = "main.py",
    [string]$ExeName = "SOFIA",
    [string]$IconPath = ""  # opcional .ico absoluto si lo tienes
)

Write-Host "== SOFIA: build_installer.ps1 =="
Set-StrictMode -Version Latest

Push-Location $ProjectDir

# 1) Instalar dependencias de build (solo si falta)
Write-Host "Comprobando dependencias Python..."
python -c "import sys" 2>$null
if ($LASTEXITCODE -ne 0) {
    Write-Error "Python no encontrado en PATH. Instala Python 3.8+ y vuelve a ejecutar."
    Exit 1
}

Write-Host "Instalando PyInstaller y requerimientos (si hace falta)..."
pip install --upgrade pyinstaller requests twilio > $null

# 2) Ejecutar PyInstaller para generar exe en dist\
$specArgs = "--onefile --name $ExeName"
if ($IconPath -ne "") { $specArgs += " --icon `"$IconPath`"" }
$pyCmd = "pyinstaller $specArgs `"$MainPy`""
Write-Host "Ejecutando PyInstaller: $pyCmd"
Invoke-Expression $pyCmd

$distExe = Join-Path "$ProjectDir\dist" "$ExeName.exe"
if (-not (Test-Path $distExe)) {
    Write-Error "Error: no se encontró el exe en dist\. Revisa logs de PyInstaller."
    Pop-Location
    Exit 1
}

# 3) Preparar estructura para instalador (copiar assets)
$installerDir = Join-Path $ProjectDir "installer\build"
Remove-Item -Recurse -Force $installerDir -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $installerDir | Out-Null
Copy-Item -Path $distExe -Destination (Join-Path $installerDir "$ExeName.exe") -Force

# Si tienes icono u otros archivos los puedes copiar aquí.
if ($IconPath -ne "" -and (Test-Path $IconPath)) {
    Copy-Item -Path $IconPath -Destination $installerDir -Force
}

# 4) Compilar Inno Setup (.iss)
$issFile = Join-Path $ProjectDir "installer\sofia_installer.iss"
# buscar ISCC.exe en la ubicación típica
$defaultIscc = "C:\Program Files (x86)\Inno Setup 6\ISCC.exe"
if (Test-Path $defaultIscc) {
    $iscc = $defaultIscc
} else {
    $iscc = Read-Host "ISCC.exe no encontrado en la ruta por defecto. Introduce la ruta completa a ISCC.exe (o presiona Enter para abortar)"
    if ([string]::IsNullOrWhiteSpace($iscc)) {
        Write-Error "ISCC no proporcionado. Instalar Inno Setup y ejecutar manualmente: ISCC.exe $issFile"
        Pop-Location
        Exit 1
    }
}

Write-Host "Compilando instalador Inno Setup..."
& "$iscc" "$issFile"

# 5) Resultado
$installerOut = Join-Path $ProjectDir "Output\Setup_$ExeName.exe"
if (Test-Path $installerOut) {
    Write-Host "Instalador generado: $installerOut"
} else {
    Write-Host "La compilación finalizó. Busca el instalador generado en la carpeta Output del script Inno Setup."
}

Pop-Location
```